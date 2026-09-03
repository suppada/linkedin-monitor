import json
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from job_agent.intelligence import JobRelevanceAI
from job_agent.linkedin_email import canonical_job_url, extract_jobs
from job_agent.models import Job
from job_agent.sources import arbeitnow, jobicy, remotive
from job_agent.state import State


TRAINING = Path(__file__).parents[1] / "src" / "job_agent" / "data" / "training.json"


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


if __name__ == "__main__":
    unittest.main()
