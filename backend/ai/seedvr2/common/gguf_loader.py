# // Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# //
# // Licensed under the Apache License, Version 2.0 (the "License");
# // you may not use this file except in compliance with the License.
# // You may obtain a copy of the License at
# //
# //     http://www.apache.org/licenses/LICENSE-2.0
# //
# // Unless required by applicable law or agreed to in writing, software
# // distributed under the License is distributed on an "AS IS" BASIS,
# // WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# // See the License for the specific language governing permissions and
# // limitations under the License.

"""Loads GGUF-quantized SeedVR2 checkpoints (e.g. Q4_K_M/Q8_0 from
cmeka/SeedVR2-GGUF) into the vendored NaDiT model.

The GGUF files were verified to carry the exact same parameter names as this
model's ``state_dict()`` (no renaming needed) and to only quantize the 2D weight
matrix of each ``nn.Linear``-like layer -- biases, norms, embeddings, and RoPE
frequency buffers stay F16/F32. Quantized layers are replaced with
:class:`GGUFQuantizedLinear`, which keeps the compressed bytes on CPU (as a plain
numpy array, never moved to the GPU) and dequantizes to a full-precision weight
matrix just-in-time on every forward pass, discarding it immediately after. This
is what makes the VRAM saving real: the alternative of eagerly dequantizing
everything once at load time would reproduce the same resident footprint as
loading the original (non-quantized) checkpoint directly, defeating the point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn


def _set_submodule(root: nn.Module, dotted_name: str, new_module: nn.Module) -> None:
    parent_path, _, leaf = dotted_name.rpartition(".")
    parent = root.get_submodule(parent_path) if parent_path else root
    setattr(parent, leaf, new_module)


class GGUFQuantizedLinear(nn.Module):
    """Drop-in replacement for an ``nn.Linear`` whose weight stays GGUF-quantized.

    The quantized weight bytes are kept as a plain (non-tensor) numpy array on
    CPU -- deliberately not a registered buffer/parameter -- so ``nn.Module.to()``
    never moves them to the GPU: ``gguf.quants.dequantize`` only operates on CPU
    numpy arrays, and there is no benefit to a GPU-resident copy of bytes that
    would just be copied back to CPU for every forward pass anyway.
    """

    def __init__(
        self,
        *,
        in_features: int,
        out_features: int,
        has_bias: bool,
        tensor_type,
        orig_shape: tuple[int, ...],
    ) -> None:
        super().__init__()
        self.in_features = in_features
        self.out_features = out_features
        self.tensor_type = tensor_type
        self.orig_shape = tuple(orig_shape)
        self._qweight_np: Optional[np.ndarray] = None
        if has_bias:
            self.bias = nn.Parameter(torch.empty(out_features))
        else:
            self.register_parameter("bias", None)

    def set_raw_weight(self, raw: np.ndarray) -> None:
        # GGUFReader's `.data` is a read-only memmap view; copy it out since the
        # module needs to outlive the reader (and its underlying mmap).
        self._qweight_np = np.ascontiguousarray(raw).copy()

    def _dequantized_weight(self, *, device: torch.device, dtype: torch.dtype) -> torch.Tensor:
        import gguf

        if self._qweight_np is None:
            raise RuntimeError("GGUFQuantizedLinear.forward called before set_raw_weight().")
        array = gguf.quants.dequantize(self._qweight_np, self.tensor_type)
        weight = torch.from_numpy(np.ascontiguousarray(array))
        return weight.reshape(self.orig_shape).to(device=device, dtype=dtype)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        weight = self._dequantized_weight(device=x.device, dtype=x.dtype)
        bias = self.bias.to(device=x.device, dtype=x.dtype) if self.bias is not None else None
        return F.linear(x, weight, bias)


def load_gguf_checkpoint(dit: nn.Module, gguf_path: str | Path) -> None:
    """Load a GGUF checkpoint into ``dit`` in place.

    Quantized 2D weight matrices are swapped to :class:`GGUFQuantizedLinear`
    submodules holding the raw compressed bytes; everything else (biases, norms,
    embeddings, RoPE frequency buffers) is dequantized/converted once and loaded
    as plain tensors via the model's normal ``load_state_dict``.
    """
    import gguf

    reader = gguf.GGUFReader(str(gguf_path))
    tensors = {t.name: t for t in reader.tensors}

    dit_keys = set(dit.state_dict().keys())
    missing_in_file = dit_keys - tensors.keys()
    extra_in_file = tensors.keys() - dit_keys
    if missing_in_file or extra_in_file:
        raise RuntimeError(
            "SeedVR2 GGUF checkpoint does not match this model's architecture "
            f"({len(missing_in_file)} parameter(s) missing from the file, "
            f"{len(extra_in_file)} unexpected tensor(s) in the file) -- this "
            f"checkpoint was not produced for this exact model config: {gguf_path}"
        )

    unquantized = {gguf.GGMLQuantizationType.F32, gguf.GGMLQuantizationType.F16}
    linear_modules = {
        name: module for name, module in dit.named_modules() if isinstance(module, nn.Linear)
    }
    replaced_keys: set[str] = set()
    for name, linear in linear_modules.items():
        weight_key = f"{name}.weight"
        tensor = tensors[weight_key]
        if tensor.tensor_type in unquantized:
            continue
        quant_linear = GGUFQuantizedLinear(
            in_features=linear.in_features,
            out_features=linear.out_features,
            has_bias=linear.bias is not None,
            tensor_type=tensor.tensor_type,
            orig_shape=tuple(linear.weight.shape),
        )
        quant_linear.set_raw_weight(tensor.data)
        _set_submodule(dit, name, quant_linear)
        replaced_keys.add(weight_key)

    state = {}
    for name, tensor in tensors.items():
        if name in replaced_keys:
            continue
        if tensor.tensor_type in unquantized:
            array = tensor.data
        else:
            array = gguf.quants.dequantize(tensor.data, tensor.tensor_type)
        # GGUFReader's `.data` is a read-only memmap view; copy so torch never warns
        # about (or risks) writing through a non-writable buffer.
        state[name] = torch.from_numpy(np.ascontiguousarray(array).copy())

    missing, unexpected = dit.load_state_dict(state, strict=False, assign=True)
    real_missing = [key for key in missing if key not in replaced_keys]
    if real_missing or unexpected:
        raise RuntimeError(
            f"SeedVR2 GGUF load left {len(real_missing)} parameter(s) unset and "
            f"{len(unexpected)} unexpected after loading {gguf_path}: "
            f"missing={real_missing[:5]} unexpected={list(unexpected)[:5]}"
        )
    print(
        f"SeedVR2: loaded GGUF checkpoint ({len(replaced_keys)} quantized layers, "
        f"{len(state)} plain tensors) from {gguf_path}"
    )
