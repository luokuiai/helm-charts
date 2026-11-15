"""Run with PyYAML installed: python3 tests/redis/test_chart.py."""
from pathlib import Path
import subprocess
import unittest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts/redis/1.0.0"


def render(values=None):
    result = subprocess.run(["helm", "template", "cache", str(CHART), "--namespace", "apps", "-f", "-"],
                            input=yaml.safe_dump(values or {}), capture_output=True, text=True, check=True)
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(docs, kind):
    return next(doc for doc in docs if doc["kind"] == kind)


class RedisChartTests(unittest.TestCase):
    def test_default_no_auth_and_persistent_aof(self):
        docs = render()
        ss = resource(docs, "StatefulSet")["spec"]
        pod = ss["template"]["spec"]
        app = pod["containers"][0]
        self.assertEqual(ss["replicas"], 1)
        self.assertEqual(app["command"], ["redis-server"])
        self.assertEqual(app["args"][-2:], ["--appendonly", "yes"])
        self.assertIn({"name": "data", "mountPath": "/data"}, app["volumeMounts"])
        self.assertEqual(ss["volumeClaimTemplates"][0]["spec"]["storageClassName"], "local-path")
        self.assertNotIn("volumes", pod)
        svc = next(d for d in docs if d["kind"] == "Service" and d["metadata"]["name"] == "cache")
        self.assertEqual(svc["spec"]["type"], "ClusterIP")
        self.assertEqual(svc["spec"]["ports"][0]["port"], 6379)

    def test_optional_secret_and_existing_claim(self):
        docs = render({"redis": {"configSecret": "cache-config"},
                       "persistence": {"existingClaim": "cache-data"},
                       "image": {"pullSecret": "harbor"}})
        ss = resource(docs, "StatefulSet")["spec"]
        pod = ss["template"]["spec"]
        app = pod["containers"][0]
        self.assertEqual(app["command"], ["redis-server", "/etc/redis/redis.conf"])
        self.assertIn({"name": "config", "secret": {"secretName": "cache-config", "items": [{"key": "redis.conf", "path": "redis.conf"}]}}, pod["volumes"])
        self.assertIn({"name": "data", "persistentVolumeClaim": {"claimName": "cache-data"}}, pod["volumes"])
        self.assertEqual(pod["imagePullSecrets"], [{"name": "harbor"}])
        self.assertNotIn("volumeClaimTemplates", ss)

    def test_optional_config_and_storage_independently(self):
        for values in ({"redis": {"configSecret": "cache-config"}},
                       {"persistence": {"existingClaim": "cache-data"}}):
            with self.subTest(values=values):
                ss = resource(render(values), "StatefulSet")["spec"]
                names = {v["name"] for v in ss["template"]["spec"]["volumes"]}
                self.assertEqual(names, {"config"} if "redis" in values else {"data"})

    def test_form_defaults(self):
        questions = yaml.safe_load((CHART / "questions.yaml").read_text())["questions"]
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        for question in questions:
            current = values
            for part in question["variable"].split("."):
                current = current[part]
            self.assertEqual(question["default"], current, question["variable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
