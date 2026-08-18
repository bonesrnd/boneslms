#!/usr/bin/env bash
set -Eeuo pipefail

image_ref="${1:?Usage: deploy.sh <ghcr-image@sha256:digest>}"
release_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root_dir="${BONESLMS_ROOT:-/opt/boneslms}"
config_dir="${root_dir}/shared/config"
secret_dir="${root_dir}/shared/secrets"
current_link="${root_dir}/current"
release_env="${release_dir}/release.env"
runtime_gid=9999

if [[ ! "${image_ref}" =~ ^ghcr\.io/.+@sha256:[a-f0-9]{64}$ ]]; then
  echo "The deployment image must be an immutable GHCR digest reference" >&2
  exit 1
fi

for path in "${config_dir}" "${secret_dir}"; do
  if [[ ! -d "${path}" ]]; then
    echo "Missing deployment directory: ${path}" >&2
    exit 1
  fi
done

umask 077
printf 'CANVAS_IMAGE=%s\nCONFIG_DIR=%s\nSECRET_DIR=%s\n' \
  "${image_ref}" "${config_dir}" "${secret_dir}" >"${release_env}"

compose=(
  docker compose
  --project-name boneslms
  --file "${release_dir}/compose.yaml"
  --env-file "${release_env}"
)

previous_release=""
if [[ -L "${current_link}" ]]; then
  previous_release="$(readlink -f "${current_link}")"
fi
deployment_started=false

prepare_runtime_permissions() {
  docker run --rm \
    --user 0:0 \
    --entrypoint /bin/sh \
    --volume "${config_dir}:/runtime-config" \
    --volume "${secret_dir}:/runtime-secrets" \
    --env "RUNTIME_GID=${runtime_gid}" \
    "${image_ref}" -ceu '
      set -- /runtime-config/*.yml /runtime-config/database_ca.crt
      if [ ! -f "$1" ]; then
        echo "No rendered Canvas configuration files were found" >&2
        exit 1
      fi
      chgrp "${RUNTIME_GID}" /runtime-config "$@"
      chmod 0750 /runtime-config
      chmod 0440 "$@"
      for path in \
        /runtime-secrets/rce_ecosystem_key \
        /runtime-secrets/rce_ecosystem_secret; do
        if [ ! -f "${path}" ]; then
          echo "Missing RCE runtime secret: ${path}" >&2
          exit 1
        fi
        chgrp "${RUNTIME_GID}" "${path}"
        chmod 0440 "${path}"
      done
    '
}

rollback() {
  local status=$?
  if [[ "${deployment_started}" == "true" ]]; then
    if [[ -n "${previous_release}" && -r "${previous_release}/release.env" ]]; then
      echo "Deployment failed; restoring ${previous_release}" >&2
      local previous_compose=(
        docker compose
        --project-name boneslms
        --file "${previous_release}/compose.yaml"
        --env-file "${previous_release}/release.env"
      )
      "${previous_compose[@]}" run --rm --no-deps brandable-css-init
      "${previous_compose[@]}" up --detach --remove-orphans
    else
      echo "Initial deployment failed; stopping the failed release" >&2
      "${compose[@]}" down --remove-orphans
    fi
  fi
  exit "${status}"
}
trap rollback ERR

"${compose[@]}" config --quiet
"${compose[@]}" pull
prepare_runtime_permissions
"${release_dir}/bin/bootstrap-database.sh" "${secret_dir}"

if "${compose[@]}" run --rm web \
  bundle exec rails runner 'exit(Account.default.present? ? 0 : 1)'; then
  "${compose[@]}" run --rm web bundle exec rails db:migrate:predeploy
else
  "${compose[@]}" \
    --file "${release_dir}/initial-setup.override.yaml" \
    run --rm web bundle exec rails db:initial_setup
fi

deployment_started=true
"${compose[@]}" run --rm --no-deps brandable-css-init
"${compose[@]}" up --detach --remove-orphans --wait --wait-timeout 300

ready=false
for _ in $(seq 1 60); do
  if curl --fail --silent --show-error \
    --header "Host: canvas.bonesrnd.com" \
    --header "X-Forwarded-Proto: https" \
    "http://127.0.0.1:8080/readiness" >/dev/null &&
    curl --fail --silent --show-error \
      "http://127.0.0.1:3000/readiness" >/dev/null; then
    ready=true
    break
  fi
  sleep 5
done

if [[ "${ready}" != "true" ]]; then
  echo "Canvas or RCE failed its readiness check" >&2
  "${compose[@]}" ps >&2
  exit 1
fi

ln -sfn "${release_dir}" "${current_link}"
trap - ERR

if ! "${compose[@]}" run --rm web bundle exec rails "db:migrate:tagged[postdeploy]"; then
  echo "Postdeploy migration failed; the new release remains active for forward repair" >&2
  exit 1
fi

"${compose[@]}" ps
echo "Deployed ${image_ref}"
