from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    source: str
    external_id: str
    company: str
    title: str
    location: str
    description: str
    url: str
    published_at: str = ""
    salary: str = ""

    @property
    def identity(self) -> str:
        return f"{self.source}:{self.company}:{self.external_id}"


@dataclass(frozen=True)
class Match:
    job: Job
    score: float
    ai_probability: float
    sponsorship: str
    reasons: tuple[str, ...]

