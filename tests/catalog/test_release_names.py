"""Run with: uv run --with pyyaml python tests/catalog/test_release_names.py."""

from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]


class ReleaseNameTests(unittest.TestCase):
    def test_rancher_installation_names_are_editable_for_all_charts(self):
        for path in sorted((ROOT / "charts").glob("*/*/Chart.yaml")):
            with self.subTest(chart=str(path.relative_to(ROOT))):
                chart = yaml.safe_load(path.read_text())
                self.assertNotIn("catalog.cattle.io/release-name", chart.get("annotations", {}))

    def test_komodo_names_follow_the_release_and_preserve_explicit_overrides(self):
        for release, values, expected in [
            ("komodo", {}, "komodo"),
            ("komodo-a", {}, "komodo-a"),
            ("komodo-b", {}, "komodo-b"),
            ("custom", {"fullnameOverride": "original-komodo"}, "original-komodo"),
        ]:
            with self.subTest(release=release, values=values):
                result = subprocess.run(
                    ["helm", "template", release, str(ROOT / "charts/komodo/1.0.0"),
                     "--values", "-"],
                    input=yaml.safe_dump(values), capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
                deployment = next(doc for doc in docs if doc["kind"] == "Deployment")
                mongo = next(doc for doc in docs if doc["kind"] == "StatefulSet")
                self.assertEqual(deployment["metadata"]["name"], expected)
                self.assertEqual(mongo["metadata"]["name"], expected + "-mongo")
                for doc in (deployment, mongo):
                    self.assertEqual(doc["metadata"]["labels"]["app.kubernetes.io/instance"], release)


if __name__ == "__main__":
    unittest.main(verbosity=2)
