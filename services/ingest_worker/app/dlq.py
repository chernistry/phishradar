from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .paths import BUFFER_DIR


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_dlq(op: str, payload: dict[str, Any], reason: str) -> None:
    """Append a DLQ entry for failed side-effects.

    Structure: {op, payload, reason, ts}
    """
    dlq_dir = os.path.join(BUFFER_DIR, "dlq")
    _ensure_dir(dlq_dir)
    line = {
        "op": op,
        "payload": payload,
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    path = os.path.join(dlq_dir, f"{op}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")

