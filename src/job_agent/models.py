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
    employment_type: str = ""

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
    resume_score: int = 0
    resume_level: str = ""
    matched_skills: tuple[str, ...] = ()
    missing_skills: tuple[str, ...] = ()
