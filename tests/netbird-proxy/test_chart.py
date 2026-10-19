"""Render checks: HELM=helm python3 tests/netbird-proxy/test_chart.py (requires PyYAML)."""

import base64
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/netbird-proxy/1.0.0"
HELM = os.environ.get("HELM", "helm")


class ChartTest(unittest.TestCase):
    def render(self, changes=None, error=None):
        values = {
            "proxy": {"domain": "proxy.example.com"},
            "auth": {"token": "test-only-proxy-token"},
        }
        for section, updates in (changes or {}).items():
            if isinstance(updates, dict):
                values.setdefault(section, {}).update(updates)
            else:
                values[section] = updates
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.yaml"
            path.write_text(yaml.safe_dump(values))
            result = subprocess.run(
                [HELM, "template", "test-proxy", str(CHART), "--namespace", "netbird", "-f", str(path)],
                capture_output=True,
                text=True,
            )
        if error:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(error, result.stderr)
            return
        self.assertEqual(result.returncode, 0, result.stderr)
        return {doc["kind"]: doc for doc in yaml.safe_load_all(result.stdout) if doc}

    def pod(self, resources):
        return resources["Deployment"]["spec"]["template"]["spec"]

    def env(self, resources):
        return {env["name"]: env for env in self.pod(resources)["containers"][0]["env"]}

    def test_default_proxy_manages_certificates_behind_passthrough(self):
        resources = self.render()
        self.assertEqual(set(resources), {"Deployment", "Service", "Secret", "PersistentVolumeClaim", "IngressRouteTCP"})
        pod = self.pod(resources)
        env = self.env(resources)
        container = pod["containers"][0]
        self.assertNotIn("args", container)
        self.assertNotIn("command", container)
        self.assertFalse(pod["enableServiceLinks"])
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(pod["securityContext"]["runAsUser"], 1000)
        self.assertEqual(pod["securityContext"]["fsGroup"], 1000)
        self.assertEqual(env["NB_PROXY_MANAGEMENT_ADDRESS"]["value"], "https://api.netbird.io:443")
        self.assertEqual(env["NB_PROXY_ADDRESS"]["value"], ":8443")
        self.assertEqual(env["NB_PROXY_HEALTH_ADDRESS"]["value"], ":8080")
        self.assertEqual(env["NB_PROXY_ACME_CERTIFICATES"]["value"], "true")
        self.assertEqual(env["NB_PROXY_ACME_CHALLENGE_TYPE"]["value"], "tls-alpn-01")
        self.assertTrue(all(isinstance(e["value"], str) for e in env.values() if "value" in e))
        self.assertEqual(env["NB_PROXY_TOKEN"]["valueFrom"]["secretKeyRef"], {"name": "test-proxy-auth", "key": "token"})
        self.assertEqual(base64.b64decode(resources["Secret"]["data"]["token"]).decode(), "test-only-proxy-token")
        self.assertEqual(resources["Service"]["spec"]["ports"], [{"name": "https", "port": 443, "targetPort": "https"}])
        self.assertNotIn("secret", pod["volumes"][0])
        self.assertFalse(container["volumeMounts"][0]["readOnly"])
        self.assertEqual(container["volumeMounts"][0]["mountPath"], "/certs")
        claim = resources["PersistentVolumeClaim"]
        self.assertEqual(pod["volumes"][0]["persistentVolumeClaim"]["claimName"], claim["metadata"]["name"])
        self.assertEqual(claim["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        self.assertEqual(resources["IngressRouteTCP"]["spec"]["tls"], {"passthrough": True})
        for name, path in (("startup", "startup"), ("readiness", "ready"), ("liveness", "live")):
            self.assertEqual(container[f"{name}Probe"]["httpGet"], {"path": f"/healthz/{path}", "port": "health"})

    def test_optional_external_certificate_remains_read_only(self):
        resources = self.render({"tls": {"mode": "existingSecret", "existingSecret": "proxy-tls"}})
        self.assertNotIn("PersistentVolumeClaim", resources)
        self.assertEqual(self.env(resources)["NB_PROXY_ACME_CERTIFICATES"]["value"], "false")
        pod = self.pod(resources)
        self.assertEqual(pod["volumes"][0]["secret"]["secretName"], "proxy-tls")
        self.assertEqual(pod["volumes"][0]["secret"]["defaultMode"], 0o440)
        mount = pod["containers"][0]["volumeMounts"][0]
        self.assertTrue(mount["readOnly"])
        self.assertNotIn("subPath", mount)
        self.assertEqual(resources["IngressRouteTCP"]["spec"]["tls"], {"passthrough": True})

    def test_form_values_reach_environment_and_certificate_mount(self):
        resources = self.render({
            "proxy": {
                "managementAddress": "http://management.internal:33073",
                "domain": "edge.example.org",
                "logLevel": "debug",
                "private": False,
                "forwardedProto": "auto",
                "proxyProtocol": True,
                "trustedProxies": "10.42.1.2/32",
            },
            "tls": {"certificateDirectory": "/etc/netbird/certs"},
            "extraEnv": [{"name": "NB_PROXY_MAX_DIAL_TIMEOUT", "value": "30s"}],
        })
        env = self.env(resources)
        expected = {
            "NB_PROXY_MANAGEMENT_ADDRESS": "http://management.internal:33073",
            "NB_PROXY_DOMAIN": "edge.example.org",
            "NB_PROXY_LOG_LEVEL": "debug",
            "NB_PROXY_PRIVATE": "false",
            "NB_PROXY_FORWARDED_PROTO": "auto",
            "NB_PROXY_PROXY_PROTOCOL": "true",
            "NB_PROXY_TRUSTED_PROXIES": "10.42.1.2/32",
            "NB_PROXY_CERTIFICATE_DIRECTORY": "/etc/netbird/certs",
            "NB_PROXY_MAX_DIAL_TIMEOUT": "30s",
        }
        for name, value in expected.items():
            self.assertEqual(env[name]["value"], value, name)
        self.assertEqual(self.pod(resources)["containers"][0]["volumeMounts"][0]["mountPath"], "/etc/netbird/certs")

    def test_existing_token_secret_and_extra_secret_reference(self):
        ref = {"secretKeyRef": {"name": "proxy-extra", "key": "key"}}
        resources = self.render({
            "auth": {"useExistingSecret": True, "existingSecret": "proxy-auth", "secretKey": "proxy-token", "token": ""},
            "extraEnv": [{"name": "NB_PROXY_PRESHARED_KEY", "valueFrom": ref}],
        })
        self.assertNotIn("Secret", resources)
        self.assertNotIn("annotations", resources["Deployment"]["spec"]["template"]["metadata"])
        env = self.env(resources)
        self.assertEqual(env["NB_PROXY_TOKEN"]["valueFrom"]["secretKeyRef"], {"name": "proxy-auth", "key": "proxy-token"})
        self.assertEqual(env["NB_PROXY_PRESHARED_KEY"]["valueFrom"], ref)

    def test_managed_token_rotation_changes_pod_checksum(self):
        original = self.render()["Deployment"]["spec"]["template"]["metadata"]["annotations"]
        rotated = self.render({"auth": {"token": "rotated-test-token"}})["Deployment"]["spec"]["template"]["metadata"]["annotations"]
        self.assertNotEqual(original["checksum/auth"], rotated["checksum/auth"])

    def test_custom_token_key_is_a_string_even_for_yaml_keywords(self):
        resources = self.render({"auth": {"secretKey": "true"}})
        self.assertIn("true", resources["Secret"]["data"])
        self.assertEqual(self.env(resources)["NB_PROXY_TOKEN"]["valueFrom"]["secretKeyRef"]["key"], "true")

    def test_acme_alpn_creates_writable_retained_claim(self):
        resources = self.render({"traefik": {"enabled": False}, "service": {"type": "LoadBalancer"}})
        self.assertNotIn("IngressRouteTCP", resources)
        env = self.env(resources)
        claim = resources["PersistentVolumeClaim"]
        self.assertEqual(env["NB_PROXY_ACME_CERTIFICATES"]["value"], "true")
        self.assertEqual(env["NB_PROXY_ACME_CHALLENGE_TYPE"]["value"], "tls-alpn-01")
        self.assertEqual(env["NB_PROXY_CERT_LOCK_METHOD"]["value"], "flock")
        self.assertEqual(claim["metadata"]["annotations"]["helm.sh/resource-policy"], "keep")
        self.assertEqual(self.pod(resources)["volumes"][0]["persistentVolumeClaim"]["claimName"], claim["metadata"]["name"])
        self.assertFalse(self.pod(resources)["containers"][0]["volumeMounts"][0]["readOnly"])
        self.assertEqual(len(resources["Service"]["spec"]["ports"]), 1)

    def test_http_challenge_node_ports_and_existing_claim(self):
        resources = self.render({
            "tls": {"mode": "acme", "acme": {"challengeType": "http-01", "directory": "https://acme-staging-v02.api.letsencrypt.org/directory"}},
            "service": {"type": "NodePort", "httpsNodePort": 30443, "httpNodePort": 30080},
            "persistence": {"existingClaim": "retained-certs"},
            "traefik": {"enabled": False},
        })
        self.assertNotIn("PersistentVolumeClaim", resources)
        self.assertEqual(self.pod(resources)["volumes"][0]["persistentVolumeClaim"]["claimName"], "retained-certs")
        self.assertEqual(resources["Service"]["spec"]["ports"], [
            {"name": "https", "port": 443, "targetPort": "https", "nodePort": 30443},
            {"name": "acme-http", "port": 80, "targetPort": "acme-http", "nodePort": 30080},
        ])
        env = self.env(resources)
        self.assertEqual(env["NB_PROXY_ACME_ADDRESS"]["value"], ":8081")
        self.assertEqual(env["NB_PROXY_ACME_DIRECTORY"]["value"], "https://acme-staging-v02.api.letsencrypt.org/directory")
        self.assertIn({"name": "acme-http", "containerPort": 8081}, self.pod(resources)["containers"][0]["ports"])

    def test_traefik_keeps_rancher_hostname_outside_tcp_route(self):
        for proxy_protocol in (False, True):
            with self.subTest(proxy_protocol=proxy_protocol):
                resources = self.render({"traefik": {"enabled": True}, "proxy": {"proxyProtocol": proxy_protocol, "trustedProxies": "10.42.1.2/32"}})
                route = resources["IngressRouteTCP"]["spec"]
                self.assertEqual(route["tls"], {"passthrough": True})
                self.assertEqual(route["entryPoints"], ["websecure"])
                backend = route["routes"][0]["services"][0]
                self.assertEqual(backend["name"], resources["Service"]["metadata"]["name"])
                self.assertEqual("proxyProtocol" in backend, proxy_protocol)
                if proxy_protocol:
                    self.assertEqual(backend["proxyProtocol"], {"version": 2})
                match = route["routes"][0]["match"]
                self.assertIn("HostSNI(`proxy.example.com`)", match)
                expression = re.search(r"HostSNIRegexp\(`(.*?)`\)", match).group(1)
                self.assertRegex("app.proxy.example.com", expression)
                for host in ("rancher.example.com", "evilproxy.example.com", "app.proxyXexample.com", "proxy.example.com.evil"):
                    self.assertIsNone(re.fullmatch(expression, host), host)

    def test_invalid_combinations_fail_before_installation(self):
        cases = [
            ({"auth": {"token": ""}}, "token"),
            ({"auth": {"useExistingSecret": True, "existingSecret": ""}}, "existingSecret"),
            ({"tls": {"mode": "existingSecret", "existingSecret": ""}}, "existingSecret"),
            ({"proxy": {"domain": "https://proxy.example.com"}}, "domain"),
            ({"proxy": {"proxyProtocol": True}}, "trustedProxies"),
            ({"tls": {"certificateDirectory": "/tmp"}}, "certificateDirectory"),
            ({"tls": {"certificateDirectory": "certs"}}, "certificateDirectory"),
            ({"tls": {"acme": {"challengeType": "http-01"}}}, "requires tls-alpn-01"),
            ({"traefik": {"enabled": True}, "service": {"type": "LoadBalancer"}}, "Use service.type=ClusterIP"),
            ({"extraEnv": [{"name": "NB_PROXY_DOMAIN", "value": "wrong.example.com"}]}, "chart-managed variable"),
            ({"extraEnv": [{"name": "X", "value": "a"}, {"name": "X", "value": "b"}]}, "duplicate"),
            ({"traefik": {"enabled": False}, "tls": {"acme": {"challengeType": "http-01"}}, "service": {"httpPort": 443}}, "must differ"),
            ({"traefik": {"enabled": False}, "tls": {"acme": {"challengeType": "http-01"}}, "service": {"type": "NodePort", "httpNodePort": 30443, "httpsNodePort": 30443}}, "NodePorts must differ"),
        ]
        for changes, error in cases:
            with self.subTest(changes=changes):
                self.render(changes, error=error)

    def test_rancher_form_paths_and_defaults_match_values(self):
        defaults = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        seen = set()
        for question in questions:
            path = question["variable"]
            self.assertNotIn(path, seen)
            seen.add(path)
            value = defaults
            for component in path.split("."):
                value = value[component]
            form_default = question["default"]
            if isinstance(value, bool):
                form_default = {"true": True, "false": False}[form_default]
            self.assertEqual(form_default, value, path)
        for path in ("proxy.managementAddress", "proxy.domain", "auth.token", "auth.existingSecret", "tls.mode", "tls.existingSecret", "tls.certificateDirectory", "traefik.enabled"):
            self.assertIn(path, seen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
