"""Run with PyYAML installed: python3 tests/iconf-sdzz/test_chart.py."""
from pathlib import Path
import subprocess
import unittest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts/iconf-sdzz/1.0.2"


def render(extra=None):
    values = extra or {}
    result = subprocess.run(["helm", "template", "meeting", str(CHART), "--namespace", "apps", "-f", "-"],
                            input=yaml.safe_dump(values), text=True, capture_output=True, check=True)
    return {doc["kind"]: doc for doc in yaml.safe_load_all(result.stdout) if doc}

def render_all(values):
    result = subprocess.run(["helm", "template", "meeting", str(CHART), "--namespace", "apps", "-f", "-"],
                            input=yaml.safe_dump(values), text=True, capture_output=True, check=True)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


class ChartTests(unittest.TestCase):
    def test_s3_storage_and_config(self):
        docs = render()
        spec = docs["Deployment"]["spec"]
        pod = spec["template"]["spec"]
        app = pod["containers"][0]
        self.assertEqual(app["image"], "harbor.luokuiai.com/iconf-sdzz:1.0.0")
        self.assertEqual(spec["strategy"]["type"], "Recreate")
        self.assertNotIn("envFrom", app)
        self.assertIn({"name": "SPRING_PROFILES_ACTIVE", "value": "prod"}, app["env"])
        self.assertIn({"name": "STORAGE_TYPE", "value": "s3"}, app["env"])
        self.assertEqual(app["readinessProbe"]["httpGet"]["path"], "/health")
        self.assertNotIn("PersistentVolumeClaim", docs)
        self.assertIn({"name": "config", "configMap": {"name": "iconf-sdzz-config"}}, pod["volumes"])
        self.assertEqual(docs["Service"]["spec"]["ports"][0]["port"], 8080)

    def test_existing_config(self):
        docs = render({"configMap": "meeting-config"})
        self.assertNotIn("PersistentVolumeClaim", docs)
        pod = docs["Deployment"]["spec"]["template"]["spec"]
        self.assertIn({"name": "config", "configMap": {"name": "meeting-config"}}, pod["volumes"])
        self.assertIn({"name": "config", "mountPath": "/app/config", "readOnly": True}, pod["containers"][0]["volumeMounts"])

    def test_ingress(self):
        docs = render({"ingress": {"enabled": True, "className": "traefik-vpn",
                                   "host": "meeting.example.com",
                                   "certificate": {"mode": "existing", "secretName": "meeting-tls"}}})
        ingress = docs["Ingress"]["spec"]
        self.assertEqual(ingress["ingressClassName"], "traefik-vpn")
        self.assertEqual(ingress["tls"][0]["secretName"], "meeting-tls")
        self.assertEqual(ingress["rules"][0]["http"]["paths"][0]["backend"]["service"]["port"]["name"], "http")

    def test_bundled_redis(self):
        self.assertNotIn("StatefulSet", render())
        docs = render_all({"redis": {"enabled": True}})
        deployment = next(d for d in docs if d["kind"] == "Deployment")
        env = deployment["spec"]["template"]["spec"]["containers"][0]["env"]
        redis = next(d for d in docs if d["kind"] == "StatefulSet")
        service = next(d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "meeting-redis")
        self.assertIn({"name": "SPRING_DATA_REDIS_HOST", "value": service["metadata"]["name"]}, env)
        self.assertIn({"name": "SPRING_DATA_REDIS_PORT", "value": "6379"}, env)
        self.assertEqual(redis["spec"]["replicas"], 1)
        self.assertNotIn("volumeClaimTemplates", redis["spec"])
        self.assertEqual(redis["spec"]["template"]["spec"]["containers"][0]["image"], "redis:8")
        docs = render_all({"redis": {"enabled": True, "redis": {"configSecret": "auth"}}})
        redis = next(d for d in docs if d["kind"] == "StatefulSet")
        pod = redis["spec"]["template"]["spec"]
        self.assertIn({"name": "config", "secret": {"secretName": "auth", "items": [{"key": "redis.conf", "path": "redis.conf"}]}}, pod["volumes"])

    def test_form_defaults_match_values(self):
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        self.assertFalse(any(q["variable"].startswith("redis.persistence.") or
                             q["variable"] == "redis.image.pullSecret" for q in questions))
        for q in questions:
            value = values
            for part in q["variable"].split("."):
                value = value[part]
            self.assertEqual(q["default"], value, q["variable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
