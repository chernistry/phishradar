from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import aiofiles
import aiofiles.os
from anyio import to_thread

from .paths import BUFFER_DIR  # shared buffer dir path


QUEUE_FILE = os.path.join(BUFFER_DIR, "incoming.jsonl")
LOCK_FILE = os.path.join(BUFFER_DIR, ".incoming.lock")


class IngestQueue:
    def __init__(self) -> None:
        os.makedirs(BUFFER_DIR, exist_ok=True)

    async def _lock(self, retries: int = 50, delay: float = 0.02) -> None:
        """Acquire file lock using async operations."""
        for _ in range(retries):
            try:
                # Use thread pool for blocking os.open call
                await to_thread.run_sync(
                    lambda: os.close(os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                )
                return
            except FileExistsError:
                await asyncio.sleep(delay)
        # Best-effort: if lock persists, proceed to avoid deadlock in dev

    async def _unlock(self) -> None:
        """Release file lock using async operations."""
        try:
            await aiofiles.os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    async def push(self, row: dict[str, Any]) -> None:
        """Push item to queue using async file I/O."""
        await self._lock()
        try:
            async with aiofiles.open(QUEUE_FILE, "a", encoding="utf-8") as f:
                await f.write(json.dumps(row, ensure_ascii=False) + "\n")
        finally:
            await self._unlock()

    async def fetch(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch items from queue using async file I/O."""
        await self._lock()
        try:
            lines: list[str] = []
            try:
                async with aiofiles.open(QUEUE_FILE, "r", encoding="utf-8") as f:
                    lines = await f.readlines()
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
                async with aiofiles.open(QUEUE_FILE + ".tmp", "w", encoding="utf-8") as f:
                    await f.writelines(rest_lines)
                await aiofiles.os.replace(QUEUE_FILE + ".tmp", QUEUE_FILE)
            else:
                # Empty queue
                try:
                    await aiofiles.os.remove(QUEUE_FILE)
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
            await self._unlock()
