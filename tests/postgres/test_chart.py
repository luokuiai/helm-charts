"""Run with: uv run --with pyyaml python tests/postgres/test_chart.py."""

import base64
from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/postgres/1.0.0"


def render(values=None, release="postgres"):
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "infra", "--values", "-"],
        input=yaml.safe_dump(values or {}), capture_output=True, text=True,
    )


def manifests(values=None, **kwargs):
    result = render(values, **kwargs)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def container(docs):
    statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
    return statefulset["spec"]["template"]["spec"]["containers"][0]


class PostgresChartTests(unittest.TestCase):
    def test_default_environment_secret_and_pg18_storage(self):
        docs = manifests()
        app = container(docs)
        self.assertEqual(app["image"], "postgres:18.6")
        self.assertEqual(app["envFrom"], [{"secretRef": {"name": "postgres-env"}}])
        env = {item["name"]: item for item in app["env"]}
        self.assertEqual(env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"],
                         {"name": "postgres-env", "key": "POSTGRES_PASSWORD"})
        self.assertNotIn("POSTGRES_DB", env)
        self.assertEqual(env["PGDATA"]["value"], "/var/lib/postgresql/18/docker")
        self.assertEqual(app["volumeMounts"], [{"name": "data", "mountPath": "/var/lib/postgresql"}])
        self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertIn('${POSTGRES_DB:-${POSTGRES_USER:-postgres}}',
                          app[probe]["exec"]["command"][-1])

    def test_database_is_optional_and_custom_values_are_used(self):
        docs = manifests({"postgres": {"envSecret": "db-env"},
                          "auth": {"username": "dbadmin", "database": "appdb"}})
        app = container(docs)
        env = {item["name"]: item for item in app["env"]}
        self.assertEqual(app["envFrom"], [{"secretRef": {"name": "db-env"}}])
        self.assertEqual(env["POSTGRES_USER"]["value"], "dbadmin")
        self.assertEqual(env["POSTGRES_DB"]["value"], "appdb")
        self.assertEqual(env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]["name"], "db-env")

    def test_full_image_references_and_legacy_tags(self):
        digest = "sha256:" + "a" * 64
        cases = [
            ({"repository": "postgres"}, "postgres:18.6"),
            ({"repository": "registry.example.com:5000/team/postgres"},
             "registry.example.com:5000/team/postgres:18.6"),
            ({"repository": "registry.example.com:5000/team/postgres:18.6-alpine", "tag": "17"},
             "registry.example.com:5000/team/postgres:18.6-alpine"),
            ({"repository": f"postgres@{digest}"}, f"postgres@{digest}"),
            ({"repository": "postgres", "tag": "18.5"}, "postgres:18.5"),
        ]
        for image, expected in cases:
            with self.subTest(image=image):
                self.assertEqual(container(manifests({"image": image}))["image"], expected)

    def test_legacy_authentication_remains_available(self):
        password = "test-only-password"
        docs = manifests({"postgres": {"envSecret": ""}, "auth": {"password": password}})
        secret, = [doc for doc in docs if doc["kind"] == "Secret"]
        self.assertEqual(base64.b64decode(secret["data"]["password"]).decode(), password)
        self.assertNotIn("envFrom", container(docs))
        docs = manifests({"postgres": {"envSecret": ""},
                          "auth": {"useExistingSecret": True, "existingSecret": "legacy-auth",
                                   "secretKey": "db-password"}})
        env = {item["name"]: item for item in container(docs)["env"]}
        self.assertEqual(env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"],
                         {"name": "legacy-auth", "key": "db-password"})
        self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))

    def test_release_name_and_existing_claim(self):
        docs = manifests({"persistence": {"existingClaim": "original-data"}}, release="db-main")
        statefulset = next(doc for doc in docs if doc["kind"] == "StatefulSet")
        self.assertEqual(statefulset["metadata"]["name"], "db-main")
        self.assertEqual(statefulset["spec"]["serviceName"], "db-main-headless")
        self.assertNotIn("volumeClaimTemplates", statefulset["spec"])
        self.assertEqual(statefulset["spec"]["template"]["spec"]["volumes"],
                         [{"name": "data", "persistentVolumeClaim": {"claimName": "original-data"}}])

    def test_invalid_configuration_is_rejected(self):
        for values in [
            {"postgres": {"envSecret": "Invalid/Secret"}},
            {"postgres": {"envSecret": ""}},
            {"postgres": {"envSecret": ""}, "auth": {"useExistingSecret": True}},
            {"image": {"repository": "postgres:17"}},
            {"image": {"repository": "postgres", "tag": "17"}},
            {"auth": {"username": ""}},
            {"persistence": {"size": "invalid"}},
        ]:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_form_has_one_image_and_secret_field_without_password_inputs(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        by_variable = {question["variable"]: question for question in questions}
        self.assertNotIn("image.tag", by_variable)
        self.assertFalse(any(question["type"] == "password" for question in questions))
        self.assertFalse(by_variable["auth.database"].get("required", False))
        self.assertEqual(by_variable["postgres.envSecret"]["type"], "reference[secret]")
        for question in questions:
            with self.subTest(variable=question["variable"]):
                value = values
                for part in question["variable"].split("."):
                    value = value[part]
                self.assertEqual(value, question["default"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
