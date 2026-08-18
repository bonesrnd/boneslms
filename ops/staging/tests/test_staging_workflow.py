import re
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "staging.yml"


class StagingWorkflowTest(unittest.TestCase):
    def test_builds_and_deploys_an_immutable_image_from_prod(self):
        self.assertTrue(WORKFLOW.exists(), "staging workflow is missing")
        workflow = WORKFLOW.read_text()

        self.assertIn("branches: [prod]", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("name: staging", workflow)
        self.assertIn("needs.build.outputs.digest", workflow)
        self.assertIn("ghcr.io/${GITHUB_REPOSITORY}@${IMAGE_DIGEST}", workflow)
        build_job = workflow.split("  build:", maxsplit=1)[1].split(
            "  deploy:",
            maxsplit=1,
        )[0]
        self.assertIn("if: github.ref == 'refs/heads/prod'", build_job)
        self.assertIn("python3 -B -m unittest discover", build_job)
        self.assertNotIn("ghcr.io/${{ github.repository }}:staging", build_job)

    def test_third_party_actions_are_pinned_to_commits(self):
        workflow = WORKFLOW.read_text()
        uses = re.findall(r"^\s*uses:\s*(\S+)", workflow, flags=re.MULTILINE)

        self.assertTrue(uses)
        for action in uses:
            with self.subTest(action=action):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")

    def test_uses_environment_secrets_and_verifies_the_ssh_host(self):
        self.assertTrue(WORKFLOW.exists(), "staging workflow is missing")
        workflow = WORKFLOW.read_text()

        self.assertIn("sops --decrypt", workflow)
        self.assertIn("secrets.RESEND_API_KEY", workflow)
        self.assertIn("secrets.SOPS_AGE_KEY", workflow)
        self.assertIn("secrets.SSH_KNOWN_HOSTS", workflow)
        self.assertIn("TUNNEL_SERVICE_TOKEN_ID", workflow)
        self.assertNotIn("StrictHostKeyChecking no", workflow)
        deploy_header = workflow.split("  deploy:", maxsplit=1)[1].split(
            "    steps:",
            maxsplit=1,
        )[0]
        self.assertNotIn("secrets.", deploy_header)

    def test_runtime_transfer_replaces_read_only_previous_config(self):
        workflow = WORKFLOW.read_text()
        runtime_transfer = workflow.split(
            '--directory "${RUNNER_TEMP}/runtime"',
            maxsplit=1,
        )[1].split("          printf", maxsplit=1)[0]

        self.assertIn("--unlink-first", runtime_transfer)


if __name__ == "__main__":
    unittest.main()
