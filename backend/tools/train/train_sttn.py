import os
import json
import argparse
from shutil import copyfile
import torch
import torch.multiprocessing as mp

from backend.tools.train.trainer_sttn import Trainer
from backend.tools.train.utils_sttn import (
    get_world_size,
    get_local_rank,
    get_global_rank,
    get_master_ip,
)

parser = argparse.ArgumentParser(description='STTN')
parser.add_argument('-c', '--config', default='configs_sttn/youtube-vos.json', type=str)
parser.add_argument('-m', '--model', default='sttn', type=str)
parser.add_argument('-p', '--port', default='23455', type=str)
parser.add_argument('-e', '--exam', action='store_true')
args = parser.parse_args()


def main_worker(rank, config):
    # If local_rank is missing from config, set local_rank and global_rank from rank
    if 'local_rank' not in config:
        config['local_rank'] = config['global_rank'] = rank

    # Distributed training setup
    if config['distributed']:
        # Bind CUDA device to the current local rank GPU
        torch.cuda.set_device(int(config['local_rank']))
        # Initialize the distributed process group with the NCCL backend
        torch.distributed.init_process_group(
            backend='nccl',
            init_method=config['init_method'],
            world_size=config['world_size'],
            rank=config['global_rank'],
            group_name='mtorch'
        )
        # Print which GPU is used, with global and local ranks
        print('using GPU {}-{} for training'.format(
            int(config['global_rank']), int(config['local_rank']))
        )

    # Build the model save directory from model name and config filename
    config['save_dir'] = os.path.join(
        config['save_dir'], '{}_{}'.format(config['model'], os.path.basename(args.config).split('.')[0])
    )

    # Use CUDA when available, otherwise CPU
    if torch.cuda.is_available():
        config['device'] = torch.device("cuda:{}".format(config['local_rank']))
    else:
        config['device'] = 'cpu'

    # On non-distributed runs or the rank-0 process
    if (not config['distributed']) or config['global_rank'] == 0:
        # Create the save directory (exist_ok=True)
        os.makedirs(config['save_dir'], exist_ok=True)
        # Destination path for the copied config file
        config_path = os.path.join(
            config['save_dir'], config['config'].split('/')[-1]
        )
        # Copy the config file into the save directory if missing
        if not os.path.isfile(config_path):
            copyfile(config['config'], config_path)
        # Log the created directory
        print('[**] create folder {}'.format(config['save_dir']))

    # Initialize trainer with config and debug flag
    trainer = Trainer(config, debug=args.exam)
    # Start training
    trainer.train()


if __name__ == "__main__":
    # Load config file
    config = json.load(open(args.config))
    config['model'] = args.model  # Model name
    config['config'] = args.config  # Config file path

    # Distributed-training settings
    config['world_size'] = get_world_size()  # Total number of processes / GPUs
    config['init_method'] = f"tcp://{get_master_ip()}:{args.port}"  # Process-group init method (master IP + port)
    config['distributed'] = True if config['world_size'] > 1 else False  # Enable distributed training when world_size > 1

    # Set up the distributed training environment
    if get_master_ip() == "127.0.0.1":
        # Local master: spawn multiple distributed training processes
        mp.spawn(main_worker, nprocs=config['world_size'], args=(config,))
    else:
        # Already launched by another tool (e.g. OpenMPI); do not spawn processes.
        config['local_rank'] = get_local_rank()  # Local (per-node) rank
        config['global_rank'] = get_global_rank()  # Global rank
        main_worker(-1, config)  # Start the main worker
