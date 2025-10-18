from __future__ import annotations

import os as _os

# Shared buffer directory (can be overridden via env BUFFER_DIR)
BUFFER_DIR = _os.getenv("BUFFER_DIR", "/app/buffer")

