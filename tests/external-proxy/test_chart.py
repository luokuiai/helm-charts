"""Run with: uv run --with pyyaml python tests/external-proxy/test_chart.py."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/external-proxy/1.0.0"


def render(values=None, release="remote"):
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "infra",
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


class ExternalProxyTests(unittest.TestCase):
    def test_ip_backend_links_ingress_service_and_endpoint_without_public_workloads(self):
        docs = manifests()
        self.assertEqual({doc["kind"] for doc in docs}, {"Ingress", "Service", "EndpointSlice"})
        service = resource(docs, "Service")
        self.assertNotIn("selector", service["spec"])
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertNotIn("externalIPs", service["spec"])
        endpoint = resource(docs, "EndpointSlice")
        self.assertEqual(endpoint["metadata"]["labels"]["kubernetes.io/service-name"],
                         service["metadata"]["name"])
        self.assertEqual(endpoint["addressType"], "IPv4")
        self.assertEqual(endpoint["endpoints"][0]["addresses"], ["192.0.2.10"])
        route = resource(docs, "Ingress")
        self.assertEqual(route["spec"]["ingressClassName"], "traefik-vpn")
        path = route["spec"]["rules"][0]["http"]["paths"][0]
        self.assertEqual(path["backend"]["service"],
                         {"name": service["metadata"]["name"], "port": {"name": "upstream"}})
        self.assertEqual(path["path"], "/")
        self.assertNotIn("tls", route["spec"])

    def test_explicit_http_mode_does_not_request_a_certificate(self):
        docs = manifests({"ingress": {"certificate": {"mode": "disabled"}}})
        route = resource(docs, "Ingress")
        self.assertNotIn("tls", route["spec"])
        self.assertNotIn("annotations", route["metadata"])

    def test_backend_port_and_ipv6_family_are_consistent(self):
        docs = manifests({"backend": {"addressType": "IPv6", "address": "2001:db8::10", "port": 3430}})
        service = resource(docs, "Service")
        self.assertEqual(service["spec"]["ipFamilies"], ["IPv6"])
        endpoint = resource(docs, "EndpointSlice")
        self.assertEqual(endpoint["addressType"], "IPv6")
        self.assertEqual(endpoint["endpoints"][0]["addresses"], ["2001:db8::10"])
        for ports in (service["spec"]["ports"], endpoint["ports"]):
            self.assertEqual(ports[0]["port"], 3430)
            self.assertEqual(ports[0]["name"], "upstream")

    def test_dns_backend_uses_external_name_without_synthetic_ip_endpoints(self):
        docs = manifests({"backend": {"addressType": "DNS", "address": "backend.example.com"}})
        self.assertFalse(any(doc["kind"] == "EndpointSlice" for doc in docs))
        service = resource(docs, "Service")
        self.assertEqual(service["spec"]["type"], "ExternalName")
        self.assertEqual(service["spec"]["externalName"], "backend.example.com")
        self.assertNotIn("ipFamilies", service["spec"])

    def test_original_host_and_https_sni_match_remote_traefik_domain(self):
        docs = manifests({"ingress": {"host": "magpie.example.com"},
                          "backend": {"scheme": "https", "port": 443}})
        annotations = resource(docs, "Service")["metadata"]["annotations"]
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/service.passhostheader"], "true")
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/service.serversscheme"], "https")
        self.assertEqual(annotations["traefik.ingress.kubernetes.io/service.serverstransport"],
                         "infra-remote@kubernetescrd")
        transport = resource(docs, "ServersTransport")
        self.assertEqual(transport["spec"], {"serverName": "magpie.example.com"})
        self.assertEqual(transport["metadata"]["name"], "remote")
        for doc in docs:
            self.assertNotIn("middlewares", yaml.safe_dump(doc).lower())

    def test_backend_host_mode_and_custom_ca_do_not_disable_tls_verification(self):
        docs = manifests({"backend": {"scheme": "https", "hostHeader": "backend",
                                      "addressType": "DNS", "address": "upstream.example.com"}})
        self.assertEqual(resource(docs, "ServersTransport")["spec"]["serverName"],
                         "upstream.example.com")
        self.assertEqual(resource(docs, "Service")["metadata"]["annotations"][
            "traefik.ingress.kubernetes.io/service.passhostheader"], "false")
        docs = manifests({"backend": {"scheme": "https", "tls": {
            "serverName": "certificate.example.com", "caSecret": "private-ca"}}})
        self.assertEqual(resource(docs, "ServersTransport")["spec"], {
            "serverName": "certificate.example.com", "rootCAsSecrets": ["private-ca"]})

    def test_existing_certificate_is_selected_without_requesting_a_new_certificate(self):
        docs = manifests({"ingress": {"certificate": {"mode": "existing", "existingSecret": "shared-tls"}}})
        route = resource(docs, "Ingress")
        self.assertEqual(route["spec"]["tls"], [{"secretName": "shared-tls", "hosts": ["proxy.example.com"]}])
        self.assertNotIn("annotations", route["metadata"])

    def test_ingress_class_and_certificate_mode_are_independent_install_choices(self):
        for ingress_class in ("traefik", "traefik-vpn"):
            for mode in ("disabled", "existing", "cert-manager"):
                with self.subTest(ingress_class=ingress_class, mode=mode):
                    docs = manifests({"ingress": {"className": ingress_class, "certificate": {
                        "mode": mode, "existingSecret": "chosen-tls", "issuerName": "chosen-issuer"}}})
                    route = resource(docs, "Ingress")
                    self.assertEqual(route["spec"]["ingressClassName"], ingress_class)
                    if mode == "disabled":
                        self.assertNotIn("tls", route["spec"])
                    else:
                        expected = "chosen-tls" if mode == "existing" else "remote-tls"
                        self.assertEqual(route["spec"]["tls"][0]["secretName"], expected)
                    self.assertEqual(resource(docs, "Service")["metadata"]["annotations"][
                        "traefik.ingress.kubernetes.io/service.serversscheme"], "http")

    def test_cert_manager_issuer_kind_and_release_specific_secrets(self):
        for kind, annotation in (("ClusterIssuer", "cert-manager.io/cluster-issuer"),
                                 ("Issuer", "cert-manager.io/issuer")):
            with self.subTest(kind=kind):
                values = {"ingress": {"certificate": {"mode": "cert-manager", "issuerKind": kind,
                                                     "issuerName": "letsencrypt"},
                                      "annotations": {"cert-manager.io/issuer": "stale",
                                                      "cert-manager.io/cluster-issuer": "stale",
                                                      "example.com/annotation": "kept"}}}
                for release in ("magpie-remote", "another-proxy"):
                    route = resource(manifests(values, release=release), "Ingress")
                    self.assertEqual(route["metadata"]["annotations"],
                                     {annotation: "letsencrypt", "example.com/annotation": "kept"})
                    self.assertEqual(route["spec"]["tls"][0]["secretName"], f"{release}-tls")
                values["ingress"]["certificate"]["secretName"] = "custom-tls"
                route = resource(manifests(values), "Ingress")
                self.assertEqual(route["spec"]["tls"][0]["secretName"], "custom-tls")

    def test_invalid_addresses_ports_and_certificate_settings_are_rejected(self):
        cases = [
            {"ingress": {"host": "https://example.com"}},
            {"ingress": {"host": ""}},
            {"ingress": {"className": ""}},
            {"ingress": {"certificate": {"mode": "existing"}}},
            {"ingress": {"certificate": {"mode": "cert-manager", "issuerName": ""}}},
            {"backend": {"scheme": "tcp"}},
            {"backend": {"hostHeader": "anything"}},
            {"backend": {"address": "https://backend.example.com"}},
            {"backend": {"address": "192.0.2.999"}},
            {"backend": {"address": "127.0.0.1"}},
            {"backend": {"address": "169.254.1.1"}},
            {"backend": {"address": "224.0.0.1"}},
            {"backend": {"address": "192.0.2.1:3430"}},
            {"backend": {"addressType": "IPv6", "address": "gg::10"}},
            {"backend": {"addressType": "IPv6", "address": "::1"}},
            {"backend": {"addressType": "IPv6", "address": "[2001:db8::10]"}},
            {"backend": {"addressType": "DNS", "address": "192.0.2.10"}},
            {"backend": {"addressType": "DNS", "address": "backend.example.com/path"}},
            {"backend": {"port": 0}},
            {"backend": {"port": 65536}},
            {"backend": {"port": "443"}},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_rancher_form_defaults_visibility_and_dropdowns_match_values(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]

        def at(path):
            value = values
            for part in path.split("."):
                value = value[part]
            return value

        for question in questions:
            with self.subTest(variable=question["variable"]):
                self.assertEqual(at(question["variable"]), question["default"])
                for condition in question.get("show_if", "").split("&&"):
                    if condition:
                        at(condition.split("=", 1)[0])
                if question["type"] == "enum":
                    self.assertIn(question["default"], question["options"])
        types = {q["variable"]: q["type"] for q in questions}
        for variable in ("backend.addressType", "backend.scheme", "backend.hostHeader",
                         "ingress.certificate.mode", "ingress.certificate.issuerKind"):
            self.assertEqual(types[variable], "enum")
        for variable in ("ingress.className", "ingress.certificate.existingSecret",
                         "ingress.certificate.issuerName", "backend.tls.caSecret"):
            self.assertTrue(types[variable].startswith("reference["))


if __name__ == "__main__":
    unittest.main(verbosity=2)
