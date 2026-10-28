"""Run with: uv run --with pyyaml python tests/openbao/test_chart.py."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/openbao/1.0.0"


def render(*overrides, release="openbao"):
    command = [
        "helm", "template", release, str(CHART),
        "--namespace", "secrets", "--kube-version", "1.30.0",
    ]
    for override in overrides:
        command.extend(["--set", override])
    return subprocess.run(command, capture_output=True, text=True)


def manifests(*overrides, release="openbao"):
    result = render(*overrides, release=release)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(docs, kind, name=None):
    matches = [doc for doc in docs if doc["kind"] == kind
               and (name is None or doc["metadata"]["name"] == name)]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind} {name}, found {len(matches)}")
    return matches[0]


class OpenBaoChartTests(unittest.TestCase):
    def test_full_image_reference_for_server_and_test_hook(self):
        digest = "sha256:" + "a" * 64
        cases = [
            ((), "openbao/openbao:2.7.2"),
            (("server.image.repository=openbao/openbao",), "openbao/openbao:2.7.2"),
            (("server.image.repository=openbao/openbao:2.7.2",), "openbao/openbao:2.7.2"),
            (("server.image.repository=docker.io/openbao/openbao",),
             "docker.io/openbao/openbao:2.7.2"),
            (("server.image.repository=quay.io/openbao/openbao",),
             "quay.io/openbao/openbao:2.7.2"),
            (("server.image.repository=registry.example.com:5000/team/openbao:custom",),
             "registry.example.com:5000/team/openbao:custom"),
            (("server.image.repository=registry.example.com:5000/team/openbao",
              "server.image.tag=custom"), "registry.example.com:5000/team/openbao:custom"),
            (("server.image.repository=localhost:5000/openbao",),
             "localhost:5000/openbao:2.7.2"),
            (("server.image.registry=quay.io",), "quay.io/openbao/openbao:2.7.2"),
            (("server.image.registry=quay.io",
              "server.image.repository=docker.io/openbao/openbao"),
             "docker.io/openbao/openbao:2.7.2"),
            (("server.image.registry=quay.io",
              "server.image.repository=registry.example.com/team/openbao:2.7.2",
              "server.image.tag=legacy"), "registry.example.com/team/openbao:2.7.2"),
            (("server.image.repository=openbao/openbao:2.7.1", "server.image.tag=legacy"),
             "openbao/openbao:2.7.1"),
            (("server.image.repository=openbao/openbao", "server.image.tag=2.7.2"),
             "openbao/openbao:2.7.2"),
            ((f"server.image.repository=openbao/openbao@{digest}",),
             f"openbao/openbao@{digest}"),
        ]
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                docs = manifests(*overrides)
                server = resource(docs, "StatefulSet")["spec"]["template"]["spec"]["containers"][0]
                hook = resource(docs, "Pod", "openbao-server-test")["spec"]["containers"][0]
                self.assertEqual(server["image"], expected)
                self.assertEqual(hook["image"], expected)
                self.assertEqual(server["imagePullPolicy"], "IfNotPresent")
                self.assertEqual(hook["imagePullPolicy"], "IfNotPresent")

    def test_standalone_persistence_and_no_public_ingress(self):
        docs = manifests()
        stateful = resource(docs, "StatefulSet")
        self.assertEqual(stateful["spec"]["replicas"], 1)
        self.assertEqual(stateful["spec"]["podManagementPolicy"], "Parallel")
        self.assertEqual(stateful["spec"]["persistentVolumeClaimRetentionPolicy"],
                         {"whenDeleted": "Retain", "whenScaled": "Retain"})
        claim = stateful["spec"]["volumeClaimTemplates"][0]["spec"]
        self.assertEqual(claim["storageClassName"], "local-path")
        self.assertEqual(claim["resources"]["requests"]["storage"], "10Gi")
        self.assertFalse(any(doc["kind"] in ("Deployment", "Ingress", "PodDisruptionBudget")
                             for doc in docs))
        config = resource(docs, "ConfigMap")["data"]["extraconfig-from-values.hcl"]
        self.assertIn('storage "pebbledb"', config)
        self.assertNotIn('storage "raft"', config)

    def test_raft_topology_and_domain_route_to_leader(self):
        for replicas in (3, 5):
            with self.subTest(replicas=replicas):
                docs = manifests("server.ha.enabled=true", f"server.ha.replicas={replicas}",
                                 "server.ingress.enabled=true", release="secrets-store")
                stateful = resource(docs, "StatefulSet")
                name = stateful["metadata"]["name"]
                self.assertEqual(stateful["spec"]["replicas"], replicas)
                pod = stateful["spec"]["template"]["spec"]
                affinity = pod["affinity"]["podAntiAffinity"]
                self.assertIn("requiredDuringSchedulingIgnoredDuringExecution", affinity)
                env = {item["name"]: item for item in pod["containers"][0]["env"]}
                self.assertEqual(env["BAO_RAFT_NODE_ID"]["valueFrom"]["fieldRef"]["fieldPath"],
                                 "metadata.name")
                config = resource(docs, "ConfigMap")["data"]["extraconfig-from-values.hcl"]
                self.assertIn('storage "raft"', config)
                self.assertIn('service_registration "kubernetes"', config)
                self.assertEqual(config.count("retry_join {"), replicas)
                for node in range(replicas):
                    self.assertIn(f'http://{name}-{node}.{name}-internal:8200', config)
                self.assertEqual(resource(docs, "PodDisruptionBudget")["spec"]["maxUnavailable"],
                                 (replicas - 1) // 2)
                backend = resource(docs, "Ingress")["spec"]["rules"][0]["http"]["paths"][0]
                self.assertEqual(backend["backend"]["service"]["name"], f"{name}-active")
                self.assertEqual(resource(docs, "Service", f"{name}-active")["spec"]
                                 ["selector"]["openbao-active"], "true")

    def test_https_existing_secret_in_both_modes(self):
        for ha in ("false", "true"):
            with self.subTest(ha=ha):
                docs = manifests(f"server.ha.enabled={ha}", "server.ingress.enabled=true",
                                 "server.ingress.hosts[0].host=bao.example.com",
                                 "server.ingress.ingressClassName=traefik",
                                 "server.ingress.certificate.mode=existing",
                                 "server.ingress.certificate.secretName=bao-tls")
                ingress = resource(docs, "Ingress")
                self.assertEqual(ingress["spec"]["ingressClassName"], "traefik")
                self.assertEqual(ingress["spec"]["tls"], [
                    {"hosts": ["bao.example.com"], "secretName": "bao-tls"}])
                path = ingress["spec"]["rules"][0]["http"]["paths"][0]
                self.assertEqual(path["path"], "/")
                self.assertEqual(path["backend"]["service"]["name"],
                                 "openbao-active" if ha == "true" else "openbao")

    def test_http_ingress_omits_tls(self):
        ingress = resource(manifests("server.ingress.enabled=true"), "Ingress")
        self.assertNotIn("tls", ingress["spec"])

    def test_upstream_annotation_formats_and_templates_are_preserved(self):
        for override in (
            "server.ingress.annotations.example\\.com/release=release-{{ .Release.Name }}",
            "server.ingress.annotations=example.com/release: 'release-{{ .Release.Name }}'",
        ):
            with self.subTest(override=override):
                ingress = resource(manifests("server.ingress.enabled=true", override), "Ingress")
                self.assertEqual(ingress["metadata"]["annotations"],
                                 {"example.com/release": "release-openbao"})

    def test_cert_manager_issuer_annotations(self):
        for kind, annotation in (("Issuer", "cert-manager.io/issuer"),
                                 ("ClusterIssuer", "cert-manager.io/cluster-issuer")):
            with self.subTest(kind=kind):
                ingress = resource(manifests(
                    "server.ingress.enabled=true",
                    "server.ingress.certificate.mode=cert-manager",
                    f"server.ingress.certificate.issuerKind={kind}",
                    "server.ingress.certificate.issuerName=letsencrypt",
                    "server.ingress.annotations.cert-manager\\.io/issuer=stale",
                    "server.ingress.annotations.cert-manager\\.io/cluster-issuer=stale",
                ), "Ingress")
                annotations = ingress["metadata"]["annotations"]
                self.assertEqual(annotations, {annotation: "letsencrypt"})
                self.assertEqual(ingress["spec"]["tls"][0]["secretName"], "openbao-tls")

    def test_invalid_form_values_are_rejected(self):
        cases = [
            ("server.ha.enabled=true", "server.ha.replicas=2"),
            ("server.ha.enabled=true", "server.ha.replicas=4"),
            ("server.ha.enabled=true", "server.ha.raft.enabled=false"),
            ("server.ingress.enabled=true", "server.ingress.certificate.mode=invalid"),
            ("server.ingress.enabled=true", "server.ingress.certificate.mode=cert-manager"),
            ("server.ingress.enabled=true", "server.ingress.hosts[0].host="),
            ("server.ingress.enabled=true", "server.ingress.certificate.mode=existing",
             "server.ingress.certificate.secretName="),
            ("server.ingress.enabled=true", "server.ingress.certificate.mode=existing",
             "server.ingress.tls[0].secretName=another-secret"),
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = render(*overrides)
                self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_form_defaults_and_visibility_paths_exist(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        self.assertNotIn("server.image.registry", [q["variable"] for q in questions])
        self.assertNotIn("server.image.tag", [q["variable"] for q in questions])

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
