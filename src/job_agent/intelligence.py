from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .models import Job, Match

TOKENS = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.-]{1,50}")


class JobRelevanceAI:
    """Multinomial Naive Bayes classifier plus explainable eligibility policy."""

    def __init__(self, training_path: str | Path) -> None:
        examples = json.loads(Path(training_path).read_text(encoding="utf-8"))
        self.docs: Counter[str] = Counter()
        self.words: dict[str, Counter[str]] = defaultdict(Counter)
        self.totals: Counter[str] = Counter()
        self.vocab: set[str] = set()
        for example in examples:
            label = example["label"]
            words = self._tokens(example["text"])
            self.docs[label] += 1
            self.words[label].update(words)
            self.totals[label] += len(words)
            self.vocab.update(words)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [word.casefold() for word in TOKENS.findall(text)]

    def probability(self, text: str) -> float:
        scores: dict[str, float] = {}
        document_total = sum(self.docs.values())
        vocabulary_size = max(len(self.vocab), 1)
        for label, count in self.docs.items():
            score = math.log(count / document_total)
            denominator = self.totals[label] + vocabulary_size
            for word in self._tokens(text):
                score += math.log((self.words[label][word] + 1) / denominator)
            scores[label] = score
        maximum = max(scores.values())
        probabilities = {label: math.exp(score - maximum) for label, score in scores.items()}
        normalizer = sum(probabilities.values())
        return probabilities.get("match", 0) / normalizer

    def evaluate(self, job: Job, preferences: dict) -> Match | None:
        text = f"{job.title} {job.location} {job.description}".casefold()
        if any(term.casefold() in text for term in preferences.get("exclude_terms", [])):
            return None
        title_ok = any(term.casefold() in job.title.casefold() for term in preferences["title_terms"])
        skills = [term for term in preferences.get("skills", []) if term.casefold() in text]
        ai_probability = self.probability(text[:50_000])
        sponsorship_positive = any(term in text for term in preferences.get("sponsorship_positive", []))
        sponsorship_negative = any(term in text for term in preferences.get("sponsorship_negative", []))
        sponsorship = "confirmed" if sponsorship_positive and not sponsorship_negative else "not_confirmed"
        if preferences.get("require_sponsorship", False) and sponsorship != "confirmed":
            return None
        if not title_ok or ai_probability < float(preferences.get("minimum_ai_probability", 0.55)):
            return None
        score = min(100.0, ai_probability * 65 + min(len(skills), 7) * 5)
        reasons = [f"AI relevance {ai_probability:.0%}"]
        if skills:
            reasons.append("Skills: " + ", ".join(skills[:7]))
        reasons.append(f"Sponsorship: {sponsorship.replace('_', ' ')}")
        return Match(job, round(score, 1), ai_probability, sponsorship, tuple(reasons))

