from __future__ import annotations

import html
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
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


def fetch_text(url: str) -> str:
    request = Request(url, headers={"Accept": "application/rss+xml", "User-Agent": "DevOpsJobAgent/1.5"})
    try:
        with urlopen(request, timeout=45) as response:
            return response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Company careers request failed: {url}: {exc}") from exc


def post_json(url: str, payload: dict) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "DevOpsJobAgent/1.6"},
    )
    try:
        with urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError(f"Company careers request failed: {url}: {exc}") from exc


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[dict[str, str], str]] = []
        self._attrs: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "a":
            self._attrs = {key: value or "" for key, value in attrs}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._attrs is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._attrs is not None:
            self.links.append((self._attrs, " ".join(self._text)))
            self._attrs = None
            self._text = []


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


def official_company(
    company: str,
    domain: str,
    path_prefix: str = "",
    query_terms: str = "devops platform engineer site reliability cloud infrastructure kubernetes",
) -> list[Job]:
    """Find indexed postings restricted to one official employer career domain."""
    query = f'site:{domain}{path_prefix} ({query_terms}) "United States"'
    feed_url = "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"})
    try:
        root = ET.fromstring(fetch_text(feed_url))
    except ET.ParseError as exc:
        raise RuntimeError(f"Invalid careers search response for {company}: {exc}") from exc
    jobs: list[Job] = []
    allowed = domain.casefold().removeprefix("www.")
    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        url = clean(item.findtext("link"))
        host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
        if not url or not (host == allowed or host.endswith("." + allowed)):
            continue
        if path_prefix and path_prefix not in url:
            continue
        description = clean(item.findtext("description"))
        external_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        jobs.append(Job(
            source=f"company:{company.casefold().replace(' ', '_')}",
            external_id=external_id,
            company=company,
            title=title,
            location="United States",
            description=description,
            url=url,
            published_at=clean(item.findtext("pubDate")),
            employment_type="Full-time",
        ))
    return jobs


SEARCH_TERMS = ("devops", "platform engineer", "site reliability", "cloud infrastructure", "kubernetes")


def nvidia_careers() -> list[Job]:
    endpoint = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        for offset in range(0, 100, 20):
            payload = post_json(endpoint, {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term})
            postings = payload.get("jobPostings", [])
            for item in postings:
                path = str(item.get("externalPath", ""))
                if "/job/US-" not in path:
                    continue
                external_id = clean(" ".join(item.get("bulletFields") or [])) or path
                jobs[external_id] = Job(
                    source="company:nvidia", external_id=external_id, company="NVIDIA",
                    title=clean(item.get("title")),
                    location="United States — " + clean(item.get("locationsText")),
                    description=clean(item.get("title")),
                    url="https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite" + path,
                    published_at=clean(item.get("postedOn")), employment_type="Full-time",
                )
            if len(postings) < 20 or offset + 20 >= int(payload.get("total", 0)):
                break
    return list(jobs.values())


def apple_careers() -> list[Job]:
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        url = "https://jobs.apple.com/en-us/search?" + urlencode({
            "search": term, "location": "united-states-USA", "sort": "newest"
        })
        parser = AnchorParser()
        parser.feed(fetch_text(url))
        for attrs, text_value in parser.links:
            path = html.unescape(attrs.get("href", ""))
            if not path.startswith("/en-us/details/"):
                continue
            title = clean(text_value)
            if not title or title.casefold().startswith("see full role"):
                continue
            external_id = path.split("/", 4)[3]
            jobs[external_id] = Job(
                source="company:apple", external_id=external_id, company="Apple",
                title=title, location="United States", description=title,
                url="https://jobs.apple.com" + path, employment_type="Full-time",
            )
    return list(jobs.values())


def google_careers() -> list[Job]:
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        url = "https://www.google.com/about/careers/applications/jobs/results/?" + urlencode({
            "q": term, "location": "United States", "employment_type": "FULL_TIME"
        })
        parser = AnchorParser()
        parser.feed(fetch_text(url))
        for attrs, _ in parser.links:
            path = html.unescape(attrs.get("href", ""))
            label = clean(attrs.get("aria-label", ""))
            if "jobs/results/" not in path or not label.startswith("Learn more about "):
                continue
            relative = path[path.index("jobs/results/"):].split("?", 1)[0]
            external_id = relative.split("/", 2)[2].split("-", 1)[0]
            title = label.removeprefix("Learn more about ")
            jobs[external_id] = Job(
                source="company:google", external_id=external_id, company="Google",
                title=title, location="United States", description=title,
                url="https://www.google.com/about/careers/applications/" + relative,
                employment_type="Full-time",
            )
    return list(jobs.values())


def tesla_careers() -> list[Job]:
    payload = fetch_json("https://www.tesla.com/cua-api/apps/careers/state")
    locations = payload.get("lookup", {}).get("locations", {})
    types = payload.get("lookup", {}).get("types", {})
    us_states = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming"}
    jobs: list[Job] = []
    for item in payload.get("listings", []):
        title = clean(item.get("t"))
        location = clean(locations.get(str(item.get("l")), ""))
        job_type = clean(types.get(str(item.get("y")), ""))
        if not any(term in title.casefold() for term in SEARCH_TERMS):
            continue
        if job_type.casefold() != "fulltime":
            continue
        if not any(state in location.casefold() for state in us_states):
            continue
        external_id = str(item["id"])
        jobs.append(Job(
            source="company:tesla", external_id=external_id, company="Tesla",
            title=title, location=location, description=title,
            url=f"https://www.tesla.com/careers/search/job/{external_id}",
            employment_type="Full-time",
        ))
    return jobs


def amazon_careers() -> list[Job]:
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        url = "https://www.amazon.jobs/en/search.json?" + urlencode({
            "base_query": term, "loc_query": "United States", "result_limit": 100
        })
        payload = fetch_json(url)
        for item in payload.get("jobs", []):
            if str(item.get("country_code", "")).upper() not in {"USA", "US"}:
                continue
            if item.get("is_intern"):
                continue
            external_id = str(item.get("id") or item.get("job_path", ""))
            jobs[external_id] = Job(
                source="company:amazon", external_id=external_id, company="Amazon",
                title=clean(item.get("title")), location=clean(item.get("location")),
                description=clean(f"{item.get('description_short', '')} {item.get('description', '')}"),
                url="https://www.amazon.jobs" + str(item.get("job_path", "")),
                published_at=clean(item.get("posted_date")),
                employment_type=clean(item.get("job_schedule_type") or "Full-time"),
            )
    return list(jobs.values())


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
            elif source["type"] == "official_company":
                jobs.extend(official_company(
                    str(source["company"]),
                    str(source["domain"]),
                    str(source.get("path_prefix", "")),
                    str(source.get("query_terms", "devops platform engineer site reliability cloud infrastructure kubernetes")),
                ))
            elif source["type"] == "nvidia_careers":
                jobs.extend(nvidia_careers())
            elif source["type"] == "apple_careers":
                jobs.extend(apple_careers())
            elif source["type"] == "google_careers":
                jobs.extend(google_careers())
            elif source["type"] == "tesla_careers":
                jobs.extend(tesla_careers())
            elif source["type"] == "amazon_careers":
                jobs.extend(amazon_careers())
            else:
                errors.append(f"Unsupported source type: {source.get('type')}")
        except RuntimeError as exc:
            errors.append(str(exc))
    return jobs, errors
