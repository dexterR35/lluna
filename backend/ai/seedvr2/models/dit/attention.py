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

import os
import warnings

import torch
import torch.nn.functional as F

try:
    from flash_attn import flash_attn_varlen_func
    _FLASH_ATTN_AVAILABLE = True
except ImportError:
    flash_attn_varlen_func = None
    _FLASH_ATTN_AVAILABLE = False

from torch import nn

class TorchAttention(nn.Module):
    def tflops(self, args, kwargs, output) -> float:
        assert len(args) == 0 or len(args) > 2, "query, key should both provided by args / kwargs"
        q = kwargs.get("query") or args[0]
        k = kwargs.get("key") or args[1]
        b, h, sq, d = q.shape
        b, h, sk, d = k.shape
        return b * h * (4 * d * (sq / 1e6) * (sk / 1e6))

    def forward(self, *args, **kwargs):
        return F.scaled_dot_product_attention(*args, **kwargs)


class FlashAttentionVarlen(nn.Module):
    def tflops(self, args, kwargs, output) -> float:
        cu_seqlens_q = kwargs["cu_seqlens_q"]
        cu_seqlens_k = kwargs["cu_seqlens_k"]
        _, h, d = output.shape
        seqlens_q = (cu_seqlens_q[1:] - cu_seqlens_q[:-1]) / 1e6
        seqlens_k = (cu_seqlens_k[1:] - cu_seqlens_k[:-1]) / 1e6
        return h * (4 * d * (seqlens_q * seqlens_k).sum())

    def forward(self, *args, **kwargs):
        kwargs["deterministic"] = torch.are_deterministic_algorithms_enabled()
        return flash_attn_varlen_func(*args, **kwargs)


class PytorchVarlenAttention(nn.Module):
    """SDPA-based fallback for FlashAttentionVarlen.

    flash-attn only publishes prebuilt Linux wheels, so this reimplements the same
    packed-varlen call (q/k/v shaped ``(total_tokens, heads, head_dim)`` plus
    ``cu_seqlens_q/k`` boundaries) on top of ``F.scaled_dot_product_attention``, which
    has no native varlen support: each sample is unpacked via ``cu_seqlens``, run
    through SDPA individually (batch size 1), and the outputs re-concatenated in
    order. This is a drop-in replacement for FlashAttentionVarlen's forward signature.
    """

    def tflops(self, args, kwargs, output) -> float:
        cu_seqlens_q = kwargs["cu_seqlens_q"]
        cu_seqlens_k = kwargs["cu_seqlens_k"]
        _, h, d = output.shape
        seqlens_q = (cu_seqlens_q[1:] - cu_seqlens_q[:-1]) / 1e6
        seqlens_k = (cu_seqlens_k[1:] - cu_seqlens_k[:-1]) / 1e6
        return h * (4 * d * (seqlens_q * seqlens_k).sum())

    def forward(
        self,
        q,
        k,
        v,
        cu_seqlens_q,
        cu_seqlens_k,
        max_seqlen_q=None,
        max_seqlen_k=None,
        dropout_p=0.0,
        causal=False,
        **_ignored,
    ):
        # tensor_split's boundary argument must be a CPU int64 tensor.
        splits_q = torch.tensor_split(q, cu_seqlens_q[1:-1].long().cpu(), dim=0)
        splits_k = torch.tensor_split(k, cu_seqlens_k[1:-1].long().cpu(), dim=0)
        splits_v = torch.tensor_split(v, cu_seqlens_k[1:-1].long().cpu(), dim=0)
        outputs = []
        for q_i, k_i, v_i in zip(splits_q, splits_k, splits_v):
            q_i = q_i.permute(1, 0, 2).unsqueeze(0)
            k_i = k_i.permute(1, 0, 2).unsqueeze(0)
            v_i = v_i.permute(1, 0, 2).unsqueeze(0)
            out_i = F.scaled_dot_product_attention(
                q_i, k_i, v_i, dropout_p=dropout_p, is_causal=causal
            )
            outputs.append(out_i.squeeze(0).permute(1, 0, 2))
        return torch.cat(outputs, dim=0)


_warned_sdpa_fallback = False


def build_varlen_attention() -> nn.Module:
    """Pick the packed-varlen attention backend.

    flash-attn's prebuilt wheels are Linux-only, so this degrades to the SDPA-based
    ``PytorchVarlenAttention`` fallback wherever flash-attn isn't importable. Set
    ``LLUNA_SEEDVR_ATTENTION=sdpa`` to force the fallback even where flash-attn is
    available, or ``=flash`` to require flash-attn and error out if it's missing.
    """
    global _warned_sdpa_fallback
    mode = os.environ.get("LLUNA_SEEDVR_ATTENTION", "auto").strip().lower()
    if mode not in ("auto", "flash", "sdpa"):
        mode = "auto"
    if mode == "flash" and not _FLASH_ATTN_AVAILABLE:
        raise RuntimeError(
            "LLUNA_SEEDVR_ATTENTION=flash was set but flash-attn is not installed."
        )
    use_flash = _FLASH_ATTN_AVAILABLE and mode in ("auto", "flash")
    if use_flash:
        return FlashAttentionVarlen()
    if not _warned_sdpa_fallback:
        warnings.warn(
            "SeedVR2: flash-attn is not available, falling back to a PyTorch SDPA "
            "attention implementation. This is slower but numerically equivalent.",
            stacklevel=2,
        )
        _warned_sdpa_fallback = True
    return PytorchVarlenAttention()