import re
import unittest
from pathlib import Path

STAGING_DIR = Path(__file__).resolve().parent.parent
CLOUD_INIT = STAGING_DIR / "infra" / "main" / "cloud-init.yaml.tftpl"
CLOUDFLARE = STAGING_DIR / "infra" / "main" / "cloudflare.tf"
COMPUTE = STAGING_DIR / "infra" / "main" / "compute.tf"
DATABASE = STAGING_DIR / "infra" / "main" / "database.tf"
MAIN_VERSIONS = STAGING_DIR / "infra" / "main" / "versions.tf"
STORAGE = STAGING_DIR / "infra" / "main" / "storage.tf"
VARIABLES = STAGING_DIR / "infra" / "main" / "variables.tf"
BACKEND = STAGING_DIR / "infra" / "main" / "backend.hcl.example"
BOOTSTRAP_MAIN = STAGING_DIR / "infra" / "bootstrap" / "main.tf"
BOOTSTRAP_VERSIONS = STAGING_DIR / "infra" / "bootstrap" / "versions.tf"
TEMPORARY_SPACES_KEY = STAGING_DIR / "bin" / "with-temporary-spaces-key"


class InfrastructureTest(unittest.TestCase):
    def test_cloud_init_provisions_host_keys_in_the_ssh_module(self):
        template = CLOUD_INIT.read_text()

        self.assertIn("ssh_keys:", template)
        self.assertIn("ed25519_private: |", template)
        self.assertIn("ssh_genkeytypes: [ed25519]", template)
        self.assertNotIn("path: /etc/ssh/ssh_host_ed25519_key", template)

    def test_cloudflared_can_read_its_token(self):
        template = CLOUD_INIT.read_text()
        token_file = template.split(
            "- path: ${cloudflared_tokenfile}",
            maxsplit=1,
        )[1].split("- path:", maxsplit=1)[0]

        self.assertIn("owner: root:root", token_file)
        self.assertNotIn("owner: 65532:65532", token_file)
        self.assertIn("permissions: \"0600\"", token_file)
        self.assertIn("chown 65532:65532 ${cloudflared_tokenfile}", template)
        self.assertIn("tunnel --protocol http2 run", template)

    def test_firewall_exists_before_and_targets_only_the_app(self):
        configuration = COMPUTE.read_text()

        self.assertIn('resource "digitalocean_tag" "app_firewall"', configuration)
        self.assertIn("depends_on = [digitalocean_firewall.app]", configuration)
        self.assertNotIn("droplet_ids =", configuration)
        self.assertIn("tags = [digitalocean_tag.app_firewall.id]", configuration)

    def test_first_boot_and_backup_api_drift_do_not_replace_the_app(self):
        droplet = COMPUTE.read_text().split(
            'resource "digitalocean_droplet" "app"',
            maxsplit=1,
        )[1].split('resource "digitalocean_firewall"', maxsplit=1)[0]

        self.assertRegex(
            droplet,
            r"ignore_changes\s*=\s*\[\s*backups,\s*user_data,\s*\]",
        )

    def test_remote_state_is_locked_and_bucket_scoped(self):
        self.assertRegex(BACKEND.read_text(), r"use_lockfile\s*=\s*true")
        bootstrap = BOOTSTRAP_MAIN.read_text()
        self.assertIn("bucket     = digitalocean_spaces_bucket.state.name", bootstrap)
        self.assertIn('permission = "readwrite"', bootstrap)
        self.assertNotIn('permission = "fullaccess"', bootstrap)
        for versions in (MAIN_VERSIONS, BOOTSTRAP_VERSIONS):
            self.assertIn('required_version = ">= 1.11.0"', versions.read_text())

    def test_spaces_management_uses_an_ephemeral_full_access_key(self):
        self.assertTrue(TEMPORARY_SPACES_KEY.exists())
        script = TEMPORARY_SPACES_KEY.read_text()

        self.assertIn("permission=fullaccess", script)
        self.assertIn("trap cleanup EXIT", script)
        self.assertIn("spaces keys delete", script)
        self.assertIn("export SPACES_ACCESS_KEY_ID", script)
        self.assertIn("export SPACES_SECRET_ACCESS_KEY", script)
        self.assertIn('"$@"', script)

    def test_managed_database_ca_is_provisioned(self):
        self.assertIn(
            'data "digitalocean_database_ca" "postgres"',
            DATABASE.read_text(),
        )

    def test_database_user_ignores_provider_empty_settings_drift(self):
        database_user = DATABASE.read_text().split(
            'resource "digitalocean_database_user" "canvas"',
            maxsplit=1,
        )[1]

        self.assertIn("ignore_changes = [settings]", database_user)

    def test_spaces_cors_uses_the_dedicated_resource(self):
        configuration = STORAGE.read_text()

        self.assertIn(
            'resource "digitalocean_spaces_bucket_cors_configuration" "files"',
            configuration,
        )
        bucket = configuration.split(
            'resource "digitalocean_spaces_bucket" "files"',
            maxsplit=1,
        )[1].split("resource ", maxsplit=1)[0]
        self.assertNotIn("cors_rule", bucket)

    def test_bootstrap_ssh_is_restricted_to_an_explicit_cidr(self):
        cloud_init = CLOUD_INIT.read_text()
        compute = COMPUTE.read_text()
        variables = VARIABLES.read_text()

        self.assertIn("sudo: ALL=(ALL) NOPASSWD:ALL", cloud_init)
        self.assertIn(
            "ufw allow from ${bootstrap_ssh_cidr} to any port 22 proto tcp",
            cloud_init,
        )
        self.assertLess(
            cloud_init.index(
                "ufw allow from ${bootstrap_ssh_cidr} to any port 22 proto tcp"
            ),
            cloud_init.index("ufw --force enable"),
        )
        self.assertIn('dynamic "inbound_rule"', compute)
        self.assertIn("var.enable_bootstrap_ssh_ingress", compute)
        self.assertIn("source_addresses = [var.bootstrap_ssh_cidr]", compute)
        self.assertIn('variable "bootstrap_ssh_cidr"', variables)
        self.assertIn('variable "enable_bootstrap_ssh_ingress"', variables)

    def test_ssh_access_allows_admins_and_deployment_automation(self):
        configuration = CLOUDFLARE.read_text()
        ssh_application = configuration.split(
            'resource "cloudflare_zero_trust_access_application" "ssh"',
            maxsplit=1,
        )[1]

        self.assertIn("cloudflare_zero_trust_access_policy.admin.id", ssh_application)
        self.assertIn(
            "cloudflare_zero_trust_access_policy.github.id",
            ssh_application,
        )

    def test_canvas_access_bypasses_only_the_app_host(self):
        configuration = CLOUDFLARE.read_text()

        self.assertIn(
            'resource "cloudflare_zero_trust_access_policy" "app_origin"',
            configuration,
        )

    def test_cloudflare_reuses_the_builtin_otp_provider(self):
        configuration = CLOUDFLARE.read_text()

        self.assertIn(
            'data "cloudflare_zero_trust_access_identity_provider" "otp"',
            configuration,
        )
        self.assertNotIn(
            'resource "cloudflare_zero_trust_access_identity_provider" "otp"',
            configuration,
        )
        self.assertIn("digitalocean_droplet.app.ipv4_address", configuration)
        self.assertIn("digitalocean_droplet.app.ipv6_address", configuration)

    def test_files_domain_routes_through_the_tunnel(self):
        configuration = CLOUDFLARE.read_text()

        self.assertIn("local.files_hostname", configuration)
        self.assertIn('resource "cloudflare_dns_record" "files"', configuration)


if __name__ == "__main__":
    unittest.main()
