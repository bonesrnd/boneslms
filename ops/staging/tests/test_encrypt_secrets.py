import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STAGING_DIR = Path(__file__).resolve().parent.parent
ENCRYPTOR = STAGING_DIR / "bin" / "encrypt-secrets.py"

RUNTIME_SECRETS = {
    "CANVAS_ENCRYPTION_KEY": "a" * 64,
    "CANVAS_JWT_ENCRYPTION_KEY": "b" * 64,
    "CANVAS_LMS_ACCOUNT_NAME": "Bones LMS",
    "CANVAS_LMS_ADMIN_EMAIL": "bones@bonesrnd.com",
    "CANVAS_LMS_ADMIN_PASSWORD": "c" * 32,
    "DATABASE_CA_CERT_BASE64": (
        "LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCnRlc3QK"
        "LS0tLS1FTkQgQ0VSVElGSUNBVEUtLS0tLQo="
    ),
    "DATABASE_ADMIN_PASSWORD": "d" * 32,
    "DATABASE_ADMIN_USERNAME": "doadmin",
    "DATABASE_HOST": "private-database.example.com",
    "DATABASE_NAME": "canvas_production",
    "DATABASE_PASSWORD": "e" * 32,
    "DATABASE_PORT": "25060",
    "DATABASE_USERNAME": "canvas",
    "RCE_ECOSYSTEM_KEY": "f" * 32,
    "RCE_ECOSYSTEM_SECRET": "g" * 32,
    "SPACES_ACCESS_KEY_ID": "spaces-access-key",
    "SPACES_BUCKET_NAME": "boneslms-staging-files",
    "SPACES_SECRET_ACCESS_KEY": "spaces-secret-key",
}


class EncryptSecretsTest(unittest.TestCase):
    def run_encryptor(
        self,
        root: Path,
        runtime_secrets: dict[str, str] | None = None,
    ):
        runtime_json = root / "runtime.json"
        runtime_json.write_text(json.dumps(runtime_secrets or RUNTIME_SECRETS))
        output = root / "staging.env.sops"
        fake_bin = root / "bin"
        fake_bin.mkdir()
        fake_sops = fake_bin / "sops"
        fake_sops.write_text(
            """#!/usr/bin/env python3
import sys

plaintext = sys.stdin.read()
required = ("DATABASE_PASSWORD", "CANVAS_ENCRYPTION_KEY")
if not all(f"{key}=" in plaintext for key in required):
    raise SystemExit(1)
if "RESEND_API_KEY=" in plaintext:
    raise SystemExit(1)
sys.stdout.write("encrypted-by-sops\\n")
"""
        )
        fake_sops.chmod(0o700)
        env = {
            **os.environ,
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        }
        env.pop("RESEND_API_KEY", None)
        result = subprocess.run(
            [
                sys.executable,
                str(ENCRYPTOR),
                "--runtime-secrets-json",
                str(runtime_json),
                "--output",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        return result, output

    def test_encrypts_runtime_output_without_writing_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            result, output = self.run_encryptor(Path(directory))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_text(), "encrypted-by-sops\n")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertNotIn(RUNTIME_SECRETS["DATABASE_PASSWORD"], output.read_text())

    def test_requires_every_opentofu_runtime_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime_secrets = dict(RUNTIME_SECRETS)
            runtime_secrets.pop("DATABASE_PASSWORD")
            result, output = self.run_encryptor(Path(directory), runtime_secrets)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DATABASE_PASSWORD", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
