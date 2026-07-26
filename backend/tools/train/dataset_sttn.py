import os
import json
import random
import torch
import torchvision.transforms as transforms
from backend.tools.train.utils_sttn import ZipReader, create_random_shape_with_random_motion
from backend.tools.train.utils_sttn import Stack, ToTorchFormatTensor, GroupRandomHorizontalFlip


# Custom dataset
class Dataset(torch.utils.data.Dataset):
    def __init__(self, args: dict, split='train', debug=False):
        # Init with config dict and split type (default: 'train')
        self.args = args
        self.split = split
        self.sample_length = args['sample_length']  # Sample length
        self.size = self.w, self.h = (args['w'], args['h'])  # Target image width/height

        # Load dataset metadata JSON
        with open(os.path.join(args['data_root'], args['name'], split+'.json'), 'r') as f:
            self.video_dict = json.load(f)  # Video metadata
        self.video_names = list(self.video_dict.keys())  # Video name list
        if debug or split != 'train':  # In debug / non-train splits, keep only the first 100 videos
            self.video_names = self.video_names[:100]

        # Transform pipeline: stack into tensors
        self._to_tensors = transforms.Compose([
            Stack(),
            ToTorchFormatTensor(),  # PyTorch tensor format
        ])

    def __len__(self):
        # Number of videos in the dataset
        return len(self.video_names)

    def __getitem__(self, index):
        # Fetch one sample
        try:
            item = self.load_item(index)  # Try loading the item at index
        except:
            print('Loading error in video {}'.format(self.video_names[index]))  # Log load failure
            item = self.load_item(0)  # Fall back to the first item
        return item

    def load_item(self, index):
        # Load a single data item
        video_name = self.video_names[index]  # Video name for this index
        # Build frame filename list for the video
        all_frames = [f"{str(i).zfill(5)}.jpg" for i in range(self.video_dict[video_name])]
        # Create random free-form masks with random motion
        all_masks = create_random_shape_with_random_motion(
            len(all_frames), imageHeight=self.h, imageWidth=self.w)
        # Sample reference frame indices
        ref_index = get_ref_index(len(all_frames), self.sample_length)
        # Read video frames
        frames = []
        masks = []
        for idx in ref_index:
            # Read image, convert to RGB, resize, and append
            img = ZipReader.imread('{}/{}/JPEGImages/{}.zip'.format(
                self.args['data_root'], self.args['name'], video_name), all_frames[idx]).convert('RGB')
            img = img.resize(self.size)
            frames.append(img)
            masks.append(all_masks[idx])
        if self.split == 'train':
            # Random horizontal flip on the training split
            frames = GroupRandomHorizontalFlip()(frames)
        # Convert to tensors
        frame_tensors = self._to_tensors(frames)*2.0 - 1.0  # Normalize to [-1, 1]
        mask_tensors = self._to_tensors(masks)  # Convert masks to tensors
        return frame_tensors, mask_tensors  # Return frame and mask tensors


def get_ref_index(length, sample_length):
    # Sample reference frame indices
    if random.uniform(0, 1) > 0.5:
        # 50%: sample random frames
        ref_index = random.sample(range(length), sample_length)
        ref_index.sort()  # Keep temporal order
    else:
        # 50%: sample a contiguous clip
        pivot = random.randint(0, length-sample_length)
        ref_index = [pivot+i for i in range(sample_length)]
    return ref_index
