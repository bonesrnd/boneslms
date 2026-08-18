import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

STAGING_DIR = Path(__file__).resolve().parent.parent
RENDERER = STAGING_DIR / "bin" / "render-config.py"
EXAMPLE_ENV = STAGING_DIR / "secrets" / "staging.env.example"


class RenderConfigTest(unittest.TestCase):
    def run_renderer(
        self,
        env_file: Path,
        config_dir: Path,
        secret_dir: Path,
        environment: dict[str, str] | None = None,
    ):
        return subprocess.run(
            [
                str(RENDERER),
                "--env-file",
                str(env_file),
                "--config-dir",
                str(config_dir),
                "--secret-dir",
                str(secret_dir),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "RESEND_API_KEY": "re_test_default",
                **(environment or {}),
            },
        )

    def test_renders_private_yaml_and_runtime_secret_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            secret_dir = root / "secrets"
            result = self.run_renderer(EXAMPLE_ENV, config_dir, secret_dir)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(list(config_dir.glob("*.yml"))), 13)
            self.assertEqual(
                (secret_dir / "rce_ecosystem_key").read_text(),
                "00000000000000000000000000000000",
            )
            self.assertEqual(
                (config_dir / "database_ca.crt").read_text(),
                "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n",
            )
            for path in [*config_dir.iterdir(), *secret_dir.iterdir()]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)

    def test_quotes_values_instead_of_emitting_yaml_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "runtime.env"
            env_file.write_text(
                EXAMPLE_ENV.read_text().replace(
                    "replace-with-managed-database-user-password",
                    'value: with # yaml "syntax"',
                )
            )
            result = self.run_renderer(env_file, root / "config", root / "secrets")

            self.assertEqual(result.returncode, 0, result.stderr)
            database_config = (root / "config" / "database.yml").read_text()
            self.assertIn(
                'password: "value: with # yaml \\"syntax\\""',
                database_config,
            )

    def test_rejects_multiline_secret_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "runtime.env"
            env_file.write_text(EXAMPLE_ENV.read_text() + 'EXTRA="line\\nvalue"\n')
            result = self.run_renderer(env_file, root / "config", root / "secrets")

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must be a single-line value", result.stderr)

    def test_reads_the_resend_key_from_the_deployment_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "runtime.env"
            env_file.write_text(EXAMPLE_ENV.read_text())
            result = self.run_renderer(
                env_file,
                root / "config",
                root / "secrets",
                {"RESEND_API_KEY": "re_environment_secret"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            outgoing_mail = (root / "config" / "outgoing_mail.yml").read_text()
            self.assertIn('password: "re_environment_secret"', outgoing_mail)


if __name__ == "__main__":
    os.umask(0o077)
    unittest.main()
