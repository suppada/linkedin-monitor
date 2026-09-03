from __future__ import annotations

import html
import imaplib
import os
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from urllib.parse import unquote

from .models import Job


JOB_ID = re.compile(
    r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#&]*-)?(\d+)|[?&]currentJob=(\d+)",
    re.IGNORECASE,
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text)))
            self._href = None
            self._text = []


def canonical_job_url(value: str) -> tuple[str, str] | None:
    decoded = html.unescape(value)
    for _ in range(3):
        decoded = unquote(decoded)
    match = JOB_ID.search(decoded)
    if not match:
        return None
    job_id = next(group for group in match.groups() if group)
    return job_id, f"https://www.linkedin.com/jobs/view/{job_id}"


def extract_jobs(
    content: str,
    message_id: str,
    location: str = "United States",
    employment_type: str = "Full-time",
) -> list[Job]:
    parser = LinkParser()
    parser.feed(content)
    description = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", content)).split())
    jobs: list[Job] = []
    seen: set[str] = set()
    for href, anchor_text in parser.links:
        canonical = canonical_job_url(href)
        if not canonical or canonical[0] in seen:
            continue
        seen.add(canonical[0])
        title = " ".join(html.unescape(anchor_text).split()) or "LinkedIn job"
        jobs.append(Job(
            source="linkedin_email",
            external_id=canonical[0],
            company="LinkedIn job alert",
            title=title,
            location=location,
            description=description,
            url=canonical[1],
            published_at=message_id,
            employment_type=employment_type,
        ))
    return jobs


def read_linkedin_alerts(
    address: str,
    app_password: str,
    lookback_days: int = 7,
    location: str = "United States",
    employment_type: str = "Full-time",
) -> list[Job]:
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, lookback_days))).strftime("%d-%b-%Y")
    jobs: list[Job] = []
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", 993) as mailbox:
            mailbox.login(address, app_password)
            mailbox.select("INBOX", readonly=True)
            status, identifiers = mailbox.search(None, "SINCE", since)
            if status != "OK":
                raise RuntimeError("Gmail IMAP search failed")
            for identifier in identifiers[0].split():
                status, payload = mailbox.fetch(identifier, "(BODY.PEEK[])")
                if status != "OK":
                    continue
                raw = next((part[1] for part in payload if isinstance(part, tuple)), None)
                if not raw:
                    continue
                message = BytesParser(policy=policy.default).parsebytes(raw)
                sender = str(message.get("From", "")).casefold()
                subject = str(message.get("Subject", "")).casefold()
                if "linkedin" not in sender or "job" not in subject:
                    continue
                html_parts = [
                    part.get_content()
                    for part in message.walk()
                    if part.get_content_type() == "text/html"
                ]
                content = "\n".join(html_parts)
                if content:
                    jobs.extend(extract_jobs(
                        content,
                        str(message.get("Message-ID", identifier.decode())),
                        location,
                        employment_type,
                    ))
    except (imaplib.IMAP4.error, OSError) as exc:
        raise RuntimeError(f"LinkedIn Gmail source failed: {exc}") from exc
    return jobs


def from_environment(source: dict) -> list[Job]:
    address = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not address or not password:
        raise RuntimeError("LinkedIn Gmail source requires GMAIL_ADDRESS and GMAIL_APP_PASSWORD")
    return read_linkedin_alerts(
        address,
        password,
        int(source.get("lookback_days", 7)),
        str(source.get("location", "United States")),
        str(source.get("employment_type", "Full-time")),
    )
