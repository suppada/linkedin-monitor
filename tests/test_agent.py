import json
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from job_agent.intelligence import JobRelevanceAI
from job_agent.emailer import build_email_html
from job_agent.linkedin_email import canonical_job_url, extract_jobs
from job_agent.models import Job, Match
from job_agent.resume_matcher import ResumeMatcher
from job_agent.sources import arbeitnow, jobicy, official_company, remotive
from job_agent.state import State
from job_agent.uscis_monitor import parse_status, status_fingerprint


TRAINING = Path(__file__).parents[1] / "src" / "job_agent" / "data" / "training.json"
PROFILE = Path(__file__).parents[1] / "resume_profile.json"


class JobAgentTests(unittest.TestCase):
    def setUp(self):
        self.ai = JobRelevanceAI(TRAINING)
        self.preferences = json.loads(
            (Path(__file__).parents[1] / "config.json").read_text()
        )["preferences"]

    def test_matches_devops_job(self):
        job = Job("test", "1", "Example", "Senior DevOps Engineer", "Remote US",
                  "AWS Kubernetes Terraform GitHub Actions platform automation. H1B transfer.",
                  "https://example/jobs/1", employment_type="Full-time")
        self.assertIsNotNone(self.ai.evaluate(job, self.preferences))

    def test_flags_citizenship_requirement_without_hiding_job(self):
        job = Job("test", "2", "Example", "DevOps Engineer", "Virginia",
                  "AWS Kubernetes. U.S. citizenship required and polygraph. Will sponsor H-1B.",
                  "https://example/jobs/2", employment_type="Full-time")
        match = self.ai.evaluate(job, self.preferences)
        self.assertIsNotNone(match)
        self.assertTrue(any("Eligibility warning" in reason for reason in match.reasons))

    def test_labels_no_sponsorship(self):
        job = Job("test", "3", "Example", "Platform Engineer", "Remote US",
                  "AWS Kubernetes Terraform. No sponsorship available.",
                  "https://example/jobs/3", employment_type="Full-time")
        match = self.ai.evaluate(job, self.preferences)
        self.assertIsNotNone(match)
        self.assertEqual(match.sponsorship, "unavailable")

    def test_state_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / "state.db")
            self.assertFalse(state.is_seen("job:1"))
            state.mark_seen(["job:1"])
            self.assertTrue(state.is_seen("job:1"))

    def test_parses_uscis_status(self):
        page = '''<html><h1>USCIS Is Currently Processing the Case</h1>
        <p>As of August 13, 2026, USCIS is currently processing your Form I-140,
        Immigrant Petition for Alien Worker. We do not currently need anything from you.</p></html>'''
        status = parse_status(page)
        self.assertEqual(status["status_date"], "August 13, 2026")
        self.assertIn("Processing", status["title"])

    def test_uscis_fingerprint_changes_with_status(self):
        first = {"title": "Processing", "description": "Case processing", "status_date": ""}
        second = {"title": "Approved", "description": "Case approved", "status_date": ""}
        self.assertNotEqual(status_fingerprint(first), status_fingerprint(second))

    def test_builds_mobile_friendly_email_card(self):
        job = Job("test", "10", "Example", "Senior DevOps Engineer", "Charlotte, NC",
                  "AWS Kubernetes", "https://example/jobs/10", employment_type="Full-time")
        match = Match(job, 82.4, 0.95, "not_confirmed",
                      ("AI relevance 95%", "Sponsorship: not_confirmed", "AWS skill match"))
        body = build_email_html([match])
        self.assertIn("1 new job match", body)
        self.assertIn("View &amp; Apply", body)
        self.assertIn("82%", body)
        self.assertEqual(body.count("Sponsorship:"), 1)
        self.assertIn("AWS skill match", body)

    def test_resume_matcher_rewards_sre_cloud_alignment(self):
        matcher = ResumeMatcher(PROFILE)
        job = Job("test", "11", "Example", "Senior Site Reliability Engineer", "United States",
                  "AWS EKS Kubernetes Terraform Helm GitHub Actions Python incident response",
                  "https://example/jobs/11", employment_type="Full-time")
        result = matcher.evaluate(job)
        self.assertGreaterEqual(result.score, 80)
        self.assertEqual(result.level, "STRONG MATCH")
        self.assertIn("kubernetes", result.matched_skills)

    def test_resume_matcher_exposes_ml_research_gap(self):
        matcher = ResumeMatcher(PROFILE)
        job = Job("test", "12", "Example", "Research Scientist, ML Systems", "United States",
                  "Develop machine learning algorithms using PyTorch TensorFlow CUDA and LLM training",
                  "https://example/jobs/12", employment_type="Full-time")
        result = matcher.evaluate(job)
        self.assertLess(result.score, 65)
        self.assertIn("pytorch", result.missing_skills)

    def test_extracts_linkedin_job_alert(self):
        content = '''
        <html><body>
          <a href="https://www.linkedin.com/comm/jobs/view/senior-devops-engineer-4455791144">
            Senior DevOps Engineer
          </a>
        </body></html>
        '''
        jobs = extract_jobs(content, "message-1")
        self.assertEqual(jobs[0].external_id, "4455791144")
        self.assertEqual(jobs[0].title, "Senior DevOps Engineer")
        self.assertEqual(jobs[0].employment_type, "Full-time")

    def test_decodes_linkedin_redirect_url(self):
        result = canonical_job_url(
            "https://www.linkedin.com/redir/redirect?url=https%3A%2F%2Fwww.linkedin.com%2Fjobs%2Fview%2F4455791144"
        )
        self.assertEqual(result[0], "4455791144")

    @patch("job_agent.sources.fetch_json")
    def test_reads_remotive_feed(self, fetch_json):
        fetch_json.return_value = {"jobs": [{
            "id": 7, "company_name": "Acme", "title": "DevOps Engineer",
            "candidate_required_location": "USA", "description": "AWS Terraform",
            "url": "https://example/7", "publication_date": "2026-09-03"
        }]}
        jobs = remotive()
        self.assertEqual(jobs[0].company, "Acme")
        self.assertEqual(jobs[0].source, "remotive")

    @patch("job_agent.sources.fetch_json")
    def test_reads_jobicy_feed(self, fetch_json):
        fetch_json.return_value = {"jobs": [{
            "id": 8, "companyName": "Example", "jobTitle": "Platform Engineer",
            "jobGeo": "USA", "jobDescription": "Kubernetes Helm",
            "jobIndustry": ["Engineering"], "jobType": "Full-time",
            "url": "https://example/8"
        }]}
        jobs = jobicy()
        self.assertEqual(jobs[0].title, "Platform Engineer")
        self.assertIn("Engineering", jobs[0].description)
        self.assertEqual(jobs[0].employment_type, "Full-time")

    def test_rejects_non_us_job(self):
        job = Job("test", "9", "Example", "Senior DevOps Engineer", "Munich, Germany",
                  "AWS Kubernetes Terraform", "https://example/jobs/9",
                  employment_type="Full-time")
        self.assertIsNone(self.ai.evaluate(job, self.preferences))

    @patch("job_agent.sources.fetch_json")
    def test_reads_arbeitnow_sponsored_feed(self, fetch_json):
        fetch_json.return_value = {"data": [{
            "slug": "devops-1", "company_name": "Acme", "title": "DevOps Engineer",
            "location": "New York", "description": "Visa sponsorship available",
            "tags": ["Full-time", "AWS"], "url": "https://example/devops-1"
        }]}
        jobs = arbeitnow()
        self.assertEqual(jobs[0].location, "New York")
        self.assertEqual(jobs[0].employment_type, "full-time")

    @patch("job_agent.sources.fetch_text")
    def test_reads_only_official_company_links(self, fetch_text):
        fetch_text.return_value = '''<?xml version="1.0"?>
        <rss><channel>
          <item><title>Senior DevOps Engineer</title>
            <link>https://jobs.example.com/en-us/job/123</link>
            <description>AWS Kubernetes Terraform</description></item>
          <item><title>Wrong domain</title>
            <link>https://aggregator.example/job/123</link></item>
        </channel></rss>'''
        jobs = official_company("Example", "jobs.example.com", "/en-us/")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Example")
        self.assertEqual(jobs[0].employment_type, "Full-time")


if __name__ == "__main__":
    unittest.main()
