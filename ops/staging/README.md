# Bones LMS staging

This directory defines a production-like Bones LMS staging environment:

- Canvas and the RCE API run as pinned containers on one Ubuntu 24.04 Droplet.
- PostgreSQL 16 and attachment storage are managed by DigitalOcean.
- Redis runs locally with an append-only volume.
- Cloudflare Tunnel is the only ingress path for Canvas, RCE, and SSH.
- Cloudflare Access protects Canvas and SSH. RCE remains publicly reachable and
  relies on Canvas-signed requests; only the app host bypasses Access for RCE
  proxy calls.
- `files.bonesrnd.com` is a separate, cookie-isolated Canvas file host routed
  through the tunnel.
- Resend provides mandatory-STARTTLS SMTP delivery from
  `notifications@bonesrnd.com`.
- OpenTofu owns infrastructure, SOPS/age owns runtime secrets, and GitHub
  Actions builds and deploys immutable GHCR digests.

The default sizes create paid DigitalOcean resources in `nyc3`. Review the
OpenTofu plan before approving it.

This environment is approved for synthetic data only. Do not restore production
users, courses, submissions, or credentials into staging.

## Prerequisites

Install `opentofu`, `sops`, `age`, `gh`, `doctl`, and `cloudflared`, then
authenticate:

```bash
gh auth login
```

The Cloudflare token needs permission to manage DNS, Tunnels, Access
applications, policies, and service tokens, plus read identity providers for
`bonesrnd.com`.

Keep bootstrap API tokens out of shell history by writing them to the ignored
`ops/staging/.credentials.env` with mode `0600`:

```dotenv
DIGITALOCEAN_TOKEN=...
CLOUDFLARE_API_TOKEN=...
RESEND_BOOTSTRAP_API_KEY=...
```

Load this file only for provisioning commands, and delete it after staging is
launched. The Resend bootstrap key needs full access to configure the sending
domain; use a domain-scoped sending key for the GitHub `RESEND_API_KEY` secret.

```bash
set -a
. ops/staging/.credentials.env
set +a
```

The project age identity is stored outside the repository at:

```text
~/Library/Application Support/sops/age/keys.txt
```

Back this file up in a password manager. Losing it makes the committed SOPS
file unrecoverable.

## 1. Bootstrap remote state

```bash
tofu -chdir=ops/staging/infra/bootstrap init
ops/staging/bin/with-temporary-spaces-key \
  tofu -chdir=ops/staging/infra/bootstrap apply \
  -var='state_bucket_name=<globally-unique-private-bucket>'
```

DigitalOcean requires a full-access Spaces key to create or configure buckets.
The wrapper creates one only for the duration of the command and deletes it on
exit. OpenTofu creates a separate bucket-scoped key for the state backend.

Store the two sensitive Spaces outputs securely, then export them for the S3
backend:

```bash
export AWS_ACCESS_KEY_ID="$(tofu -chdir=ops/staging/infra/bootstrap output -raw tofu_spaces_access_key_id)"
export AWS_SECRET_ACCESS_KEY="$(tofu -chdir=ops/staging/infra/bootstrap output -raw tofu_spaces_secret_access_key)"
cp ops/staging/infra/main/backend.hcl.example ops/staging/infra/main/backend.hcl
```

Set the bucket name in `backend.hcl`. The main backend uses S3 lock files to
serialize state changes. The one-time bootstrap state remains local and
contains the bucket-scoped Spaces secret; back it up in an encrypted password
manager, never commit it, and do not run bootstrap concurrently.

## 2. Provision staging

Copy `terraform.tfvars.example` to the ignored `terraform.tfvars`, then set the
Cloudflare account, zone, existing One-Time PIN identity-provider ID, and a
single administrator `/32` or `/128`. Set `enable_bootstrap_ssh_ingress = true`
only while validating a new host.

```bash
tofu -chdir=ops/staging/infra/main init \
  -backend-config=backend.hcl
ops/staging/bin/with-temporary-spaces-key \
  tofu -chdir=ops/staging/infra/main plan
ops/staging/bin/with-temporary-spaces-key \
  tofu -chdir=ops/staging/infra/main apply
```

The apply creates the VPC, pre-attached firewall, Droplet, managed database,
private Spaces bucket, Cloudflare Tunnel and DNS records, Access policies,
service token, SSH keys, managed-database CA, and generated Canvas/RCE secrets.
Destructive changes to the database and storage buckets are blocked with
`prevent_destroy`.

