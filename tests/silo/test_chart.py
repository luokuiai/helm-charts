"""Run with: uv run --with pyyaml python tests/silo/test_chart.py."""

import base64
from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/silo/1.0.0"
PASSWORD = "test-password-123456"


def render(values=None, *, with_password=True, release="silo"):
    supplied = {"silo": {"envSecret": ""}, "auth": {"rootPassword": PASSWORD}} if with_password else {}
    for key, value in (values or {}).items():
        if isinstance(value, dict) and key in supplied:
            supplied[key].update(value)
        else:
            supplied[key] = value
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "storage",
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


def container(docs):
    return resource(docs, "StatefulSet")["spec"]["template"]["spec"]["containers"][0]


def environment(docs):
    return {item["name"]: item for item in container(docs)["env"]}


def ingress(mode="disabled", **certificate):
    return {"ingress": {"enabled": True, "className": "traefik",
                        "apiHost": "s3.example.org", "consoleHost": "console.example.org",
                        "certificate": {"mode": mode, **certificate}}}


class SiloChartTests(unittest.TestCase):
    def test_environment_secret_is_the_default_credential_source(self):
        for replicas in (1, 3):
            for secret in ("silo-env", "custom-env"):
                with self.subTest(replicas=replicas, secret=secret):
                    docs = manifests({"replicaCount": replicas, "silo": {"envSecret": secret}},
                                     with_password=False)
                    self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
                    self.assertEqual(container(docs)["envFrom"], [{"secretRef": {"name": secret}}])
                    for key in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
                        self.assertEqual(environment(docs)[key]["valueFrom"]["secretKeyRef"],
                                         {"name": secret, "key": key})
                    pod = resource(docs, "StatefulSet")["spec"]["template"]
                    self.assertNotIn("checksum/auth", pod["metadata"].get("annotations", {}))
        self.assertEqual(render(with_password=False).returncode, 0)

    def test_environment_secret_takes_precedence_over_legacy_credentials(self):
        docs = manifests({"silo": {"envSecret": "silo-env"}, "auth": {
            "useExistingSecret": True, "existingSecret": "legacy-root",
            "rootUser": "ab", "rootPassword": "short"}})
        self.assertFalse(any(doc["kind"] == "Secret" for doc in docs))
        for key in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"):
            self.assertEqual(environment(docs)[key]["valueFrom"]["secretKeyRef"],
                             {"name": "silo-env", "key": key})

    def test_full_image_references_in_single_and_distributed_modes(self):
        pinned = "RELEASE.2026-10-26T00-00-00Z"
        digest = "sha256:" + "a" * 64
        cases = [
            ({}, f"pgsty/silo:{pinned}"),
            ({"repository": "pgsty/silo"}, f"pgsty/silo:{pinned}"),
            ({"repository": "registry.example.com:5000/team/silo"},
             f"registry.example.com:5000/team/silo:{pinned}"),
            ({"repository": f"registry.example.com:5000/team/silo:{pinned}", "tag": "legacy"},
             f"registry.example.com:5000/team/silo:{pinned}"),
            ({"repository": f"pgsty/silo@{digest}", "tag": "legacy"}, f"pgsty/silo@{digest}"),
            ({"repository": "pgsty/silo", "tag": "custom"}, "pgsty/silo:custom"),
        ]
        for replicas in (1, 3):
            for image, expected in cases:
                with self.subTest(replicas=replicas, image=image):
                    app = container(manifests({"replicaCount": replicas, "image": image}))
                    self.assertEqual(app["image"], expected)
                    self.assertEqual(app["imagePullPolicy"], "IfNotPresent")

    def test_standalone_persists_data_and_retains_claim(self):
        docs = manifests()
        stateful = resource(docs, "StatefulSet")["spec"]
        self.assertEqual(stateful["replicas"], 1)
        self.assertEqual(stateful["serviceName"], "silo-headless")
        self.assertNotIn("volumeClaimTemplates", stateful)
        self.assertEqual(stateful["template"]["spec"]["volumes"],
                         [{"name": "data", "persistentVolumeClaim": {"claimName": "silo-data"}}])
        self.assertEqual(container(docs)["command"], ["/usr/bin/silo"])
        self.assertEqual(container(docs)["args"],
                         ["server", "--address", ":9000", "--console-address", ":9001", "/data"])
        self.assertEqual(container(docs)["image"], "pgsty/silo:RELEASE.2026-10-26T00-00-00Z")
        self.assertEqual(container(docs)["volumeMounts"], [{"name": "data", "mountPath": "/data"}])
        claim = resource(docs, "PersistentVolumeClaim")
        self.assertEqual(claim["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        self.assertEqual(claim["spec"]["storageClassName"], "local-path")
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "10Gi")
        self.assertFalse(any(d["kind"] in ("Ingress", "PodDisruptionBudget") for d in docs))

    def test_every_integer_from_two_to_sixteen_renders_distributed_peers(self):
        for replicas in range(2, 17):
            with self.subTest(replicas=replicas):
                docs = manifests({"replicaCount": replicas}, release="objects")
                stateful = resource(docs, "StatefulSet")["spec"]
                self.assertEqual(stateful["replicas"], replicas)
                self.assertEqual(stateful["podManagementPolicy"], "Parallel")
                self.assertEqual(stateful["persistentVolumeClaimRetentionPolicy"],
                                 {"whenDeleted": "Retain", "whenScaled": "Retain"})
                peers = container(docs)["args"][5:]
                self.assertEqual(peers, [
                    f"http://objects-{i}.objects-headless.storage.svc.cluster.local:9000/data"
                    for i in range(replicas)])
                self.assertNotIn("volumes", stateful["template"]["spec"])
                claims = stateful["volumeClaimTemplates"]
                self.assertEqual(len(claims), 1)
                self.assertEqual(claims[0]["metadata"]["name"], "data")
                self.assertEqual(claims[0]["spec"]["resources"]["requests"]["storage"], "10Gi")
                self.assertFalse(any(d["kind"] == "PersistentVolumeClaim" for d in docs))
                anti = stateful["template"]["spec"]["affinity"]["podAntiAffinity"]
                rule = anti["requiredDuringSchedulingIgnoredDuringExecution"][0]
                self.assertEqual(rule["topologyKey"], "kubernetes.io/hostname")
                self.assertEqual(rule["labelSelector"], stateful["selector"])
                pdb = resource(docs, "PodDisruptionBudget")["spec"]
                self.assertEqual(pdb["maxUnavailable"], 0 if replicas == 2 else 1)

    def test_peer_dns_uses_custom_domain(self):
        docs = manifests({"replicaCount": 3, "clusterDomain": "kube.internal"})
        self.assertEqual(container(docs)["args"][-1],
                         "http://silo-2.silo-headless.storage.svc.kube.internal:9000/data")

    def test_existing_secret_and_standalone_claim(self):
        docs = manifests({"silo": {"envSecret": ""},
                          "auth": {"useExistingSecret": True, "existingSecret": "object-credentials"},
                          "persistence": {"existingClaim": "existing-objects"}}, with_password=False)
        self.assertFalse(any(d["kind"] in ("Secret", "PersistentVolumeClaim") for d in docs))
        for variable, key in [("MINIO_ROOT_USER", "rootUser"), ("MINIO_ROOT_PASSWORD", "rootPassword")]:
            self.assertEqual(environment(docs)[variable]["valueFrom"]["secretKeyRef"],
                             {"name": "object-credentials", "key": key})
        pod = resource(docs, "StatefulSet")["spec"]["template"]
        self.assertNotIn("checksum/auth", pod["metadata"].get("annotations", {}))
        self.assertEqual(pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"],
                         "existing-objects")

    def test_credentials_are_secret_backed_and_rotation_restarts_pods(self):
        docs = manifests()
        data = resource(docs, "Secret")["data"]
        self.assertEqual(base64.b64decode(data["rootUser"]).decode(), "silo-admin")
        self.assertEqual(base64.b64decode(data["rootPassword"]).decode(), PASSWORD)
        before = resource(docs, "StatefulSet")["spec"]["template"]
        self.assertNotIn(PASSWORD, yaml.safe_dump(before))
        after = resource(manifests({"auth": {"rootPassword": "another-test-password"}}),
                         "StatefulSet")["spec"]["template"]
        self.assertNotEqual(before["metadata"]["annotations"]["checksum/auth"],
                            after["metadata"]["annotations"]["checksum/auth"])

    def test_security_probes_and_service_discovery(self):
        docs = manifests()
        pod = resource(docs, "StatefulSet")["spec"]["template"]["spec"]
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 1000)
        self.assertEqual(pod["securityContext"]["fsGroup"], 1000)
        self.assertTrue(pod["securityContext"]["runAsNonRoot"])
        self.assertFalse(container(docs)["securityContext"]["allowPrivilegeEscalation"])
        for probe in ["startupProbe", "livenessProbe"]:
            self.assertEqual(container(docs)[probe]["httpGet"],
                             {"path": "/minio/health/live", "port": "api"})
        self.assertEqual(container(docs)["readinessProbe"]["httpGet"],
                         {"path": "/minio/health/ready", "port": "api"})
        service = resource(docs, "Service", "silo")["spec"]
        self.assertEqual(service["type"], "ClusterIP")
        self.assertEqual({p["name"]: p["port"] for p in service["ports"]},
                         {"api": 9000, "console": 9001})
        headless = resource(docs, "Service", "silo-headless")["spec"]
        self.assertEqual(headless["clusterIP"], "None")
        self.assertTrue(headless["publishNotReadyAddresses"])

    def test_default_storage_class_in_both_modes(self):
        for replicas in [1, 2]:
            with self.subTest(replicas=replicas):
                docs = manifests({"replicaCount": replicas, "persistence": {"storageClass": ""}})
                claim = (resource(docs, "PersistentVolumeClaim") if replicas == 1 else
                         resource(docs, "StatefulSet")["spec"]["volumeClaimTemplates"][0])
                self.assertNotIn("storageClassName", claim["spec"])

    def test_separate_api_console_hosts_and_tls(self):
        docs = manifests(ingress("existing", secretName="storage-tls"))
        route = resource(docs, "Ingress")["spec"]
        self.assertEqual(route["ingressClassName"], "traefik")
        self.assertEqual(route["tls"], [{"secretName": "storage-tls", "hosts":
                                       ["s3.example.org", "console.example.org"]}])
        rules = {r["host"]: r["http"]["paths"][0] for r in route["rules"]}
        for host, port in [("s3.example.org", "api"), ("console.example.org", "console")]:
            self.assertEqual(rules[host]["path"], "/")
            self.assertEqual(rules[host]["backend"]["service"],
                             {"name": "silo", "port": {"name": port}})
        self.assertEqual(environment(docs)["MINIO_BROWSER_REDIRECT_URL"]["value"],
                         "https://console.example.org")

    def test_http_and_internal_console_access(self):
        self.assertNotIn("MINIO_BROWSER_REDIRECT_URL", environment(manifests()))
        docs = manifests(ingress())
        self.assertNotIn("tls", resource(docs, "Ingress")["spec"])
        self.assertEqual(environment(docs)["MINIO_BROWSER_REDIRECT_URL"]["value"],
                         "http://console.example.org")

    def test_api_and_console_ingress_can_be_enabled_independently(self):
        for replicas in (1, 3):
            for api, console in ((False, True), (True, False), (False, False)):
                with self.subTest(replicas=replicas, api=api, console=console):
                    values = ingress("cert-manager", issuerName="letsencrypt")
                    values["replicaCount"] = replicas
                    values["ingress"].update({"apiEnabled": api, "consoleEnabled": console})
                    if not api:
                        values["ingress"]["apiHost"] = ""
                    if not console:
                        values["ingress"]["consoleHost"] = ""
                    docs = manifests(values)
                    routes = [doc for doc in docs if doc["kind"] == "Ingress"]
                    expected = {}
                    if api:
                        expected["s3.example.org"] = "api"
                    if console:
                        expected["console.example.org"] = "console"
                    if expected:
                        route, = routes
                        self.assertEqual({rule["host"]: rule["http"]["paths"][0]["backend"][
                            "service"]["port"]["name"] for rule in route["spec"]["rules"]}, expected)
                        self.assertEqual(set(route["spec"]["tls"][0]["hosts"]), set(expected))
                    else:
                        self.assertFalse(routes)
                    self.assertEqual("MINIO_BROWSER_REDIRECT_URL" in environment(docs), console)
                    self.assertEqual({port["name"]: port["port"]
                                      for port in resource(docs, "Service", "silo")["spec"]["ports"]},
                                     {"api": 9000, "console": 9001})

    def test_disabled_endpoints_do_not_require_a_hostname_or_certificate(self):
        values = ingress("cert-manager")
        values["ingress"].update({"apiEnabled": False, "consoleEnabled": False,
                                  "apiHost": "", "consoleHost": ""})
        docs = manifests(values)
        self.assertFalse(any(doc["kind"] == "Ingress" for doc in docs))
        self.assertNotIn("MINIO_BROWSER_REDIRECT_URL", environment(docs))

    def test_certificate_issuer_selectors(self):
        for kind, key in [("Issuer", "cert-manager.io/issuer"),
                          ("ClusterIssuer", "cert-manager.io/cluster-issuer")]:
            with self.subTest(kind=kind):
                values = ingress("cert-manager", issuerKind=kind, issuerName="letsencrypt")
                values["ingress"]["annotations"] = {"cert-manager.io/issuer": "old",
                    "cert-manager.io/cluster-issuer": "old", "custom.annotation": "kept"}
                route = resource(manifests(values), "Ingress")
                self.assertEqual(route["metadata"]["annotations"],
                                 {key: "letsencrypt", "custom.annotation": "kept"})
                self.assertEqual(route["spec"]["tls"][0]["secretName"], "silo-tls")

    def test_invalid_configurations_are_rejected(self):
        self.assertNotEqual(render({"silo": {"envSecret": ""}}, with_password=False).returncode, 0)
        cases = [{"silo": {"envSecret": "bad/name"}}, {"silo": {"envSecret": 123}}] + [{"replicaCount": n} for n in [0, -1, 17, 2.5, "3", True]] + [
            {"auth": {"rootUser": "ab"}}, {"auth": {"rootPassword": "short"}},
            {"auth": {"useExistingSecret": True}},
            {"replicaCount": 2, "persistence": {"existingClaim": "shared-data"}},
            {"persistence": {"size": "bad-size"}}, {"clusterDomain": "bad/domain"},
            ingress("invalid"), ingress("existing", secretName=""), ingress("cert-manager"),
            {"ingress": {"enabled": True, "apiHost": "same.test", "consoleHost": "same.test"}},
            {"ingress": {"apiHost": "https://example.org"}},
            {"ingress": {"enabled": True, "consoleHost": ""}},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_form_defaults_and_numeric_node_input(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        variables = {question["variable"]: question for question in questions}
        self.assertNotIn("image.tag", variables)
        self.assertFalse(any(variable.startswith("auth.") for variable in variables))
        self.assertEqual(variables["silo.envSecret"]["type"], "reference[secret]")
        self.assertTrue(variables["silo.envSecret"]["required"])

        def value_at(path):
            value = values
            for part in path.split("."):
                value = value[part]
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
        nodes = next(q for q in questions if q["variable"] == "replicaCount")
        self.assertEqual(nodes["type"], "int")
        self.assertNotIn("options", nodes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
