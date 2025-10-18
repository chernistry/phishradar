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
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "value": json.dumps({"action": "approve", "url": url}),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "style": "danger",
                    "value": json.dumps({"action": "reject", "url": url}),
                },
            ],
        },
    ]

