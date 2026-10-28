"""Run with: uv run --with pyyaml python tests/netbird-operator-network/test_chart.py."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/netbird-operator-network/1.0.0"


def render(values=None, namespace="infra-system"):
    return subprocess.run(
        ["helm", "template", "netbird-operator-network", str(CHART),
         "--namespace", namespace, "--values", "-"],
        input=yaml.safe_dump(values or {}), capture_output=True, text=True,
    )


def manifests(values=None, **kwargs):
    result = render(values, **kwargs)
    if result.returncode:
        raise AssertionError(result.stderr)
    return {doc["kind"]: doc for doc in yaml.safe_load_all(result.stdout) if doc}


class NetBirdOperatorNetworkTests(unittest.TestCase):
    def test_shared_entrypoint_has_one_router_and_no_application_workloads(self):
        docs = manifests()
        self.assertEqual(set(docs), {"NetworkRouter", "NetworkResource"})
        router, resource = docs["NetworkRouter"], docs["NetworkResource"]
        self.assertEqual(router["apiVersion"], "netbird.io/v1alpha1")
        self.assertEqual(resource["apiVersion"], "netbird.io/v1alpha1")
        self.assertEqual(router["spec"]["workloadOverride"], {"replicas": 1})
        self.assertEqual(router["spec"]["dnsZoneRef"], {"name": "k3s.netbird.internal"})
        self.assertEqual(resource["spec"]["serviceRef"], {"name": "traefik-vpn"})
        self.assertEqual(resource["spec"]["groups"], [{"name": "k3s-web"}])

    def test_namespace_and_custom_router_are_referenced_consistently(self):
        docs = manifests({"router": {"name": "private-web", "replicas": 3,
                                     "dnsZone": "apps.example.internal"},
                          "resource": {"serviceName": "private-ingress",
                                       "groupNames": ["Web Users", "admin: ops"]}},
                         namespace="networking")
        router, resource = docs["NetworkRouter"], docs["NetworkResource"]
        self.assertTrue(all(doc["metadata"]["namespace"] == "networking" for doc in docs.values()))
        self.assertEqual(resource["spec"]["networkRouterRef"],
                         {"name": router["metadata"]["name"], "namespace": "networking"})
        self.assertEqual(resource["metadata"]["name"], "private-ingress")
        self.assertEqual(resource["spec"]["groups"],
                         [{"name": "Web Users"}, {"name": "admin: ops"}])
        self.assertEqual(router["spec"]["workloadOverride"]["replicas"], 3)

    def test_empty_or_invalid_routing_configuration_is_rejected(self):
        cases = [
            {"router": {"name": "Bad Name"}},
            {"router": {"dnsZone": ""}},
            {"router": {"dnsZone": "https://netbird.example.com"}},
            {"router": {"replicas": 0}},
            {"router": {"replicas": 1.5}},
            {"resource": {"serviceName": ""}},
            {"resource": {"serviceName": "infra-system/traefik-vpn"}},
            {"resource": {"groupNames": []}},
            {"resource": {"groupNames": [" "]}},
            {"resource": {"groupNames": ["k3s-web", "k3s-web"]}},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_service_picker_and_form_defaults_match_values(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        by_variable = {question["variable"]: question for question in questions}
        self.assertEqual(by_variable["resource.serviceName"]["type"], "reference[service]")
        self.assertEqual(by_variable["resource.groupNames"]["type"], "array[string]")
        for question in questions:
            with self.subTest(variable=question["variable"]):
                value = values
                for part in question["variable"].split("."):
                    value = value[part]
                self.assertEqual(value, question["default"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
