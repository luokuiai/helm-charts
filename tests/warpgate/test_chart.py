"""uv run --with pyyaml python tests/warpgate/test_chart.py

Set WARPGATE_BIN to a Warpgate 0.30.2 binary to include runtime integration tests.
Requires Docker, ssh-keyscan and a cached postgres:16-alpine image; creates a disposable database.
"""

import base64
import http.client
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, quote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/warpgate/1.0.0"
BINARY = os.environ.get("WARPGATE_BIN")
OIDC = {"enabled": True, "issuerURL": "https://auth.example.com", "clientID": "warpgate"}


def render(values=None, release="warpgate"):
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "access", "--values", "-"],
        input=yaml.safe_dump(values or {}), capture_output=True, text=True,
    )


def manifests(values=None, **kwargs):
    result = render(values, **kwargs)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(docs, kind):
    found = [doc for doc in docs if doc["kind"] == kind]
    if len(found) != 1:
        raise AssertionError(f"Expected one {kind}; found {len(found)}")
    return found[0]


def config(docs):
    return yaml.safe_load(resource(docs, "ConfigMap")["data"]["warpgate.yaml"])


class ChartTests(unittest.TestCase):
    def test_s3_configuration_uses_environment_credentials_and_optional_ephemeral_storage(self):
        for endpoint in ("", "https://s3.example.com"):
            with self.subTest(endpoint=endpoint):
                docs = manifests({"recordings": {"s3": {"enabled": True, "bucket": "recordings",
                                   "endpoint": endpoint, "prefix": "sessions/o'hare"}},
                                  "persistence": {"enabled": False}})
                self.assertFalse(any(d["kind"] == "PersistentVolumeClaim" for d in docs))
                pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
                self.assertEqual(pod["volumes"][0], {"name": "data", "emptyDir": {"sizeLimit": "1Gi"}})
                setup = pod["initContainers"][2]
                self.assertEqual(setup["name"], "configure-recordings")
                self.assertEqual(setup["image"], "postgres:18.6-alpine")
                self.assertEqual(setup["command"], ["psql"])
                self.assertIn("--set=ON_ERROR_STOP=1", setup["args"])
                self.assertEqual(setup["envFrom"], [{"secretRef": {"name": "warpgate-env"}}])
                self.assertEqual(setup["env"][0]["valueFrom"]["secretKeyRef"],
                                 {"name": "warpgate-env", "key": "WARPGATE_DATABASE_URL"})
                storage = json.loads(setup["env"][1]["value"])
                self.assertEqual(storage, {"kind": "S3", "bucket": "recordings", "region": "us-east-1",
                    "endpoint": endpoint or None, "prefix": "sessions/o'hare", "path_style": True,
                    "credentials": {"mode": "Auto"}, "scratch_path": "/data/recordings-scratch"})
                refs = {e["name"]: e["valueFrom"]["secretKeyRef"]
                        for e in pod["containers"][0]["env"] if "secretKeyRef" in e["valueFrom"]}
                self.assertEqual(set(refs), {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"})
                for key, ref in refs.items():
                    self.assertEqual(ref, {"name": "warpgate-env", "key": key})
                sql = resource(docs, "ConfigMap")["data"]["configure-recordings.sql"]
                self.assertIn("\\getenv storage WARPGATE_RECORDINGS_STORAGE", sql)
                self.assertIn("SET recordings_storage = :'storage'", sql)
                self.assertNotIn("sessions/o'hare", sql)

    def test_untagged_mirror_uses_the_pinned_application_version(self):
        docs = manifests({"image": {"repository": "mirror.example.com:5000/team/warpgate"}})
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        for container in pod["initContainers"] + pod["containers"]:
            self.assertEqual(container["image"], "mirror.example.com:5000/team/warpgate:0.30.2")

    def test_default_is_single_replica_with_local_recordings_and_pvc(self):
        docs = manifests()
        deployment = resource(docs, "Deployment")
        self.assertEqual(deployment["spec"]["replicas"], 1)
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        pvc = resource(docs, "PersistentVolumeClaim")
        self.assertEqual(pvc["spec"]["resources"]["requests"]["storage"], "1Gi")
        self.assertEqual(pvc["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], "warpgate-data")
        self.assertEqual(len(pod["containers"]), 1)
        self.assertEqual(len(pod["initContainers"]), 2)
        self.assertEqual(pod["securityContext"]["fsGroup"], 1000)
        self.assertFalse(pod["automountServiceAccountToken"])
        install = pod["initContainers"][0]
        self.assertEqual(install["args"], ["internal-install-files", "--substitute-env=WARPGATE_DATABASE_URL", "/seed", "/data"])
        self.assertEqual(install["env"][0]["valueFrom"]["secretKeyRef"],
                         {"name": "warpgate-env", "key": "WARPGATE_DATABASE_URL"})
        self.assertIn("--if-config-exists=bootstrap", pod["initContainers"][1]["args"])
        self.assertIn("--record-sessions", pod["initContainers"][1]["args"])
        self.assertNotIn("configure-recordings.sql", resource(docs, "ConfigMap")["data"])
        for container in pod["initContainers"] + pod["containers"]:
            self.assertEqual(container["image"], "ghcr.io/warp-tech/warpgate:0.30.2")
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "warpgate-env"}}])
        self.assertEqual(config(docs)["database_url"], "$WARPGATE_DATABASE_URL")
        self.assertFalse(any(d["kind"] in ("StatefulSet", "Job") for d in docs))
        self.assertEqual(config(docs)["sso_providers"], [])
        self.assertFalse(any(d["kind"] == "Ingress" for d in docs))
        probes = pod["containers"][0]
        for name in ("startupProbe", "readinessProbe", "livenessProbe"):
            self.assertEqual(probes[name]["exec"]["command"][-1], "healthcheck")

    def test_recordings_and_persistent_storage_can_be_disabled(self):
        docs = manifests({"warpgate": {"recordSessions": False}, "persistence": {"enabled": False}})
        self.assertFalse(any(d["kind"] == "PersistentVolumeClaim" for d in docs))
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        self.assertNotIn("--record-sessions", pod["initContainers"][1]["args"])
        self.assertEqual(pod["volumes"][0], {"name": "data", "emptyDir": {"sizeLimit": "1Gi"}})

    def test_ha_file_recordings_share_only_the_recording_volume(self):
        for replicas in (2, 3, 5):
            with self.subTest(replicas=replicas):
                docs = manifests({"ha": {"enabled": True, "replicas": replicas,
                                         "sharedRecordingsClaim": "recordings-rwx"}})
                self.assertFalse(any(d["kind"] in ("Deployment", "PersistentVolumeClaim") for d in docs))
                workload = resource(docs, "StatefulSet")["spec"]
                self.assertEqual(workload["replicas"], replicas)
                self.assertEqual(workload["podManagementPolicy"], "OrderedReady")
                self.assertEqual(workload["updateStrategy"], {"type": "RollingUpdate"})
                self.assertEqual(workload["persistentVolumeClaimRetentionPolicy"],
                                 {"whenDeleted": "Retain", "whenScaled": "Retain"})
                claim = workload["volumeClaimTemplates"][0]
                self.assertEqual(claim["metadata"]["name"], "data")
                self.assertEqual(claim["spec"], {"accessModes": ["ReadWriteOnce"],
                    "storageClassName": "local-path", "resources": {"requests": {"storage": "1Gi"}}})
                pod = workload["template"]["spec"]
                self.assertFalse(any(v["name"] == "data" for v in pod["volumes"]))
                self.assertIn({"name": "shared-recordings", "persistentVolumeClaim":
                               {"claimName": "recordings-rwx"}}, pod["volumes"])
                recording_mount = {"name": "shared-recordings", "mountPath": "/data/recordings"}
                self.assertIn(recording_mount, pod["containers"][0]["volumeMounts"])
                self.assertIn(recording_mount, pod["initContainers"][1]["volumeMounts"])
                self.assertNotIn(recording_mount, pod["initContainers"][0]["volumeMounts"])
                anti = pod["affinity"]["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
                self.assertEqual(anti, [{"topologyKey": "kubernetes.io/hostname",
                    "labelSelector": workload["selector"]}])
                env = {e["name"]: e["valueFrom"] for e in pod["containers"][0]["env"]}
                self.assertEqual(env["POD_IP"], {"fieldRef": {"fieldPath": "status.podIP"}})
                self.assertEqual(env["WARPGATE_ENCRYPTION_KEY"],
                    {"secretKeyRef": {"name": "warpgate-env", "key": "WARPGATE_ENCRYPTION_KEY"}})
                for container in pod["initContainers"] + pod["containers"]:
                    self.assertEqual(container["envFrom"], [{"secretRef": {"name": "warpgate-env"}}])
                services = {d["metadata"]["name"]: d["spec"] for d in docs if d["kind"] == "Service"}
                peers = services[workload["serviceName"]]
                self.assertEqual(peers["clusterIP"], "None")
                self.assertEqual(peers["ports"], [{"name": "https", "port": 8888, "targetPort": "https"}])
                self.assertEqual(services["warpgate"]["selector"], peers["selector"])
                pdb = resource(docs, "PodDisruptionBudget")["spec"]
                self.assertEqual(pdb["maxUnavailable"], 1)
                self.assertEqual(pdb["selector"], workload["selector"])

    def test_ha_s3_keeps_independent_buffers_and_exposes_native_tcp(self):
        docs = manifests({"ha": {"enabled": True}, "warpgate": {"envSecret": "access-env"},
                          "recordings": {"s3": {"enabled": True, "bucket": "recordings"}},
                          "service": {"type": "LoadBalancer", "annotations": {"example.com/internal": "true"}},
                          "ingress": {"enabled": True}, "oidc": OIDC,
                          "protocols": {"mysql": {"enabled": False}, "postgres": {"enabled": False}}})
        spec = resource(docs, "StatefulSet")["spec"]
        pod = spec["template"]["spec"]
        self.assertFalse(any(v["name"] == "shared-recordings" for v in pod["volumes"]))
        self.assertEqual(pod["containers"][0]["volumeMounts"], [{"name": "data", "mountPath": "/data"}])
        storage = json.loads(pod["initContainers"][2]["env"][1]["value"])
        self.assertEqual(storage["scratch_path"], "/data/recordings-scratch")
        for container in pod["initContainers"] + pod["containers"]:
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "access-env"}}])
        env = {e["name"]: e["valueFrom"] for e in pod["containers"][0]["env"]}
        for key in ("WARPGATE_ENCRYPTION_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            self.assertEqual(env[key], {"secretKeyRef": {"name": "access-env", "key": key}})
        entry = next(d["spec"] for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "warpgate")
        self.assertEqual(entry["type"], "LoadBalancer")
        self.assertEqual([p["name"] for p in entry["ports"]], ["https", "ssh"])
        self.assertTrue(any(d["kind"] == "Ingress" for d in docs))
        self.assertEqual(len(config(docs)["sso_providers"]), 1)

    def test_ha_can_scale_to_one_without_replacing_its_workload_or_claims(self):
        docs = manifests({"ha": {"enabled": True, "replicas": 1, "sharedRecordingsClaim": "recordings-rwx"},
                          "warpgate": {"recordSessions": False}})
        spec = resource(docs, "StatefulSet")["spec"]
        self.assertEqual(spec["replicas"], 1)
        self.assertFalse(any(d["kind"] == "PodDisruptionBudget" for d in docs))
        self.assertNotIn("--record-sessions", spec["template"]["spec"]["initContainers"][1]["args"])
        self.assertIn({"name": "shared-recordings", "mountPath": "/data/recordings"},
                      spec["template"]["spec"]["containers"][0]["volumeMounts"])

    def test_custom_image_secret_existing_storage_and_release_names(self):
        docs = manifests({"image": {"repository": "mirror.example.com:5000/team/warpgate@sha256:" + "a" * 64},
                          "warpgate": {"envSecret": "access-env", "backendTLSSecret": "backend-cert"},
                          "persistence": {"enabled": True, "existingClaim": "access-data"}}, release="bastion")
        self.assertFalse(any(d["kind"] in ("Secret", "PersistentVolumeClaim") for d in docs))
        deployment = resource(docs, "Deployment")
        self.assertEqual(deployment["metadata"]["name"], "bastion")
        pod = deployment["spec"]["template"]["spec"]
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], "access-data")
        self.assertEqual(pod["volumes"][1]["projected"]["sources"][1]["secret"]["name"], "backend-cert")
        for container in pod["initContainers"] + pod["containers"]:
            self.assertIn("@sha256:", container["image"])
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "access-env"}}])
        admin_ref = pod["initContainers"][1]["env"][0]["valueFrom"]["secretKeyRef"]
        self.assertEqual(admin_ref, {"name": "access-env", "key": "WARPGATE_ADMIN_PASSWORD"})
        self.assertEqual(pod["initContainers"][0]["env"][0]["valueFrom"]["secretKeyRef"],
                         {"name": "access-env", "key": "WARPGATE_DATABASE_URL"})

    def test_oidc_secrets_are_runtime_references_and_roles_are_nested_correctly(self):
        oidc = {**OIDC, "autoCreateUsers": True, "rolesClaim": "groups",
                "roleMappings": {"operators": ["servers", "databases"]}}
        docs = manifests({"oidc": oidc, "ingress": {"enabled": True}})
        settings = config(docs)
        self.assertEqual(settings["external_host"], "warpgate.example.com")
        self.assertEqual(settings["http"]["external_port"], 443)
        sso = settings["sso_providers"][0]
        self.assertTrue(sso["auto_create_users"])
        self.assertEqual(sso["return_domain_whitelist"], ["warpgate.example.com"])
        self.assertEqual(sso["provider"]["issuer_url"], OIDC["issuerURL"])
        self.assertEqual(sso["provider"]["client_secret"], "$WARPGATE_OIDC_CLIENT_SECRET")
        self.assertEqual(sso["provider"]["role_mappings"], oidc["roleMappings"])
        self.assertEqual(sso["provider"]["admin_role_mappings"], {})
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        install = pod["initContainers"][0]
        self.assertIn("--substitute-env=WARPGATE_DATABASE_URL WARPGATE_OIDC_CLIENT_SECRET", install["args"])
        self.assertEqual(install["env"][1]["valueFrom"]["secretKeyRef"],
                         {"name": "warpgate-env", "key": "WARPGATE_OIDC_CLIENT_SECRET"})
        self.assertEqual([d["metadata"]["name"] for d in docs if d["kind"] == "Secret"], ["warpgate-backend-tls"])

    def test_oidc_without_chart_ingress_uses_explicit_https_host_and_port(self):
        docs = manifests({"oidc": OIDC, "warpgate": {"externalHost": "access.example.com", "externalPort": 9443}})
        settings = config(docs)
        self.assertEqual(settings["external_host"], "access.example.com")
        self.assertEqual(settings["http"]["external_port"], 9443)
        self.assertFalse(settings["http"]["trust_x_forwarded_headers"])

    def test_traefik_verifies_backend_certificate_and_service_name(self):
        docs = manifests({"ingress": {"enabled": True, "className": "traefik"}})
        transport = resource(docs, "ServersTransport")
        self.assertEqual(transport["spec"], {"serverName": "warpgate.access.svc",
                                            "rootCAsSecrets": ["warpgate-backend-tls"]})
        annotations = resource(docs, "Service")["metadata"]["annotations"]
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/service.serversscheme"], "https")
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/service.serverstransport"],
                         "access-warpgate-backend@kubernetescrd")
        ingress = resource(docs, "Ingress")["spec"]
        self.assertEqual(ingress["ingressClassName"], "traefik")
        self.assertEqual(ingress["tls"], [{"secretName": "warpgate-tls", "hosts": ["warpgate.example.com"]}])
        self.assertEqual(ingress["rules"][0]["http"]["paths"][0]["backend"]["service"]["port"], {"name": "https"})
        secret = resource(docs, "Secret")
        self.assertEqual(secret["data"]["ca.crt"], secret["data"]["tls.crt"])

    def test_nginx_backend_verification_and_certificate_issuer_choices(self):
        for kind in ("Issuer", "ClusterIssuer"):
            docs = manifests({"ingress": {"enabled": True, "controller": "nginx", "className": "nginx",
                "annotations": {"cert-manager.io/issuer": "old", "cert-manager.io/cluster-issuer": "old"},
                "certificate": {"mode": "cert-manager", "issuerKind": kind, "issuerName": "letsencrypt"}}})
            self.assertFalse(any(d["kind"] == "ServersTransport" for d in docs))
            annotations = resource(docs, "Ingress")["metadata"]["annotations"]
            self.assertEqual(annotations["nginx.ingress.kubernetes.io/backend-protocol"], "HTTPS")
            self.assertEqual(annotations["nginx.ingress.kubernetes.io/proxy-ssl-verify"], "on")
            self.assertEqual(annotations["nginx.ingress.kubernetes.io/proxy-ssl-secret"], "access/warpgate-backend-tls")
            key = "cert-manager.io/issuer" if kind == "Issuer" else "cert-manager.io/cluster-issuer"
            self.assertEqual(annotations[key], "letsencrypt")
            self.assertEqual(sum(k.startswith("cert-manager.io/") for k in annotations), 1)

    def test_protocol_switches_ports_and_nodeports_stay_consistent(self):
        docs = manifests({"service": {"type": "NodePort", "httpsNodePort": 30888}, "protocols": {
            "ssh": {"port": 2223, "nodePort": 30222}, "mysql": {"enabled": False},
            "postgres": {"enabled": False}}})
        ports = resource(docs, "Service")["spec"]["ports"]
        self.assertEqual(ports, [{"name": "https", "port": 8888, "targetPort": "https", "nodePort": 30888},
                                 {"name": "ssh", "port": 2223, "targetPort": "ssh", "nodePort": 30222}])
        settings = config(docs)
        self.assertTrue(settings["ssh"]["enable"])
        self.assertEqual(settings["ssh"]["listen"], "0.0.0.0:2223")
        self.assertFalse(settings["mysql"]["enable"])
        self.assertFalse(settings["postgres"]["enable"])
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        self.assertIn("--ssh-port=2223", pod["initContainers"][1]["args"])
        self.assertNotIn("--mysql-port=33306", pod["initContainers"][1]["args"])
        self.assertEqual(pod["containers"][0]["ports"], [{"name": "https", "containerPort": 8888},
                                                         {"name": "ssh", "containerPort": 2223}])

    def test_invalid_configuration_is_rejected(self):
        cases = [
            {"warpgate": {"envSecret": ""}}, {"warpgate": {"envSecret": "bad/name"}},
            {"warpgate": {"externalHost": "https://host"}}, {"warpgate": {"externalPort": 65536}},
            {"oidc": {"enabled": True}}, {"oidc": OIDC},
            {"oidc": {**OIDC, "clientID": ""}, "ingress": {"enabled": True}},
            {"oidc": {**OIDC, "issuerURL": "not-a-url"}, "ingress": {"enabled": True}},
            {"oidc": {**OIDC, "issuerURL": "https://auth.example.com?invalid"}, "ingress": {"enabled": True}},
            {"protocols": {"ssh": {"port": 8888}}}, {"protocols": {"ssh": {"port": 33306}}},
            {"protocols": {"ssh": {"port": 22}}}, {"protocols": {"mysql": {"port": 65536}}},
            {"ingress": {"controller": "unknown"}}, {"ingress": {"hostname": "https://host"}},
            {"ingress": {"certificate": {"mode": "disabled"}}},
            {"ingress": {"enabled": True, "certificate": {"mode": "cert-manager"}}},
            {"ingress": {"enabled": True}, "warpgate": {"externalHost": "different.example.com"}},
            {"persistence": {"size": "0Gi"}},
            {"recordings": {"s3": {"enabled": True}}},
            {"recordings": {"s3": {"endpoint": "silo:9000"}}},
            {"recordings": {"s3": {"region": ""}}},
            {"recordings": {"s3": {"prefix": ""}}},
            {"recordings": {"s3": {"prefix": "/sessions"}}},
            {"ha": {"replicas": 0}}, {"ha": {"replicas": "2"}},
            {"ha": {"sharedRecordingsClaim": "bad/name"}},
            {"ha": {"enabled": True}},
            {"ha": {"enabled": True}, "warpgate": {"recordSessions": False}},
            {"ha": {"enabled": True, "sharedRecordingsClaim": "recordings-rwx"},
             "persistence": {"enabled": False}},
            {"ha": {"enabled": True, "sharedRecordingsClaim": "recordings-rwx"},
             "persistence": {"existingClaim": "shared-data"}},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_form_defaults_metadata_and_visibility_paths(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        metadata = yaml.safe_load((CHART / "Chart.yaml").read_text())
        self.assertEqual(metadata["version"], "1.0.0")
        self.assertNotIn("catalog.cattle.io/release-name", metadata["annotations"])
        self.assertTrue((CHART / "icon.png").read_bytes().startswith(b"\x89PNG"))

        def value_at(path):
            current = values
            for part in path.split("."):
                current = current[part]
            return current

        for question in questions:
            with self.subTest(variable=question["variable"]):
                expected = question["default"]
                if question["type"] == "boolean":
                    expected = str(expected).lower() == "true"
                self.assertEqual(value_at(question["variable"]), expected)
                for condition in question.get("show_if", "").split("&&"):
                    if condition:
                        value_at(condition.split("=", 1)[0])

    def test_documented_casdoor_example_uses_the_shared_environment_secret(self):
        values = yaml.safe_load((ROOT / "docs/warpgate/oidc-values.example.yaml").read_text())
        secret = yaml.safe_load((ROOT / "docs/warpgate/env-secret.example.yaml").read_text())
        self.assertEqual(values["warpgate"]["envSecret"], secret["metadata"]["name"])
        self.assertIn("WARPGATE_ADMIN_PASSWORD", secret["stringData"])
        self.assertTrue(secret["stringData"]["WARPGATE_DATABASE_URL"].startswith("postgresql://"))
        self.assertIn("WARPGATE_OIDC_CLIENT_SECRET", secret["stringData"])
        docs = manifests(values)
        settings = config(docs)
        self.assertEqual(settings["external_host"], "access.example.com")
        self.assertEqual(settings["sso_providers"][0]["name"], "casdoor")
        self.assertEqual(settings["sso_providers"][0]["provider"]["issuer_url"], "https://auth.example.com")
        self.assertTrue(settings["sso_providers"][0]["auto_create_users"])

    def test_documented_s3_example_uses_no_pvc(self):
        values = yaml.safe_load((ROOT / "docs/warpgate/s3-values.example.yaml").read_text())
        docs = manifests(values)
        self.assertFalse(any(d["kind"] == "PersistentVolumeClaim" for d in docs))
        self.assertEqual(resource(docs, "Deployment")["spec"]["template"]["spec"]["initContainers"][-1]["name"],
                         "configure-recordings")

    def test_documented_ha_example_uses_retained_data_and_shared_file_recordings(self):
        values = yaml.safe_load((ROOT / "docs/warpgate/ha-values.example.yaml").read_text())
        docs = manifests(values)
        self.assertEqual(resource(docs, "StatefulSet")["spec"]["replicas"], 2)
        self.assertFalse(values["recordings"]["s3"]["enabled"])
        self.assertTrue(values["persistence"]["enabled"])
        self.assertEqual(values["ha"]["sharedRecordingsClaim"], "warpgate-recordings")


class Discovery(BaseHTTPRequestHandler):
    def do_GET(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.path.endswith("/.well-known/openid-configuration"):
            body = {"issuer": origin, "authorization_endpoint": origin + "/authorize",
                    "token_endpoint": origin + "/token", "jwks_uri": origin + "/jwks",
                    "response_types_supported": ["code"], "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "token_endpoint_auth_methods_supported": ["client_secret_basic"]}
        elif self.path == "/jwks":
            body = {"keys": []}
        else:
            self.send_error(404)
            return
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


@unittest.skipUnless(BINARY, "Set WARPGATE_BIN for native initialization and OIDC tests")
class RuntimeTests(unittest.TestCase):
    def test_native_bootstrap_oidc_cluster_proxy_and_instance_failure(self):
        # This test owns an isolated database, never an externally supplied connection.
        credential = "test-only'@:/&value"
        container = subprocess.check_output([
            "docker", "run", "--rm", "--detach", "--pull=never",
            "--publish", "127.0.0.1::5432", "--env", "POSTGRES_USER=warpgate_test",
            "--env", "POSTGRES_DB=warpgate", "--env", f"POSTGRES_PASSWORD={credential}",
            "postgres:16-alpine",
        ], text=True, timeout=60).strip()
        self.addCleanup(subprocess.run, ["docker", "rm", "--force", container],
                        capture_output=True, timeout=30)
        endpoint = subprocess.check_output(["docker", "port", container, "5432/tcp"], text=True, timeout=10).strip()
        database_url = f"postgresql://warpgate_test:{quote(credential, safe='')}@{endpoint}/warpgate?sslmode=disable"
        for _ in range(100):
            ready = subprocess.run(["docker", "exec", container, "pg_isready", "--host=127.0.0.1",
                                    "--username=warpgate_test", "--dbname=warpgate"], capture_output=True, timeout=10)
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            self.fail("Disposable PostgreSQL did not become ready")

        def query(sql):
            return subprocess.check_output([
                "docker", "exec", container, "psql", "--username=warpgate_test", "--dbname=warpgate",
                "--tuples-only", "--no-align", "--command=" + sql,
            ], text=True, timeout=10).strip()

        def admin_id():
            return query("SELECT id FROM users WHERE username = 'admin'")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed, data = root / "seed", root / "data"
            seed.mkdir()
            data.mkdir()
            server = ThreadingHTTPServer(("127.0.0.1", 0), Discovery)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(thread.join, 5)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                ssh_port = listener.getsockname()[1]
            docs = manifests({"ha": {"enabled": True}, "ingress": {"enabled": True}, "recordings": {"s3": {
                "enabled": True, "bucket": "recordings", "endpoint": "http://127.0.0.1:19000",
                "prefix": "sessions/o'hare"}}, "oidc": {
                **OIDC, "issuerURL": f"http://127.0.0.1:{server.server_port}"}, "protocols": {
                    "ssh": {"enabled": True, "port": ssh_port},
                    "mysql": {"enabled": False}, "postgres": {"enabled": False}}})
            template = resource(docs, "ConfigMap")["data"]["warpgate.yaml"]
            template = template.replace("/data/", str(data) + "/").replace("0.0.0.0:8888", f"127.0.0.1:{port}")
            template = template.replace(f"0.0.0.0:{ssh_port}", f"127.0.0.1:{ssh_port}")
            (seed / "warpgate.yaml").write_text(template)
            certificate = resource(docs, "Secret")["data"]
            for key, name in (("tls.crt", "tls.certificate.pem"), ("tls.key", "tls.key.pem")):
                (seed / name).write_bytes(base64.b64decode(certificate[key]))
            env = {**os.environ, "WARPGATE_ADMIN_PASSWORD": "test-only-long-random-value",
                   "WARPGATE_DATABASE_URL": database_url,
                   "WARPGATE_ENCRYPTION_KEY": base64.b64encode(bytes(range(32))).decode(),
                   "POD_IP": "127.0.0.1",
                   # Peer URLs use this SNI name with explicit Pod-IP resolution.
                   # Keep these local test connections out of developer HTTP proxies.
                   "NO_PROXY": "localhost,127.0.0.1,warpgate-cluster.internal",
                   "no_proxy": "localhost,127.0.0.1,warpgate-cluster.internal",
                   "AWS_ACCESS_KEY_ID": "test-only-access-id", "AWS_SECRET_ACCESS_KEY": "test-only-secret",
                   "WARPGATE_OIDC_CLIENT_SECRET": "quotes'\" slash\\ colon: hash# dollar$ ampersand&"}

            def run(args, **kwargs):
                result = subprocess.run([BINARY, *args], env=env, capture_output=True, text=True, timeout=60, **kwargs)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                return result

            pod = resource(docs, "StatefulSet")["spec"]["template"]["spec"]
            install_args = pod["initContainers"][0]["args"]
            run(install_args[:-2] + [str(seed), str(data)])
            actual = yaml.safe_load((data / "warpgate.yaml").read_text())
            self.assertEqual(actual["database_url"], database_url)
            self.assertEqual(actual["sso_providers"][0]["provider"]["client_secret"], env["WARPGATE_OIDC_CLIENT_SECRET"])
            run(["--config", str(data / "warpgate.yaml"), "check"])
            setup_args = pod["initContainers"][1]["args"]
            setup_args = [arg.replace("/data", str(data)) for arg in setup_args]
            run(setup_args)
            before = admin_id()
            self.assertTrue(before)
            recording_enabled = subprocess.check_output([
                "docker", "exec", container, "psql", "--username=warpgate_test", "--dbname=warpgate",
                "--tuples-only", "--no-align", "--command=SELECT recordings_enable FROM parameters",
            ], text=True, timeout=10).strip()
            self.assertEqual(recording_enabled, "t")
            recording_setup = pod["initContainers"][2]
            storage_json = recording_setup["env"][1]["value"]
            sql = resource(docs, "ConfigMap")["data"]["configure-recordings.sql"]

            def configure_recordings():
                # Execute the rendered psql command as the same unprivileged UID.
                local_database_url = database_url.replace(endpoint, "127.0.0.1:5432")
                result = subprocess.run([
                    "docker", "exec", "--interactive", "--user", "1000:1000",
                    "--env", f"WARPGATE_RECORDINGS_STORAGE={storage_json}", container,
                    *recording_setup["command"],
                    *[arg.replace("/seed/configure-recordings.sql", "-")
                      .replace("$(WARPGATE_DATABASE_URL)", local_database_url)
                      for arg in recording_setup["args"]],
                ], input=sql, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            self.assertIn("UPDATE 1", configure_recordings())
            stored = subprocess.check_output([
                "docker", "exec", container, "psql", "--username=warpgate_test", "--dbname=warpgate",
                "--tuples-only", "--no-align", "--command=SELECT recordings_storage FROM parameters",
            ], text=True, timeout=10)
            self.assertEqual(json.loads(stored), json.loads(storage_json))
            retained_recording = data / "recordings" / "retained-session.ndjson"
            retained_recording.parent.mkdir()
            retained_recording.write_text('{"time":0,"data":"existing recording"}\n')
            retained_paths = [data / name for name in ("warpgate.yaml", "tls.certificate.pem", "tls.key.pem")]
            retained_paths.append(retained_recording)
            retained_contents = {path: path.read_bytes() for path in retained_paths}
            # A restart re-copies chart configuration, preserving the database and administrator.
            run(install_args[:-2] + [str(seed), str(data)])
            run(setup_args)
            self.assertIn("UPDATE 0", configure_recordings())
            for path, content in retained_contents.items():
                with self.subTest(retained_file=path.name):
                    self.assertEqual(path.read_bytes(), content)
            after = admin_id()
            self.assertEqual(before, after)
            with (root / "warpgate.log").open("w+") as log:
                process = subprocess.Popen([BINARY, "--config", str(data / "warpgate.yaml"), "run"],
                                           env=env, stdout=log, stderr=log)
                try:
                    context = ssl.create_default_context(cafile=str(data / "tls.certificate.pem"))
                    for _ in range(100):
                        if process.poll() is not None:
                            break
                        try:
                            with socket.create_connection(("127.0.0.1", port), timeout=1) as raw:
                                with context.wrap_socket(raw, server_hostname="warpgate.access.svc"):
                                    break
                        except OSError:
                            time.sleep(0.1)
                    else:
                        self.fail("Warpgate did not become ready")
                    if process.poll() is not None:
                        log.seek(0)
                        self.fail(log.read())
                    run(["--config", str(data / "warpgate.yaml"), "healthcheck"])
                    # The socket above validates the backend cert/SNI. Here connect by IP to exercise the API.
                    connection = http.client.HTTPSConnection("127.0.0.1", port, context=ssl._create_unverified_context(), timeout=10)
                    try:
                        connection.request("GET", "/@warpgate/api/sso/providers/oidc/start",
                                           headers={"Host": "warpgate.example.com", "X-Forwarded-Proto": "https"})
                        response = connection.getresponse()
                        payload = response.read()
                        self.assertEqual(response.status, 200, payload)
                        auth_url = json.loads(payload)
                        if isinstance(auth_url, dict):
                            auth_url = auth_url["url"]
                        params = parse_qs(urlsplit(auth_url).query)
                        self.assertEqual(params["client_id"], ["warpgate"])
                        self.assertEqual(params["redirect_uri"], ["https://warpgate.example.com/@warpgate/api/sso/return"])
                        self.assertEqual(set(params["scope"][0].split()), {"openid", "email", "profile"})
                        self.assertEqual(params["code_challenge_method"], ["S256"])
                    finally:
                        connection.close()
                    # A second independent data volume joins the same PostgreSQL cluster.
                    peer_seed, peer_data = root / "peer-seed", root / "peer-data"
                    peer_seed.mkdir()
                    peer_data.mkdir()
                    with socket.socket() as listener:
                        listener.bind(("127.0.0.1", 0))
                        peer_port = listener.getsockname()[1]
                    with socket.socket() as listener:
                        listener.bind(("127.0.0.1", 0))
                        peer_ssh_port = listener.getsockname()[1]
                    (peer_seed / "warpgate.yaml").write_text(
                        template.replace(str(data), str(peer_data))
                                .replace(f"127.0.0.1:{port}", f"127.0.0.1:{peer_port}")
                                .replace(f"127.0.0.1:{ssh_port}", f"127.0.0.1:{peer_ssh_port}"))
                    for name in ("tls.certificate.pem", "tls.key.pem"):
                        (peer_seed / name).write_bytes((seed / name).read_bytes())
                    run(install_args[:-2] + [str(peer_seed), str(peer_data)])
                    keys_query = "SELECT md5(ssh_host_key_ed25519::text || ssh_host_key_rsa::text) FROM parameters"
                    host_keys = query(keys_query)
                    run([arg.replace(str(data), str(peer_data)) for arg in setup_args])
                    self.assertEqual(query(keys_query), host_keys)
                    self.assertEqual(admin_id(), before)
                    with (root / "peer.log").open("w+") as peer_log:
                        peer = subprocess.Popen([BINARY, "--config", str(peer_data / "warpgate.yaml"), "run"],
                                                env=env, stdout=peer_log, stderr=peer_log)
                        try:
                            for _ in range(100):
                                if peer.poll() is not None:
                                    peer_log.seek(0)
                                    self.fail(peer_log.read())
                                if query("SELECT count(*) FROM nodes") == "2":
                                    health = subprocess.run([BINARY, "--config", str(peer_data / "warpgate.yaml"),
                                                             "healthcheck"], env=env, capture_output=True, timeout=10)
                                    if health.returncode == 0:
                                        break
                                time.sleep(0.1)
                            else:
                                self.fail("Second Warpgate instance did not join / become ready")
                            addresses = query("SELECT address FROM nodes ORDER BY address").splitlines()
                            self.assertEqual(set(addresses), {f"127.0.0.1:{port}", f"127.0.0.1:{peer_port}"})
                            self.assertEqual(query("SELECT count(DISTINCT encryption_key_fingerprint) FROM nodes"), "1")

                            def scan_host_keys(gateway_port):
                                result = subprocess.run(["ssh-keyscan", "-T", "3", "-p", str(gateway_port),
                                                         "127.0.0.1"], capture_output=True, text=True, timeout=15)
                                self.assertEqual(result.returncode, 0, result.stderr)
                                keys = {tuple(line.split()[1:]) for line in result.stdout.splitlines()
                                        if line and not line.startswith("#")}
                                self.assertTrue(keys)
                                return keys

                            public_host_keys = scan_host_keys(ssh_port)
                            self.assertEqual(scan_host_keys(peer_ssh_port), public_host_keys)
                            cookies = SimpleCookie()

                            def api_request(api_port, route, body=None):
                                conn = http.client.HTTPSConnection("127.0.0.1", api_port,
                                    context=ssl._create_unverified_context(), timeout=15)
                                try:
                                    headers = {"Host": "warpgate.example.com", "X-Forwarded-Proto": "https",
                                               "Cookie": "; ".join(f"{k}={v.value}" for k, v in cookies.items())}
                                    if body is not None:
                                        headers["Content-Type"] = "application/json"
                                    conn.request("POST" if body is not None else "GET", "/@warpgate/api/" + route,
                                                 body=json.dumps(body) if body is not None else None, headers=headers)
                                    response = conn.getresponse()
                                    payload = response.read()
                                    for key, value in response.getheaders():
                                        if key.lower() == "set-cookie":
                                            cookies.load(value)
                                    return response.status, payload
                                finally:
                                    conn.close()

                            # The first failed login owns a pending auth flow on node A.
                            status, payload = api_request(port, "auth/login", {"username": "admin", "password": "wrong"})
                            self.assertEqual(status, 401, payload)
                            self.assertTrue(cookies)
                            # Node B must proxy the same flow to A using direct peer TLS.
                            status, payload = api_request(peer_port, "auth/login",
                                {"username": "admin", "password": env["WARPGATE_ADMIN_PASSWORD"]})
                            if status != 201:
                                log.seek(0)
                                peer_log.seek(0)
                                self.fail(f"Peer login returned {status}: {payload!r}\n{log.read()}\n{peer_log.read()}")
                            status, payload = api_request(peer_port, "info")
                            self.assertEqual(status, 200, payload)
                            self.assertEqual(json.loads(payload)["username"], "admin")
                            # A disappears; the authenticated browser session and B survive.
                            process.terminate()
                            process.wait(timeout=10)
                            run(["--config", str(peer_data / "warpgate.yaml"), "healthcheck"])
                            self.assertEqual(scan_host_keys(peer_ssh_port), public_host_keys)
                            status, payload = api_request(peer_port, "info")
                            self.assertEqual(status, 200, payload)
                            self.assertEqual(json.loads(payload)["username"], "admin")
                            self.assertEqual(query(keys_query), host_keys)
                        finally:
                            if peer.poll() is None:
                                peer.terminate()
                            peer.wait(timeout=10)
                finally:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
