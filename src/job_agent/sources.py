from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Job

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
            else:
                errors.append(f"Unsupported source type: {source.get('type')}")
        except RuntimeError as exc:
            errors.append(str(exc))
    return jobs, errors
