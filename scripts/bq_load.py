#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Load buffered events JSONL into BigQuery events_raw")
    ap.add_argument("buffer", nargs="?", default="buffer/events.jsonl", help="Path to JSONL buffer file")
    ns = ap.parse_args()

    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    dataset = os.environ.get("BQ_DATASET", "pradar")
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        print("GCP_PROJECT_ID not set", file=sys.stderr)
        sys.exit(2)

    # Filter valid events (must have 'url' field)
    valid_count = 0
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
        tmp_path = tmp.name
        with open(ns.buffer) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if "url" in obj:
                        tmp.write(line)
                        valid_count += 1
                except json.JSONDecodeError:
                    continue

    if valid_count == 0:
        print(f"No valid events found in {ns.buffer}", file=sys.stderr)
        os.unlink(tmp_path)
        sys.exit(0)

    table = f"{project}:{dataset}.events_raw"
    cmd = ["bq", "load", "--source_format=NEWLINE_DELIMITED_JSON", table, tmp_path]
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    try:
        subprocess.check_call(cmd)
        print(f"Loaded {valid_count} events into {table}")
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()

