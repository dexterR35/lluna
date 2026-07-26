import os
import glob
from tqdm import tqdm
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.utils.data.distributed import DistributedSampler
from torch.nn.parallel import DistributedDataParallel as DDP
from tensorboardX import SummaryWriter

from backend.inpaint.sttn.auto_sttn import Discriminator
from backend.inpaint.sttn.auto_sttn import InpaintGenerator
from backend.tools.train.dataset_sttn import Dataset
from backend.tools.train.loss_sttn import AdversarialLoss


class Trainer:
    def __init__(self, config, debug=False):
        # Trainer initialization
        self.config = config  # Config
        self.epoch = 0  # Current epoch
        self.iteration = 0  # Current iteration
        if debug:
            # Debug mode: save/validate more frequently
            self.config['trainer']['save_freq'] = 5
            self.config['trainer']['valid_freq'] = 5
            self.config['trainer']['iterations'] = 5

        # Dataset and data loader
        self.train_dataset = Dataset(config['data_loader'], split='train', debug=debug)  # Training dataset
        self.train_sampler = None  # Distributed sampler (optional)
        self.train_args = config['trainer']  # Trainer hyperparameters
        if config['distributed']:
            # Distributed sampler for multi-GPU training
            self.train_sampler = DistributedSampler(
                self.train_dataset,
                num_replicas=config['world_size'],
                rank=config['global_rank']
            )
        self.train_loader = DataLoader(
            self.train_dataset,
            batch_size=self.train_args['batch_size'] // config['world_size'],
            shuffle=(self.train_sampler is None),  # Shuffle when no sampler is set
            num_workers=self.train_args['num_workers'],
            sampler=self.train_sampler
        )

        # Loss functions
        self.adversarial_loss = AdversarialLoss(type=self.config['losses']['GAN_LOSS'])  # Adversarial loss
        self.adversarial_loss = self.adversarial_loss.to(self.config['device'])  # Move loss to device
        self.l1_loss = nn.L1Loss()  # L1 loss

        # Generator and discriminator
        self.netG = InpaintGenerator()  # Generator network
        self.netG = self.netG.to(self.config['device'])  # Move to device
        self.netD = Discriminator(
            in_channels=3, use_sigmoid=config['losses']['GAN_LOSS'] != 'hinge'
        )
        self.netD = self.netD.to(self.config['device'])  # Discriminator on device
        # Optimizers
        self.optimG = torch.optim.Adam(
            self.netG.parameters(),  # Generator parameters
            lr=config['trainer']['lr'],  # Learning rate
            betas=(self.config['trainer']['beta1'], self.config['trainer']['beta2'])
        )
        self.optimD = torch.optim.Adam(
            self.netD.parameters(),  # Discriminator parameters
            lr=config['trainer']['lr'],  # Learning rate
            betas=(self.config['trainer']['beta1'], self.config['trainer']['beta2'])
        )
        self.load()  # Load checkpoint if available

        if config['distributed']:
            # Wrap models with DistributedDataParallel
            self.netG = DDP(
                self.netG,
                device_ids=[self.config['local_rank']],
                output_device=self.config['local_rank'],
                broadcast_buffers=True,
                find_unused_parameters=False
            )
            self.netD = DDP(
                self.netD,
                device_ids=[self.config['local_rank']],
                output_device=self.config['local_rank'],
                broadcast_buffers=True,
                find_unused_parameters=False
            )

        # TensorBoard writers
        self.dis_writer = None  # Discriminator writer
        self.gen_writer = None  # Generator writer
        self.summary = {}  # Running summary stats
        if self.config['global_rank'] == 0 or (not config['distributed']):
            # Non-distributed or rank-0 process
            self.dis_writer = SummaryWriter(
                os.path.join(config['save_dir'], 'dis')
            )
            self.gen_writer = SummaryWriter(
                os.path.join(config['save_dir'], 'gen')
            )

    # Current learning rate
    def get_lr(self):
        return self.optimG.param_groups[0]['lr']

    # Adjust learning rate
    def adjust_learning_rate(self):
        # Decayed learning rate
        decay = 0.1 ** (min(self.iteration, self.config['trainer']['niter_steady']) // self.config['trainer']['niter'])
        new_lr = self.config['trainer']['lr'] * decay
        # Update optimizer LRs when the value changes
        if new_lr != self.get_lr():
            for param_group in self.optimG.param_groups:
                param_group['lr'] = new_lr
            for param_group in self.optimD.param_groups:
                param_group['lr'] = new_lr

    # Add summary scalar
    def add_summary(self, writer, name, val):
        # Accumulate stats every iteration
        if name not in self.summary:
            self.summary[name] = 0
        self.summary[name] += val
        # Log every 100 iterations
        if writer is not None and self.iteration % 100 == 0:
            writer.add_scalar(name, self.summary[name] / 100, self.iteration)
            self.summary[name] = 0

    # Load netG and netD checkpoints
    def load(self):
        model_path = self.config['save_dir']  # Checkpoint directory
        # Check for the latest checkpoint
        if os.path.isfile(os.path.join(model_path, 'latest.ckpt')):
            # Read the latest epoch id
            latest_epoch = open(os.path.join(
                model_path, 'latest.ckpt'), 'r').read().splitlines()[-1]
        else:
            # No latest.ckpt: fall back to the newest *.pth file
            ckpts = [os.path.basename(i).split('.pth')[0] for i in glob.glob(
                os.path.join(model_path, '*.pth'))]
            ckpts.sort()  # Sort to pick the newest
            latest_epoch = ckpts[-1] if len(ckpts) > 0 else None  # Latest epoch id
        if latest_epoch is not None:
            # Build generator/discriminator/optimizer checkpoint paths
            gen_path = os.path.join(
                model_path, 'gen_{}.pth'.format(str(latest_epoch).zfill(5)))
            dis_path = os.path.join(
                model_path, 'dis_{}.pth'.format(str(latest_epoch).zfill(5)))
            opt_path = os.path.join(
                model_path, 'opt_{}.pth'.format(str(latest_epoch).zfill(5)))
            # Rank 0: log model load path
            if self.config['global_rank'] == 0:
                print('Loading model from {}...'.format(gen_path))
            # Load generator
            data = torch.load(gen_path, map_location=self.config['device'])
            self.netG.load_state_dict(data['netG'])
            # Load discriminator
            data = torch.load(dis_path, map_location=self.config['device'])
            self.netD.load_state_dict(data['netD'])
            # Load optimizer states
            data = torch.load(opt_path, map_location=self.config['device'])
            self.optimG.load_state_dict(data['optimG'])
            self.optimD.load_state_dict(data['optimD'])
            # Restore epoch and iteration counters
            self.epoch = data['epoch']
            self.iteration = data['iteration']
        else:
            # Warn when no checkpoint is found
            if self.config['global_rank'] == 0:
                print('Warning: There is no trained model found. An initialized model will be used.')

    # Save model parameters (called every eval/save cycle)
    def save(self, it):
        # Save only on the global rank-0 process
        if self.config['global_rank'] == 0:
            # Generator checkpoint path
            gen_path = os.path.join(
                self.config['save_dir'], 'gen_{}.pth'.format(str(it).zfill(5)))
            # Discriminator checkpoint path
            dis_path = os.path.join(
                self.config['save_dir'], 'dis_{}.pth'.format(str(it).zfill(5)))
            # Optimizer checkpoint path
            opt_path = os.path.join(
                self.config['save_dir'], 'opt_{}.pth'.format(str(it).zfill(5)))

            # Log that a checkpoint is being saved
            print('\nsaving model to {} ...'.format(gen_path))

            # Unwrap DataParallel/DDP to get the underlying module
            if isinstance(self.netG, torch.nn.DataParallel) or isinstance(self.netG, DDP):
                netG = self.netG.module
                netD = self.netD.module
            else:
                netG = self.netG
                netD = self.netD

            # Save generator and discriminator weights
            torch.save({'netG': netG.state_dict()}, gen_path)
            torch.save({'netD': netD.state_dict()}, dis_path)
            # Save epoch, iteration, and optimizer states
            torch.save({
                'epoch': self.epoch,
                'iteration': self.iteration,
                'optimG': self.optimG.state_dict(),
                'optimD': self.optimD.state_dict()
            }, opt_path)

            # Write the latest iteration id to latest.ckpt
            os.system('echo {} > {}'.format(str(it).zfill(5),
                                            os.path.join(self.config['save_dir'], 'latest.ckpt')))

        # Training entry point

    def train(self):
        # Progress bar over total iterations
        pbar = range(int(self.train_args['iterations']))
        # Show progress bar on global rank 0
        if self.config['global_rank'] == 0:
            pbar = tqdm(pbar, initial=self.iteration, dynamic_ncols=True, smoothing=0.01)

        # Training loop
        while True:
            self.epoch += 1  # Increment epoch
            if self.config['distributed']:
                # Set sampler epoch so each process sees a different shuffle
                self.train_sampler.set_epoch(self.epoch)

            # Train one epoch
            self._train_epoch(pbar)
            # Stop when iteration budget is exceeded
            if self.iteration > self.train_args['iterations']:
                break
        # Training finished
        print('\nEnd training....')

        # Process inputs and compute losses for one epoch

    def _train_epoch(self, pbar):
        device = self.config['device']  # Device

        # Iterate over the data loader
        for frames, masks in self.train_loader:
            # Adjust learning rate
            self.adjust_learning_rate()
            # Increment iteration
            self.iteration += 1

            # Move frames and masks to device
            frames, masks = frames.to(device), masks.to(device)
            b, t, c, h, w = frames.size()  # Frame/mask tensor shape
            masked_frame = (frames * (1 - masks).float())  # Apply mask to frames
            pred_img = self.netG(masked_frame, masks)  # Generator inpainting
            # Reshape frames/masks for the discriminator input layout
            frames = frames.view(b * t, c, h, w)
            masks = masks.view(b * t, 1, h, w)
            comp_img = frames * (1. - masks) + masks * pred_img  # Composite final image

            gen_loss = 0  # Generator loss
            dis_loss = 0  # Discriminator loss

            # Discriminator adversarial loss
            real_vid_feat = self.netD(frames)  # Discriminator on real frames
            fake_vid_feat = self.netD(comp_img.detach())  # Discriminator on generated frames (detached)
            dis_real_loss = self.adversarial_loss(real_vid_feat, True, True)  # Real-sample loss
            dis_fake_loss = self.adversarial_loss(fake_vid_feat, False, True)  # Fake-sample loss
            dis_loss += (dis_real_loss + dis_fake_loss) / 2  # Averaged discriminator loss
            # Log discriminator losses
            self.add_summary(self.dis_writer, 'loss/dis_vid_fake', dis_fake_loss.item())
            self.add_summary(self.dis_writer, 'loss/dis_vid_real', dis_real_loss.item())
            # Optimize discriminator
            self.optimD.zero_grad()
            dis_loss.backward()
            self.optimD.step()

            # Generator adversarial loss
            gen_vid_feat = self.netD(comp_img)
            gan_loss = self.adversarial_loss(gen_vid_feat, True, False)  # Generator adversarial loss
            gan_loss = gan_loss * self.config['losses']['adversarial_weight']  # Apply adversarial weight
            gen_loss += gan_loss  # Accumulate generator loss
            # Log generator adversarial loss
            self.add_summary(self.gen_writer, 'loss/gan_loss', gan_loss.item())

            # Generator L1 hole loss
            hole_loss = self.l1_loss(pred_img * masks, frames * masks)  # L1 only inside the mask
            # Normalize by mean mask area and apply hole_weight
            hole_loss = hole_loss / torch.mean(masks) * self.config['losses']['hole_weight']
            gen_loss += hole_loss  # Accumulate generator loss
            # Log hole_loss
            self.add_summary(self.gen_writer, 'loss/hole_loss', hole_loss.item())

            # L1 loss outside the mask
            valid_loss = self.l1_loss(pred_img * (1 - masks), frames * (1 - masks))
            # Normalize by mean valid area and apply valid_weight
            valid_loss = valid_loss / torch.mean(1 - masks) * self.config['losses']['valid_weight']
            gen_loss += valid_loss  # Accumulate generator loss
            # Log valid_loss
            self.add_summary(self.gen_writer, 'loss/valid_loss', valid_loss.item())

            # Optimize generator
            self.optimG.zero_grad()
            gen_loss.backward()
            self.optimG.step()

            # Console progress logging
            if self.config['global_rank'] == 0:
                pbar.update(1)  # Update progress bar
                pbar.set_description((  # Progress bar description
                    f"d: {dis_loss.item():.3f}; g: {gan_loss.item():.3f};"  # Loss values
                    f"hole: {hole_loss.item():.3f}; valid: {valid_loss.item():.3f}")
                )

            # Periodic checkpoint save
            if self.iteration % self.train_args['save_freq'] == 0:
                self.save(int(self.iteration // self.train_args['save_freq']))
            # Stop when iteration budget is exceeded
            if self.iteration > self.train_args['iterations']:
                break

