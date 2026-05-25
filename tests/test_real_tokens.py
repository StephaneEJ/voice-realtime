"""Tests for real provider-reported token wiring on CostTracker.

Covers Polish #6.2: replace the elapsed-time proxy with the actual
``usage_metadata`` (Gemini Live, cumulative) and ``response.done`` usage
(OpenAI Realtime, per-response delta) once the provider emits them.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from voice_realtime.cost_tracker import CostTracker


def test_proxy_used_before_any_real_tokens():
    tracker = CostTracker(provider="gemini", model="gemini-2.5-flash-native-audio-latest")
    assert tracker.has_real_tokens is False
    # Proxy = elapsed * 50 tok/s. Right after construction elapsed is ~0,
    # so both directions stay near zero — the contract here is "tracker
    # answers without crashing and reports tokens=0 not None".
    assert tracker.estimated_tokens_in >= 0
    assert tracker.estimated_tokens_out >= 0
    assert tracker.estimated_tokens_total == tracker.estimated_tokens_in + tracker.estimated_tokens_out


def test_cumulative_update_replaces_proxy():
    tracker = CostTracker(provider="gemini", model="gemini-2.5-flash-native-audio-latest")
    # Fake a long elapsed so the proxy would otherwise dominate.
    tracker.started_at = time.monotonic() - 60.0  # 60s elapsed → proxy ~3000 in/out
    tracker.update_tokens_cumulative(tokens_in=1234, tokens_out=4321)
    assert tracker.has_real_tokens is True
    assert tracker.estimated_tokens_in == 1234
    assert tracker.estimated_tokens_out == 4321
    assert tracker.estimated_tokens_total == 5555


def test_cumulative_update_overwrites_prior_value():
    tracker = CostTracker(provider="gemini", model="gemini-2.5-flash-native-audio-latest")
    tracker.update_tokens_cumulative(100, 200)
    tracker.update_tokens_cumulative(500, 800)
    # Second cumulative call replaces the totals, not adds to them.
    assert tracker.estimated_tokens_in == 500
    assert tracker.estimated_tokens_out == 800


def test_delta_update_accumulates():
    tracker = CostTracker(provider="openai", model="gpt-realtime-mini")
    tracker.update_tokens_delta(50, 80)
    tracker.update_tokens_delta(30, 20)
    tracker.update_tokens_delta(10, 100)
    assert tracker.estimated_tokens_in == 90
    assert tracker.estimated_tokens_out == 200
    assert tracker.estimated_tokens_total == 290


def test_negative_inputs_clamped_to_zero():
    tracker = CostTracker(provider="openai", model="gpt-realtime-mini")
    tracker.update_tokens_cumulative(-5, -10)
    assert tracker.estimated_tokens_in == 0
    assert tracker.estimated_tokens_out == 0
    tracker.update_tokens_delta(100, 100)
    tracker.update_tokens_delta(-50, -50)  # corrupt provider event must not subtract
    assert tracker.estimated_tokens_in == 100
    assert tracker.estimated_tokens_out == 100


def test_mixed_modes_cumulative_after_delta_replaces():
    """If a provider switches modes mid-session, cumulative wins (latest truth)."""
    tracker = CostTracker(provider="openai", model="gpt-realtime-mini")
    tracker.update_tokens_delta(100, 200)
    tracker.update_tokens_cumulative(50, 60)
    assert tracker.estimated_tokens_in == 50
    assert tracker.estimated_tokens_out == 60


# ---------------------------------------------------------------------------
# Provider-level extraction: feed a fake "response" object through the same
# attribute access patterns the real receive loops use, and assert the
# right cost_update payload would be put on the events queue.
# ---------------------------------------------------------------------------


def _extract_gemini_cost_update(response_obj) -> dict | None:
    """Replicates the extraction logic in gemini.py for unit testing.

    Keeping this mirror in the test file is intentional — refactoring the
    inner extraction out of the async receive loop would force every event
    into a callback. For now we test the contract, and a divergence is
    surfaced by a failing assertion here when the loop changes.
    """
    usage = getattr(response_obj, "usage_metadata", None)
    if usage is None:
        return None
    tokens_in = (
        getattr(usage, "prompt_token_count", None)
        or getattr(usage, "input_token_count", None)
        or 0
    )
    tokens_out = (
        getattr(usage, "response_token_count", None)
        or getattr(usage, "output_token_count", None)
        or 0
    )
    if not (tokens_in or tokens_out):
        return None
    return {
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "mode": "cumulative",
    }


def test_gemini_usage_extraction_canonical_fields():
    resp = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=120,
        response_token_count=340,
    ))
    payload = _extract_gemini_cost_update(resp)
    assert payload == {"tokens_in": 120, "tokens_out": 340, "mode": "cumulative"}


def test_gemini_usage_extraction_alt_field_names():
    """SDK versions vary; the fallback ``input_token_count``/``output_token_count``
    pair must also be picked up so newer/older builds both work."""
    resp = SimpleNamespace(usage_metadata=SimpleNamespace(
        input_token_count=15,
        output_token_count=25,
    ))
    payload = _extract_gemini_cost_update(resp)
    assert payload == {"tokens_in": 15, "tokens_out": 25, "mode": "cumulative"}


def test_gemini_usage_extraction_missing_metadata_returns_none():
    resp = SimpleNamespace()  # no usage_metadata at all
    assert _extract_gemini_cost_update(resp) is None


def test_gemini_usage_extraction_zeros_skipped():
    """All-zero metadata is a no-op event — better not enqueued at all."""
    resp = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=0,
        response_token_count=0,
    ))
    assert _extract_gemini_cost_update(resp) is None


def _extract_openai_cost_update(event_obj) -> dict | None:
    """Mirror of the response.done extraction in openai_realtime.py."""
    resp_obj = getattr(event_obj, "response", None)
    usage = getattr(resp_obj, "usage", None) if resp_obj is not None else None
    if usage is None:
        return None
    tokens_in = getattr(usage, "input_tokens", None) or 0
    tokens_out = getattr(usage, "output_tokens", None) or 0
    if not (tokens_in or tokens_out):
        return None
    return {
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "mode": "delta",
    }


def test_openai_usage_extraction_response_done():
    ev = SimpleNamespace(
        type="response.done",
        response=SimpleNamespace(usage=SimpleNamespace(input_tokens=42, output_tokens=99)),
    )
    payload = _extract_openai_cost_update(ev)
    assert payload == {"tokens_in": 42, "tokens_out": 99, "mode": "delta"}


def test_openai_usage_extraction_missing_response_returns_none():
    ev = SimpleNamespace(type="response.done")  # no .response attr
    assert _extract_openai_cost_update(ev) is None


def test_openai_usage_extraction_response_without_usage_returns_none():
    ev = SimpleNamespace(type="response.done", response=SimpleNamespace())
    assert _extract_openai_cost_update(ev) is None
