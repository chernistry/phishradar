from __future__ import annotations

import os as _os

# Shared buffer directory (can be overridden via env BUFFER_DIR)
# Default to a local relative path for test/dev; container can set /app/buffer via env.
BUFFER_DIR = _os.getenv("BUFFER_DIR", "./buffer")
