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
    supplied = {"casdoor": {"envSecret": ""}, "database": deepcopy(DATABASE)} if with_credentials else {}
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


def app_container(docs):
    return resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]


class CasdoorChartTests(unittest.TestCase):
    def test_full_image_and_legacy_references(self):
        cases = [
            ({}, "casbin/casdoor:v4.24.0"),
            ({"repository": "mirror.example.com:5000/team/casdoor:v4.24.0", "name": "ignored", "tag": "old"},
             "mirror.example.com:5000/team/casdoor:v4.24.0"),
            ({"repository": "mirror.example.com:5000/team/casdoor"},
             "mirror.example.com:5000/team/casdoor:v4.24.0"),
            ({"repository": "casbin", "name": "casdoor", "tag": "v4.23.0"},
             "casbin/casdoor:v4.23.0"),
            ({"repository": "casbin/casdoor@sha256:" + "a" * 64},
             "casbin/casdoor@sha256:" + "a" * 64),
        ]
        for image, expected in cases:
            with self.subTest(image=image):
                self.assertEqual(app_container(manifests({"image": image}))["image"], expected)

    def test_environment_secret_is_default_and_wins_over_legacy_database(self):
        for driver in ("postgres", "mysql"):
            docs = manifests({"database": {"driver": driver}, "envFrom": [
                {"type": "configmap", "name": "extra-config"},
                {"type": "secret", "name": "extra-secret"}]}, with_credentials=False)
            self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
            container = app_container(docs)
            self.assertEqual(container["envFrom"], [
                {"configMapRef": {"name": "extra-config"}},
                {"secretRef": {"name": "extra-secret"}},
                {"secretRef": {"name": "casdoor-env"}}])
            env = {item["name"]: item for item in container["env"]}
            self.assertEqual(env["dataSourceName"]["valueFrom"]["secretKeyRef"],
                             {"name": "casdoor-env", "key": "dataSourceName"})
            annotations = resource(docs, "Deployment")["spec"]["template"]["metadata"]["annotations"]
            self.assertNotIn("checksum/database", annotations)
        docs = manifests({"casdoor": {"envSecret": "custom-env"}, "database": {
            "useExistingSecret": True, "existingSecret": "old-db"}})
        self.assertEqual(app_container(docs)["envFrom"], [{"secretRef": {"name": "custom-env"}}])
        env = {item["name"]: item for item in app_container(docs)["env"]}
        self.assertEqual(env["dataSourceName"]["valueFrom"]["secretKeyRef"]["name"], "custom-env")

    def test_storage_provider_initialization_from_existing_secret(self):
        docs = manifests({"initData": {"enabled": True, "existingSecret": "casdoor-storage",
                                       "existingSecretKey": "init_data.yaml"}},
                         with_credentials=False)
        self.assertFalse(any(doc["kind"] in ("Secret", "PersistentVolumeClaim") for doc in docs))
        container = app_container(docs)
        env = {item["name"]: item for item in container["env"]}
        self.assertEqual(env["initDataFile"]["value"], "/init-data/init_data.yaml")
        self.assertEqual(env["initDataMerge"]["value"], "true")
        self.assertEqual(env["initDataWatchInterval"]["value"], "30")
        volumes = resource(docs, "Deployment")["spec"]["template"]["spec"]["volumes"]
        self.assertEqual(next(v for v in volumes if v["name"] == "init-data")["secret"],
                         {"secretName": "casdoor-storage", "items": [
                             {"key": "init_data.yaml", "path": "init_data.yaml"}]})
        self.assertIn({"name": "init-data", "mountPath": "/init-data", "readOnly": True},
                      container["volumeMounts"])

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

    def test_silo_example_can_initialize_from_inline_data_without_leaking_to_config(self):
        example = yaml.safe_load((ROOT / "docs/casdoor/s3-init-secret.example.yaml").read_text())
        data = yaml.safe_load(example["stringData"]["init_data.yaml"])
        docs = manifests({"initData": {"enabled": True, "data": data, "watchInterval": 0}},
                         with_credentials=False)
        secret = resource(docs, "Secret", "casdoor-init-data")
        self.assertEqual(yaml.safe_load(secret["stringData"]["init_data.json"]), data)
        self.assertNotIn(data["providers"][0]["clientSecret"],
                         resource(docs, "ConfigMap")["data"]["app.conf"])
        pod = resource(docs, "Deployment")["spec"]["template"]
        self.assertIn("checksum/init-data", pod["metadata"]["annotations"])
        self.assertEqual(data["providers"][0]["type"], "MinIO")
        self.assertEqual(data["providers"][0]["pathPrefix"], data["providers"][0]["bucket"])

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
                docs = manifests({"casdoor": {"envSecret": ""},
                                  "database": {"driver": driver, "useExistingSecret": True,
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

    def test_storage_proxy_is_optional_and_shares_the_environment_secret(self):
        default = manifests(with_credentials=False)
        self.assertEqual(len(resource(default, "Deployment")["spec"]["template"]["spec"]["containers"]), 1)
        self.assertEqual(len(resource(default, "Service")["spec"]["ports"]), 1)
        self.assertFalse(any(doc["metadata"]["name"].endswith("-storage-proxy") for doc in default))
        docs = manifests({"storageProxy": {"enabled": True},
                          "casdoor": {"envSecret": "shared-env"}}, with_credentials=False)
        pod = resource(docs, "Deployment")["spec"]["template"]
        proxy = pod["spec"]["containers"][1]
        self.assertEqual(proxy["image"], "caddy:2.11.7-alpine")
        self.assertEqual(proxy["envFrom"], app_container(docs)["envFrom"])
        refs = {entry["name"]: entry["valueFrom"]["secretKeyRef"] for entry in proxy["env"]
                if "valueFrom" in entry}
        self.assertEqual(refs, {key: {"name": "shared-env", "key": key}
                                for key in ("S3_ENDPOINT", "S3_BUCKET")})
        self.assertIn("checksum/storage-proxy", pod["metadata"]["annotations"])
        self.assertEqual(resource(docs, "Service")["spec"]["ports"][1],
                         {"port": 8080, "targetPort": "files", "protocol": "TCP", "name": "files"})
        self.assertFalse(any(doc["kind"] in ("Secret", "PersistentVolumeClaim") for doc in docs))

    def test_file_domain_routes_only_to_caddy_and_joins_the_certificate(self):
        for mode in ("disabled", "existing", "cert-manager"):
            values = ingress_values(mode, issuerName="letsencrypt")
            values["storageProxy"] = {"enabled": True, "hostname": "files.example.com", "port": 18080}
            docs = manifests(values, with_credentials=False)
            ingress = resource(docs, "Ingress")
            rules = ingress["spec"]["rules"]
            self.assertEqual([r["host"] for r in rules], ["sso.example.com", "files.example.com"])
            self.assertEqual(rules[0]["http"]["paths"][0]["backend"]["service"]["port"], {"name": "http"})
            self.assertEqual(rules[1]["http"]["paths"][0]["backend"]["service"]["port"], {"name": "files"})
            if mode != "disabled":
                self.assertEqual(ingress["spec"]["tls"][0]["hosts"], ["sso.example.com", "files.example.com"])
            proxy = resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][1]
            self.assertEqual(proxy["ports"][0]["containerPort"], 18080)
            self.assertIn(":18080 {", resource(docs, "ConfigMap", "casdoor-storage-proxy")["data"]["Caddyfile"])

    def test_combined_secret_example_matches_the_proxy_and_imports_automatically(self):
        example = yaml.safe_load((ROOT / "docs/casdoor/s3-init-secret.example.yaml").read_text())
        data = example["stringData"]
        provider = yaml.safe_load(data["init_data.yaml"])["providers"][0]
        self.assertEqual(data["S3_ENDPOINT"], provider["endpoint"])
        self.assertEqual(data["S3_BUCKET"], provider["bucket"])
        self.assertEqual(data["S3_BUCKET"], provider["pathPrefix"])
        self.assertEqual(data["defaultStorageProvider"], provider["name"])
        self.assertIn("dataSourceName", data)
        values = ingress_values("existing")
        values["storageProxy"] = {"enabled": True}
        values["casdoor"] = {"envSecret": example["metadata"]["name"]}
        values["initData"] = {"enabled": True, "existingSecret": example["metadata"]["name"]}
        docs = manifests(values, with_credentials=False)
        self.assertEqual(provider["domain"], "https://" + resource(docs, "Ingress")["spec"]["rules"][1]["host"])
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        init_volume = next(v for v in pod["volumes"] if v["name"] == "init-data")
        self.assertEqual(init_volume["secret"]["secretName"], example["metadata"]["name"])
        self.assertEqual(pod["containers"][0]["envFrom"], pod["containers"][1]["envFrom"])

    def test_optional_full_config_secret_uses_string_data(self):
        docs = manifests({"configFromSecret": "custom-config", "config": "runmode = prod"})
        secret = resource(docs, "Secret", "custom-config")
        self.assertEqual(secret["stringData"]["app.conf"].strip(), "runmode = prod")

    def test_invalid_configuration_is_rejected(self):
        self.assertEqual(render(with_credentials=False).returncode, 0)
        self.assertNotEqual(render({"casdoor": {"envSecret": ""}}, with_credentials=False).returncode, 0)
        cases = [
            {"storageProxy": {"enabled": True}},
            {"casdoor": {"envSecret": "casdoor-env"}, "storageProxy": {"enabled": True, "port": 8000}},
            {"storageProxy": {"hostname": "https://files.example.com"}},
            {"casdoor": {"envSecret": "casdoor-env"}, "storageProxy": {"enabled": True, "hostname": "casdoor.example.com"}, "ingress": {"enabled": True}},
            {"casdoor": {"envSecret": "bad/name"}},
            {"initData": {"enabled": True}},
            {"initData": {"watchInterval": -1}},
            {"initData": {"enabled": True, "existingSecret": "storage", "existingSecretKey": "../bad"}},
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

        by_variable = {q["variable"]: q for q in questions}
        self.assertNotIn("image.name", by_variable)
        self.assertNotIn("image.tag", by_variable)
        for variable in ("database.password", "database.user", "database.host", "database.useExistingSecret"):
            self.assertNotIn(variable, by_variable)
        self.assertEqual(by_variable["casdoor.envSecret"]["type"], "reference[secret]")
        self.assertEqual(by_variable["initData.existingSecret"]["type"], "reference[secret]")

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
