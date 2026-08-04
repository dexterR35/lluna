import os
import gc
from typing import List

import cv2
import torch
import numpy as np
from tqdm import tqdm

from backend.inpaint.sttn.auto_sttn import InpaintGenerator
from backend.inpaint.tensor_transforms import to_tensors
from backend.tools.inpaint_tools import get_inpaint_area_by_mask, is_frame_number_in_ab_sections
from backend.tools.video_io import FramePrefetcher
from backend.tools.hardware_accelerator import HardwareAccelerator

# Define image preprocessing pipeline
_to_tensors = to_tensors()

class STTNInpaint:
    def __init__(
        self,
        device,
        model_path,
        *,
        neighbor_stride: int = 5,
        reference_length: int = 10,
    ):
        self.device = device
        # 1. Create InpaintGenerator and move it to the selected device
        self.model = InpaintGenerator().to(self.device)
        # 2. Load pretrained weights into the model state dict
        self.model.load_state_dict(torch.load(model_path, map_location='cpu')['netG'])
        # 3. Set the model to evaluation mode
        self.model.eval()
        # Model input width and height
        self.model_input_width, self.model_input_height = 640, 120
        # Set neighboring frame stride
        self.neighbor_stride = neighbor_stride
        self.ref_length = reference_length

    def __call__(self, input_frames: List[np.ndarray], input_mask: np.ndarray):
        """
        :param input_frames: Original video frames
        :param mask: Subtitle-region mask
        """
        _, mask = cv2.threshold(input_mask, 127, 1, cv2.THRESH_BINARY)
        mask = mask[:, :, None]
        H_ori, W_ori = mask.shape[:2]
        H_ori = int(H_ori + 0.5)
        W_ori = int(W_ori + 0.5)
        # Determine the vertical crop height for subtitle removal
        split_h = int(W_ori * 3 / 16)
        inpaint_area = get_inpaint_area_by_mask(W_ori, H_ori, split_h, mask)
        # Initialize frame storage
        # High-resolution frames (shallow list + per-frame copy; avoid deepcopy cost)
        frames_hr = [f.copy() for f in input_frames]
        frames_scaled = {}  # Dict of scaled frames
        comps = {}  # Dict of inpainted frames
        # Store final video frames
        inpainted_frames = []
        for k in range(len(inpaint_area)):
            frames_scaled[k] = []  # Init list for each inpaint region

        # Read and scale frames
        for j in range(len(frames_hr)):
            image = frames_hr[j]
            # Crop and scale each inpaint region
            for k in range(len(inpaint_area)):
                image_crop = image[inpaint_area[k][0]:inpaint_area[k][1], :, :]  # Crop
                image_resize = cv2.resize(image_crop, (self.model_input_width, self.model_input_height))  # Resize
                frames_scaled[k].append(image_resize)  # Append scaled frame

        # Process each inpaint region
        for k in range(len(inpaint_area)):
            # Run inpainting
            comps[k] = self.inpaint(frames_scaled[k])

        # If there are regions to inpaint
        if inpaint_area:
            for j in range(len(frames_hr)):
                frame = frames_hr[j]  # Original frame
                # For each inpaint region segment
                for k in range(len(inpaint_area)):
                    comp = cv2.resize(comps[k][j], (W_ori, split_h))  # Resize inpainted frame back to original size
                    comp = cv2.cvtColor(comp.astype(np.uint8), cv2.COLOR_BGR2RGB)  # Convert color space
                    # Get mask region and compose the image
                    mask_area = mask[inpaint_area[k][0]:inpaint_area[k][1], :]  # Mask crop
                    # Blend within the masked region
                    frame[inpaint_area[k][0]:inpaint_area[k][1], :, :] = mask_area * comp + (1 - mask_area) * frame[inpaint_area[k][0]:inpaint_area[k][1], :, :]
                # Append final frame
                inpainted_frames.append(frame)
                # print(f'processing frame, {len(frames_hr) - j} left')
        else:
            inpainted_frames = frames_hr
        return inpainted_frames

    @staticmethod
    def read_mask(path):
        img = cv2.imread(path, 0)
        # Convert to binary mask
        ret, img = cv2.threshold(img, 127, 1, cv2.THRESH_BINARY)
        img = img[:, :, None]
        return img

    def get_ref_index(self, neighbor_ids, length):
        """
        Sample reference frames across the whole video.
        """
        # Initialize reference-frame index list
        ref_index = []
        # Iterate over the video length with ref_length stride
        for i in range(0, length, self.ref_length):
            # Skip frames already in the neighbor set
            if i not in neighbor_ids:
                # Add to reference-frame list
                ref_index.append(i)
        # Return reference-frame indices
        return ref_index

    def inpaint(self, frames: List[np.ndarray]):
        """
        Fill masked holes using STTN.
        """
        frame_length = len(frames)
        # Preprocess frames to tensors and normalize
        feats = _to_tensors(frames).unsqueeze(0) * 2 - 1
        # Move feature tensors to the selected device (CPU or GPU)
        feats = feats.to(self.device)
        # List (same length as video) for completed frames
        comp_frames = [None] * frame_length
        # Disable gradients for faster, lower-memory inference
        with torch.no_grad():
            # Encode frames into feature representations
            feats = self.model.encoder(feats.view(frame_length, 3, self.model_input_height, self.model_input_width))
            # Feature dimensions
            _, c, feat_h, feat_w = feats.size()
            # Reshape features to the model expected input layout
            feats = feats.view(1, frame_length, c, feat_h, feat_w)
            # Process the video in neighbor-stride windows
            for f in range(0, frame_length, self.neighbor_stride):
                # Neighbor frame IDs
                neighbor_ids = [i for i in range(max(0, f - self.neighbor_stride), min(frame_length, f + self.neighbor_stride + 1))]
                # Reference frame indices
                ref_ids = self.get_ref_index(neighbor_ids, frame_length)
                # Infer features and decode completed frames
                pred_feat = self.model.infer(feats[0, neighbor_ids + ref_ids, :, :, :])
                # Decode predicted features and apply tanh
                pred_img = torch.tanh(self.model.decoder(pred_feat[:len(neighbor_ids), :, :, :]))
                # Rescale result tensors to the 0–255 range
                pred_img = (pred_img + 1) / 2
                # Move tensors back to CPU and convert to NumPy
                pred_img = pred_img.cpu().permute(0, 2, 3, 1).numpy() * 255
                # Iterate over neighbor frames
                for i in range(len(neighbor_ids)):
                    idx = neighbor_ids[i]
                    img = pred_img[i].astype(np.uint8)
                    if comp_frames[idx] is None:
                        comp_frames[idx] = img
                    else:
                        comp_frames[idx] = comp_frames[idx].astype(np.float32) * 0.5 + img.astype(np.float32) * 0.5
        # Return completed frame sequence
        return comp_frames


class STTNAutoInpaint:

    def read_frame_info_from_video(self):
        # Open the video with OpenCV
        reader = cv2.VideoCapture(self.video_path)
        # Store video width, height, fps, and frame count in frame_info
        frame_info = {
            'W_ori': int(reader.get(cv2.CAP_PROP_FRAME_WIDTH) + 0.5),  # Original video width
            'H_ori': int(reader.get(cv2.CAP_PROP_FRAME_HEIGHT) + 0.5),  # Original video height
            'fps': reader.get(cv2.CAP_PROP_FPS),  # Video frame rate
            'len': int(reader.get(cv2.CAP_PROP_FRAME_COUNT) + 0.5)  # Total frame count
        }
        # Return video reader and frame info
        return reader, frame_info

    def __init__(
        self,
        device,
        model_path,
        video_path,
        mask_path=None,
        clip_gap=50,
        *,
        neighbor_stride: int = 5,
        reference_length: int = 10,
    ):
        # Initialize STTNInpaint video inpainting instance
        self.sttn_inpaint = STTNInpaint(
            device,
            model_path,
            neighbor_stride=neighbor_stride,
            reference_length=reference_length,
        )
        try:
            from backend.tools.inpaint_release import register_video_inpaint_model
            register_video_inpaint_model(self.sttn_inpaint)
        except Exception:
            pass
        # Video and mask paths
        self.video_path = video_path
        self.mask_path = mask_path
        # Output video path
        self.video_out_path = os.path.join(
            os.path.dirname(os.path.abspath(self.video_path)),
            f"{os.path.basename(self.video_path).rsplit('.', 1)[0]}_no_sub.mp4"
        )
        # Max frames loaded per processing chunk
        self.clip_gap = clip_gap

    def __call__(self, input_mask=None, input_sub_remover=None, tbar=None):
        reader = None
        writer = None
        try:
            # Read video frame info
            reader, frame_info = self.read_frame_info_from_video()
            # Prefetch frames so I/O overlaps with inference
            prefetcher = FramePrefetcher(reader)
            if input_sub_remover is not None:
                ab_sections = input_sub_remover.ab_sections
                
                writer = input_sub_remover.video_writer
            else:
                ab_sections = None
                # Create video writer for the inpainted output
                writer = cv2.VideoWriter(self.video_out_path, cv2.VideoWriter_fourcc(*"mp4v"), frame_info['fps'], (frame_info['W_ori'], frame_info['H_ori']))
            
            # Compute split height used to size inpaint regions
            split_h = int(frame_info['W_ori'] * 3 / 16)

            if input_mask is None:
                # Read mask
                mask = self.sttn_inpaint.read_mask(self.mask_path)
            else:
                _, mask = cv2.threshold(input_mask, 127, 1, cv2.THRESH_BINARY)
                mask = mask[:, :, None]

            # Locate inpaint regions
            inpaint_area = get_inpaint_area_by_mask(frame_info['W_ori'], frame_info['H_ori'], split_h, mask)
            # Dynamically adjust clip_gap from available VRAM to avoid OOM
            effective_clip_gap = self.clip_gap
            vram_mb = HardwareAccelerator.instance().get_available_vram_mb()
            if vram_mb > 0:
                # Estimate ~ (W * H * 3 * 4) bytes per frame; clip_gap frames need ~ clip_gap * W * H * 12 bytes (incl. intermediate tensors)
                bytes_per_frame = frame_info['W_ori'] * frame_info['H_ori'] * 12
                max_frames_by_vram = int(vram_mb * 1024 * 1024 / bytes_per_frame)
                max_frames_by_vram = max(max_frames_by_vram, 10)  # At least 10 frames
                effective_clip_gap = min(self.clip_gap, max_frames_by_vram)
                if effective_clip_gap < self.clip_gap:
                    tqdm.write(f'GPU VRAM: {vram_mb:.0f}MB, adjusting clip_gap: {self.clip_gap} -> {effective_clip_gap}')
            # Number of chunk iterations needed
            rec_time = frame_info['len'] // effective_clip_gap if frame_info['len'] % effective_clip_gap == 0 else frame_info['len'] // effective_clip_gap + 1
            # Iterate over each chunk
            for i in range(rec_time):
                start_f = i * effective_clip_gap  # Start frame index
                end_f = min((i + 1) * effective_clip_gap, frame_info['len'])  # End frame index
                tqdm.write(f'Processing: {start_f + 1} - {end_f} / Total: {frame_info['len']}')
                
                frames_hr = []  # High-resolution frame list
                frames = {}  # Cropped frames per region
                comps = {}  # Inpainted frames per region
                
                # Initialize per-region frame lists
                for k in range(len(inpaint_area)):
                    frames[k] = []
                    
                # Read high-resolution frames
                valid_frames_count = 0
                for j in range(start_f, end_f):
                    success, image = prefetcher.read()
                    if not success:
                        print(f"Warning: Failed to read frame {j}.")
                        break
                    
                    frames_hr.append(image)
                    valid_frames_count += 1
                    
                    if is_frame_number_in_ab_sections(j, ab_sections):
                        for k in range(len(inpaint_area)):
                            # Crop, resize, and append to the frame dict
                            image_crop = image[inpaint_area[k][0]:inpaint_area[k][1], :, :]
                            image_resize = cv2.resize(image_crop, (self.sttn_inpaint.model_input_width, self.sttn_inpaint.model_input_height))
                            frames[k].append(image_resize)
                
                # Skip this iteration if no valid frames were read
                if valid_frames_count == 0:
                    print(f"Warning: No valid frames found in range {start_f+1}-{end_f}. Skipping this segment.")
                    continue
                    
                # Inpaint each region
                for k in range(len(inpaint_area)):
                    if len(frames[k]) > 0:  # Ensure there are frames to process
                        comps[k] = self.sttn_inpaint.inpaint(frames[k])
                    else:
                        comps[k] = []
                
                # If there are regions to inpaint
                if inpaint_area and valid_frames_count > 0:
                    # Map processed frames to their indices in frames[k]
                    processed_frames_map = {}
                    processed_idx = 0
                    
                    # Build the mapping
                    for j in range(start_f, end_f):
                        if j - start_f < valid_frames_count and is_frame_number_in_ab_sections(j, ab_sections):
                            processed_frames_map[j - start_f] = processed_idx
                            processed_idx += 1
                    
                    # Apply inpainting results
                    for j in range(valid_frames_count):
                        if input_sub_remover is not None and input_sub_remover.interactive:
                            original_frame = frames_hr[j].copy()
                        else:
                            original_frame = None
                            
                        frame = frames_hr[j]
                        
                        # Only apply results to processed frames
                        if j in processed_frames_map:
                            comp_idx = processed_frames_map[j]
                            for k in range(len(inpaint_area)):
                                if comp_idx < len(comps[k]):  # Ensure index is valid
                                    # Upscale inpainted image to original resolution and blend into the frame
                                    comp = cv2.resize(comps[k][comp_idx], (frame_info['W_ori'], split_h))
                                    comp = cv2.cvtColor(comp.astype(np.uint8), cv2.COLOR_BGR2RGB)
                                    mask_area = mask[inpaint_area[k][0]:inpaint_area[k][1], :]
                                    frame[inpaint_area[k][0]:inpaint_area[k][1], :, :] = mask_area * comp + (1 - mask_area) * frame[inpaint_area[k][0]:inpaint_area[k][1], :, :]
                        
                        writer.write(frame)
                        
                        if input_sub_remover is not None:
                            if tbar is not None:
                                input_sub_remover.update_progress(tbar, increment=1)
                            if original_frame is not None and input_sub_remover.interactive:
                                input_sub_remover.update_preview_with_comp(original_frame, frame)
                # Clear GPU cache after each chunk
                del frames_hr, frames, comps
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
        except Exception as e:
            print(f"Error during video processing: {str(e)}")
            raise
        finally:
            if reader:
                prefetcher.release()
            if writer:
                writer.release()
