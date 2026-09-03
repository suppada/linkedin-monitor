import json
import tempfile
import unittest
from pathlib import Path

from job_agent.intelligence import JobRelevanceAI
from job_agent.models import Job
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
                  "AWS Kubernetes Terraform GitHub Actions platform automation", "https://example/jobs/1")
        self.assertIsNotNone(self.ai.evaluate(job, self.preferences))

    def test_excludes_citizenship_requirement(self):
        job = Job("test", "2", "Example", "DevOps Engineer", "Virginia",
                  "AWS Kubernetes. U.S. citizenship required and polygraph", "https://example/jobs/2")
        self.assertIsNone(self.ai.evaluate(job, self.preferences))

    def test_state_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            state = State(Path(directory) / "state.db")
            self.assertFalse(state.is_seen("job:1"))
            state.mark_seen(["job:1"])
            self.assertTrue(state.is_seen("job:1"))


if __name__ == "__main__":
    unittest.main()

