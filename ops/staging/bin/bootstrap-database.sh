#!/usr/bin/env bash
set -euo pipefail

secret_dir="${1:-/opt/boneslms/shared/secrets}"
env_file="${secret_dir}/database_bootstrap.env"

if [[ ! -r "${env_file}" ]]; then
  echo "Missing database bootstrap environment: ${env_file}" >&2
  exit 1
fi

docker run --rm \
  --env-file "${env_file}" \
  postgres:16-alpine@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685 \
  sh -ceu '
    ca_file="$(mktemp)"
    trap '"'"'rm -f "${ca_file}"'"'"' EXIT
    printf "%s" "${DATABASE_CA_CERT_BASE64}" | base64 -d >"${ca_file}"
    chmod 0400 "${ca_file}"
    export PGPASSWORD="${DATABASE_ADMIN_PASSWORD}"
    psql \
      "host=${DATABASE_HOST} port=${DATABASE_PORT} dbname=${DATABASE_NAME} user=${DATABASE_ADMIN_USERNAME} sslmode=verify-full sslrootcert=${ca_file}" \
      --set ON_ERROR_STOP=1 \
      --set app_user="${DATABASE_USERNAME}" \
      --set db_name="${DATABASE_NAME}" <<'"'"'SQL'"'"'
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
SELECT format('"'"'GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I'"'"', :'"'"'db_name'"'"', :'"'"'app_user'"'"') \gexec
SELECT format('"'"'GRANT USAGE, CREATE ON SCHEMA public TO %I'"'"', :'"'"'app_user'"'"') \gexec
SQL
  '
