# DevOps Job AI Agent

This is Suresh Kumar Uppada's independent job-monitoring agent. It runs from a
GitHub repository every hour, checks configured public job sources, uses its own
machine-learning classifier to identify DevOps/platform/cloud opportunities,
remembers jobs already processed, and emails only new matches directly to Gmail.

It does not use ChatGPT, an LLM, or an external AI service. The relevance model
is a multinomial Naive Bayes classifier implemented directly in Python and
trained from the bundled labeled dataset.

## What it does

```text
Hourly GitHub Actions schedule
          ↓
Read current job postings
          ↓
Ignore previously processed job IDs
          ↓
Apply exclusions and sponsorship policy
          ↓
Run AI relevance classification
          ↓
Rank new matching DevOps jobs
          ↓
Email results to your Gmail
          ↓
Persist seen-job database
```

The bundled configuration monitors selected large-company career domains. The
agent can also be configured for Remote OK, Remotive, Jobicy, Arbeitnow, public
Greenhouse and Lever boards, or LinkedIn job-alert email ingestion.

It also reads LinkedIn job-alert emails from the configured Gmail inbox. It does
not scrape LinkedIn or store a LinkedIn password. Configure the LinkedIn alert
itself for United States and Full-time before enabling email delivery; the agent
then extracts LinkedIn job links, applies its classifier, deduplicates them, and
combines them with the other sources.

The default configuration monitors official careers domains for NVIDIA, Google,
Apple, Tesla, Microsoft, Amazon, Meta, Netflix, Salesforce, and Oracle. Results
are discovered through a domain-restricted RSS search and accepted only when
the destination hostname is the configured employer domain. Every alert links
to the employer's careers site. Search-engine indexing can introduce delay, so
this is polling rather than a real-time employer webhook.

## 1. Create your GitHub repository

Create a private repository such as:

```text
devops-job-ai-agent
```

Extract this project, push its contents to the repository's default branch, and
keep `.github/workflows/job-agent.yml` enabled.

## 2. Create a Gmail app password

Do not use your normal Gmail password.

1. Enable 2-Step Verification on your Google account.
2. Open Google Account **App passwords**.
3. Create an app password named `DevOps Job Agent`.
4. Copy the generated 16-character password.

App passwords may be unavailable for some managed Workspace accounts or when an
administrator disables them.

## 3. Configure GitHub Actions secrets

In the repository, open **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `GMAIL_ADDRESS` | Gmail address used to send the alert |
| `GMAIL_APP_PASSWORD` | Google-generated app password, never normal password |
| `GMAIL_TO` | Gmail address that should receive alerts |

Never put these values in `config.json` or commit them.

## 4. Configure job preferences

Edit `config.json`. It already targets:

- DevOps
- Platform Engineering
- Cloud Engineering and Architecture
- DevSecOps
- Site Reliability Engineering
- Infrastructure Engineering
- CI/CD and Kubernetes roles

It recognizes experience with AWS, Kubernetes/EKS, Terraform, GitHub Actions,
FluxCD, Helm, Docker, AppDynamics, observability and SLSA. By default it reports
all DevOps-related roles and flags citizenship, clearance, polygraph, and
no-sponsorship language as eligibility warnings rather than hiding the posting.

`require_full_time` defaults to `true`, while `require_sponsorship` defaults to
`false`. An alert therefore requires a full-time DevOps-related posting, and
the email labels sponsorship as confirmed, unavailable, or not confirmed. The
agent does not infer sponsorship from a company's historical behavior.

`require_location_match` restricts alerts to explicit United States locations.
Company-site searches are scoped to the United States. A Jobicy source configured
with `geo=usa` is also treated as US-eligible.

## 5. Add employer career boards

The Greenhouse Job Board API uses the token visible in a company's career URL:

```text
https://boards.greenhouse.io/BOARD_TOKEN
```

Add to `config.json`:

```json
{
  "type": "greenhouse",
  "company": "Company Name",
  "board": "BOARD_TOKEN"
}
```

For Lever, use the account name from:

```text
https://jobs.lever.co/ACCOUNT_NAME
```

Add:

```json
{
  "type": "lever",
  "company": "Company Name",
  "account": "ACCOUNT_NAME"
}
```

See `sources.example.json`.

## 6. Test it

Open **Actions → DevOps Job AI Agent → Run workflow**.

For a local scan without sending email:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --no-build-isolation -e .
job-agent --config config.json --state data/job-agent.db --dry-run
```

Run unit tests without dependencies:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Schedule

The included workflow runs at minute 17 of every hour:

```yaml
schedule:
  - cron: "17 * * * *"
```

GitHub scheduled workflows are polling, not truly instantaneous, and may start
later during high system load. Public job boards do not provide one universal
webhook for every employer. Therefore the agent detects a posting during its
next scheduled scan.

## Seen-job state

The SQLite database stores stable source/company/job identifiers. GitHub Actions
cache restores the latest database before scanning and saves the updated state
afterward. A matching job is emailed once, not during every hourly run.

The first run treats all currently active matching postings as new. Subsequent
runs email only newly discovered matches.

The run summary includes counts for every source, unseen postings, preference
rejections, cross-source duplicates, matches, and source errors. A zero-match
run therefore explains whether there were no new postings or the preferences
rejected them.

## AI limitations and improvement

The included labeled dataset bootstraps the model. It does not prove production
accuracy. Improve it with accurately labeled examples and measure precision,
recall and F1 score on a separate evaluation set. Do not train on confidential
job-search or personal information that you plan to publish.

## Ownership

Copyright 2026 Suresh Kumar Uppada. Apache License 2.0.
