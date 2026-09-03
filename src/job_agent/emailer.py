from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage

from .models import Match


def _label(value: str, fallback: str = "Not specified") -> str:
    value = (value or "").strip().replace("_", " ")
    return value.title() if value else fallback


def build_email_html(matches: list[Match]) -> str:
    cards = []
    for match in matches:
        job = match.job
        score = max(0, min(100, round(match.score)))
        score_color = "#16803c" if score >= 70 else "#b45309" if score >= 50 else "#475569"
        reasons = [
            reason for reason in match.reasons
            if not reason.lower().startswith(("ai relevance", "sponsorship:"))
        ]
        details = "".join(
            f"<li style='margin:4px 0'>{html.escape(reason)}</li>" for reason in reasons[:4]
        )
        resume_section = ""
        if match.resume_level:
            resume_color = "#16803c" if match.resume_score >= 80 else "#b45309" if match.resume_score >= 65 else "#475569"
            matched_text = ", ".join(html.escape(skill) for skill in match.matched_skills) or "General role alignment"
            missing_text = ", ".join(html.escape(skill) for skill in match.missing_skills)
            resume_section = f"""
          <div style="background:#f8fafc;border-radius:10px;padding:13px;margin-top:15px;font-size:13px;color:#334155">
            <strong style="color:{resume_color}">Resume match: {match.resume_score}% - {html.escape(match.resume_level)}</strong><br>
            <span style="line-height:1.7"><strong>Matched:</strong> {matched_text}</span>
            {f'<br><span style="line-height:1.7"><strong>Potential gaps:</strong> {missing_text}</span>' if missing_text else ''}
          </div>"""
        cards.append(f"""
        <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;
                    margin:0 0 18px;padding:20px;box-shadow:0 2px 6px rgba(15,23,42,.06)">
          <div style="color:#2563eb;font-size:13px;font-weight:700;letter-spacing:.5px;
                      text-transform:uppercase">{html.escape(job.company)}</div>
          <h2 style="font-size:20px;line-height:1.3;margin:7px 0 12px;color:#0f172a">
            {html.escape(job.title)}
          </h2>
          <div style="color:#475569;font-size:14px;line-height:1.8">
            &#128205; {html.escape(job.location or 'Location not specified')}<br>
            &#128188; {_label(job.employment_type)}<br>
            &#127915; Sponsorship: {_label(match.sponsorship, 'Not confirmed')}
          </div>
          <div style="margin:15px 0 8px;font-size:14px;color:#334155">
            Match score: <strong style="color:{score_color}">{score}%</strong>
          </div>
          <div style="height:7px;background:#e2e8f0;border-radius:10px;overflow:hidden">
            <div style="height:7px;width:{score}%;background:{score_color}"></div>
          </div>
          {resume_section}
          {f'<ul style="color:#475569;font-size:13px;padding-left:20px;margin:14px 0">{details}</ul>' if details else ''}
          <a href="{html.escape(job.url, quote=True)}"
             style="display:inline-block;margin-top:10px;background:#2563eb;color:#ffffff;
                    text-decoration:none;font-size:15px;font-weight:700;padding:12px 22px;
                    border-radius:9px">View &amp; Apply</a>
        </div>""")

    count = len(matches)
    return f"""<!doctype html>
<html><body style="margin:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif">
  <div style="max-width:640px;margin:auto;padding:24px 14px">
    <div style="background:#0f172a;border-radius:14px;padding:24px;margin-bottom:18px;color:#ffffff">
      <div style="font-size:13px;color:#93c5fd;font-weight:700;letter-spacing:1px">DEVOPS JOB AGENT</div>
      <h1 style="font-size:26px;margin:7px 0">{count} new job {'match' if count == 1 else 'matches'}</h1>
      <p style="margin:0;color:#cbd5e1;font-size:14px">Official company career sites · New listings only</p>
    </div>
    {''.join(cards)}
    <p style="color:#64748b;font-size:12px;text-align:center;line-height:1.5">
      Automatically selected using your DevOps job preferences.<br>
      Always confirm employment and sponsorship terms with the employer.
    </p>
  </div>
</body></html>"""


def send_gmail(sender: str, app_password: str, recipient: str, matches: list[Match]) -> None:
    message = EmailMessage()
    count = len(matches)
    message["Subject"] = f"New DevOps job alert: {count} {'match' if count == 1 else 'matches'}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("New matching DevOps jobs were found. View this email in HTML format.")
    message.add_alternative(build_email_html(matches), subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as server:
        server.login(sender, app_password)
        server.send_message(message)
