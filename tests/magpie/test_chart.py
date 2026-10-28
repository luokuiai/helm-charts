"""Run with: uv run --with pyyaml python tests/magpie/test_chart.py."""

import base64
from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/magpie/1.0.0"
WEB_KEY = "test-web-key-1234567890"


def render(values=None, *, release="magpie"):
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "ai",
         "--kube-version", "1.30.0", "--values", "-"],
        input=yaml.safe_dump(values or {}), capture_output=True, text=True,
    )


def manifests(values=None, **kwargs):
    result = render(values, **kwargs)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(docs, kind):
    matches = [doc for doc in docs if doc["kind"] == kind]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}, found {len(matches)}")
    return matches[0]


def env(docs):
    container = resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
    return {item["name"]: item for item in container["env"]}


def ingress(mode="disabled", **certificate):
    return {"ingress": {"enabled": True, "className": "traefik",
                        "hosts": [{"host": "gateway.example.com"}],
                        "certificate": {"mode": mode, **certificate}}}


class MagpieChartTests(unittest.TestCase):
    def test_single_writer_and_complete_config_persistence(self):
        docs = manifests()
        deployment = resource(docs, "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        pod = deployment["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 65532)
        self.assertEqual(pod["securityContext"]["fsGroup"], 65532)
        container = pod["containers"][0]
        self.assertEqual(container["image"], "ghcr.io/yetone/magpie:0.1.1836")
        self.assertEqual(container["args"], ["web", "--addr", "0.0.0.0:3430", "--no-open"])
        self.assertEqual(container["volumeMounts"], [{"name": "config", "mountPath": "/config"}])
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], "magpie-config")
        claim = resource(docs, "PersistentVolumeClaim")
        self.assertEqual(claim["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        self.assertEqual(claim["spec"]["storageClassName"], "local-path")
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "1Gi")
        self.assertFalse(any(doc["kind"] == "Ingress" for doc in docs))

    def test_native_probes_and_cluster_only_ports(self):
        docs = manifests()
        container = resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
        for name in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertEqual(container[name]["exec"]["command"], ["/magpie", "healthcheck"])
        service = resource(docs, "Service")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        ports = {port["name"]: port for port in service["spec"]["ports"]}
        self.assertEqual((ports["http"]["port"], ports["http"]["targetPort"]), (3430, "web"))
        self.assertEqual(ports["gateway"]["port"], 3425)
        self.assertEqual(env(docs)["MAGPIE_ADDR"]["value"], "0.0.0.0:3425")

    def test_full_image_references_and_legacy_tags(self):
        digest = "sha256:" + "a" * 64
        cases = [
            ({"repository": "ghcr.io/yetone/magpie"}, "ghcr.io/yetone/magpie:0.1.1836"),
            ({"repository": "registry.example.com:5000/team/magpie"},
             "registry.example.com:5000/team/magpie:0.1.1836"),
            ({"repository": "registry.example.com:5000/team/magpie:custom", "tag": "legacy"},
             "registry.example.com:5000/team/magpie:custom"),
            ({"repository": f"ghcr.io/yetone/magpie@{digest}", "tag": "legacy"},
             f"ghcr.io/yetone/magpie@{digest}"),
            ({"repository": "ghcr.io/yetone/magpie", "tag": "0.1.1734"},
             "ghcr.io/yetone/magpie:0.1.1734"),
        ]
        for image, expected in cases:
            with self.subTest(image=image):
                container = resource(manifests({"image": image}), "Deployment")["spec"][
                    "template"]["spec"]["containers"][0]
                self.assertEqual(container["image"], expected)

    def test_environment_secret_supplies_web_key_and_other_variables(self):
        for name in ("magpie-env", "custom-magpie-env"):
            with self.subTest(secret=name):
                docs = manifests({"magpie": {"envSecret": name}, "auth": {"webKey": "unused"}})
                pod = resource(docs, "Deployment")["spec"]["template"]
                container = pod["spec"]["containers"][0]
                self.assertEqual(container["envFrom"], [{"secretRef": {"name": name}}])
                self.assertEqual(env(docs)["MAGPIE_WEB_KEY"]["valueFrom"]["secretKeyRef"],
                                 {"name": name, "key": "MAGPIE_WEB_KEY"})
                self.assertNotIn("optional", container["envFrom"][0]["secretRef"])
                self.assertNotIn("optional", env(docs)["MAGPIE_WEB_KEY"]["valueFrom"]["secretKeyRef"])
                self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
                self.assertNotIn("checksum/auth", pod["metadata"].get("annotations", {}))

    def test_legacy_web_key_is_secret_backed_and_rotation_rolls_the_pod(self):
        docs = manifests({"magpie": {"envSecret": ""}, "auth": {"webKey": WEB_KEY}})
        self.assertEqual(base64.b64decode(resource(docs, "Secret")["data"]["MAGPIE_WEB_KEY"])
                         .decode(), WEB_KEY)
        self.assertEqual(env(docs)["MAGPIE_WEB_KEY"]["valueFrom"]["secretKeyRef"],
                         {"name": "magpie-web", "key": "MAGPIE_WEB_KEY"})
        before = resource(docs, "Deployment")["spec"]["template"]
        self.assertNotIn(WEB_KEY, yaml.safe_dump(before))
        self.assertNotIn("envFrom", before["spec"]["containers"][0])
        after = resource(manifests({"magpie": {"envSecret": ""},
                                    "auth": {"webKey": "another-web-key-123456"}}),
                         "Deployment")["spec"]["template"]
        self.assertNotEqual(before["metadata"]["annotations"]["checksum/auth"],
                            after["metadata"]["annotations"]["checksum/auth"])

    def test_existing_secret_and_pvc_are_reused(self):
        docs = manifests({"magpie": {"envSecret": ""},
                          "auth": {"useExistingSecret": True, "existingSecret": "my-web-key",
                                    "secretKey": "web-key"},
                          "persistence": {"existingClaim": "existing-config"}})
        self.assertFalse(any(doc["kind"] in ("Secret", "PersistentVolumeClaim") for doc in docs))
        self.assertEqual(env(docs)["MAGPIE_WEB_KEY"]["valueFrom"]["secretKeyRef"],
                         {"name": "my-web-key", "key": "web-key"})
        pod = resource(docs, "Deployment")["spec"]["template"]
        self.assertNotIn("checksum/auth", pod["metadata"].get("annotations", {}))
        self.assertEqual(pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"],
                         "existing-config")

    def test_cluster_default_storage_class(self):
        claim = resource(manifests({"persistence": {"storageClass": ""}}), "PersistentVolumeClaim")
        self.assertNotIn("storageClassName", claim["spec"])

    def test_domain_routes_web_and_api_to_the_web_port(self):
        docs = manifests(ingress("existing", secretName="gateway-tls"), release="my-gateway")
        route = resource(docs, "Ingress")
        self.assertEqual(route["spec"]["ingressClassName"], "traefik")
        self.assertEqual(route["spec"]["tls"],
                         [{"secretName": "gateway-tls", "hosts": ["gateway.example.com"]}])
        path = route["spec"]["rules"][0]["http"]["paths"][0]
        self.assertEqual(path["path"], "/")
        self.assertEqual(path["pathType"], "Prefix")
        self.assertEqual(path["backend"]["service"], {"name": "my-gateway", "port": {"name": "http"}})
        for name in ("MAGPIE_PUBLIC_URL", "MAGPIE_WEB_URL"):
            self.assertEqual(env(docs)[name]["value"], "https://gateway.example.com")

    def test_public_url_override_and_http_mode(self):
        self.assertNotIn("MAGPIE_PUBLIC_URL", env(manifests()))
        docs = manifests(ingress())
        self.assertNotIn("tls", resource(docs, "Ingress")["spec"])
        self.assertEqual(env(docs)["MAGPIE_PUBLIC_URL"]["value"], "http://gateway.example.com")
        docs = manifests({"magpie": {"publicURL": "https://proxy.example.com:8443/"}})
        self.assertEqual(env(docs)["MAGPIE_PUBLIC_URL"]["value"], "https://proxy.example.com:8443")

    def test_cert_manager_issuer_selection(self):
        for kind, key in (("Issuer", "cert-manager.io/issuer"),
                          ("ClusterIssuer", "cert-manager.io/cluster-issuer")):
            with self.subTest(kind=kind):
                values = ingress("cert-manager", issuerKind=kind, issuerName="letsencrypt")
                values["ingress"]["annotations"] = {"cert-manager.io/issuer": "stale",
                    "cert-manager.io/cluster-issuer": "stale", "example.com/custom": "kept"}
                route = resource(manifests(values), "Ingress")
                self.assertEqual(route["metadata"]["annotations"],
                                 {key: "letsencrypt", "example.com/custom": "kept"})
                self.assertEqual(route["spec"]["tls"][0]["secretName"], "magpie-tls")

    def test_invalid_configuration_is_rejected(self):
        cases = [
            {"magpie": {"envSecret": ""}},
            {"magpie": {"envSecret": "Invalid/Secret"}},
            {"magpie": {"envSecret": ""}, "auth": {"webKey": "too-short"}},
            {"magpie": {"envSecret": ""}, "auth": {"webKey": "a key with spaces 12345"}},
            {"magpie": {"envSecret": ""}, "auth": {"useExistingSecret": True}},
            {"magpie": {"envSecret": ""}, "auth": {"webKey": WEB_KEY,
                                                           "secretKey": "invalid/key"}},
            {"image": {"repository": ""}},
            {"persistence": {"size": "bad-size"}},
            {"magpie": {"publicURL": "ftp://invalid.example.com"}},
            {"magpie": {"publicURL": "https://example.com/v1"}},
            ingress("invalid"),
            ingress("existing", secretName=""),
            ingress("cert-manager"),
            {"ingress": {"enabled": True, "hosts": []}},
            {"ingress": {"hosts": [{"host": "https://invalid"}]}},
            {"ingress": {"enabled": True, "certificate": {"mode": "existing"},
                         "tls": [{"secretName": "another-secret"}]}},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_form_defaults_and_visibility_paths_exist(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        self.assertNotIn("image.tag", [question["variable"] for question in questions])
        self.assertFalse(any(question["variable"].startswith("auth.") for question in questions))
        secret_question = next(question for question in questions
                               if question["variable"] == "magpie.envSecret")
        self.assertEqual(secret_question["type"], "reference[secret]")

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
