from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage

from .models import Match


def send_gmail(sender: str, app_password: str, recipient: str, matches: list[Match]) -> None:
    message = EmailMessage()
    message["Subject"] = f"DevOps Job Agent: {len(matches)} new matching job(s)"
    message["From"] = sender
    message["To"] = recipient
    rows = []
    for match in matches:
        job = match.job
        rows.append(
            f"<h3><a href='{html.escape(job.url)}'>{html.escape(job.title)}</a></h3>"
            f"<p><b>{html.escape(job.company)}</b> — {html.escape(job.location)}<br>"
            f"Match score: {match.score}/100 | Sponsorship: {match.sponsorship}<br>"
            f"{' | '.join(html.escape(reason) for reason in match.reasons)}</p>"
        )
    body = "<h2>New DevOps job matches</h2>" + "".join(rows)
    message.set_content("New matching DevOps jobs were found. View this email in HTML format.")
    message.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as server:
        server.login(sender, app_password)
        server.send_message(message)

