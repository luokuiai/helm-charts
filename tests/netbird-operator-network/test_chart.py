"""Run with: uv run --with pyyaml python tests/netbird-operator-network/test_chart.py."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/netbird-operator-network/1.0.1"


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
        all_questions = questions + [child for question in questions
                                     for child in question.get("subquestions", [])]
        self.assertNotIn("natWorkaround.image.tag", [question["variable"] for question in all_questions])
        for question in all_questions:
            with self.subTest(variable=question["variable"]):
                value = values
                for part in question["variable"].split("."):
                    value = value[part]
                self.assertEqual(value, question["default"])

    def test_maintenance_and_cleanup_share_complete_image_references(self):
        digest = "sha256:" + "a" * 64
        cases = [
            ({}, "ghcr.io/nicolaka/netshoot:v0.14"),
            ({"repository": "mirror.example.com:5000/netshoot:v0.14"},
             "mirror.example.com:5000/netshoot:v0.14"),
            ({"repository": "mirror.example.com:5000/netshoot"},
             "mirror.example.com:5000/netshoot:v0.14"),
            ({"repository": "mirror.example.com/netshoot", "tag": "v0.13"},
             "mirror.example.com/netshoot:v0.13"),
            ({"repository": "mirror.example.com/netshoot:v0.14", "tag": "v0.13"},
             "mirror.example.com/netshoot:v0.14"),
            ({"repository": f"mirror.example.com/netshoot@{digest}", "tag": "v0.13"},
             f"mirror.example.com/netshoot@{digest}"),
        ]
        for image, expected in cases:
            with self.subTest(image=image):
                docs = manifests({"natWorkaround": {"enabled": True, "image": image}})
                for kind in ("DaemonSet", "Job"):
                    self.assertEqual(docs[kind]["spec"]["template"]["spec"]["containers"][0]["image"], expected)

    def test_enabled_workaround_has_scoped_permissions_and_no_public_listener(self):
        docs = manifests({"natWorkaround": {"enabled": True}})
        self.assertEqual(set(docs), {"NetworkRouter", "NetworkResource", "DaemonSet", "ConfigMap",
                                     "ServiceAccount", "Role", "RoleBinding", "Job"})
        self.assertEqual(docs["NetworkRouter"]["spec"]["workloadOverride"], {"replicas": 1})
        pod = docs["DaemonSet"]["spec"]["template"]["spec"]
        self.assertTrue(pod["hostNetwork"])
        self.assertEqual(pod["containers"][0]["securityContext"]["capabilities"],
                         {"drop": ["ALL"], "add": ["NET_ADMIN"]})
        self.assertNotIn("ports", pod["containers"][0])
        self.assertTrue(all("hostPath" not in volume for volume in pod["volumes"]))
        self.assertTrue(all(rule["verbs"] == ["get", "patch"] if "patch" in rule["verbs"]
                            else set(rule["verbs"]) <= {"get", "list"}
                            for rule in docs["Role"]["rules"]))
        writes = [rule for rule in docs["Role"]["rules"] if "patch" in rule["verbs"]]
        self.assertEqual(writes[0]["resources"], ["configmaps"])
        self.assertEqual(writes[0]["resourceNames"], [docs["ConfigMap"]["metadata"]["name"]])
        job = docs["Job"]
        self.assertEqual(job["metadata"]["annotations"]["helm.sh/hook"], "pre-delete")
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertNotIn("hostNetwork", job["spec"]["template"]["spec"])
        self.assertNotIn("hook-failed", job["metadata"]["annotations"]["helm.sh/hook-delete-policy"])

    def test_workaround_rejects_invalid_values(self):
        for value in [{"enabled": "yes"}, {"image": {"repository": "bad repo"}},
                      {"excludedCIDRs": []}, {"excludedCIDRs": ["0.0.0.0/33"]},
                      {"excludedCIDRs": ["999.0.0.0/8"]}]:
            with self.subTest(value=value):
                self.assertNotEqual(render({"natWorkaround": value}).returncode, 0)

    def test_existing_installation_hooks_handle_disabling_without_a_future_delete_hook(self):
        import shutil
        import tempfile

        # Replace only the API lookup dependency; exercise the real Helm conditionals.
        with tempfile.TemporaryDirectory() as temp:
            chart = Path(temp) / "chart"
            shutil.copytree(CHART, chart)
            path = chart / "templates/nat-cleanup.yaml"
            path.write_text(path.read_text().replace(
                'lookup "v1" "ConfigMap" .Release.Namespace $name | default dict',
                'dict "data" (dict "mode" "active")'))
            for enabled, hooks in [(True, "pre-upgrade,pre-delete"), (False, "pre-upgrade")]:
                result = subprocess.run(["helm", "template", "netbird-operator-network", str(chart),
                                         "--is-upgrade", "--set", "natWorkaround.enabled=" + str(enabled).lower()],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                job = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc["kind"] == "Job")
                self.assertEqual(job["metadata"]["annotations"]["helm.sh/hook"], hooks)


if __name__ == "__main__":
    unittest.main(verbosity=2)
