"""Ask-before-acting helpers for the tool confirmation gate.

The CLI's talk loop opens a per-session ``pending`` dict mapping ``call_id``
to an ``asyncio.Future[bool]``. When a tool is gated, the dispatcher calls
``request_confirmation`` to emit a ``tool.confirm_request`` event over the
attached UI channel and await the matching reply. The UI command handler
calls ``resolve_confirmation`` (with approve=True/False) on each
``tool.confirm_reply`` it receives, releasing the awaiting future.

These helpers are extracted out of ``cli.py`` so the gate flow can be
exercised in pytest without spinning up sounddevice, WebSockets, or a real
provider.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol


class _Attached(Protocol):
    async def emit(self, msg: dict[str, Any]) -> None: ...


async def request_confirmation(
    attached: _Attached,
    pending: dict[str, asyncio.Future[bool]],
    *,
    call_id: str,
    name: str,
    args: dict[str, Any],
    timeout: float = 60.0,
) -> bool:
    """Emit ``tool.confirm_request`` and wait for the matching reply.

    Returns True on user approval, False on denial or timeout. The future is
    always removed from ``pending`` before returning (cleanup on any path).
    """
    loop = asyncio.get_event_loop()
    fut: asyncio.Future[bool] = loop.create_future()
    pending[call_id] = fut
    await attached.emit({
        "ev": "tool.confirm_request",
        "callId": call_id,
        "name": name,
        "args": args,
        "ts": int(time.time() * 1000),
    })
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return False
    finally:
        pending.pop(call_id, None)


def resolve_confirmation(
    pending: dict[str, asyncio.Future[bool]],
    *,
    call_id: str,
    approve: bool,
) -> bool:
    """Resolve a pending confirmation future from a ``tool.confirm_reply``.

    Returns True when a matching un-settled future was found and resolved;
    False when no such ``call_id`` exists or the future is already done
    (caller can log a stale-reply warning).
    """
    fut = pending.get(call_id)
    if fut is None or fut.done():
        return False
    fut.set_result(approve)
    return True
