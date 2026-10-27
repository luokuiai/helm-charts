"""Run with: uv run --with pyyaml python tests/casdoor/test_chart.py."""

import base64
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/casdoor/1.0.0"
DATABASE = {"host": "postgres.database.svc.cluster.local", "user": "casdoor",
            "password": "test-only"}


def merge(base, updates):
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def render(values=None, *, with_credentials=True, release="casdoor"):
    supplied = {"database": deepcopy(DATABASE)} if with_credentials else {}
    merge(supplied, values or {})
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "identity",
         "--kube-version", "1.30.0", "--values", "-"],
        input=yaml.safe_dump(supplied), capture_output=True, text=True,
    )


def manifests(values=None, **kwargs):
    result = render(values, **kwargs)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(docs, kind, name=None):
    matches = [doc for doc in docs if doc["kind"] == kind
               and (name is None or doc["metadata"]["name"] == name)]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind} {name}, found {len(matches)}")
    return matches[0]


def connection_string(docs):
    secret = resource(docs, "Secret")
    return base64.b64decode(secret["data"]["dataSourceName"]).decode()


def ingress_values(mode="disabled", **certificate):
    return {"ingress": {"enabled": True, "className": "traefik",
                        "hosts": [{"host": "sso.example.com"}],
                        "certificate": {"mode": mode, **certificate}}}