Verify `cloud-init status --long` reports `status: done` and
`extended_status: done`, then set `enable_bootstrap_ssh_ingress = false` and
apply again through the wrapper. The DigitalOcean firewall must have no inbound
rules after bootstrap; operational SSH goes only through Cloudflare Access.

The Droplet lifecycle ignores `user_data` after creation because cloud-init is
first-boot configuration and replacing the host destroys its local Docker
volumes. It also ignores the provider's false backup drift for DigitalOcean's
current daily backup API. Use an explicit reviewed
`-replace=digitalocean_droplet.app` only when intentionally rebuilding the
host.

## 3. Encrypt runtime outputs

After a successful apply:

```bash
ops/staging/bin/encrypt-secrets.py
sops filestatus --input-type dotenv ops/staging/secrets/staging.env.sops
```

The script streams sensitive OpenTofu output directly into SOPS. It does not
write an intermediate plaintext file. Commit `staging.env.sops`; never commit a
decrypted `.env`.

The Resend API key is intentionally excluded from the SOPS file so it can be
rotated independently as a GitHub staging environment secret.

## 4. Configure the GitHub staging environment

Create a `staging` environment in `bonesrnd/boneslms` and add a required
reviewer before allowing deployments. Configure these variables:

```bash
tofu -chdir=ops/staging/infra/main output -raw canvas_url |
  gh variable set CANVAS_URL --env staging
tofu -chdir=ops/staging/infra/main output -raw rce_url |
  gh variable set RCE_URL --env staging
tofu -chdir=ops/staging/infra/main output -raw ssh_hostname |
  gh variable set SSH_HOSTNAME --env staging
```

Configure these environment secrets without printing their values:

```bash
tofu -chdir=ops/staging/infra/main output -raw ssh_private_key |
  gh secret set SSH_PRIVATE_KEY --env staging
tofu -chdir=ops/staging/infra/main output -raw ssh_known_hosts |
  gh secret set SSH_KNOWN_HOSTS --env staging
tofu -chdir=ops/staging/infra/main output -raw cloudflare_access_client_id |
  gh secret set CF_ACCESS_CLIENT_ID --env staging
tofu -chdir=ops/staging/infra/main output -raw cloudflare_access_client_secret |
  gh secret set CF_ACCESS_CLIENT_SECRET --env staging
gh secret set SOPS_AGE_KEY --env staging \
  <"$HOME/Library/Application Support/sops/age/keys.txt"
printf '%s' "$RESEND_API_KEY" |
  gh secret set RESEND_API_KEY --env staging
```

## 5. Deploy

A push to `prod` runs `.github/workflows/staging.yml`. The workflow:

1. Builds `Dockerfile.production` for `linux/amd64`.
2. Pushes the image, SBOM, and provenance to GHCR.
3. Passes the immutable image digest to the protected deploy job.
4. Decrypts and renders private config on the ephemeral runner.
5. Connects through Cloudflare Access with strict SSH host verification.
6. Runs predeploy migrations, replaces services, checks readiness, then runs
   tagged postdeploy migrations.

The deployment restores the previous image and release-specific theme assets if
service startup or readiness fails. Once the new release becomes current,
postdeploy migrations are forward-only: a failure leaves the new image active
for forward repair rather than restoring an incompatible old image.

## Operations

On the server, the active release is `/opt/boneslms/current`, private config is
under `/opt/boneslms/shared`, and persistent Docker volumes hold Redis data,
logs, temporary Canvas files, and generated theme assets.

Useful checks:

```bash
docker compose \
  --project-name boneslms \
  --file /opt/boneslms/current/compose.yaml \
  --env-file /opt/boneslms/current/release.env ps
curl --fail --header 'Host: canvas.bonesrnd.com' \
  --header 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8080/readiness
curl --fail http://127.0.0.1:3000/readiness
systemctl status boneslms-tunnel
```

DigitalOcean database backups and Spaces bucket versioning protect durable
data. Test database and attachment restores before treating the environment as
production-ready.

## Local validation

```bash
python3 -m unittest discover -s ops/staging/tests -p 'test_*.py' -v
shellcheck ops/staging/bin/*.sh ops/staging/bin/with-temporary-spaces-key
actionlint .github/workflows/staging.yml
tofu -chdir=ops/staging/infra/bootstrap validate
tofu -chdir=ops/staging/infra/main validate
```
