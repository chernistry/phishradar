from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from .config import settings
from .retry import net_retry


class SlackError(Exception):
    pass


def _secret_bytes() -> bytes:
    return (settings.slack_signing_secret or "").encode("utf-8")


def _is_fresh(ts: str, tolerance_secs: int = 300) -> bool:
    try:
        req_ts = int(ts)
    except Exception:
        return False
    now = int(time.time())
    return abs(now - req_ts) <= tolerance_secs


def verify_signature(ts: str, sig: str, body: bytes) -> bool:
    if not _is_fresh(ts):
        return False
    base = f"v0:{ts}:{body.decode('utf-8')}".encode("utf-8")
    digest = hmac.new(_secret_bytes(), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, sig)


@net_retry()
async def send_message(text: str, blocks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not settings.slack_bot_token or not settings.slack_channel_id:
        raise SlackError("Slack not configured")
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {settings.slack_bot_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    payload: dict[str, Any] = {
        "channel": settings.slack_channel_id,
        "text": text,
    }
    if blocks:
        payload["blocks"] = blocks
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise SlackError(str(data))
        return data


async def respond(response_url: str, text: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(response_url, json={"text": text, "replace_original": False})


def action_blocks(url: str, title: str, similarity: float) -> list[dict[str, Any]]:
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*PhishRadar alert*\n<{url}|{title}>\nSimilarity: {similarity:.2f}",
            },
        },
        {
            "type": "actions",
            "block_id": "phishradar_actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": "phishradar_approve",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "value": json.dumps({"action": "approve", "url": url}),
                },
                {
                    "type": "button",
                    "action_id": "phishradar_reject",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "value": json.dumps({"action": "reject", "url": url}),
                },
            ],
        },
    ]


# --- Optional: Socket Mode support (no public URL needed) ---
_socket_mode_client = None  # type: ignore[var-annotated]


async def start_socket_mode() -> None:
    """Start Slack Socket Mode listener if app-level token is present.

    Requires:
    - settings.slack_app_level_token (xapp-...)
    - settings.slack_bot_token (xoxb-...)
    """
    global _socket_mode_client
    if not settings.slack_app_level_token or not settings.slack_bot_token:
        return
    try:
        from slack_sdk.socket_mode.aiohttp import SocketModeClient
        from slack_sdk.socket_mode.request import SocketModeRequest
        from slack_sdk.socket_mode.response import SocketModeResponse
        from slack_sdk.web.async_client import AsyncWebClient
    except Exception:
        return

    web = AsyncWebClient(token=settings.slack_bot_token)
    client = SocketModeClient(app_token=settings.slack_app_level_token, web_client=web)

    @client.socket_mode_request_listeners.append  # type: ignore[attr-defined]
    async def handle(req: "SocketModeRequest"):  # noqa: F821
        try:
            # Ack ASAP
            await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        except Exception:
            pass
        try:
            if req.type == "interactive":
                payload = req.payload  # interactive payload dict
                action = (payload.get("actions") or [{}])[0]
                val = action.get("value")
                parsed = json.loads(val) if val else {}
                resp_url = payload.get("response_url")
                user = (payload.get("user") or {}).get("username") or (payload.get("user") or {}).get("id")
                # Optional quick ack to response_url
                if resp_url:
                    try:
                        await respond(resp_url, f"Thanks <@{user}>. Action received.")
                    except Exception:
                        pass
        except Exception:
            pass

    await client.connect()
    try:
        # Small log to indicate connection established
        await web.api_call("auth.test")
    except Exception:
        pass
    _socket_mode_client = client


async def stop_socket_mode() -> None:
    global _socket_mode_client
    client = _socket_mode_client
    if client is not None:
        try:
            await client.close()  # type: ignore[attr-defined]
        except Exception:
            pass
        _socket_mode_client = None