class CasdoorChartTests(unittest.TestCase):
    def test_external_database_without_bundled_database_or_file_pvc(self):
        docs = manifests()
        self.assertFalse(any(doc["kind"] in ("StatefulSet", "PersistentVolumeClaim", "Ingress")
                             for doc in docs))
        self.assertEqual(sum(doc["kind"] == "Deployment" for doc in docs), 1)
        deployment = resource(docs, "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["image"], "casbin/casdoor:v4.24.0")
        self.assertEqual(container["startupProbe"]["httpGet"]["path"], "/api/health")
        env = {item["name"]: item for item in container["env"]}
        self.assertEqual(env["dataSourceName"]["valueFrom"]["secretKeyRef"],
                         {"name": "casdoor-database", "key": "dataSourceName"})
        self.assertEqual(env["RUNNING_IN_DOCKER"]["value"], "false")
        config = resource(docs, "ConfigMap")["data"]["app.conf"]
        self.assertIn("runmode = prod", config)
        self.assertNotIn(DATABASE["password"], config)
        self.assertNotIn("postgres://", config)

    def test_postgres_credentials_are_encoded_and_kept_in_a_secret(self):
        password = "space ' quote\" slash\\ @:/?#&% localhost"
        docs = manifests({"database": {"user": "user name@db", "password": password,
                                       "port": 15432, "sslMode": "require"}})
        url = urlsplit(connection_string(docs))
        self.assertEqual(url.scheme, "postgres")
        self.assertEqual(unquote(url.username), "user name@db")
        self.assertEqual(unquote(url.password), password)
        self.assertEqual(url.hostname, DATABASE["host"])
        self.assertEqual(url.port, 15432)
        self.assertEqual(url.path, "/casdoor")
        self.assertEqual(parse_qs(url.query), {"sslmode": ["require"]})
        config = resource(docs, "ConfigMap")["data"]["app.conf"]
        self.assertNotIn(password, config)

    def test_default_database_ports_and_mysql_dsn(self):
        postgres = urlsplit(connection_string(manifests()))
        self.assertEqual(postgres.port, 5432)
        for port, expected in ((0, 3306), (13306, 13306)):
            with self.subTest(port=port):
                password = "password'\"@:/?#&%"
                docs = manifests({"database": {"driver": "mysql", "port": port,
                                               "password": password}})
                self.assertEqual(connection_string(docs),
                                 f"casdoor:{password}@tcp({DATABASE['host']}:{expected})/")
                config = resource(docs, "ConfigMap")["data"]["app.conf"]
                self.assertIn("driverName = mysql", config)
                self.assertIn("dbName = casdoor", config)
                self.assertNotIn(password, config)

    def test_existing_secret_needs_no_inline_credentials(self):
        for driver in ("postgres", "mysql"):
            with self.subTest(driver=driver):
                docs = manifests({"database": {"driver": driver, "useExistingSecret": True,
                                               "existingSecret": "external-db"}},
                                 with_credentials=False, release="identity")
                self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
                deployment = resource(docs, "Deployment")
                pod = deployment["spec"]["template"]
                self.assertNotIn("checksum/database", pod["metadata"]["annotations"])
                env = pod["spec"]["containers"][0]["env"]
                reference = next(item for item in env if item["name"] == "dataSourceName")
                self.assertEqual(reference["valueFrom"]["secretKeyRef"]["name"], "external-db")

    def test_database_credential_changes_trigger_a_rollout(self):
        before = resource(manifests(), "Deployment")["spec"]["template"]
        after = resource(manifests({"database": {"password": "replacement"}}),
                         "Deployment")["spec"]["template"]
        self.assertNotEqual(before["metadata"]["annotations"]["checksum/database"],
                            after["metadata"]["annotations"]["checksum/database"])

    def test_ingress_existing_tls_and_origin(self):
        values = ingress_values("existing", secretName="identity-tls")
        docs = manifests(values, release="identity")
        ingress = resource(docs, "Ingress")
        self.assertEqual(ingress["spec"]["ingressClassName"], "traefik")
        self.assertEqual(ingress["spec"]["tls"],
                         [{"secretName": "identity-tls", "hosts": ["sso.example.com"]}])
        path = ingress["spec"]["rules"][0]["http"]["paths"][0]
        self.assertEqual(path["path"], "/")
        self.assertEqual(path["backend"]["service"]["name"], "identity-casdoor")
        self.assertIn('origin = "https://sso.example.com"',
                      resource(docs, "ConfigMap")["data"]["app.conf"])

    def test_http_origin_and_explicit_origin(self):
        values = ingress_values()
        docs = manifests(values)
        self.assertNotIn("tls", resource(docs, "Ingress")["spec"])
        self.assertIn('origin = "http://sso.example.com"',
                      resource(docs, "ConfigMap")["data"]["app.conf"])
        values["origin"] = "https://public.example.com"
        config = resource(manifests(values), "ConfigMap")["data"]["app.conf"]
        self.assertIn('origin = "https://public.example.com"', config)

    def test_cert_manager_issuer_annotations(self):
        for kind, key in (("Issuer", "cert-manager.io/issuer"),
                          ("ClusterIssuer", "cert-manager.io/cluster-issuer")):
            with self.subTest(kind=kind):
                values = ingress_values("cert-manager", issuerKind=kind,
                                        issuerName="letsencrypt")
                values["ingress"]["annotations"] = {
                    "cert-manager.io/issuer": "stale",
                    "cert-manager.io/cluster-issuer": "stale",
                    "example.com/custom": "kept",
                }
                docs = manifests(values)
                self.assertEqual(resource(docs, "Ingress")["metadata"]["annotations"],
                                 {key: "letsencrypt", "example.com/custom": "kept"})
                self.assertIn('origin = "https://sso.example.com"',
                              resource(docs, "ConfigMap")["data"]["app.conf"])

    def test_storage_provider_setting_creates_no_storage_resources(self):
        docs = manifests({"defaultStorageProvider": "my-storage-provider"})
        self.assertIn('defaultStorageProvider = "my-storage-provider"',
                      resource(docs, "ConfigMap")["data"]["app.conf"])
        self.assertFalse(any(doc["kind"] == "PersistentVolumeClaim" for doc in docs))

    def test_optional_full_config_secret_uses_string_data(self):
        docs = manifests({"configFromSecret": "custom-config", "config": "runmode = prod"})
        secret = resource(docs, "Secret", "custom-config")
        self.assertEqual(secret["stringData"]["app.conf"].strip(), "runmode = prod")

    def test_invalid_configuration_is_rejected(self):
        self.assertNotEqual(render(with_credentials=False).returncode, 0)
        cases = [
            {"database": {"driver": "sqlite"}},
            {"database": {"host": ""}},
            {"database": {"password": ""}},
            {"database": {"port": 65536}},
            {"database": {"useExistingSecret": True}},
            {"database": {"driver": "mysql", "user": "user:invalid"}},
            {"origin": "not-a-url"},
            ingress_values("invalid"),
            ingress_values("existing", secretName=""),
            ingress_values("cert-manager"),
            {"ingress": {"enabled": True, "hosts": []}},
            {"ingress": {"enabled": True, "hosts": [{"host": "https://invalid"}]}},
            {"ingress": {"enabled": True, "certificate": {"mode": "existing"},
                         "tls": [{"secretName": "another-secret"}]}},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_form_defaults_and_visibility_paths_exist(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]

        def value_at(path):
            value = values
            for part in path.split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
            return value

        for question in questions:
            with self.subTest(variable=question["variable"]):
                expected = question["default"]
                if question["type"] == "boolean":
                    expected = str(expected).lower() == "true"
                self.assertEqual(value_at(question["variable"]), expected)
                for condition in question.get("show_if", "").split("&&"):
                    if condition:
                        value_at(condition.split("=", 1)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
