from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Job
from .linkedin_email import from_environment as linkedin_email

TAG = re.compile(r"<[^>]+>")


def fetch_json(url: str) -> Any:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "DevOpsJobAgent/1.0"})
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Job source request failed: {url}: {exc}") from exc


def clean(value: str | None) -> str:
    return " ".join(html.unescape(TAG.sub(" ", value or "")).split())


def join_values(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def greenhouse(board: str, company: str) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    payload = fetch_json(url)
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        metadata = " ".join(str(entry.get("value", "")) for entry in item.get("metadata", []))
        jobs.append(Job(
            source="greenhouse",
            external_id=str(item["id"]),
            company=company,
            title=clean(item.get("title")),
            location=clean(item.get("location", {}).get("name")),
            description=clean(f"{item.get('content', '')} {metadata}"),
            url=item.get("absolute_url", ""),
            published_at=item.get("updated_at", ""),
            employment_type=metadata,
        ))
    return jobs


def lever(account: str, company: str) -> list[Job]:
    query = urlencode({"mode": "json"})
    payload = fetch_json(f"https://api.lever.co/v0/postings/{account}?{query}")
    jobs: list[Job] = []
    for item in payload:
        categories = item.get("categories", {})
        lists = " ".join(clean(entry.get("content")) for entry in item.get("lists", []))
        jobs.append(Job(
            source="lever",
            external_id=str(item["id"]),
            company=company,
            title=clean(item.get("text")),
            location=clean(categories.get("location") or item.get("workplaceType")),
            description=clean(f"{item.get('descriptionPlain', '')} {lists}"),
            url=item.get("hostedUrl", item.get("applyUrl", "")),
            published_at=str(item.get("createdAt", "")),
            employment_type=clean(categories.get("commitment")),
        ))
    return jobs


def remoteok() -> list[Job]:
    payload = fetch_json("https://remoteok.com/api")
    jobs: list[Job] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("id") or not item.get("position"):
            continue
        tags = " ".join(str(tag) for tag in item.get("tags", []))
        salary = ""
        if item.get("salary_min") or item.get("salary_max"):
            salary = f"{item.get('salary_min', '')}-{item.get('salary_max', '')}"
        url = item.get("url") or f"https://remoteok.com/remote-jobs/{item['id']}"
        if url.startswith("/"):
            url = "https://remoteok.com" + url
        jobs.append(Job(
            source="remoteok",
            external_id=str(item["id"]),
            company=clean(item.get("company")),
            title=clean(item.get("position")),
            location=clean(item.get("location") or "Remote"),
            description=clean(f"{item.get('description', '')} {tags}"),
            url=url,
            published_at=str(item.get("date", item.get("epoch", ""))),
            salary=salary,
            employment_type="full-time",
        ))
    return jobs


def remotive() -> list[Job]:
    """Read Remotive's public remote-jobs feed."""
    payload = fetch_json("https://remotive.com/api/remote-jobs")
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        jobs.append(Job(
            source="remotive",
            external_id=str(item["id"]),
            company=clean(item.get("company_name")),
            title=clean(item.get("title")),
            location=clean(item.get("candidate_required_location") or "Remote"),
            description=clean(item.get("description")),
            url=item.get("url", ""),
            published_at=str(item.get("publication_date", "")),
            salary=clean(item.get("salary")),
            employment_type=clean(item.get("job_type")),
        ))
    return jobs


def jobicy(count: int = 200, geo: str = "usa") -> list[Job]:
    """Read Jobicy's public remote-jobs feed."""
    query = urlencode({"count": max(1, min(count, 200)), "geo": geo})
    payload = fetch_json(f"https://jobicy.com/api/v2/remote-jobs?{query}")
    jobs: list[Job] = []
    for item in payload.get("jobs", []):
        salary_parts = [
            str(item.get("annualSalaryMin") or ""),
            str(item.get("annualSalaryMax") or ""),
            str(item.get("salaryCurrency") or ""),
        ]
        jobs.append(Job(
            source="jobicy",
            external_id=str(item.get("id") or item.get("url", "")),
            company=clean(item.get("companyName")),
            title=clean(item.get("jobTitle")),
            location=clean(item.get("jobGeo") or "Remote"),
            description=clean(
                f"{item.get('jobExcerpt', '')} {item.get('jobDescription', '')} "
                f"{' '.join(item.get('jobIndustry') or [])}"
            ),
            url=item.get("url", ""),
            published_at=str(item.get("pubDate", "")),
            salary=" ".join(part for part in salary_parts if part),
            employment_type=clean(join_values(item.get("jobType"))),
        ))
    return jobs


def arbeitnow(visa_sponsorship: bool = True) -> list[Job]:
    """Read Arbeitnow's public ATS-backed job feed, including non-remote roles."""
    query = urlencode({"visa_sponsorship": str(visa_sponsorship).lower()})
    payload = fetch_json(f"https://www.arbeitnow.com/api/job-board-api?{query}")
    jobs: list[Job] = []
    for item in payload.get("data", []):
        tags = " ".join(str(tag) for tag in item.get("tags", []))
        jobs.append(Job(
            source="arbeitnow",
            external_id=str(item.get("slug") or item.get("url", "")),
            company=clean(item.get("company_name")),
            title=clean(item.get("title")),
            location=clean(item.get("location")),
            description=clean(f"{item.get('description', '')} {tags}"),
            url=item.get("url", ""),
            published_at=str(item.get("created_at", "")),
            employment_type="full-time" if "full-time" in tags.casefold() else tags,
        ))
    return jobs


def collect(config: dict) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    errors: list[str] = []
    for source in config.get("sources", []):
        try:
            if source["type"] == "greenhouse":
                jobs.extend(greenhouse(source["board"], source["company"]))
            elif source["type"] == "lever":
                jobs.extend(lever(source["account"], source["company"]))
            elif source["type"] == "remoteok":
                jobs.extend(remoteok())
            elif source["type"] == "remotive":
                jobs.extend(remotive())
            elif source["type"] == "jobicy":
                jobs.extend(jobicy(
                    int(source.get("count", 200)),
                    str(source.get("geo", "usa")),
                ))
            elif source["type"] == "arbeitnow":
                jobs.extend(arbeitnow(bool(source.get("visa_sponsorship", True))))
            elif source["type"] == "linkedin_email":
                jobs.extend(linkedin_email(source))
            else:
                errors.append(f"Unsupported source type: {source.get('type')}")
        except RuntimeError as exc:
            errors.append(str(exc))
    return jobs, errors
