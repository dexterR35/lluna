import logging
from functools import cached_property

import cv2
from tqdm import tqdm

from .common import get_readable_path
from .ocr import get_coordinates
from backend.configuration.models import SubtitleSettings
from backend.models.paths import SubtitleModelPaths
from backend.scenedetect import scene_detect
from backend.scenedetect.detectors import ContentDetector
from backend.tools.media.inpaint import is_frame_number_in_ab_sections
from backend.tools.shared.hardware import HardwareAccelerator

logger = logging.getLogger(__name__)


class SubtitleDetect:
    """
    Text-box detector for checking whether video frames contain text boxes
    """

    # Sample interval; adaptively set from video FPS in _init_sample_step
    SAMPLE_STEP = 3

    def __init__(
        self,
        video_path,
        sub_areas=None,
        *,
        settings: SubtitleSettings,
        model_paths: SubtitleModelPaths,
    ):
        self.video_path = video_path
        self.sub_areas = list(sub_areas or ())
        self.settings = settings
        self.model_paths = model_paths
        self._init_sample_step()

    def _init_sample_step(self):
        """Adaptively set sample interval from video FPS, sampling at least 8 frames per second"""
        cap = cv2.VideoCapture(get_readable_path(self.video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if fps >= 60:
            self.SAMPLE_STEP = 4
        elif fps >= 30:
            self.SAMPLE_STEP = 3
        else:
            self.SAMPLE_STEP = 2

    @cached_property
    def text_detector(self):
        from backend.ai.runtimes.paddle_cdn import strip_paddle_cdn_hoster_check
        from backend.ai.runtimes.paddle import (
            disable_paddle_background_services,
            preferred_paddle_device,
        )

        # Local PP-OCR under backend/models/V5 - strip PaddleX CDN hoster check
        disable_paddle_background_services()
        strip_paddle_cdn_hoster_check()

        import paddle
        paddle.disable_signal_handler()
        from paddleocr import TextDetection
        # enable_hpi requires the optional paddlex ultra-infer plugin.
        enable_hpi = False
        try:
            from paddlex.utils.deps import is_hpip_available
            enable_hpi = (
                is_hpip_available()
                and HardwareAccelerator.instance().has_accelerator()
            )
        except Exception:
            pass
        hw = HardwareAccelerator.instance()
        device = preferred_paddle_device(
            paddle,
            acceleration_enabled=hw.has_cuda(),
        )
        options = {
            "model_name": self.model_paths.detection_model_name,
            "model_dir": str(self.model_paths.detection_dir),
            "enable_hpi": enable_hpi,
        }
        try:
            detector = TextDetection(device=device, **options)
        except Exception:
            if device == "cpu":
                raise
            logger.warning(
                "Paddle OCR GPU initialization failed; retrying on CPU",
                exc_info=True,
            )
            device = "cpu"
            detector = TextDetection(device=device, **options)
        logger.info("Paddle OCR device: %s", device)
        return detector

    def detect_subtitle(self, img):
        temp_list = []
        results = self.text_detector.predict(img)
        sub_areas = self.sub_areas
        has_areas = sub_areas is not None and len(sub_areas) > 0
        for res in results:
            dt_polys = res['dt_polys']
            if dt_polys is None or len(dt_polys) == 0:
                continue
            coordinate_list = get_coordinates(dt_polys.tolist())
            if not coordinate_list:
                continue
            if not has_areas:
                temp_list.extend(coordinate_list)
            elif len(sub_areas) == 1:
                # Single-area fast path (most common case)
                s_ymin, s_ymax, s_xmin, s_xmax = sub_areas[0]
                for xmin, xmax, ymin, ymax in coordinate_list:
                    if s_xmin <= xmin and xmax <= s_xmax and s_ymin <= ymin and ymax <= s_ymax:
                        temp_list.append((xmin, xmax, ymin, ymax))
            else:
                for xmin, xmax, ymin, ymax in coordinate_list:
                    for s_ymin, s_ymax, s_xmin, s_xmax in sub_areas:
                        if s_xmin <= xmin and xmax <= s_xmax and s_ymin <= ymin and ymax <= s_ymax:
                            temp_list.append((xmin, xmax, ymin, ymax))
                            break
        return temp_list

    def find_subtitle_frame_no(self, sub_remover=None):
        video_cap = cv2.VideoCapture(get_readable_path(self.video_path))
        frame_count = video_cap.get(cv2.CAP_PROP_FRAME_COUNT)
        tbar = tqdm(
            total=int(frame_count),
            unit="frame",
            position=0,
            desc="Subtitle Finding",
            disable=bool(sub_remover and sub_remover.interactive),
        )
        current_frame_no = 0
        # Phase 1: sample detection - run OCR only every sample_step frames
        sampled_results = {}  # frame_no -> temp_list
        if sub_remover:
            sub_remover.append_output("[Processing] Detecting subtitles...")
        while video_cap.isOpened():
            if sub_remover:
                sub_remover.cancellation_token.raise_if_cancelled()
            ret, frame = video_cap.read()
            # Failed to read frame (reached end of video)
            if not ret:
                break
            # Frame read successfully
            current_frame_no += 1
            if not is_frame_number_in_ab_sections(current_frame_no - 1, sub_remover.ab_sections):
                tbar.update(1)
                continue
            # Run OCR inference only on sampled frames
            if (current_frame_no - 1) % self.SAMPLE_STEP == 0 or self.SAMPLE_STEP <= 1:
                temp_list = self.detect_subtitle(frame)
                if len(temp_list) > 0:
                    sampled_results[current_frame_no] = temp_list
            tbar.update(1)
            if sub_remover:
                sub_remover.progress_total = (100 * float(current_frame_no) / float(frame_count)) // 2
        video_cap.release()
        tbar.close()
        # Phase 2: interpolate - if two sampled frames both have subtitles, mark middle frames too
        subtitle_frame_no_box_dict = {}
        detected_nos = sorted(sampled_results.keys())
        max_gap = self.SAMPLE_STEP * 2
        for f, next_f in zip(detected_nos, detected_nos[1:]):
            subtitle_frame_no_box_dict[f] = sampled_results[f]
            if next_f - f <= max_gap:
                fill_mask = sampled_results[f]
                for fill_f in range(f + 1, next_f):
                    subtitle_frame_no_box_dict[fill_f] = fill_mask
        # Add the last detected frame
        if detected_nos:
            subtitle_frame_no_box_dict[detected_nos[-1]] = sampled_results[detected_nos[-1]]
        subtitle_frame_no_box_dict = self.unify_regions(subtitle_frame_no_box_dict)
        if sub_remover:
            sub_remover.append_output("[Complete] Subtitle detection finished.")
        new_subtitle_frame_no_box_dict = dict()
        for key in subtitle_frame_no_box_dict.keys():
            if len(subtitle_frame_no_box_dict[key]) > 0:
                new_subtitle_frame_no_box_dict[key] = subtitle_frame_no_box_dict[key]
        return new_subtitle_frame_no_box_dict

    @staticmethod
    def split_range_by_scene(intervals, points):
        # Ensure the discrete points list is sorted
        points.sort()
        # Result intervals
        result_intervals = []
        # Iterate intervals
        for start, end in intervals:
            # Points inside the current interval
            current_points = [p for p in points if start <= p <= end]

            # Iterate discrete points inside the current interval
            for p in current_points:
                # If the point is not the interval start, add [start, p-1]
                if start < p:
                    result_intervals.append((start, p - 1))
                # Update interval start to the current discrete point
                start = p
            # Add the interval from the last discrete point (or start) to the end
            result_intervals.append((start, end))
        # Return results
        return result_intervals

    @staticmethod
    def get_scene_div_frame_no(v_path):
        """
        Get frame numbers where scene cuts occur
        """
        scene_div_frame_no_list = []
        scene_list = scene_detect(v_path, ContentDetector())
        for scene in scene_list:
            start, end = scene
            if start.frame_num == 0:
                pass
            else:
                scene_div_frame_no_list.append(start.frame_num + 1)
        return scene_div_frame_no_list

    def are_similar(self, region1, region2):
        """Return whether two regions are similar."""
        xmin1, xmax1, ymin1, ymax1 = region1
        xmin2, xmax2, ymin2, ymax2 = region2

        return (
            abs(xmin1 - xmin2) <= self.settings.box_tolerance_x_px
            and abs(xmax1 - xmax2) <= self.settings.box_tolerance_x_px
            and abs(ymin1 - ymin2) <= self.settings.box_tolerance_y_px
            and abs(ymax1 - ymax2) <= self.settings.box_tolerance_y_px
        )

    def unify_regions(self, raw_regions):
        """Unify consecutive similar regions while preserving list structure."""
        if len(raw_regions) > 0:
            keys = sorted(raw_regions.keys())  # Sort keys so they are consecutive
            unified_regions = {}

            # Initialize
            last_key = keys[0]
            unify_value_map = {last_key: raw_regions[last_key]}

            for key in keys[1:]:
                current_regions = raw_regions[key]

                # Collect matched canonical intervals
                new_unify_values = []

                for idx, region in enumerate(current_regions):
                    last_standard_region = unify_value_map[last_key][idx] if idx < len(unify_value_map[last_key]) else None

                    # If the current region is similar to the previous key's matching region, unify them
                    if last_standard_region and self.are_similar(region, last_standard_region):
                        new_unify_values.append(last_standard_region)
                    else:
                        new_unify_values.append(region)

                # Update unify_value_map with the latest interval values
                unify_value_map[key] = new_unify_values
                last_key = key

            # Pass the final unified results to unified_regions
            for key in keys:
                unified_regions[key] = unify_value_map[key]
            return unified_regions
        else:
            return raw_regions

    @staticmethod
    def find_continuous_ranges(subtitle_frame_no_box_dict):
        """
        Get start and end frame numbers where subtitles appear
        """
        numbers = sorted(list(subtitle_frame_no_box_dict.keys()))
        ranges = []
        start = numbers[0]  # Initial range start

        for i in range(1, len(numbers)):
            # If the gap from the previous number is more than 1,
            # close the previous range and record start/end
            if numbers[i] - numbers[i - 1] != 1:
                end = numbers[i - 1]  # End of the current continuous range
                ranges.append((start, end))
                start = numbers[i]  # Start the next continuous range
        # Append the last range
        ranges.append((start, numbers[-1]))
        return ranges

    @staticmethod
    def find_continuous_ranges_with_same_mask(subtitle_frame_no_box_dict):
        numbers = sorted(list(subtitle_frame_no_box_dict.keys()))
        ranges = []
        start = numbers[0]  # Initial range start
        for i in range(1, len(numbers)):
            # If the gap from the previous frame number is more than 1,
            # close the previous range and record start/end
            if numbers[i] - numbers[i - 1] != 1:
                end = numbers[i - 1]  # End of the current continuous range
                ranges.append((start, end))
                start = numbers[i]  # Start the next continuous range
            # If consecutive frames differ by 1 but their coordinate boxes differ,
            # close the current range and start a new one
            if numbers[i] - numbers[i - 1] == 1:
                if subtitle_frame_no_box_dict[numbers[i]] != subtitle_frame_no_box_dict[numbers[i - 1]]:
                    end = numbers[i - 1]  # End of the current continuous range
                    ranges.append((start, end))
                    start = numbers[i]  # Start the next continuous range
        # Append the last range
        ranges.append((start, numbers[-1]))
        return ranges

    @staticmethod
    def filter_and_merge_intervals(intervals, target_length):
        """
        Merge subtitle start intervals so each range is at least STTN_REFERENCE_LENGTH long.
        Complexity O(n log n)
        """
        if not intervals:
            return []
        intervals = sorted(intervals, key=lambda x: x[0])
        # Single pass: expand single-point intervals using sorted neighbors O(n)
        expanded = []
        for i, (start, end) in enumerate(intervals):
            if start == end:  # Single-point interval
                prev_end = expanded[-1][1] if expanded else float('-inf')
                next_start = intervals[i + 1][0] if i + 1 < len(intervals) else float('inf')
                half = (target_length - 1) // 2
                new_start = max(start - half, prev_end + 1)
                new_end = min(start + half, next_start - 1)
                if new_end < new_start:
                    new_start, new_end = start, start
                expanded.append((new_start, new_end))
            else:
                expanded.append((start, end))
        # Single pass: merge overlapping or adjacent short intervals O(n)
        merged = [expanded[0]]
        for start, end in expanded[1:]:
            last_start, last_end = merged[-1]
            last_len = last_end - last_start + 1
            cur_len = end - start + 1
            if (start <= last_end or start == last_end + 1) and (cur_len < target_length or last_len < target_length):
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged
