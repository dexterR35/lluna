import time

import cv2
import numpy as np
import torch
from torchvision import transforms
from typing import List
from backend.inpaint.sttn.network_sttn import InpaintGenerator
from backend.inpaint.utils.sttn_utils import Stack, ToTorchFormatTensor
from backend.tools.inpaint_tools import get_inpaint_area_by_mask

# Define image preprocessing pipeline
_to_tensors = transforms.Compose([
    Stack(),  # Stack images into a sequence
    ToTorchFormatTensor()  # Convert stacked images to PyTorch tensors
])

class STTNDetInpaint:
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
        self.model_input_width, self.model_input_height = 432, 240
        # Set neighboring frame stride
        self.neighbor_stride = neighbor_stride
        self.ref_length = reference_length

    def __call__(self, input_frames: List[np.ndarray], input_mask: np.ndarray):
        """
        :param input_frames: Original video frames
        :param mask: Subtitle-region mask
        """
        mask = input_mask[:, :, None]
        H_ori, W_ori = mask.shape[:2]
        H_ori = int(H_ori + 0.5)
        W_ori = int(W_ori + 0.5)
        # Determine the vertical crop height for subtitle removal
        if H_ori > W_ori:
            split_h = int(H_ori * 5 / 9)
        else:
            split_h = int(W_ori * 5 / 18)
        inpaint_area = get_inpaint_area_by_mask(W_ori, H_ori, split_h, mask)
        # Initialize frame storage
        # High-resolution frames (shallow list + per-frame copy; avoid deepcopy cost)
        frames_hr = [f.copy() for f in input_frames]
        frames_scaled = {}  # Dict of scaled frames
        masks_scaled = {}  # Dict of scaled masks
        comps = {}  # Dict of inpainted frames
        # Store final video frames
        inpainted_frames = []
        for k in range(len(inpaint_area)):
            frames_scaled[k] = []  # Init list for each inpaint region
            masks_scaled[k] = []  # Init list for each inpaint region

        # Read and scale frames
        for j in range(len(frames_hr)):
            image = frames_hr[j]
            # Crop and scale each inpaint region
            for k in range(len(inpaint_area)):
                image_crop = image[inpaint_area[k][0]:inpaint_area[k][1], :, :]  # Crop
                mask_crop = mask[inpaint_area[k][0]:inpaint_area[k][1], :, :]  # Crop
                image_resize = cv2.resize(image_crop, (self.model_input_width, self.model_input_height))  # Resize
                mask_resize = cv2.resize(mask_crop, (self.model_input_width, self.model_input_height))  # Resize
                frames_scaled[k].append(image_resize)  # Append scaled frame
                masks_scaled[k].append(mask_resize)  # Append scaled mask

        # Process each inpaint region
        for k in range(len(inpaint_area)):
            # Run inpainting
            comps[k] = self.inpaint(frames_scaled[k], masks_scaled[k])

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
                    frame[inpaint_area[k][0]:inpaint_area[k][1], :, :] = comp
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

    def inpaint(self, frames: List[np.ndarray], masks: List[np.ndarray]):
        """
        Fill masked holes using STTN.
        """
        frame_length = len(frames)
        # Preprocess frames to tensors and normalize
        feats = _to_tensors(frames).unsqueeze(0) * 2 - 1

        binary_masks = [np.expand_dims((np.array(m) > 0.5).astype(np.uint8), 2) for m in masks]
        # Convert masks to tensors
        masks_tensor = (_to_tensors(masks).unsqueeze(0) > 0.5).float()

        # Move feature tensors to the selected device (CPU or GPU)
        feats, masks_tensor = feats.to(self.device), masks_tensor.to(self.device)
        # List (same length as video) for completed frames
        comp_frames = [None] * frame_length
        # Disable gradients for faster, lower-memory inference
        with torch.no_grad():
            # Encode frames into feature representations
            feats = self.model.encoder((feats*(1-masks_tensor).float()).view(frame_length, 3, self.model_input_height, self.model_input_width))
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
                pred_feat = self.model.infer(
                    feats[0, neighbor_ids + ref_ids, :, :, :], masks_tensor[0, neighbor_ids + ref_ids, :, :, :])

                # Decode predicted features and apply tanh
                pred_img = torch.tanh(self.model.decoder(pred_feat[:len(neighbor_ids), :, :, :]))
                # Rescale result tensors to the 0–255 pixel range
                pred_img = (pred_img + 1) / 2
                # Move tensors back to CPU and convert to NumPy
                pred_img = pred_img.cpu().permute(0, 2, 3, 1).numpy() * 255
                # Iterate over neighbor frames
                for i in range(len(neighbor_ids)):
                    idx = neighbor_ids[i]
                    # Convert predicted image to uint8 and composite with the mask
                    img = pred_img[i].astype(np.uint8) * binary_masks[idx] + frames[idx] * (1 - binary_masks[idx])
                    if comp_frames[idx] is None:
                        comp_frames[idx] = img
                    else:
                        comp_frames[idx] = comp_frames[idx].astype(np.float32) * 0.5 + img.astype(np.float32) * 0.5
        # Return completed frame sequence
        return comp_frames
