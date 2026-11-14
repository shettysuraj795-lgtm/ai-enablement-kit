"""Delete question text from old spans (GR-04 retention). The rest of each span is kept.

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

from governed_analytics.service import Config

DEFAULT_DAYS = 30


def purge_questions(traces: Path, now: dt.datetime, days: int = DEFAULT_DAYS) -> int:
    """Remove `kit.question` from spans that started more than `days` ago. Returns how many."""
    if not traces.exists():
        return 0
    cutoff = now - dt.timedelta(days=days)
    purged, lines = 0, []
    for line in traces.read_text().splitlines():
        span = json.loads(line)
        started = dt.datetime.fromisoformat(span["start_time"].replace("Z", "+00:00"))
        if started < cutoff and "kit.question" in span["attributes"]:
            del span["attributes"]["kit.question"]
            purged += 1
            line = json.dumps(span, ensure_ascii=False, separators=(",", ":"))
        lines.append(line)
    temporary = traces.with_suffix(".tmp")
    temporary.write_text("".join(f"{line}\n" for line in lines))
    os.replace(temporary, traces)  # atomic: a reader never sees a half-written file
    return purged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=int(os.environ.get("KIT_QUESTION_RETENTION_DAYS", DEFAULT_DAYS)))
    args = parser.parse_args()
    traces = Config.from_env().log_dir / "traces.jsonl"
    purged = purge_questions(traces, dt.datetime.now(dt.UTC), args.days)
    print(f"Removed question text from {purged} span(s) older than {args.days} days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
