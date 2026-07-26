import traceback
import importlib.util

import torch

from backend.config import tr

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
        self.__onnx_providers = []
        self.__enabled = True
        self.__device = None

    def initialize(self):
        self.check_directml_available()
        self.check_cuda_available()
        self.check_mps_available()
        self.load_onnx_providers()

    def check_directml_available(self):
        self.__dml = importlib.util.find_spec("torch_directml")

    def check_cuda_available(self):
        self.__cuda = torch.cuda.is_available()

    def check_mps_available(self):
        self.__mps = torch.backends.mps.is_available() and torch.backends.mps.is_built()

    def load_onnx_providers(self):
        try:
            import onnxruntime as ort
            available_providers = ort.get_available_providers()
            for provider in available_providers:
                if provider in [
                    "CPUExecutionProvider"
                ]:
                    continue
                if provider not in [
                    "DmlExecutionProvider",         # DirectML, for Windows GPU
                    "ROCMExecutionProvider",        # AMD ROCm
                    "MIGraphXExecutionProvider",    # AMD MIGraphX
                    "VitisAIExecutionProvider",     # AMD VitisAI, for RyzenAI & Windows; performance similar to DirectML in practice
                    "OpenVINOExecutionProvider",    # Intel GPU
                    "MetalExecutionProvider",       # Apple macOS
                    "CoreMLExecutionProvider",      # Apple macOS
                    "CUDAExecutionProvider",        # Nvidia GPU
                ]:
                    print(tr['Main']['OnnxExecutionProviderNotSupportedSkipped'].format(provider))
                    continue
                print(tr['Main']['OnnxExecutionProviderDetected'].format(provider))
                self.__onnx_providers.append(provider)
        except ModuleNotFoundError as e:
            print(tr['Main']['OnnxRuntimeNotInstall'])

    def has_accelerator(self):
        if not self.__enabled:
            return False
        return self.__cuda or self.__dml or self.__mps or len(self.__onnx_providers) > 0

    @property
    def accelerator_name(self):
        if not self.__enabled:
            return "CPU"
        if self.__dml:
            return "DirectML"
        if self.__cuda:
            return "GPU"
        if self.__mps:
            return "MPS"
        elif len(self.__onnx_providers) > 0:
            return ", ".join(self.__onnx_providers)
        else:
            return "CPU"

    @property
    def onnx_providers(self):
        if not self.__enabled:
            return ["CPUExecutionProvider"]
        # GPU search skips CPU; always keep it as the fallback provider.
        providers = list(self.__onnx_providers)
        if "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")
        return providers

    def get_onnx_execution_providers(self):
        """
        Ordered ONNX Runtime providers for InferenceSession (CUDA first when available).
        Always ends with CPUExecutionProvider as fallback.
        """
        if not self.__enabled:
            return ["CPUExecutionProvider"]
        providers = []
        # Prefer CUDA when both Torch and ORT report it (rembg / OCR)
        try:
            import onnxruntime as ort
            available = set(ort.get_available_providers())
        except ModuleNotFoundError:
            return ["CPUExecutionProvider"]

        preferred = [
            "CUDAExecutionProvider",
            "ROCMExecutionProvider",
            "MIGraphXExecutionProvider",
            "DmlExecutionProvider",
            "VitisAIExecutionProvider",
            "MetalExecutionProvider",
            "CoreMLExecutionProvider",
            "OpenVINOExecutionProvider",
        ]
        for name in preferred:
            if name in available and name not in providers:
                # Only enable CUDA/ROCM providers when Torch also sees a matching accelerator,
                # matching the rest of the app's "check CUDA first" policy.
                if name == "CUDAExecutionProvider" and not self.__cuda:
                    continue
                if name in ("ROCMExecutionProvider", "MIGraphXExecutionProvider") and not self.__cuda:
                    # ROCm often shows up similarly; keep if ORT has it and HW accel is on
                    pass
                providers.append(name)

        # Any other detected accelerators from initialize()
        for name in self.__onnx_providers:
            if name not in providers and name in available:
                providers.append(name)

        if "CPUExecutionProvider" not in providers:
            providers.append("CPUExecutionProvider")
        return providers or ["CPUExecutionProvider"]

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
        """
        onnxruntime-directml 1.21.1-1.22.0 (higher not tested) and torch-directml cannot be
        initialized at the same time; they interfere with each other.
        Error from site-packages/onnxruntime/capi/onnxruntime_inference_collection.py", line 266, in run
                return self._sess.run(output_names, input_feed, run_options)
                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
            UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb2 in position 344: invalid start bn 344: invalid start byte
        onnxruntime-directml 1.21.1 works, but fails on Win10 and works on Win11.
        To avoid conflicts and rewriting a QPT smart deploy flow, use lazy init and keep
        onnxruntime-directml 1.20.1.
        Running SubtitleDetect in a separate process is also a valid approach.
        """
        if self.__enabled:
            if self.__dml:
                try:
                    import torch_directml
                    return torch_directml.device(torch_directml.default_device())
                    self.__dml = True
                except:
                    traceback.print_exc()
                    self.__dml = False
            if self.__cuda:
                return torch.device("cuda:0")
            if self.__mps:
                return torch.device("mps")
        return torch.device("cpu")
