"""Run with: uv run --with pyyaml python tests/cert-manager-alidns-issuer/test_chart.py."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/cert-manager-alidns-issuer/1.0.0"


def render(overrides=None, namespace="cert-manager"):
    values = {"acme": {"email": "admin@example.com"},
              "alidns": {"dnsZone": "example.com"}}
    for section, entries in (overrides or {}).items():
        values.setdefault(section, {}).update(entries)
    return subprocess.run(
        ["helm", "template", "cert-manager-alidns-issuer", str(CHART),
         "--namespace", namespace, "--values", "-"],
        input=yaml.safe_dump(values), capture_output=True, text=True,
    )


def manifest(**kwargs):
    result = render(**kwargs)
    if result.returncode:
        raise AssertionError(result.stderr)
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
    if len(docs) != 1:
        raise AssertionError(f"Expected one ClusterIssuer, got {len(docs)} resources")
    return docs[0]


class AliDNSIssuerTests(unittest.TestCase):
    def test_only_cluster_issuer_with_references_and_zone_selector(self):
        doc = manifest(namespace="custom-cert-namespace")
        self.assertEqual(doc["kind"], "ClusterIssuer")
        self.assertEqual(doc["apiVersion"], "cert-manager.io/v1")
        self.assertNotIn("namespace", doc["metadata"])
        acme = doc["spec"]["acme"]
        self.assertEqual(acme["server"], "https://acme-v02.api.letsencrypt.org/directory")
        solver, = acme["solvers"]
        self.assertEqual(solver["selector"], {"dnsZones": ["example.com"]})
        webhook = solver["dns01"]["webhook"]
        self.assertEqual(webhook["solverName"], "alidns-solver")
        self.assertEqual(webhook["config"]["accessTokenSecretRef"],
                         {"name": "alidns-secrets", "key": "access-token"})
        self.assertEqual(webhook["config"]["secretKeySecretRef"],
                         {"name": "alidns-secrets", "key": "secret-key"})

    def test_staging_uses_separate_account_and_custom_secret_keys(self):
        production = manifest()["spec"]["acme"]
        doc = manifest(overrides={"issuer": {"name": "test-alidns"},
                                  "acme": {"environment": "staging"},
                                  "alidns": {"existingSecret": "dns-credentials",
                                             "accessKeyIdKey": "AccessKeyId",
                                             "accessKeySecretKey": "AccessKeySecret"},
                                  "webhook": {"groupName": "acme.example.com"}})
        acme = doc["spec"]["acme"]
        self.assertEqual(acme["server"], "https://acme-staging-v02.api.letsencrypt.org/directory")
        self.assertEqual(acme["privateKeySecretRef"], {"name": "test-alidns-staging-account-key"})
        same_name_staging = manifest(overrides={"acme": {"environment": "staging"}})["spec"]["acme"]
        self.assertNotEqual(production["privateKeySecretRef"], same_name_staging["privateKeySecretRef"])
        config = acme["solvers"][0]["dns01"]["webhook"]
        self.assertEqual(config["groupName"], "acme.example.com")
        self.assertEqual(config["config"]["accessTokenSecretRef"],
                         {"name": "dns-credentials", "key": "AccessKeyId"})
        self.assertEqual(config["config"]["secretKeySecretRef"],
                         {"name": "dns-credentials", "key": "AccessKeySecret"})

    def test_blank_or_malformed_form_values_are_rejected(self):
        for values in [
            {"acme": {"email": ""}}, {"acme": {"email": "a b@example.com"}},
            {"acme": {"environment": "invalid"}},
            {"alidns": {"dnsZone": ""}}, {"alidns": {"dnsZone": "*.example.com"}},
            {"alidns": {"dnsZone": "https://example.com"}},
            {"alidns": {"existingSecret": ""}},
            {"alidns": {"existingSecret": "cert-manager/credentials"}},
            {"alidns": {"accessKeyIdKey": ""}},
            {"alidns": {"accessKeySecretKey": "has spaces"}},
            {"webhook": {"groupName": ""}},
            {"issuer": {"name": "Invalid Name"}},
        ]:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_form_defaults_match_values_and_credentials_use_secret_picker(self):
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        by_variable = {item["variable"]: item for item in questions}
        self.assertEqual(by_variable["alidns.existingSecret"]["type"], "reference[secret]")
        self.assertEqual(set(by_variable),
                         {f"{section}.{key}" for section, entries in values.items() for key in entries})
        for question in questions:
            section, key = question["variable"].split(".")
            self.assertEqual(question["default"], values[section][key])
            self.assertTrue(question["required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
