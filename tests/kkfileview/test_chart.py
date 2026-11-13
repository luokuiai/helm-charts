"""Run with: uv run --with pyyaml python tests/kkfileview/test_chart.py."""

from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "charts/kkfileview/1.0.0"


def render(values=None, release="preview"):
    return subprocess.run(
        ["helm", "template", release, str(CHART), "--namespace", "files", "--values", "-"],
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
        raise AssertionError(f"Expected one {kind}, found {len(found)}")
    return found[0]


class KKFileViewChartTests(unittest.TestCase):
    def test_default_image_service_and_no_external_ingress(self):
        docs = manifests()
        deployment = resource(docs, "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(container["image"], "harbor.luokuiai.com/kkfileview:5.0.2")
        self.assertEqual(container["envFrom"], [{"secretRef": {"name": "kkfileview-env"}}])
        self.assertEqual(container["ports"][0]["containerPort"], 8012)
        self.assertNotIn("affinity", pod)
        self.assertFalse(pod["automountServiceAccountToken"])
        service = resource(docs, "Service")["spec"]
        self.assertEqual(service["type"], "ClusterIP")
        self.assertEqual(service["ports"][0]["port"], 8012)
        self.assertEqual(service["ports"][0]["targetPort"], "http")
        self.assertEqual(service["selector"], deployment["spec"]["selector"]["matchLabels"])
        self.assertFalse(any(d["kind"] in ("Ingress", "PersistentVolumeClaim") for d in docs))

    def test_existing_secrets(self):
        docs = manifests({"image": {"pullSecret": "harbor-auth"},
                          "envSecret": "preview-env"})
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        self.assertEqual(pod["imagePullSecrets"], [{"name": "harbor-auth"}])
        self.assertEqual(pod["containers"][0]["envFrom"], [{"secretRef": {"name": "preview-env"}}])
        pod = resource(manifests({"envSecret": ""}), "Deployment")["spec"]["template"]["spec"]
        self.assertNotIn("envFrom", pod["containers"][0])

    def test_ingress_certificate_modes_and_backend(self):
        for mode in ("disabled", "existing", "cert-manager"):
            with self.subTest(mode=mode):
                values = {"ingress": {"enabled": True, "className": "traefik-vpn", "host": "preview.example.com",
                          "certificate": {"mode": mode, "secretName": "preview-tls", "issuerName": "letsencrypt"}}}
                ingress = resource(manifests(values), "Ingress")
                self.assertEqual(ingress["spec"]["ingressClassName"], "traefik-vpn")
                self.assertEqual(ingress["spec"]["rules"][0]["http"]["paths"][0]["backend"]["service"],
                                 {"name": "preview", "port": {"name": "http"}})
                if mode == "disabled":
                    self.assertNotIn("tls", ingress["spec"])
                else:
                    self.assertEqual(ingress["spec"]["tls"], [{"secretName": "preview-tls", "hosts": ["preview.example.com"]}])
                if mode == "cert-manager":
                    self.assertEqual(ingress["metadata"]["annotations"]["cert-manager.io/cluster-issuer"], "letsencrypt")

    def test_invalid_input_rejected(self):
        for values in ({"envSecret": "bad/name"},
                       {"ingress": {"enabled": True, "host": ""}},
                       {"ingress": {"enabled": True, "certificate": {"mode": "existing", "secretName": ""}}},
                       {"ingress": {"enabled": True, "certificate": {"mode": "cert-manager", "issuerName": ""}}}):
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_rancher_form_defaults(self):
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        self.assertFalse(any(q["variable"] == "nodeName" for q in questions))
        by_variable = {}
        for question in questions:
            by_variable.setdefault(question["variable"], []).append(question)
        self.assertEqual(by_variable["ingress.className"][0]["type"], "reference[networking.k8s.io.ingressclass]")
        secrets = by_variable["ingress.certificate.secretName"]
        self.assertTrue(any(q["type"] == "reference[secret]" and q["show_if"].endswith("mode=existing") for q in secrets))
        self.assertTrue(any(q["type"] == "string" and q["show_if"].endswith("mode=cert-manager") for q in secrets))
        for question in questions:
            with self.subTest(variable=question["variable"]):
                current = values
                for part in question["variable"].split("."):
                    current = current[part]
                self.assertEqual(question["default"], current)


if __name__ == "__main__":
    unittest.main(verbosity=2)
