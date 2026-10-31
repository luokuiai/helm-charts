"""Unit tests; optional kernel checks run only inside an isolated network namespace."""

import copy
import builtins
import importlib.util
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "charts/netbird-operator-network/1.0.1/files/nat-agent.py"
spec = importlib.util.spec_from_file_location("nat_agent", SOURCE)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


def resource(uid, kind=None, owner=None, **extra):
    metadata = {"uid": uid}
    if owner:
        metadata["ownerReferences"] = [{"kind": kind, "uid": owner, "controller": True}]
    return {"metadata": metadata, **extra}


class RouterAPI:
    def __init__(self):
        self.router = resource("router")
        self.router["metadata"]["labels"] = {"app.kubernetes.io/instance": "release"}
        self.deployment = resource("deployment", "NetworkRouter", "router")
        self.replicas = [resource("ours", "Deployment", "deployment"),
                         resource("foreign", "Deployment", "another-deployment")]
        self.pods = [self.pod("10.42.0.41"), self.pod("10.42.0.42", owner="foreign"),
                     self.pod("10.42.1.41", node="node-b"),
                     self.pod("10.6.0.16", host=True), self.pod("10.42.0.99", phase="Succeeded"),
                     self.pod("fd00::1")]
        self.paths = []

    @staticmethod
    def pod(ip, owner="ours", node="node-a", host=False, phase="Running"):
        return resource(ip, "ReplicaSet", owner,
                        spec={"nodeName": node, "hostNetwork": host}, status={"podIP": ip, "phase": phase})

    def request(self, path, patch=None):
        self.paths.append(path)
        if "/networkrouters/" in path:
            return self.router
        if "/deployments/" in path:
            return self.deployment
        return {"items": self.replicas if "/replicasets?" in path else self.pods}


class CleanupAPI:
    def __init__(self, acknowledge):
        self.acknowledge = acknowledge
        self.data = {"mode": "active", "epoch": "", "node." + agent.node_key("node-a"): "node-a"}
        self.writes = []

    def request(self, path, patch=None):
        if patch:
            self.writes.append(patch)
            self.data.update(patch["data"])
            if self.acknowledge:
                self.data["clean." + agent.node_key("node-a")] = self.data["epoch"]
        if "/configmaps/" in path:
            return {"data": copy.deepcopy(self.data)}
        if "/daemonsets/" in path:
            return {"metadata": {"generation": 1},
                    "status": {"observedGeneration": 1, "desiredNumberScheduled": 1}}
        return {"items": [{"spec": {"nodeName": "node-a"}}]}


