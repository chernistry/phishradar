#!/usr/bin/env python3
import argparse
import os
import shlex
import subprocess
import sys


def main() -> None:
    ap = argparse.ArgumentParser(description="Load buffered events JSONL into BigQuery events_raw")
    ap.add_argument("buffer", nargs="?", default="buffer/events.jsonl", help="Path to JSONL buffer file")
    ns = ap.parse_args()

    dataset = os.environ.get("BQ_DATASET", "pradar")
    project = os.environ.get("GCP_PROJECT_ID")
    if not project:
        print("GCP_PROJECT_ID not set", file=sys.stderr)
        sys.exit(2)

    table = f"{project}.{dataset}.events_raw"
    cmd = [
        "bq",
        "load",
        "--source_format=NEWLINE_DELIMITED_JSON",
        table,
        ns.buffer,
    ]
    print("Running:", " ".join(shlex.quote(c) for c in cmd))
    subprocess.check_call(cmd)
    print("Loaded", ns.buffer, "into", table)


if __name__ == "__main__":
    main()

