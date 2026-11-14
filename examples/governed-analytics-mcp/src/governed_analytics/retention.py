"""Delete question text from old spans and certification requests (GR-04 retention).

Only the free-text field goes; the rest of each record is kept. The server
runs `purge_all` at start-up and every `purge_interval_seconds` while it runs;
this command does the same on demand.

    python -m governed_analytics.retention              # default: 30 days
    python -m governed_analytics.retention --days 7
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from governed_analytics.receipts import WRITE_LOCK
from governed_analytics.service import Config

DEFAULT_DAYS = 30


def purge_all(log_dir: Path, now: dt.datetime, days: int = DEFAULT_DAYS) -> tuple[int, int]:
    """Purge both logs. Returns (spans, certification requests) purged."""
    return (
        purge_questions(log_dir / "traces.jsonl", now, days),
        purge_request_shapes(log_dir / "certification_requests.jsonl", now, days),
    )


def purge_questions(traces: Path, now: dt.datetime, days: int = DEFAULT_DAYS) -> int:
    """Remove `kit.question` from spans that started more than `days` ago. Returns how many."""
    return _purge(traces, now, days, "start_time", lambda span: span["attributes"], "kit.question")


def purge_request_shapes(requests: Path, now: dt.datetime, days: int = DEFAULT_DAYS) -> int:
    """Remove `question_shape` from certification requests older than `days`. Returns how many."""
    return _purge(requests, now, days, "created_at", lambda request: request, "question_shape")


def _purge(path: Path, now: dt.datetime, days: int, time_field: str, holder, field: str) -> int:
    with WRITE_LOCK:  # no append can land between the read and the replace
        return _purge_locked(path, now, days, time_field, holder, field)


def _purge_locked(path: Path, now: dt.datetime, days: int, time_field: str, holder, field: str) -> int:
    if not path.exists():
        return 0
    cutoff = now - dt.timedelta(days=days)
    purged, lines = 0, []
    for line in path.read_text().splitlines():
        record = json.loads(line)
        created = dt.datetime.fromisoformat(record[time_field].replace("Z", "+00:00"))
        if created < cutoff and field in holder(record):
            del holder(record)[field]
            purged += 1
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        lines.append(line)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(f"{line}\n" for line in lines))
    os.replace(temporary, path)  # atomic: a reader never sees a half-written file
    return purged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    config = Config.from_env()
    parser.add_argument("--days", type=int, default=config.retention_days)
    args = parser.parse_args()
    spans, requests = purge_all(config.log_dir, dt.datetime.now(dt.UTC), args.days)
    print(f"Removed question text from {spans} span(s) and {requests} certification request(s) older than {args.days} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
