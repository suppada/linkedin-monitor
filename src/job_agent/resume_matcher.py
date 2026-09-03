from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Job


@dataclass(frozen=True)
class ResumeResult:
    score: int
    level: str
    matched_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    education_aligned: bool


class ResumeMatcher:
    """Explainable resume-to-job matcher with no external AI service."""

    def __init__(self, profile_path: str | Path) -> None:
        self.profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))

    @staticmethod
    def _contains(text: str, phrase: str) -> bool:
        normalized = re.sub(r"[^a-z0-9+#./-]+", " ", text.casefold())
        candidate = re.sub(r"[^a-z0-9+#./-]+", " ", phrase.casefold()).strip()
        return candidate in normalized

    def evaluate(self, job: Job) -> ResumeResult:
        text = f"{job.title} {job.description}".casefold()
        resume_skills = self.profile.get("skills", [])
        matched = [skill for skill in resume_skills if self._contains(text, skill)]

        # Common requirements worth identifying when they are absent from the resume.
        skill_vocabulary = (
            "go", "golang", "java", "c++", "rust", "python", "kubernetes", "terraform",
            "ansible", "aws", "azure", "gcp", "jenkins", "github actions", "gitlab ci",
            "argocd", "fluxcd", "helm", "docker", "prometheus", "grafana", "splunk",
            "machine learning", "pytorch", "tensorflow", "llm", "cuda",
        )
        missing = [
            skill for skill in skill_vocabulary
            if self._contains(text, skill)
            and not any(self._contains(resume_skill, skill) for resume_skill in resume_skills)
        ]

        title_terms = self.profile.get("target_titles", [])
        title_alignment = max(
            (self._word_overlap(job.title, target) for target in title_terms),
            default=0.0,
        )
        skill_score = min(1.0, len(matched) / 8)

        research_terms = self.profile.get("research_areas", [])
        research_alignment = any(self._contains(text, term) for term in research_terms)
        phd_requested = any(term in text for term in ("phd", "ph.d", "doctoral", "doctorate"))
        education_aligned = phd_requested or research_alignment

        experience_score = 1.0 if any(
            term in text for term in ("senior", "lead", "staff", "principal", "10+ years", "8+ years")
        ) else 0.75
        raw = (
            title_alignment * 35
            + skill_score * 40
            + experience_score * 15
            + (10 if education_aligned else 5)
            - min(len(missing) * 3, 15)
        )
        score = max(0, min(100, round(raw)))
        level = "STRONG MATCH" if score >= 80 else "GOOD MATCH" if score >= 65 else "PARTIAL MATCH"
        return ResumeResult(
            score,
            level,
            tuple(matched[:10]),
            tuple(missing[:6]),
            education_aligned,
        )

    @staticmethod
    def _word_overlap(left: str, right: str) -> float:
        ignored = {"senior", "lead", "staff", "principal", "engineer", "engineering"}
        left_words = set(re.findall(r"[a-z0-9]+", left.casefold())) - ignored
        right_words = set(re.findall(r"[a-z0-9]+", right.casefold())) - ignored
        return len(left_words & right_words) / max(len(right_words), 1)
