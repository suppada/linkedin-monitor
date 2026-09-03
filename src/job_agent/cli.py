from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .emailer import send_gmail
from .intelligence import JobRelevanceAI
from .sources import collect
from .state import State


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI agent for new DevOps job alerts")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--state", default="data/job-agent.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    training = Path(__file__).parent / "data" / "training.json"
    model = JobRelevanceAI(training)
    jobs, errors = collect(config)
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = State(state_path)
    matches = []
    for job in jobs:
        if state.is_seen(job.identity):
            continue
        match = model.evaluate(job, config["preferences"])
        if match:
            matches.append(match)
    matches.sort(key=lambda match: match.score, reverse=True)
    print(json.dumps({"scanned": len(jobs), "new_matches": len(matches), "errors": errors}, indent=2))
    for match in matches:
        print(f"{match.score:5.1f} {match.job.company}: {match.job.title} — {match.job.url}")
    if matches and not args.dry_run:
        sender = required("GMAIL_ADDRESS")
        send_gmail(sender, required("GMAIL_APP_PASSWORD"), os.getenv("GMAIL_TO", sender), matches)
    if not args.dry_run:
        state.mark_seen([job.identity for job in jobs])
    return 0


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())