class AgentTests(unittest.TestCase):
    def test_health_entrypoint_skips_network_and_nft_imports(self):
        original_import = builtins.__import__

        def health_import(name, *args, **kwargs):
            if name in {"ssl", "subprocess", "urllib.request"}:
                raise AssertionError("health check imported " + name)
            return original_import(name, *args, **kwargs)

        for age, expected in [(59, 0), (89, 0), (90, 1), (None, 1)]:
            with self.subTest(age=age), \
                 patch.object(agent.sys, "argv", [str(SOURCE), "--health"]), \
                 patch.object(agent.time, "time", return_value=1000), \
                 patch.object(Path, "stat") as stat, \
                 patch.object(builtins, "__import__", side_effect=health_import):
                if age is None:
                    stat.side_effect = FileNotFoundError
                else:
                    stat.return_value.st_mtime = 1000 - age
                with self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(SOURCE), run_name="__main__")
                self.assertEqual(result.exception.code, expected)

    def test_health_allows_a_minute_between_refreshes_but_rejects_stalled_maintenance(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "ready"
            with patch.object(agent, "STATE", state), \
                 patch.object(agent.sys, "argv", ["agent.py", "--health"]):
                self.assertEqual(agent.main(), 1)
                state.touch()
                os.utime(state, (1000, 1000))
                for age, expected in [(59, 0), (61, 0), (89, 0), (90, 1)]:
                    with self.subTest(age=age), patch.object(agent.time, "time", return_value=1000 + age):
                        self.assertEqual(agent.main(), expected)

    def test_only_current_router_owner_chain_and_local_non_host_pods_are_selected(self):
        api = RouterAPI()
        self.assertEqual(agent.router_ips(api, "infra-system", "vpn-entry", "release", "node-a"),
                         ["10.42.0.41"])
        self.assertIn("fieldSelector=spec.nodeName%3Dnode-a", api.paths[-1])

    def test_unexpected_release_and_deployment_owners_are_rejected(self):
        api = RouterAPI()
        with self.assertRaises(RuntimeError):
            agent.router_ips(api, "infra-system", "vpn-entry", "foreign-release", "node-a")
        api.deployment["metadata"]["ownerReferences"][0]["uid"] = "foreign-router"
        with self.assertRaises(RuntimeError):
            agent.router_ips(api, "infra-system", "vpn-entry", "release", "node-a")

    def test_missing_deployment_selects_nothing(self):
        api = RouterAPI()
        api.deployment = None
        self.assertEqual(agent.router_ips(api, "infra-system", "vpn-entry", "release", "node-a"), [])

    def test_rules_are_scoped_expiring_and_reject_injection(self):
        rules = agent.nft_rules("nb_nat_test", ["10.42.0.41"], ["10.42.0.0/16", "224.0.0.0/4"])
        self.assertIn("ip saddr @routers", rules)
        self.assertIn("udp sport 51820", rules)
        self.assertIn("flags timeout", rules)
        self.assertNotIn("random", rules)
        self.assertNotIn("flush ruleset", rules)
        with self.assertRaises(ValueError):
            agent.nft_rules("nb_nat_test", ["10.42.0.41; flush ruleset"], ["224.0.0.0/4"])
        with self.assertRaises(ValueError):
            agent.nft_rules("anything; flush ruleset", [], ["224.0.0.0/4"])

    def test_cleanup_requires_each_registered_node_current_epoch_and_all_scheduled_agents(self):
        a, b = agent.node_key("a"), agent.node_key("b")
        data = {"node." + a: "a", "clean." + a: "epoch"}
        self.assertTrue(agent.cleanup_complete(data, {"a"}, 1, "epoch"))
        self.assertFalse(agent.cleanup_complete(data, {"a"}, 2, "epoch"))
        self.assertFalse(agent.cleanup_complete(data, {"a"}, 1, "new-epoch"))
        data["node." + b] = "b"
        self.assertFalse(agent.cleanup_complete(data, {"a"}, 1, "epoch"))
        data["clean." + b] = "epoch"
        self.assertTrue(agent.cleanup_complete(data, {"a"}, 1, "epoch"))

    def test_cleanup_switches_mode_before_waiting_and_preserves_it_after_success(self):
        api = CleanupAPI(acknowledge=True)
        agent.cleanup(api, "infra-system", "release-nat", 120)
        self.assertEqual(api.writes[0]["data"]["mode"], "cleanup")
        self.assertEqual(api.data["mode"], "cleanup")

    def test_unacknowledged_node_makes_cleanup_fail(self):
        api = CleanupAPI(acknowledge=False)
        with patch.object(agent.time, "monotonic", side_effect=[0, 1, 121]), patch.object(agent.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                agent.cleanup(api, "infra-system", "release-nat", 120)
        self.assertEqual(api.data["mode"], "cleanup")

    def test_maintenance_acknowledges_only_successful_removal_and_never_readds_in_cleanup(self):
        for removal_fails in (False, True):
            with self.subTest(removal_fails=removal_fails), tempfile.TemporaryDirectory() as temp:
                api = CleanupAPI(acknowledge=False)
                api.data.update({"mode": "cleanup", "epoch": "cleanup-epoch"})
                handlers, events = {}, []

                def remove(_):
                    events.append("remove")
                    if removal_fails and len(events) == 1:
                        raise RuntimeError("netlink unavailable")

                original_request = api.request

                def request(path, patch=None):
                    if patch and any(key.startswith("clean.") for key in patch["data"]):
                        events.append("ack")
                    return original_request(path, patch)

                api.request = request
                with patch.object(agent.signal, "signal", side_effect=lambda sig, fn: handlers.update({sig: fn})), \
                     patch.object(agent.time, "sleep", side_effect=lambda _: handlers[agent.signal.SIGTERM]()), \
                     patch.object(agent, "STATE", Path(temp) / "ready"), \
                     patch.object(agent, "remove_table", side_effect=remove), \
                     patch.object(agent.subprocess, "run") as apply:
                    agent.maintain(api, "infra-system", "release-nat", "vpn-entry", "release",
                                   "node-a", "nb_nat_test", ["224.0.0.0/4"])
                apply.assert_not_called()
                self.assertEqual(events, ["remove", "remove"] if removal_fails
                                 else ["remove", "ack", "remove"])

    def test_cleanup_does_not_hide_netlink_failures(self):
        with patch.object(agent.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, "nft")):
            with self.assertRaises(subprocess.CalledProcessError):
                agent.remove_table("nb_nat_test")


@unittest.skipUnless(os.environ.get("RUN_NFT_INTEGRATION") == "1", "requires an isolated network namespace")
class KernelTests(unittest.TestCase):
    def test_repeated_updates_ip_replacement_expiry_and_owned_table_cleanup(self):
        table = "nb_nat_kerneltest"
        subprocess.run(["nft", "add", "table", "ip", "unrelated"], check=True)
        try:
            with patch.object(agent, "ELEMENT_TTL", 1):
                for address in ["10.42.0.41", "10.42.0.41", "10.42.0.42"]:
                    rules = agent.nft_rules(table, [address], ["10.42.0.0/16", "10.43.0.0/16", "224.0.0.0/4"])
                    subprocess.run(["nft", "-f", "-"], input=rules, text=True, check=True)
            output = subprocess.check_output(["nft", "-j", "list", "table", "ip", table], text=True)
            docs = json.loads(output)["nftables"]
            self.assertEqual(len([doc for doc in docs if "rule" in doc]), 1)
            self.assertIn("10.42.0.42", output)
            self.assertNotIn("10.42.0.41", output)
            self.assertNotIn("random", output)
            agent.time.sleep(1.2)
            self.assertNotIn("10.42.0.42", subprocess.check_output(
                ["nft", "-j", "list", "set", "ip", table, "routers"], text=True))
            agent.remove_table(table)
            agent.remove_table(table)
            tables = json.loads(subprocess.check_output(["nft", "-j", "list", "tables"], text=True))["nftables"]
            self.assertTrue(any(doc.get("table", {}).get("name") == "unrelated" for doc in tables))
            self.assertFalse(any(doc.get("table", {}).get("name") == table for doc in tables))
        finally:
            agent.remove_table(table)
            subprocess.run(["nft", "delete", "table", "ip", "unrelated"], check=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
