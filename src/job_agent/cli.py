from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from .emailer import send_gmail
from .intelligence import JobRelevanceAI
from .resume_matcher import ResumeMatcher
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
    profile_path = config.get("resume_profile")
    resume_matcher = ResumeMatcher(profile_path) if profile_path else None
    jobs, errors = collect(config)
    source_counts = Counter(job.source for job in jobs)
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = State(state_path)
    matches = []
    unseen = 0
    rejected = 0
    duplicate_postings = 0
    posting_keys: set[tuple[str, str]] = set()
    for job in jobs:
        if state.is_seen(job.identity):
            continue
        unseen += 1
        posting_key = (job.company.casefold().strip(), job.title.casefold().strip())
        if posting_key in posting_keys:
            duplicate_postings += 1
            continue
        posting_keys.add(posting_key)
        match = model.evaluate(job, config["preferences"])
        if match:
            if resume_matcher:
                resume = resume_matcher.evaluate(job)
                match = type(match)(
                    match.job, match.score, match.ai_probability, match.sponsorship, match.reasons,
                    resume.score, resume.level, resume.matched_skills, resume.missing_skills,
                )
            matches.append(match)
        else:
            rejected += 1
    matches.sort(key=lambda match: match.score, reverse=True)
    max_results = int(config.get("notifications", {}).get("max_jobs_per_email", 30))
    matches = matches[:max_results]
    print(json.dumps({
        "scanned": len(jobs),
        "by_source": dict(sorted(source_counts.items())),
        "unseen": unseen,
        "rejected_by_preferences": rejected,
        "duplicate_postings": duplicate_postings,
        "new_matches": len(matches),
        "errors": errors,
    }, indent=2))
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
