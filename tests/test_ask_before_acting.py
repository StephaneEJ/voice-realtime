"""Unit tests for the ask-before-acting confirmation gate.

Covers ``voice_realtime.tool_confirm.request_confirmation`` (the gate flow)
and ``resolve_confirmation`` (the UI reply handler that releases the awaiting
future). The CLI's full ``_dispatch_tool_call`` is exercised indirectly via
these primitives so we don't need to spin up sounddevice or a real provider.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from voice_realtime.tool_confirm import request_confirmation, resolve_confirmation


class FakeAttached:
    """Minimal stub matching the ``_Attached`` Protocol."""

    def __init__(self) -> None:
        self.emitted: list[dict[str, Any]] = []

    async def emit(self, msg: dict[str, Any]) -> None:
        self.emitted.append(msg)


@pytest.mark.asyncio
async def test_request_confirmation_returns_true_on_approve():
    attached = FakeAttached()
    pending: dict[str, asyncio.Future[bool]] = {}

    async def reply_after_emit() -> None:
        # Wait until the gate has registered the future, then resolve it.
        while "c1" not in pending:
            await asyncio.sleep(0)
        ok = resolve_confirmation(pending, call_id="c1", approve=True)
        assert ok

    asyncio.create_task(reply_after_emit())
    result = await request_confirmation(
        attached, pending,
        call_id="c1", name="vault_write", args={"path": "x"},
        timeout=2.0,
    )
    assert result is True
    assert pending == {}, "future must be cleaned up after resolution"
    assert len(attached.emitted) == 1
    msg = attached.emitted[0]
    assert msg["ev"] == "tool.confirm_request"
    assert msg["callId"] == "c1"
    assert msg["name"] == "vault_write"
    assert msg["args"] == {"path": "x"}


@pytest.mark.asyncio
async def test_request_confirmation_returns_false_on_deny():
    attached = FakeAttached()
    pending: dict[str, asyncio.Future[bool]] = {}

    async def reply_after_emit() -> None:
        while "c2" not in pending:
            await asyncio.sleep(0)
        resolve_confirmation(pending, call_id="c2", approve=False)

    asyncio.create_task(reply_after_emit())
    result = await request_confirmation(
        attached, pending,
        call_id="c2", name="vault_write", args={},
        timeout=2.0,
    )
    assert result is False
    assert pending == {}


@pytest.mark.asyncio
async def test_request_confirmation_times_out_to_false():
    attached = FakeAttached()
    pending: dict[str, asyncio.Future[bool]] = {}

    result = await request_confirmation(
        attached, pending,
        call_id="c3", name="vault_write", args={},
        timeout=0.05,
    )
    assert result is False
    assert pending == {}, "future must be cleaned even on timeout"
    assert len(attached.emitted) == 1


def test_resolve_confirmation_unknown_call_id_returns_false():
    pending: dict[str, asyncio.Future[bool]] = {}
    ok = resolve_confirmation(pending, call_id="ghost", approve=True)
    assert ok is False


@pytest.mark.asyncio
async def test_resolve_confirmation_already_settled_returns_false():
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[bool] = loop.create_future()
    fut.set_result(True)
    pending: dict[str, asyncio.Future[bool]] = {"c4": fut}
    ok = resolve_confirmation(pending, call_id="c4", approve=False)
    assert ok is False
    # The settled value should remain True — second resolve must NOT override.
    assert fut.result() is True


@pytest.mark.asyncio
async def test_concurrent_confirmations_are_independent():
    """Two simultaneous gates should resolve independently by call_id."""
    attached = FakeAttached()
    pending: dict[str, asyncio.Future[bool]] = {}

    async def gate(call_id: str) -> bool:
        return await request_confirmation(
            attached, pending,
            call_id=call_id, name="vault_write", args={},
            timeout=2.0,
        )

    async def resolver() -> None:
        while "cA" not in pending or "cB" not in pending:
            await asyncio.sleep(0)
        resolve_confirmation(pending, call_id="cA", approve=True)
        resolve_confirmation(pending, call_id="cB", approve=False)

    asyncio.create_task(resolver())
    a, b = await asyncio.gather(gate("cA"), gate("cB"))
    assert a is True
    assert b is False
    assert pending == {}
