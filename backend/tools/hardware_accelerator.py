import importlib.util
import logging

import torch

logger = logging.getLogger(__name__)


class HardwareAccelerator:

    # Class variable holding the singleton instance
    _instance = None

    @classmethod
    def instance(cls):
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = HardwareAccelerator()
            cls._instance.initialize()
        return cls._instance

    def __init__(self):
        self.__cuda = False
        self.__dml = False
        self.__mps = False
        self.__enabled = True
        self.__device = None

    def initialize(self):
        """Populate the legacy adapter from the process-wide normalized profile."""
        from backend.hardware.detector import get_hardware_profile

        profile = get_hardware_profile()
        self.__dml = profile.capabilities.torch_directml
        self.__cuda = profile.capabilities.torch_cuda
        self.__mps = profile.capabilities.torch_mps

    def check_directml_available(self):
        self.__dml = importlib.util.find_spec("torch_directml") is not None

    def check_cuda_available(self):
        self.__cuda = torch.cuda.is_available()

    def check_mps_available(self):
        self.__mps = torch.backends.mps.is_available() and torch.backends.mps.is_built()

    def has_accelerator(self):
        if not self.__enabled:
            return False
        return self.__cuda or self.__dml or self.__mps

    @property
    def accelerator_name(self):
        if not self.__enabled:
            return "CPU"
        if self.__cuda:
            return "GPU"
        if self.__dml:
            return "DirectML"
        if self.__mps:
            return "MPS"
        return "CPU"

    def has_cuda(self):
        if not self.__enabled:
            return False
        return self.__cuda
    
    def has_mps(self):
        if not self.__enabled:
            return False
        return self.__mps

    def set_enabled(self, enable):
        self.__enabled = enable

    def get_vram_mb(self):
        """Return (free_mb, total_mb). Both 0 when CUDA is unavailable / disabled."""
        if not self.__enabled:
            return 0.0, 0.0
        if self.__cuda:
            try:
                free_b, total_b = torch.cuda.mem_get_info()
                return free_b / (1024 * 1024), total_b / (1024 * 1024)
            except Exception:
                return 0.0, 0.0
        if self.__mps:
            try:
                import subprocess
                result = subprocess.run(
                    ['sysctl', '-n', 'hw.memsize'],
                    capture_output=True,
                    text=True,
                )
                total_mem = int(result.stdout.strip()) / (1024 * 1024)
                # No real free query; expose a conservative "free" estimate.
                return total_mem * 0.5, total_mem
            except Exception:
                return 0.0, 0.0
        return 0.0, 0.0

    def get_available_vram_mb(self):
        """Get available GPU VRAM in MB; returns 0 if no GPU"""
        free, _total = self.get_vram_mb()
        return free

    @property
    def device(self):
        if self.__enabled:
            if self.__cuda:
                return torch.device("cuda:0")
            if self.__dml:
                try:
                    import torch_directml
                    self.__dml = True
                    return torch_directml.device(torch_directml.default_device())
                except Exception as exc:
                    self.__dml = False
                    logger.warning(
                        "DirectML initialization failed; trying another backend: %s",
                        type(exc).__name__,
                    )
            if self.__mps:
                return torch.device("mps")
        return torch.device("cpu")
