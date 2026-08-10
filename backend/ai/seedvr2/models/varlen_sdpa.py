"""Pure-PyTorch stand-in for ``flash_attn.flash_attn_varlen_func``.

Added by Lluna, not part of the upstream SeedVR2 source.

flash-attn ships no wheels on PyPI and publishes prebuilt wheels for Linux only,
so `pip install flash_attn` compiles CUDA kernels on the user's machine. When no
wheel is available for the platform, the vendored attention modules import this
implementation instead: identical maths on torch's fused
``scaled_dot_product_attention``, at the cost of the packed-sequence kernel.

The varlen convention is unchanged. ``q`` is ``(total_q, heads, head_dim)`` with
the batch's sequences concatenated along dim 0, and ``cu_seqlens_q`` holds the
cumulative offsets, so sequence ``i`` occupies ``q[cu_seqlens_q[i]:cu_seqlens_q[i + 1]]``.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F


def flash_attn_varlen_func(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    cu_seqlens_q: torch.Tensor,
    cu_seqlens_k: torch.Tensor,
    max_seqlen_q: int | None = None,
    max_seqlen_k: int | None = None,
    dropout_p: float = 0.0,
    softmax_scale: float | None = None,
    causal: bool = False,
    **_unsupported: object,
) -> torch.Tensor:
    """Attention over concatenated variable-length sequences.

    Ignores flash-attn-only options (``window_size``, ``alibi_slopes``,
    ``deterministic``, ``return_attn_probs``); SeedVR2 never sets them to
    non-default values.
    """
    # One host sync for the whole call: the offsets drive Python-level slicing,
    # which is the price of not having the packed kernel.
    offsets_q = cu_seqlens_q.tolist()
    offsets_k = cu_seqlens_k.tolist()
    if len(offsets_q) != len(offsets_k):
        raise ValueError("cu_seqlens_q and cu_seqlens_k must describe the same batch")

    heads_q, heads_k = q.shape[1], k.shape[1]
    if heads_q % heads_k:
        raise ValueError(f"{heads_q} query heads is not a multiple of {heads_k} key/value heads")
    repeats = heads_q // heads_k

    outputs: list[torch.Tensor] = []
    for index in range(len(offsets_q) - 1):
        q_start, q_end = offsets_q[index], offsets_q[index + 1]
        k_start, k_end = offsets_k[index], offsets_k[index + 1]
        if q_end == q_start:
            outputs.append(q[q_start:q_end])
            continue
        # (seq, heads, dim) -> (1, heads, seq, dim), the layout SDPA expects.
        query = q[q_start:q_end].transpose(0, 1).unsqueeze(0)
        key = k[k_start:k_end].transpose(0, 1).unsqueeze(0)
        value = v[k_start:k_end].transpose(0, 1).unsqueeze(0)
        if repeats > 1:  # grouped/multi-query attention
            key = key.repeat_interleave(repeats, dim=1)
            value = value.repeat_interleave(repeats, dim=1)
        attended = F.scaled_dot_product_attention(
            query,
            key,
            value,
            dropout_p=dropout_p,
            is_causal=causal,
            scale=softmax_scale,
        )
        outputs.append(attended.squeeze(0).transpose(0, 1))
    return torch.cat(outputs, dim=0)
