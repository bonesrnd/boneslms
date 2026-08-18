import json
import re
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_JSON = REPOSITORY_ROOT / "package.json"
YARN_LOCK = REPOSITORY_ROOT / "yarn.lock"
GEMFILE_LOCK = REPOSITORY_ROOT / "Gemfile.lock"
DOCKERFILE = REPOSITORY_ROOT / "Dockerfile.production"
DOCKERFILE_TEMPLATE = REPOSITORY_ROOT / "build" / "Dockerfile.template"
DEPLOY_SCRIPT = REPOSITORY_ROOT / "ops" / "staging" / "bin" / "deploy.sh"
COMPOSE_FILE = REPOSITORY_ROOT / "ops" / "staging" / "compose.yaml"
DATABASE_BOOTSTRAP = (
    REPOSITORY_ROOT / "ops" / "staging" / "bin" / "bootstrap-database.sh"
)
DATABASE_CONFIG = (
    REPOSITORY_ROOT / "ops" / "staging" / "config" / "database.yml.tmpl"
)
DOMAIN_CONFIG = REPOSITORY_ROOT / "ops" / "staging" / "config" / "domain.yml.tmpl"
OUTGOING_MAIL = (
    REPOSITORY_ROOT / "ops" / "staging" / "config" / "outgoing_mail.yml.tmpl"
)


