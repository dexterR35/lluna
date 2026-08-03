"""Subtitle removal pipeline.

This module contains the legacy-compatible implementation while its media,
workspace, output-path, progress, and worker concerns are extracted.
"""

import gc
import logging
import torch
import shutil
import traceback
import subprocess
import os
from pathlib import Path
import threading
import cv2
from functools import cached_property

from backend.configuration.models import SubtitleSettings
from backend.tools.constant import InpaintMode, SubtitleDetectMode
from backend.tools.hardware_accelerator import HardwareAccelerator
from backend.tools.common_tools import get_readable_path, is_image_file, read_image
from backend.inpaint.sttn_auto_inpaint import STTNAutoInpaint
from backend.inpaint.sttn_det_inpaint import STTNDetInpaint
from backend.inpaint.lama_inpaint import LamaInpaint
from backend.inpaint.opencv_inpaint import OpenCVInpaint
from backend.inpaint.propainter_inpaint import PropainterInpaint
from backend.tools.inpaint_tools import (
    create_mask,
    batch_generator,
    expand_frame_ranges,
    inpaint_with_oom_batch_retry,
)
from backend.models.paths import (
    SubtitleModelPaths,
    prepare_bundled_subtitle_models,
)
from backend.tools.ffmpeg_cli import FFmpegCLI
from backend.tools.subtitle_detect import SubtitleDetect
from backend.tools.video_io import FramePrefetcher, FFmpegVideoWriter
import time
from tqdm import tqdm
import numpy as np
from backend.diagnostics.errors import InferenceError, InvalidMediaError
from backend.media.output_paths import default_output_path
from backend.media.progress import CancellationToken
from backend.media.video import VideoSource, create_video_writer
from backend.media.workspace import JobWorkspace

logger = logging.getLogger(__name__)

INPAINT_MODE_NAMES = {
    InpaintMode.STTN_AUTO: "STTN Smart Inpainting (Recommended)",
    InpaintMode.STTN_DET: "STTN Subtitle Detection",
    InpaintMode.LAMA: "LAMA",
    InpaintMode.PROPAINTER: "ProPainter",
    InpaintMode.OPENCV: "OpenCV",
}
SUBTITLE_DETECT_MODE_NAMES = {
    SubtitleDetectMode.PP_OCRv5_MOBILE: "Fast (Mobile)",
    SubtitleDetectMode.PP_OCRv5_SERVER: "Precise (Server) (Recommended)",
}


