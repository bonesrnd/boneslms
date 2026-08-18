#!/usr/bin/env python3
"""Render production Canvas configuration without evaluating shell input."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import tempfile
from pathlib import Path

MARKER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
REQUIRED = {
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
    "RESEND_API_KEY",
    "SPACES_ACCESS_KEY_ID",
    "SPACES_BUCKET_NAME",
    "SPACES_SECRET_ACCESS_KEY",
}


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"{path}:{number}: expected KEY=value")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"{path}:{number}: invalid key {key!r}")
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = json.loads(value)
        elif len(value) >= 2 and value[0] == value[-1] == "'":
            value = value[1:-1].replace("'\\''", "'")
        values[key] = value
    return values


def validate(values: dict[str, str]) -> None:
    missing = sorted(key for key in REQUIRED if not values.get(key))
    if missing:
        raise ValueError(f"missing required values: {', '.join(missing)}")
    if len(values["CANVAS_ENCRYPTION_KEY"]) < 20:
        raise ValueError("CANVAS_ENCRYPTION_KEY must contain at least 20 characters")
    if len(values["CANVAS_JWT_ENCRYPTION_KEY"]) != 64:
        raise ValueError("CANVAS_JWT_ENCRYPTION_KEY must contain exactly 64 characters")
    if len(values["CANVAS_LMS_ADMIN_PASSWORD"]) < 16:
        raise ValueError("CANVAS_LMS_ADMIN_PASSWORD must contain at least 16 characters")
    for key in ("RCE_ECOSYSTEM_KEY", "RCE_ECOSYSTEM_SECRET"):
        if len(values[key].encode("utf-8")) != 32:
            raise ValueError(f"{key} must contain exactly 32 bytes")
    port = int(values["DATABASE_PORT"])
    if not 1 <= port <= 65535:
        raise ValueError("DATABASE_PORT must be between 1 and 65535")
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} must be a single-line value")
    decode_database_ca(values["DATABASE_CA_CERT_BASE64"])


def decode_database_ca(value: str) -> str:
    try:
        certificate = base64.b64decode(value, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("DATABASE_CA_CERT_BASE64 must contain base64-encoded ASCII") from error
    if not (
        certificate.startswith("-----BEGIN CERTIFICATE-----\n")
        and certificate.rstrip().endswith("-----END CERTIFICATE-----")
    ):
        raise ValueError("DATABASE_CA_CERT_BASE64 must contain a PEM certificate")
    return certificate


def atomic_write(path: Path, content: str, mode: int = 0o400) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary_path = Path(handle.name)
    temporary_path.chmod(mode)
    temporary_path.replace(path)


def render_templates(
    template_dir: Path, config_dir: Path, values: dict[str, str]
) -> None:
    templates = sorted(template_dir.glob("*.yml.tmpl"))
    if not templates:
        raise ValueError(f"no templates found in {template_dir}")
    for template in templates:
        source = template.read_text(encoding="utf-8")
        markers = set(MARKER.findall(source))
        unknown = sorted(markers - values.keys())
        if unknown:
            raise ValueError(f"{template}: missing values for {', '.join(unknown)}")
        rendered = MARKER.sub(lambda match: json.dumps(values[match.group(1)]), source)
        unresolved = MARKER.findall(rendered)
        if unresolved:
            raise ValueError(f"{template}: unresolved template markers remain")
        atomic_write(config_dir / template.name.removesuffix(".tmpl"), rendered)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--secret-dir", type=Path, required=True)
    args = parser.parse_args()

    os.umask(0o077)
    values = parse_dotenv(args.env_file)
    if resend_api_key := os.environ.get("RESEND_API_KEY"):
        values["RESEND_API_KEY"] = resend_api_key
    validate(values)
    template_dir = Path(__file__).resolve().parent.parent / "config"
    render_templates(template_dir, args.config_dir, values)
    atomic_write(
        args.config_dir / "database_ca.crt",
        decode_database_ca(values["DATABASE_CA_CERT_BASE64"]),
    )
    atomic_write(args.secret_dir / "rce_ecosystem_key", values["RCE_ECOSYSTEM_KEY"])
    atomic_write(
        args.secret_dir / "rce_ecosystem_secret", values["RCE_ECOSYSTEM_SECRET"]
    )
    database_bootstrap_keys = (
        "DATABASE_CA_CERT_BASE64",
        "DATABASE_ADMIN_PASSWORD",
        "DATABASE_ADMIN_USERNAME",
        "DATABASE_HOST",
        "DATABASE_NAME",
        "DATABASE_PORT",
        "DATABASE_USERNAME",
    )
    atomic_write(
        args.secret_dir / "database_bootstrap.env",
        "".join(f"{key}={values[key]}\n" for key in database_bootstrap_keys),
    )
    initial_setup_keys = (
        "CANVAS_LMS_ACCOUNT_NAME",
        "CANVAS_LMS_ADMIN_EMAIL",
        "CANVAS_LMS_ADMIN_PASSWORD",
    )
    atomic_write(
        args.secret_dir / "initial_setup.env",
        "".join(f"{key}={values[key]}\n" for key in initial_setup_keys)
        + "CANVAS_LMS_STATS_COLLECTION=opt_out\n",
    )
    print(f"Rendered {len(list(template_dir.glob('*.yml.tmpl')))} config files")


if __name__ == "__main__":
    main()