class ReleaseImageTest(unittest.TestCase):
    def test_mediaelement_uses_an_immutable_archive(self):
        package = json.loads(PACKAGE_JSON.read_text())
        dependency = package["dependencies"]["mediaelement"]
        lockfile = YARN_LOCK.read_text()

        self.assertRegex(
            dependency,
            re.compile(
                r"^https://codeload\.github\.com/instructure/mediaelement/"
                r"tar\.gz/[0-9a-f]{40}$"
            ),
        )
        self.assertIn(f'"mediaelement@{dependency}":', lockfile)
        self.assertNotIn(
            "https://github.com/instructure/mediaelement.git",
            PACKAGE_JSON.read_text() + lockfile,
        )

    def test_discovery_page_alert_dependency_is_locked(self):
        package = json.loads(PACKAGE_JSON.read_text())
        lockfile = YARN_LOCK.read_text()

        self.assertEqual(
            package["dependencies"].get("@instructure/platform-alerts"),
            "0.2.0",
        )
        self.assertIn('"@instructure/platform-alerts@0.2.0":', lockfile)

    def test_production_image_installs_the_locked_bundler_version(self):
        locked_version = re.search(
            r"\nBUNDLED WITH\n\s+([^\s]+)\s*$",
            GEMFILE_LOCK.read_text(),
        ).group(1)

        for path in (DOCKERFILE, DOCKERFILE_TEMPLATE):
            with self.subTest(path=path):
                self.assertIn(
                    f"gem install bundler --no-document -v {locked_version}",
                    path.read_text(),
                )

    def test_production_image_pins_its_passenger_base(self):
        expected_base = (
            "instructure/ruby-passenger:$RUBY-jammy@"
            "sha256:80d3a0e22c6ae228494de406d67fca88d7ff2de89fece021423206087190fcbe"
        )

        for path in (DOCKERFILE, DOCKERFILE_TEMPLATE):
            with self.subTest(path=path):
                self.assertIn(expected_base, path.read_text())

    def test_production_image_disables_the_inherited_passenger_apt_source(self):
        for path in (DOCKERFILE, DOCKERFILE_TEMPLATE):
            with self.subTest(path=path):
                dockerfile = path.read_text()
                self.assertIn(
                    "rm -f /etc/apt/sources.list.d/passenger.list",
                    dockerfile,
                )
                disable_source = dockerfile.index(
                    "rm -f /etc/apt/sources.list.d/passenger.list"
                )
                apt_update = dockerfile.index("apt-get update -qq")

                self.assertLess(disable_source, apt_update)

    def test_deploy_runs_the_supported_postdeploy_migration_task(self):
        script = DEPLOY_SCRIPT.read_text()

        self.assertNotIn("db:migrate:postdeploy", script)
        self.assertIn('"db:migrate:tagged[postdeploy]"', script)

    def test_postdeploy_failure_never_restores_an_old_image(self):
        script = DEPLOY_SCRIPT.read_text()
        current_update = script.index('ln -sfn "${release_dir}" "${current_link}"')
        rollback_disarm = script.index("trap - ERR")
        postdeploy = script.index('"db:migrate:tagged[postdeploy]"')

        self.assertLess(current_update, rollback_disarm)
        self.assertLess(rollback_disarm, postdeploy)

    def test_first_deploy_failure_stops_the_failed_release(self):
        script = DEPLOY_SCRIPT.read_text()

        self.assertIn('"${compose[@]}" down --remove-orphans', script)

    def test_deploy_waits_for_jobs_and_other_service_health(self):
        script = DEPLOY_SCRIPT.read_text()

        self.assertIn("--wait", script)
        self.assertIn("--wait-timeout", script)

    def test_canvas_allows_enough_time_for_a_cold_passenger_start(self):
        compose = COMPOSE_FILE.read_text()

        self.assertIn('PASSENGER_STARTUP_TIMEOUT: "300"', compose)

    def test_deploy_bounds_the_readiness_wait(self):
        script = DEPLOY_SCRIPT.read_text()

        self.assertIn("readiness_deadline=$((SECONDS + 300))", script)
        self.assertIn("--connect-timeout 5", script)
        self.assertIn("--max-time 15", script)
        self.assertNotIn("for _ in $(seq 1 60)", script)

    def test_jobs_healthcheck_requires_a_master_and_worker(self):
        compose = COMPOSE_FILE.read_text()

        self.assertNotIn("pgrep -f 'script/delayed_job run'", compose)
        self.assertIn("pgrep -f '^delayed_jobs_pool( .*)?$'", compose)
        self.assertIn("pgrep -P", compose)
        self.assertIn("-f '^delayed:'", compose)

    def test_deploy_grants_only_the_container_group_runtime_secret_access(self):
        script = DEPLOY_SCRIPT.read_text()

        self.assertIn("--user 0:0", script)
        self.assertIn('--env "RUNTIME_GID=${runtime_gid}"', script)
        self.assertIn("chmod 0440", script)

    def test_initial_setup_works_with_ubuntu_compose(self):
        script = DEPLOY_SCRIPT.read_text()

        self.assertNotIn("--env-from-file", script)
        self.assertIn("initial-setup.override.yaml", script)

    def test_supporting_container_images_are_immutable(self):
        self.assertRegex(
            COMPOSE_FILE.read_text(),
            r"image: redis:[^@\s]+@sha256:[a-f0-9]{64}",
        )
        self.assertRegex(
            DATABASE_BOOTSTRAP.read_text(),
            r"postgres:[^@\s]+@sha256:[a-f0-9]{64}",
        )

    def test_database_bootstrap_uses_grants_and_verified_tls(self):
        script = DATABASE_BOOTSTRAP.read_text()

        self.assertNotIn("ALTER DATABASE", script)
        self.assertNotIn("ALTER SCHEMA", script)
        self.assertIn("GRANT CONNECT, TEMPORARY ON DATABASE", script)
        self.assertIn("sslmode=verify-full", script)
        self.assertIn("sslrootcert=", script)

    def test_canvas_database_connection_verifies_managed_ca(self):
        configuration = DATABASE_CONFIG.read_text()

        self.assertIn("sslmode: verify-full", configuration)
        self.assertIn("sslrootcert: /usr/src/app/config/database_ca.crt", configuration)
        self.assertIn("database_ca.crt:", COMPOSE_FILE.read_text())

    def test_smtp_requires_tls_and_uses_the_selected_sender(self):
        configuration = OUTGOING_MAIL.read_text()

        self.assertIn("enable_starttls: true", configuration)
        self.assertNotIn("enable_starttls_auto", configuration)
        self.assertIn('outgoing_address: "notifications@bonesrnd.com"', configuration)

    def test_canvas_uses_a_cookie_isolated_files_domain(self):
        self.assertIn(
            'files_domain: "files.bonesrnd.com"',
            DOMAIN_CONFIG.read_text(),
        )

    def test_brandable_css_is_shared_and_seeded_for_each_release(self):
        compose = COMPOSE_FILE.read_text()
        deploy = DEPLOY_SCRIPT.read_text()

        self.assertIn("canvas_brandable_css:", compose)
        self.assertIn(
            "canvas_brandable_css:/usr/src/app/public/dist/brandable_css",
            compose,
        )
        self.assertIn("brandable-css-init", compose)
        self.assertIn("run --rm --no-deps brandable-css-init", deploy)
        self.assertIn(
            '"${previous_compose[@]}" run --rm --no-deps brandable-css-init',
            deploy,
        )


if __name__ == "__main__":
    unittest.main()