class SubtitleRemover:
    def __init__(
        self,
        vd_path,
        gui_mode=False,
        *,
        settings: SubtitleSettings | None = None,
        cancellation_token: CancellationToken | None = None,
    ):
        if settings is None:
            from backend.configuration.service import get_settings

            settings = get_settings().subtitle
        self.settings = settings
        self.cancellation_token = cancellation_token or CancellationToken()
        # Thread lock
        self.lock = threading.RLock()
        # User-specified subtitle region positions
        self.sub_areas = []
        # Whether running in GUI mode (GUI needs preview)
        self.gui_mode = gui_mode
        self.hardware_accelerator = HardwareAccelerator.instance()
        # Whether to use hardware acceleration
        self.hardware_accelerator.set_enabled(settings.hardware_acceleration)
        self.model_paths = SubtitleModelPaths.resolve(settings)
        prepare_bundled_subtitle_models(self.model_paths)
        # Whether the input is an image
        self.is_picture = is_image_file(str(vd_path))
        # Video path
        self.video_path = vd_path
        self.video_source = (
            None
            if self.is_picture
            else VideoSource.open(get_readable_path(vd_path))
        )
        self.video_cap = (
            cv2.VideoCapture(get_readable_path(vd_path))
            if self.is_picture
            else self.video_source.capture
        )
        # Video name from path
        self.vd_name = Path(self.video_path).stem
        # Total frame count
        if self.video_source is not None:
            metadata = self.video_source.metadata
            self.frame_count = metadata.frame_count
            self.fps = metadata.fps
            self.size = metadata.size
            self.frame_height = metadata.height
            self.frame_width = metadata.width
        else:
            self.frame_count = 1
            self.fps = 1.0
            self.frame_width = int(self.video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.size = (self.frame_width, self.frame_height)
        self.mask_size = (self.frame_height, self.frame_width)
        self.workspace = JobWorkspace.create("subtitle")
        # Temporary video file; on Windows delete=True can cause permission denied
        self.video_temp_path = str(self.workspace.new_path("video", ".mp4"))
        # Video writer (FFmpeg libx264 - better quality and smaller files than mp4v)
        self.video_writer = None
        if not self.is_picture:
            self.video_writer = create_video_writer(
                self.video_temp_path,
                self.fps,
                self.size,
            )
        self.video_out_path = str(
            default_output_path(self.video_path, suffix="_no_sub", extension=".mp4")
        )
        self.propainter_inpaint = None
        self.ext = os.path.splitext(vd_path)[-1]
        if self.is_picture:
            pic_dir = os.path.join(os.path.dirname(self.video_path), 'no_sub')
            if not os.path.exists(pic_dir):
                os.makedirs(pic_dir)
            self.video_out_path = str(
                default_output_path(
                    self.video_path, suffix="", extension=self.ext, directory=pic_dir
                )
            )

        # Overall processing progress
        self.progress_total = 0
        self.progress_remover = 0
        self.isFinished = False
        # Whether original audio was successfully embedded into the subtitle-removed video
        self.is_successful_merged = False
        # Progress listener list
        self.progress_listeners = []
        # frame_no ranges to inpaint; default is all frames
        self.ab_sections = None

    @staticmethod
    def is_current_frame_no_start(frame_no, continuous_frame_no_list):
        """
        Return True if the given frame number is a range start; otherwise False
        """
        for start_no, end_no in continuous_frame_no_list:
            if start_no == frame_no:
                return True
        return False

    @staticmethod
    def find_frame_no_end(frame_no, continuous_frame_no_list):
        """
        If the given frame number is within a range, return the end frame number; otherwise -1
        """
        for start_no, end_no in continuous_frame_no_list:
            if start_no <= frame_no <= end_no:
                return end_no
        return -1

    def update_progress(self, tbar, increment):
        self.cancellation_token.raise_if_cancelled()
        tbar.update(increment)
        current_percentage = (tbar.n / tbar.total) * 100
        self.progress_remover = int(current_percentage)
        self.progress_total = self.progress_remover
        self.notify_progress_listeners()

    def append_output(self, *args):
        """Emit a structured default log; worker/UI adapters can replace this hook."""
        logger.info("%s", " ".join(str(arg) for arg in args))
    
    def add_progress_listener(self, listener):
        """
        Add a progress listener
        
        Args:
            listener: Callback receiving (progress_total, isFinished)
        """
        if listener not in self.progress_listeners:
            self.progress_listeners.append(listener)
    
    def remove_progress_listener(self, listener):
        """
        Remove a progress listener
        
        Args:
            listener: Listener function to remove
        """
        if listener in self.progress_listeners:
            self.progress_listeners.remove(listener)
            
    def notify_progress_listeners(self):
        """
        Notify all progress listeners of the current progress
        """
        for listener in self.progress_listeners:
            try:
                listener(self.progress_total, self.isFinished)
            except Exception as e:
                traceback.print_exc()

    def update_preview_with_comp(self, frame_ori, frame_comp):
        """
        Update preview
        """
        pass

    def propainter_mode(self, tbar):
        sub_detector = SubtitleDetect(
            self.video_path,
            self.sub_areas,
            settings=self.settings,
            model_paths=self.model_paths,
        )
        sub_list = sub_detector.find_subtitle_frame_no(sub_remover=self)
        if len(sub_list) == 0:
            raise InferenceError(f"No subtitles detected. Check file: {self.video_path}")
        continuous_frame_no_list = sub_detector.find_continuous_ranges_with_same_mask(sub_list)
        scene_div_points = sub_detector.get_scene_div_frame_no(self.video_path)
        continuous_frame_no_list = sub_detector.split_range_by_scene(continuous_frame_no_list,
                                                                          scene_div_points)
        del sub_detector
        gc.collect()        
        device = self.hardware_accelerator.device if self.hardware_accelerator.has_cuda() else torch.device("cpu")
        propainter_inpaint = PropainterInpaint(
            device,
            str(self.model_paths.propainter_dir),
            self.settings.propainter_max_load_num,
        )
        try:
            from backend.tools.inpaint_release import register_video_inpaint_model
            register_video_inpaint_model(propainter_inpaint)
        except Exception:
            pass
        self.append_output("[Processing] Removing subtitles...")
        index = 0
        # Prefetch frames so I/O overlaps with inference
        reader = FramePrefetcher(self.video_cap)
        while True:
            ret, frame = reader.read()
            if not ret:
                break
            index += 1
            # If the current frame has no watermark/text, write it directly
            if index not in sub_list.keys():
                self.video_writer.write(frame)
                # self.append_output(f'write frame: {index}')
                self.update_progress(tbar, increment=1)
                self.update_preview_with_comp(frame, frame)
                continue
            # Frame has a watermark; check whether it is a range start
            else:
                # If it is a start frame, batch-infer through the end frame
                if self.is_current_frame_no_start(index, continuous_frame_no_list):
                    # self.append_output(f'No 1 Current index: {index}')
                    start_frame_no = index
                    # self.append_output(f'find start: {start_frame_no}')
                    # Find the end frame
                    end_frame_no = self.find_frame_no_end(index, continuous_frame_no_list)
                    # Check whether the current frame is a subtitle start;
                    # a non -1 end frame means it is
                    if end_frame_no != -1:
                        # self.append_output(f'find end: {end_frame_no}')
                        # ************ Read all frames in this range - start ************
                        temp_frames = list()
                        # Add the head frame to the processing list
                        temp_frames.append(frame)
                        inner_index = 0
                        # Keep reading until the end frame
                        while index < end_frame_no:
                            ret, frame = reader.read()
                            if not ret:
                                break
                            index += 1
                            temp_frames.append(frame)
                        # ************ Read all frames in this range - end ************
                        if len(temp_frames) < 1:
                            # Nothing to process; skip
                            continue
                        elif len(temp_frames) == 1:
                            inner_index += 1
                            single_mask = create_mask(
                                self.mask_size,
                                sub_list[index],
                                expansion_px=self.settings.mask_expansion_px,
                            )
                            inpainted_frame = self.lama_inpaint.inpaint(frame, single_mask)
                            self.video_writer.write(inpainted_frame)
                            # self.append_output(f'write frame: {start_frame_no + inner_index} with mask {sub_list[start_frame_no]}')
                            self.update_progress(tbar, increment=1)
                            continue
                        else:
                            # Process the read frames in batches
                            # 1. Get the mask for the current batch
                            mask = create_mask(
                                self.mask_size,
                                sub_list[start_frame_no],
                                expansion_px=self.settings.mask_expansion_px,
                            )
                            for batch in batch_generator(
                                temp_frames,
                                self.settings.propainter_max_load_num,
                            ):
                                # 2. Run batch inference
                                if len(batch) == 1:
                                    single_mask = create_mask(
                                        self.mask_size,
                                        sub_list[start_frame_no],
                                        expansion_px=self.settings.mask_expansion_px,
                                    )
                                    inpainted_frame = self.lama_inpaint.inpaint(frame, single_mask)
                                    self.video_writer.write(inpainted_frame)
                                    # self.append_output(f'write frame: {start_frame_no + inner_index} with mask {sub_list[start_frame_no]}')
                                    inner_index += 1
                                    self.update_progress(tbar, increment=1)
                                elif len(batch) > 1:
                                    inpainted_frames = inpaint_with_oom_batch_retry(
                                        propainter_inpaint, batch, mask
                                    )
                                    for i, inpainted_frame in enumerate(inpainted_frames):
                                        self.video_writer.write(inpainted_frame)
                                        # self.append_output(f'write frame: {start_frame_no + inner_index} with mask {sub_list[index]}')
                                        inner_index += 1
                                        self.update_preview_with_comp(np.clip(batch[i]+mask[:,:,np.newaxis]*0.3,0,255).astype(np.uint8), inpainted_frame)
                                self.update_progress(tbar, increment=len(batch))

    def sttn_auto_mode(self, tbar):
        """
        Inpaint the selected region with STTN without subtitle detection
        """
        self.append_output("[Processing] Removing subtitles...")
        mask_area_coordinates = []
        for sub_area in self.sub_areas:
            ymin, ymax, xmin, xmax = sub_area
            mask_area_coordinates.append((xmin, xmax, ymin, ymax))
        mask = create_mask(
            self.mask_size,
            mask_area_coordinates,
            expansion_px=self.settings.mask_expansion_px,
        )
        sttn_video_inpaint = STTNAutoInpaint(
            self.hardware_accelerator.device,
            str(self.model_paths.sttn_auto_path),
            self.video_path,
            clip_gap=self.settings.effective_sttn_max_load_num,
            neighbor_stride=self.settings.sttn_neighbor_stride,
            reference_length=self.settings.sttn_reference_length,
        )
        sttn_video_inpaint(input_mask=mask, input_sub_remover=self, tbar=tbar)

    def video_inpaint(self, tbar, model):
        sub_detector = SubtitleDetect(
            self.video_path,
            self.sub_areas,
            settings=self.settings,
            model_paths=self.model_paths,
        )
        sub_list = sub_detector.find_subtitle_frame_no(sub_remover=self)
        if len(sub_list) == 0:
            raise InferenceError(f"No subtitles detected. Check file: {self.video_path}")
        continuous_frame_no_list = sub_detector.find_continuous_ranges_with_same_mask(sub_list)
        tbar.write(f"Subtitle detected: {continuous_frame_no_list}")
        continuous_frame_no_list = expand_frame_ranges(
            continuous_frame_no_list,
            self.settings.timeline_before_frames,
            self.settings.timeline_after_frames,
        )
        tbar.write(
            "Subtitle timeline expand "
            f"({self.settings.timeline_before_frames} <- -> "
            f"{self.settings.timeline_after_frames}): "
            f"{continuous_frame_no_list}"
        )
        continuous_frame_no_list = sub_detector.filter_and_merge_intervals(
            continuous_frame_no_list,
            self.settings.sttn_reference_length,
        )
        tbar.write(f'Subtitle filter_and_merge_intervals: {continuous_frame_no_list}')
        del sub_detector
        gc.collect()
        start_end_map = dict()
        for start, end in continuous_frame_no_list:
            # Clamp ranges to total frame count; otherwise FramePrefetcher's sentinel can be
            # consumed by the inner loop and deadlock the outer loop
            start_end_map[start] = min(end, self.frame_count)
        current_frame_index = 0
        self.append_output("[Processing] Removing subtitles...")
        # Prefetch frames so I/O overlaps with inference
        reader = FramePrefetcher(self.video_cap)
        while True:
            ret, frame = reader.read()
            # End of stream
            if not ret:
                break
            current_frame_index += 1
            # If this frame is not a subtitle-range start, write it directly
            if current_frame_index not in start_end_map.keys():
                self.video_writer.write(frame)
                # self.append_output(f'write frame: {current_frame_index}')
                self.update_progress(tbar, increment=1)
                self.update_preview_with_comp(frame, frame)
            # Range start: read through to the end
            else:
                start_frame_index = current_frame_index
                end_frame_index = start_end_map[current_frame_index]
                tbar.write(f'processing frame {start_frame_index} to {end_frame_index}')
                # Frames that need subtitle removal
                frames_need_inpaint = list()
                frames_need_inpaint.append(frame)
                inner_index = 0
                # Keep reading until the end of the range
                for j in range(end_frame_index - start_frame_index):
                    ret, frame = reader.read()
                    if not ret:
                        break
                    current_frame_index += 1
                    frames_need_inpaint.append(frame)
                mask_area_coordinates = []
                # 1. Collect all mask coordinates for the current batch
                for mask_index in range(start_frame_index, end_frame_index):
                    if mask_index in sub_list.keys():
                        for area in sub_list[mask_index]:
                            xmin, xmax, ymin, ymax = area
                            # Skip likely non-subtitle regions (height much larger than width)
                            if (
                                (ymax - ymin) - (xmax - xmin)
                                > self.settings.vertical_box_tolerance_px
                            ):
                                continue
                            if area not in mask_area_coordinates:
                                mask_area_coordinates.append(area)
                # 1. Build the mask for the current batch
                mask = create_mask(
                    self.mask_size,
                    mask_area_coordinates,
                    expansion_px=self.settings.mask_expansion_px,
                )
                # self.append_output(f'inpaint with mask: {mask_area_coordinates}')
                for batch in batch_generator(
                    frames_need_inpaint,
                    self.settings.effective_sttn_max_load_num,
                ):
                    # 2. Run batch inference (one half-batch retry on CUDA OOM)
                    if len(batch) >= 1:
                        inpainted_frames = inpaint_with_oom_batch_retry(model, batch, mask)
                        for i, inpainted_frame in enumerate(inpainted_frames):
                            self.video_writer.write(inpainted_frame)
                            # self.append_output(f'write frame: {start_frame_index + inner_index} with mask')
                            inner_index += 1
                            self.update_preview_with_comp(np.clip(batch[i]+mask[:,:,np.newaxis]*0.3,0,255).astype(np.uint8), inpainted_frame)
                    self.update_progress(tbar, increment=len(batch))
        reader.stop()

    def run(self):
        failed = True
        try:
            result = self._run_impl()
            failed = False
            return result
        finally:
            try:
                if self.video_source is not None:
                    self.video_source.close()
                else:
                    self.video_cap.release()
            except (OSError, RuntimeError) as exc:
                logger.warning("Could not close input media: %s", type(exc).__name__)
            if self.video_writer is not None:
                try:
                    self.video_writer.release()
                except (OSError, RuntimeError) as exc:
                    logger.warning(
                        "Could not close output media: %s", type(exc).__name__
                    )
            progress_bar = getattr(self, "_progress_bar", None)
            if progress_bar is not None:
                progress_bar.close()
            self.workspace.close(failed=failed)

    def _run_impl(self):
        # Record start time
        start_time = time.time()
        mode = InpaintMode(self.settings.inpaint_mode)
        if len(self.sub_areas) == 0:
            self.append_output(
                "Processing full screen (no area selected). Quality may vary."
            )
            self.sub_areas.append((0, self.frame_height, 0, self.frame_width))
        self.append_output(f"Subtitle Area: {self.sub_areas}")
        self.append_output(
            "Processing block: {}".format(
                str(self.ab_sections).replace("range", "")
                if self.ab_sections is not None and len(self.ab_sections) > 0
                else "All"
            )
        )
        # Print GPU acceleration tip when an accelerator is available
        if self.hardware_accelerator.has_accelerator():
            accelerator_name = self.hardware_accelerator.accelerator_name
            if accelerator_name == "DirectML" and mode not in {
                InpaintMode.STTN_AUTO,
                InpaintMode.STTN_DET,
            }:
                self.append_output(
                    "Warning: DirectML acceleration only works with STTN model."
                )
        os.makedirs(os.path.dirname(self.video_out_path), exist_ok=True)
        # Reset progress bar
        self.progress_total = 0
        tbar = tqdm(
            total=int(self.frame_count),
            unit="frame",
            position=0,
            desc="Subtitle Removing",
            disable=self.gui_mode,
        )
        self._progress_bar = tbar
        if self.is_picture:
            original_frame = read_image(self.video_path)
            if original_frame is None:
                raise InvalidMediaError(f"Failed to read image: {self.video_path}")
            sub_detector = SubtitleDetect(
                self.video_path,
                self.sub_areas,
                settings=self.settings,
                model_paths=self.model_paths,
            )
            sub_list = sub_detector.detect_subtitle(original_frame)
            del sub_detector
            gc.collect()
            if len(sub_list):
                mask = create_mask(
                    original_frame.shape[0:2],
                    sub_list,
                    expansion_px=self.settings.mask_expansion_px,
                )
                inpainted_frame = self.lama_inpaint.inpaint(original_frame, mask)
                self.update_preview_with_comp(np.clip(original_frame+mask[:,:,np.newaxis]*0.3,0,255).astype(np.uint8), inpainted_frame)
            else:
                inpainted_frame = original_frame
                self.update_preview_with_comp(original_frame, inpainted_frame)
            cv2.imencode(self.ext, inpainted_frame)[1].tofile(self.video_out_path)
            tbar.update(1)
            self.progress_total = 100
        else:
            # In precise mode, get scene-cut frame numbers for further splitting
            self.log_model()
            if mode == InpaintMode.PROPAINTER:
                self.propainter_mode(tbar)
            elif mode == InpaintMode.STTN_AUTO:
                self.sttn_auto_mode(tbar)
            elif mode == InpaintMode.STTN_DET:
                self.video_inpaint(tbar, self.sttn_det_inpaint)
            elif mode == InpaintMode.LAMA:
                self.video_inpaint(tbar, self.lama_inpaint)
            elif mode == InpaintMode.OPENCV:
                self.video_inpaint(tbar, OpenCVInpaint())
            else:
                raise InferenceError(
                    f"Inpaint mode is not implemented: {self.settings.inpaint_mode}"
                )

        self.video_cap.release()
        if self.video_writer is not None:
            self.video_writer.release()
        if not self.is_picture:
            # Merge original audio into the newly generated video
            self.merge_audio_to_video()
        tbar.close()
        self.append_output(
            f"[Complete] Subtitles removed. Output saved to: {self.video_out_path}"
        )
        self.append_output(
            f"Processing time: {round(time.time() - start_time)} seconds"
        )
        self.isFinished = True
        self.progress_total = 100

    def log_model(self):
        mode = InpaintMode(self.settings.inpaint_mode)
        model_friendly_name = INPAINT_MODE_NAMES[mode]
        model_device = "CPU"
        if mode != InpaintMode.OPENCV and self.hardware_accelerator.has_accelerator():
            accelerator_name = self.hardware_accelerator.accelerator_name
            if accelerator_name == "DirectML" and mode in {
                InpaintMode.STTN_AUTO,
                InpaintMode.STTN_DET,
            }:
                model_device = "DirectML"
            if self.hardware_accelerator.has_cuda() or self.hardware_accelerator.has_mps():
                model_device = accelerator_name
        self.append_output(
            f"Subtitle removal model: {model_friendly_name} ({model_device})"
        )
        providers = ", ".join(self.hardware_accelerator.onnx_providers)
        providers_str = f" ({providers})" if providers else ""
        detect_mode = SubtitleDetectMode(self.settings.subtitle_detect_mode)
        detect_mode_name = SUBTITLE_DETECT_MODE_NAMES[detect_mode]
        self.append_output(
            f"Subtitle detection model: {detect_mode_name}{providers_str}"
        )

    def merge_audio_to_video(self):
        # Temporary audio file; on Windows delete=True can cause permission denied
        temp_path = str(self.workspace.new_path("audio", ".aac"))
        audio_extract_command = [FFmpegCLI.instance().ffmpeg_path,
                                 "-y", "-i", self.video_path,
                                 "-acodec", "copy",
                                 "-vn", "-loglevel", "error", temp_path]
        try:
            with open(os.devnull, "rb") as null_input:
                subprocess.check_output(
                    audio_extract_command,
                    stdin=null_input,
                    shell=False,
                    timeout=600,
                )
        except Exception as e:
            traceback.print_exc()
            self.append_output(f"Audio extraction failed: {e}")
            return
        else:
            if os.path.exists(self.video_temp_path):
                audio_merge_command = [FFmpegCLI.instance().ffmpeg_path,
                                       "-y", "-i", self.video_temp_path,
                                       "-i", temp_path,
                                       "-vcodec", "copy",
                                       "-acodec", "copy",
                                       "-loglevel", "error", self.video_out_path]
                try:
                    with open(os.devnull, "rb") as null_input:
                        subprocess.check_output(
                            audio_merge_command,
                            stdin=null_input,
                            shell=False,
                            timeout=600,
                        )
                except Exception as e:
                    traceback.print_exc()
                    self.append_output(f"Audio merge failed: {e}")
                    return
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    #ignore
                    pass
            self.is_successful_merged = True
        finally:
            if not self.is_successful_merged:
                try:
                    shutil.copy2(self.video_temp_path, self.video_out_path)
                except IOError as e:
                    self.append_output(
                        f"Failed to copy {self.video_temp_path} to "
                        f"{self.video_out_path}. Reason: {e}"
                    )

    @cached_property
    def lama_inpaint(self):
        model_path = str(self.model_paths.lama_dir / "big-lama.pt")
        device = self.hardware_accelerator.device if self.hardware_accelerator.has_cuda() or self.hardware_accelerator.has_mps() else torch.device("cpu")
        obj = LamaInpaint(device, model_path)
        try:
            from backend.tools.inpaint_release import register_video_inpaint_model
            register_video_inpaint_model(obj)
        except Exception:
            pass
        return obj

    @cached_property
    def sttn_det_inpaint(self):
        obj = STTNDetInpaint(
            self.hardware_accelerator.device,
            str(self.model_paths.sttn_detection_path),
            neighbor_stride=self.settings.sttn_neighbor_stride,
            reference_length=self.settings.sttn_reference_length,
        )
        try:
            from backend.tools.inpaint_release import register_video_inpaint_model
            register_video_inpaint_model(obj)
        except Exception:
            pass
        return obj
