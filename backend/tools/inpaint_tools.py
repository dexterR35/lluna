import multiprocessing
import cv2
import numpy as np

from backend.config import config


def is_cuda_oom_error(exc: BaseException) -> bool:
    """True when the exception looks like GPU / CUDA memory exhaustion."""
    if isinstance(exc, MemoryError):
        return True
    msg = str(exc).lower()
    return (
        "out of memory" in msg
        or ("cuda" in msg and "memory" in msg)
        or "cudnn_status_alloc_failed" in msg
    )


def inpaint_with_oom_batch_retry(model, frames, mask):
    """
    Run model(frames, mask). On CUDA OOM, free cache and retry once with half batch.

    Matches enhance's smaller-tile retry: same model/device, smaller workload, one attempt.
    """
    try:
        return model(frames, mask)
    except (RuntimeError, MemoryError) as e:
        if not is_cuda_oom_error(e) or len(frames) <= 1:
            raise
        from backend.tools.cuda_hygiene import empty_cuda_cache

        empty_cuda_cache()
        half = max(1, len(frames) // 2)
        try:
            from tqdm import tqdm

            tqdm.write(f"GPU OOM: retrying with half batch ({len(frames)} -> {half})")
        except Exception:
            print(f"GPU OOM: retrying with half batch ({len(frames)} -> {half})")
        out = []
        for i in range(0, len(frames), half):
            out.extend(model(frames[i : i + half], mask))
        return out


def batch_generator(data, max_batch_size):
    """
    Split data into roughly even batches whose length does not exceed max_batch_size
    """
    n_samples = len(data)
    # Try a batch_size smaller than MAX_BATCH_SIZE so batch counts are as even as possible
    batch_size = max_batch_size
    num_batches = n_samples // batch_size

    # Handle a possible undersized last batch
    # If the last batch is much smaller, shrink batch_size to balance counts
    while n_samples % batch_size < batch_size / 2.0 and batch_size > 1:
        batch_size -= 1  # Shrink batch size
        num_batches = n_samples // batch_size

    # Yield the first num_batches batches
    for i in range(num_batches):
        yield data[i * batch_size:(i + 1) * batch_size]

    # Yield remaining data as the last batch
    last_batch_start = num_batches * batch_size
    if last_batch_start < n_samples:
        yield data[last_batch_start:]

def create_mask(size, coords_list):
    mask = np.zeros(size, dtype="uint8")
    if coords_list:
        for coords in coords_list:
            xmin, xmax, ymin, ymax = coords
            # Expand by a few pixels so boxes are not too small
            x1 = xmin - config.subtitleAreaDeviationPixel.value
            if x1 < 0:
                x1 = 0
            y1 = ymin - config.subtitleAreaDeviationPixel.value
            if y1 < 0:
                y1 = 0
            x2 = xmax + config.subtitleAreaDeviationPixel.value
            y2 = ymax + config.subtitleAreaDeviationPixel.value
            cv2.rectangle(mask, (x1, y1),
                          (x2, y2), (255, 255, 255), thickness=-1)
    return mask

def get_inpaint_area_by_mask(W, H, h, mask, multiple=1):
    """
    Derive subtitle removal regions from the mask: find areas to inpaint and their height,
    then adjust region size to a multiple required by the model.
    
    Args:
        W: Image width
        H: Image height
        h: Detection region height
        mask: Mask image
        multiple: Region dimensions must be a multiple of this; default 1
    
    Returns:
        Adjusted inpaint region list as [(ymin, ymax, xmin, xmax), ...]
    """
    # List of inpaint regions
    inpaint_area = []
    
    # If mask is all zeros, return empty list
    if np.all(mask == 0):
        return inpaint_area
    
    # Find all connected components (islands) in the mask
    # Ensure the mask is binary first
    binary_mask = (mask > 0).astype(np.uint8) * 255
    
    # Find connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_mask, connectivity=8)
    
    # Skip background (label 0)
    island_info = []
    for i in range(1, num_labels):
        # Stats for the current island
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        height = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        
        # Ignore tiny regions (likely noise)
        if area < 10:
            continue
        
        # Store island info: top y, bottom y, center y, area, label
        center_y = int(centroids[i][1])
        island_info.append((y, y + height, center_y, area, i))
    
    # No valid islands; return empty list
    if not island_info:
        return inpaint_area
    
    # Sort islands by center y
    island_info.sort(key=lambda x: x[2])
    
    # Try merging islands
    merged_islands = []
    current_group = [island_info[0]]
    
    for i in range(1, len(island_info)):
        # Current group bounds
        min_y = min([island[0] for island in current_group])
        max_y = max([island[1] for island in current_group])
        
        # Current island
        top_y, bottom_y, center_y, _, _ = island_info[i]
        
        # Bounds if the current island is added
        new_min_y = min(min_y, top_y)
        new_max_y = max(max_y, bottom_y)
        
        # Check whether mask connects the current group and the new island
        has_connection = False
        if max_y < top_y:  # Only need to check when the group is above the new island
            # Check for mask pixels between the two regions
            middle_region = binary_mask[max_y:top_y, :]
            if np.any(middle_region > 0):
                has_connection = True
        else:  # Overlapping or adjacent
            has_connection = True
        
        # Merge if combined height fits within h and there is a connection
        if new_max_y - new_min_y <= h and has_connection:
            # Can merge
            current_group.append(island_info[i])
        else:
            # Cannot merge; save current group and start a new one
            merged_islands.append(current_group)
            current_group = [island_info[i]]
    
    # Append the last group
    merged_islands.append(current_group)
    
    # Create a region for each merged group
    for group in merged_islands:
        # Bounds of all islands in the group
        min_y = min([island[0] for island in group])
        max_y = max([island[1] for island in group])
        
        # Group center
        center_y = sum([island[2] for island in group]) // len(group)
        
        # Ensure region height is exactly h
        half_h = h // 2
        
        # Expand from center so height equals h
        ymin = max(0, center_y - half_h)
        ymax = ymin + h  # Ensure height is exactly h
        
        # If past the bottom of the image, shift up from the bottom
        if ymax > H:
            ymax = H
            ymin = max(0, H - h)  # Ensure height is h
        
        # Check whether all islands are covered
        if ymin > min_y or ymax < max_y:
            # If the region cannot fully cover islands, try repositioning while keeping height h
            if max_y - min_y <= h:
                # Total island height fits in h; adjust position to cover them
                ymin = min_y
                ymax = ymin + h
                # If past the bottom, shift up from the bottom
                if ymax > H:
                    ymax = H
                    ymin = max(0, H - h)
            else:
                # Island height exceeds h; cannot fully cover - prefer the center area
                # Compute island center
                island_center = (min_y + max_y) // 2
                ymin = max(0, island_center - half_h)
                ymax = ymin + h
                # If past the bottom, shift up from the bottom
                if ymax > H:
                    ymax = H
                    ymin = max(0, H - h)
        
        # Use full width
        xmin = 0
        xmax = W
        
        # Adjust region size to the required multiple
        if multiple > 1:
            # Current region height
            height = ymax - ymin
            # How much to adjust so height is a multiple of multiple
            remainder = height % multiple
            
            if remainder != 0:
                # Pixels to adjust
                adjust_pixels = multiple - remainder
                
                # Region center
                center_y = (ymin + ymax) / 2
                
                # Prefer symmetric expansion
                if ymin - adjust_pixels/2 >= 0 and ymax + adjust_pixels/2 <= H:
                    # Symmetric expand
                    ymin = int(center_y - height/2 - adjust_pixels/2)
                    ymax = int(center_y + height/2 + adjust_pixels/2)
                # If symmetric expand would go out of bounds, try symmetric shrink
                elif height > multiple:  # Ensure shrunk height is at least multiple
                    # Symmetric shrink
                    ymin = int(center_y - (height - remainder)/2)
                    ymax = int(center_y + (height - remainder)/2)
                # Otherwise try one-sided adjustment
                else:
                    # Expand downward
                    if ymax + adjust_pixels <= H:
                        ymax += adjust_pixels
                    # Expand upward
                    elif ymin - adjust_pixels >= 0:
                        ymin -= adjust_pixels
                    # Last resort: shrink the region
                    elif height > multiple:
                        ymax = ymin + height - remainder
            
            # Adjust width so it is a multiple of multiple
            width = xmax - xmin
            remainder_w = width % multiple
            
            if remainder_w != 0:
                # Pixels to adjust
                adjust_pixels_w = multiple - remainder_w
                
                # Center and shrink symmetrically
                center_x = (xmin + xmax) / 2
                xmin = int(center_x - (width - remainder_w)/2)
                xmax = int(center_x + (width - remainder_w)/2)
        
        # Append region as (ymin, ymax, xmin, xmax)
        area = (int(ymin), int(ymax), int(xmin), int(xmax))
        if area not in inpaint_area:
            inpaint_area.append(area)
    
    return inpaint_area  # Inpaint regions as [(ymin, ymax, xmin, xmax), ...]
    
def expand_frame_ranges(frame_ranges, backward_frame_count, forward_frame_count):
    """
    Expand frame ranges forward and backward by the given frame counts, keeping continuity
    
    Args:
        frame_ranges: Frame range list as [(start1, end1), (start2, end2), ...]
        backward_frame_count: Frames to expand backward
        forward_frame_count: Frames to expand forward
        
    Returns:
        Expanded frame ranges, kept continuous / non-overlapping
    """
    if not frame_ranges:
        return []
    
    # Sort by start frame
    sorted_ranges = sorted(frame_ranges)
    expanded_ranges = []
    
    for i, (start, end) in enumerate(sorted_ranges):
        # Expand backward, but not below 1
        new_start = max(1, start - backward_frame_count)
        
        # Expand forward
        new_end = end + forward_frame_count
        
        # Check overlap with the next range
        if i < len(sorted_ranges) - 1:
            next_start = sorted_ranges[i + 1][0]
            
            # If expanded end reaches or passes the next range start
            if new_end >= next_start:
                # Midpoint
                mid_point = (end + next_start) // 2
                
                # If ranges are contiguous (gap of 1), keep original end
                if next_start - end == 1:
                    new_end = end  # Keep original end frame
                else:
                    # Non-contiguous: limit expand so we do not overlap the next range
                    max_expand = next_start - 1  # Ensure no overlap with next range
                    new_end = min(new_end, max_expand)
        
        # Ensure no overlap with the previous range
        if expanded_ranges:
            prev_end = expanded_ranges[-1][1]
            if new_start <= prev_end:
                # If new start is at or before previous end, bump start forward
                new_start = prev_end + 1
        
        # Ensure the range is valid (start <= end)
        if new_start <= new_end:
            expanded_ranges.append((new_start, new_end))
        else:
            # If adjustment made the range invalid, keep the original
            expanded_ranges.append((start, end))
    
    return expanded_ranges

def is_frame_number_in_ab_sections(frame_no, ab_sections):
    """
    Check whether the given frame number falls inside any A/B section.

    Args:
        frame_no: Frame number to check
        ab_sections: List of A/B sections as [range(start, end), ...]

    Returns:
        True if the frame is in an A/B section; otherwise False.
    """
    if ab_sections is None:
        return True
    if len(ab_sections) <= 0:
        return True
    for section in ab_sections:
        if frame_no in section:
            return True
    return False

if __name__ == '__main__':
    multiprocessing.set_start_method("spawn")
