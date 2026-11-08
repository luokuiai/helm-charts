"""Run with: uv run --with pyyaml python tests/silo/test_chart_102.py."""

import unittest

import test_chart as old

old.CHART = old.ROOT / "charts/silo/1.0.2"


class SeparateIngressTests(unittest.TestCase):
    def test_form_keeps_both_routes_in_same_section_without_switch(self):
        questions = old.yaml.safe_load((old.CHART / "questions.yaml").read_text())["questions"]
        fields = {q["variable"]: q for q in questions}
        self.assertNotIn("ingress.splitConsole", fields)
        for field in ("ingress.className", "ingress.certificate.mode",
                      "ingress.console.className", "ingress.console.certificate.mode"):
            self.assertEqual(fields[field]["group"], "域名 / HTTPS")
            self.assertNotIn("splitConsole", fields[field].get("show_if", ""))
        self.assertEqual(fields["ingress.className"]["label"], "S3 API Ingress 类")
        self.assertEqual(fields["ingress.console.className"]["label"], "控制台 Ingress 类")

    def test_public_api_and_vpn_console_are_always_independent(self):
        values = old.ingress("cert-manager", issuerName="public", secretName="api-tls")
        values["ingress"]["splitConsole"] = False  # Old release values cannot re-enable sharing.
        values["ingress"]["console"] = {"className": "traefik-vpn", "annotations": {"scope": "vpn"},
            "certificate": {"mode": "existing", "secretName": "console-tls"}}
        docs = old.manifests(values)
        api = old.resource(docs, "Ingress", "silo")
        console = old.resource(docs, "Ingress", "silo-console")
        self.assertEqual(api["spec"]["ingressClassName"], "traefik")
        self.assertEqual(api["spec"]["tls"], [{"secretName": "api-tls", "hosts": ["s3.example.org"]}])
        self.assertEqual(console["spec"]["ingressClassName"], "traefik-vpn")
        self.assertEqual(console["spec"]["tls"], [{"secretName": "console-tls", "hosts": ["console.example.org"]}])
        self.assertEqual(console["metadata"]["annotations"], {"scope": "vpn"})
        self.assertEqual(old.environment(docs)["MINIO_BROWSER_REDIRECT_URL"]["value"], "https://console.example.org")
        values["ingress"]["console"]["className"] = ""
        self.assertNotEqual(old.render(values).returncode, 0)

    def test_api_and_console_can_be_enabled_separately(self):
        for api, console in ((True, False), (False, True), (False, False)):
            with self.subTest(api=api, console=console):
                values = {"ingress": {"enabled": True, "apiEnabled": api,
                          "consoleEnabled": console, "console": {"className": "traefik-vpn"}}}
                docs = old.manifests(values)
                names = {d["metadata"]["name"] for d in docs if d["kind"] == "Ingress"}
                self.assertEqual(names, ({"silo"} if api else set()) | ({"silo-console"} if console else set()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
