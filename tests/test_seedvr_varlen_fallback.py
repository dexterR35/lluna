"""The pure-torch stand-in used when no flash-attn wheel exists for the platform."""

from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")

from backend.ai.seedvr2.models.varlen_sdpa import flash_attn_varlen_func  # noqa: E402


def _reference(q, k, v, cu_seqlens_q, cu_seqlens_k):
    """Textbook softmax(QK^T / sqrt(d))V, one sequence at a time."""
    outputs = []
    for index in range(len(cu_seqlens_q) - 1):
        qs, qe = int(cu_seqlens_q[index]), int(cu_seqlens_q[index + 1])
        ks, ke = int(cu_seqlens_k[index]), int(cu_seqlens_k[index + 1])
        query = q[qs:qe].transpose(0, 1)  # (heads, seq_q, dim)
        key = k[ks:ke].transpose(0, 1)
        value = v[ks:ke].transpose(0, 1)
        if key.shape[0] != query.shape[0]:
            repeats = query.shape[0] // key.shape[0]
            key = key.repeat_interleave(repeats, dim=0)
            value = value.repeat_interleave(repeats, dim=0)
        scores = query @ key.transpose(-1, -2) / math.sqrt(query.shape[-1])
        outputs.append((scores.softmax(dim=-1) @ value).transpose(0, 1))
    return torch.cat(outputs, dim=0)


def _packed(lengths, heads, dim, generator):
    total = sum(lengths)
    shape = (total, heads, dim)
    return torch.randn(shape, generator=generator, dtype=torch.float64)


@pytest.mark.parametrize("lengths", [[4], [3, 7], [5, 1, 9], [2, 2, 2, 2]])
def test_matches_reference_attention(lengths):
    generator = torch.Generator().manual_seed(11)
    heads, dim = 4, 8
    q = _packed(lengths, heads, dim, generator)
    k = _packed(lengths, heads, dim, generator)
    v = _packed(lengths, heads, dim, generator)
    offsets = torch.tensor([0, *torch.tensor(lengths).cumsum(0).tolist()], dtype=torch.int32)

    result = flash_attn_varlen_func(
        q, k, v, offsets, offsets, max_seqlen_q=max(lengths), max_seqlen_k=max(lengths)
    )

    assert result.shape == q.shape
    torch.testing.assert_close(result, _reference(q, k, v, offsets, offsets))


def test_sequences_do_not_leak_into_each_other():
    """The whole point of varlen packing: sequence 0 must not attend to sequence 1."""
    generator = torch.Generator().manual_seed(3)
    lengths = [4, 6]
    q = _packed(lengths, 2, 8, generator)
    k = _packed(lengths, 2, 8, generator)
    v = _packed(lengths, 2, 8, generator)
    offsets = torch.tensor([0, 4, 10], dtype=torch.int32)

    packed = flash_attn_varlen_func(q, k, v, offsets, offsets)
    alone = flash_attn_varlen_func(
        q[:4], k[:4], v[:4], torch.tensor([0, 4], dtype=torch.int32), torch.tensor([0, 4], dtype=torch.int32)
    )

    torch.testing.assert_close(packed[:4], alone)


def test_grouped_query_attention_repeats_kv_heads():
    generator = torch.Generator().manual_seed(5)
    lengths = [3, 5]
    q = _packed(lengths, 8, 4, generator)
    k = _packed(lengths, 2, 4, generator)
    v = _packed(lengths, 2, 4, generator)
    offsets = torch.tensor([0, 3, 8], dtype=torch.int32)

    result = flash_attn_varlen_func(q, k, v, offsets, offsets)

    assert result.shape == q.shape
    torch.testing.assert_close(result, _reference(q, k, v, offsets, offsets))


def test_rejects_head_counts_that_do_not_divide():
    generator = torch.Generator().manual_seed(7)
    q = _packed([4], 6, 4, generator)
    k = _packed([4], 4, 4, generator)
    offsets = torch.tensor([0, 4], dtype=torch.int32)

    with pytest.raises(ValueError, match="not a multiple"):
        flash_attn_varlen_func(q, k, k, offsets, offsets)


def test_empty_sequence_keeps_output_aligned():
    generator = torch.Generator().manual_seed(13)
    q = _packed([3, 0, 2], 2, 4, generator)
    offsets = torch.tensor([0, 3, 3, 5], dtype=torch.int32)

    result = flash_attn_varlen_func(q, q, q, offsets, offsets)

    assert result.shape == q.shape
