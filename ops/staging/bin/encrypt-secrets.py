#!/usr/bin/env python3
"""Encrypt OpenTofu runtime outputs for the staging deployment."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

STAGING_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = STAGING_DIR.parent.parent
DEFAULT_TOFU_DIR = STAGING_DIR / "infra" / "main"
DEFAULT_OUTPUT = STAGING_DIR / "secrets" / "staging.env.sops"
REQUIRED_RUNTIME_KEYS = {
    "CANVAS_ENCRYPTION_KEY",
    "CANVAS_JWT_ENCRYPTION_KEY",
    "CANVAS_LMS_ACCOUNT_NAME",
    "CANVAS_LMS_ADMIN_EMAIL",
    "CANVAS_LMS_ADMIN_PASSWORD",
    "DATABASE_CA_CERT_BASE64",
    "DATABASE_ADMIN_PASSWORD",
    "DATABASE_ADMIN_USERNAME",
    "DATABASE_HOST",
    "DATABASE_NAME",
    "DATABASE_PASSWORD",
    "DATABASE_PORT",
    "DATABASE_USERNAME",
    "RCE_ECOSYSTEM_KEY",
    "RCE_ECOSYSTEM_SECRET",
    "SPACES_ACCESS_KEY_ID",
    "SPACES_BUCKET_NAME",
    "SPACES_SECRET_ACCESS_KEY",
}


def load_runtime_secrets(args: argparse.Namespace) -> dict[str, str]:
    if args.runtime_secrets_json:
        raw = args.runtime_secrets_json.read_text(encoding="utf-8")
    else:
        result = subprocess.run(
            [
                "tofu",
                f"-chdir={args.tofu_dir}",
                "output",
                "-json",
                "runtime_secrets",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise ValueError(result.stderr.strip() or "Unable to read OpenTofu outputs")
        raw = result.stdout

    values = json.loads(raw)
    if not isinstance(values, dict):
        raise ValueError("runtime_secrets must be a JSON object")
    invalid = sorted(
        key for key, value in values.items() if not isinstance(key, str) or not isinstance(value, str)
    )
    if invalid:
        raise ValueError(f"runtime_secrets contains non-string values: {', '.join(invalid)}")
    missing = sorted(key for key in REQUIRED_RUNTIME_KEYS if not values.get(key))
    if missing:
        raise ValueError(f"runtime_secrets is missing: {', '.join(missing)}")
    return values


def serialize_dotenv(values: dict[str, str]) -> str:
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} must be a single-line value")
    return "".join(f"{key}={json.dumps(values[key])}\n" for key in sorted(values))


def encrypt(plaintext: str, output: Path) -> None:
    try:
        filename_override = output.resolve().relative_to(REPOSITORY_ROOT)
    except ValueError:
        filename_override = Path("ops/staging/secrets/staging.env.sops")

    result = subprocess.run(
        [
            "sops",
            "--encrypt",
            "--input-type",
            "dotenv",
            "--output-type",
            "dotenv",
            "--filename-override",
            str(filename_override),
            "/dev/stdin",
        ],
        input=plaintext,
        check=False,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "SOPS encryption failed")

    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output.parent,
        delete=False,
    ) as handle:
        handle.write(result.stdout)
        handle.flush()
        os.fsync(handle.fileno())
        temporary_path = Path(handle.name)
    temporary_path.chmod(0o600)
    temporary_path.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tofu-dir", type=Path, default=DEFAULT_TOFU_DIR)
    parser.add_argument("--runtime-secrets-json", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    os.umask(0o077)
    values = load_runtime_secrets(args)
    encrypt(serialize_dotenv(values), args.output)
    print(f"Encrypted staging secrets to {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
