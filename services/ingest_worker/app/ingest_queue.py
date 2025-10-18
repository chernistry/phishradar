from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from .paths import BUFFER_DIR  # shared buffer dir path


QUEUE_FILE = os.path.join(BUFFER_DIR, "incoming.jsonl")
LOCK_FILE = os.path.join(BUFFER_DIR, ".incoming.lock")


class IngestQueue:
    def __init__(self) -> None:
        os.makedirs(BUFFER_DIR, exist_ok=True)

    async def _lock(self, retries: int = 50, delay: float = 0.02) -> None:
        for _ in range(retries):
            try:
                # Acquire lock by creating a file exclusively
                fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return
            except FileExistsError:
                await asyncio.sleep(delay)
        # Best-effort: if lock persists, proceed to avoid deadlock in dev

    def _unlock(self) -> None:
        try:
            os.unlink(LOCK_FILE)
        except FileNotFoundError:
            pass

    async def push(self, row: dict[str, Any]) -> None:
        await self._lock()
        try:
            with open(QUEUE_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        finally:
            self._unlock()

    async def fetch(self, limit: int = 10) -> list[dict[str, Any]]:
        await self._lock()
        try:
            lines: list[str] = []
            try:
                with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                lines = []

            if not lines:
                return []
            # Pop first N
            to_take = max(0, min(limit, len(lines)))
            take_lines = lines[:to_take]
            rest_lines = lines[to_take:]
            # Rewrite rest
            if rest_lines:
                with open(QUEUE_FILE + ".tmp", "w", encoding="utf-8") as f:
                    f.writelines(rest_lines)
                os.replace(QUEUE_FILE + ".tmp", QUEUE_FILE)
            else:
                # Empty queue
                try:
                    os.remove(QUEUE_FILE)
                except FileNotFoundError:
                    pass
            out: list[dict[str, Any]] = []
            for ln in take_lines:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    continue
            return out
        finally:
            self._unlock()
