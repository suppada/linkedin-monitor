from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


USCIS_URL = "https://egov.uscis.gov/casestatus/mycasestatus.do"


class _StatusParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tag = ""
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"h1", "h2", "h3", "p"}:
            self.tag = tag
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.tag:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self.tag:
            return
        text = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
        if text:
            (self.paragraphs if tag == "p" else self.headings).append(text)
        self.tag = ""
        self.buffer = []


def parse_status(page: str) -> dict[str, str]:
    parser = _StatusParser()
    parser.feed(page)
    ignored = ("case status online", "check case status", "enter a receipt")
    headings = [h for h in parser.headings if not any(x in h.casefold() for x in ignored)]
    title = next((h for h in headings if len(h) >= 8), "")
    description = next(
        (p for p in parser.paragraphs if len(p) >= 40 and "privacy" not in p.casefold()),
        "",
    )
    if not title or not description:
        raise ValueError("USCIS returned a page, but no case status could be identified")
    date_match = re.search(
        r"(?:As of|On)\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", description
    )
    return {
        "title": title,
        "description": description,
        "status_date": date_match.group(1) if date_match else "",
    }


def fetch_status(receipt: str) -> dict[str, str]:
    receipt = receipt.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}\d{10}", receipt):
        raise ValueError("USCIS receipt number must contain 3 letters followed by 10 digits")
    request = Request(
        USCIS_URL,
        data=urlencode({"appReceiptNum": receipt}).encode(),
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; personal USCIS status monitor)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return parse_status(response.read().decode("utf-8", errors="replace"))


def status_fingerprint(status: dict[str, str]) -> str:
    content = "\n".join(status.get(key, "") for key in ("title", "description", "status_date"))
    return hashlib.sha256(content.encode()).hexdigest()


def send_alert(sender: str, password: str, recipient: str, receipt: str,
               old: dict[str, str], new: dict[str, str]) -> None:
    message = EmailMessage()
    message["Subject"] = f"USCIS case update: {new['title']}"
    message["From"] = formataddr(("USCIS Case Alert", sender))
    message["To"] = recipient
    masked = f"{receipt[:3]}*******{receipt[-3:]}"
    previous = old.get("title", "Initial status recorded")
    body = f"""<!doctype html><html><body style="font-family:Arial;background:#f1f5f9;margin:0">
    <div style="max-width:620px;margin:auto;padding:24px">
      <div style="background:#0b3b70;color:white;padding:22px;border-radius:12px 12px 0 0">
        <div style="font-size:13px">USCIS CASE ALERT</div>
        <h1 style="font-size:23px;margin:8px 0 0">{html.escape(new['title'])}</h1>
      </div>
      <div style="background:white;padding:22px;border-radius:0 0 12px 12px">
        <p><strong>Case:</strong> {html.escape(masked)}</p>
        <p><strong>Previous:</strong> {html.escape(previous)}</p>
        <p><strong>Status date:</strong> {html.escape(new.get('status_date') or 'Not displayed')}</p>
        <p style="line-height:1.6">{html.escape(new['description'])}</p>
        <a href="{USCIS_URL}" style="display:inline-block;background:#1261a0;color:white;
          padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Open USCIS Case Status</a>
      </div>
    </div></body></html>"""
    message.set_content(f"{new['title']}\n\n{new['description']}\n\n{USCIS_URL}")
    message.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as server:
        server.login(sender, password)
        server.send_message(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor an official USCIS case status")
    parser.add_argument("--state", default="data/uscis-status.json")
    parser.add_argument("--notify-initial", action="store_true")
    args = parser.parse_args(argv)
    receipt = required("USCIS_RECEIPT_NUMBER")
    state_path = Path(args.state)
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    current = fetch_status(receipt)
    changed = bool(previous) and status_fingerprint(previous) != status_fingerprint(current)
    print(json.dumps({"status": current["title"], "status_date": current["status_date"],
                      "changed": changed}, indent=2))
    if changed or (args.notify_initial and not previous):
        sender = required("GMAIL_ADDRESS")
        send_alert(sender, required("GMAIL_APP_PASSWORD"), os.getenv("GMAIL_TO", sender),
                   receipt, previous, current)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return 0


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
