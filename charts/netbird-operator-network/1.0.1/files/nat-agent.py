"""Maintain an IPv4 NAT exception for this release's locally scheduled routers."""

import os
from pathlib import Path
import sys
import time


INTERVAL = 60
ELEMENT_TTL = 90
STATE = Path("/run/netbird-nat/ready")


def health():
    try:
        return 0 if time.time() - STATE.stat().st_mtime < ELEMENT_TTL else 1
    except FileNotFoundError:
        return 1


# Probes share the container's small CPU budget; skip maintenance dependencies.
if __name__ == "__main__" and "--health" in sys.argv:
    sys.exit(health())

import hashlib
import ipaddress
import json
import signal
import ssl
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class API:
    def __init__(self):
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        if ":" in host:
            host = "[" + host + "]"
        self.url = "https://" + host + ":" + os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        self.credentials = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.context = ssl.create_default_context(cafile=str(self.credentials / "ca.crt"))

    def request(self, path, patch=None):
        headers = {"Authorization": "Bearer " + (self.credentials / "token").read_text().strip()}
        body = None
        if patch is not None:
            headers["Content-Type"] = "application/merge-patch+json"
            body = json.dumps(patch).encode()
        req = Request(self.url + path, data=body, headers=headers, method="PATCH" if patch is not None else "GET")
        try:
            with urlopen(req, context=self.context, timeout=8) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and patch is None:
                return None
            raise


def owned_by(resource, kind, uid):
    return any(ref.get("controller") and ref.get("kind") == kind and ref.get("uid") == uid
               for ref in resource.get("metadata", {}).get("ownerReferences", []))


def router_ips(api, namespace, router, release, node):
    ns = quote(namespace, safe="")
    custom = api.request(f"/apis/netbird.io/v1alpha1/namespaces/{ns}/networkrouters/{quote(router, safe='')}")
    if custom is None:
        return []
    metadata = custom["metadata"]
    if metadata.get("labels", {}).get("app.kubernetes.io/instance") != release:
        raise RuntimeError("NetworkRouter is not owned by this release")
    deployment = api.request(f"/apis/apps/v1/namespaces/{ns}/deployments/networkrouter-{quote(router, safe='')}")
    if deployment is None:
        return []
    if not owned_by(deployment, "NetworkRouter", metadata["uid"]):
        raise RuntimeError("routing Deployment has an unexpected owner")
    selector = "app.kubernetes.io/name=networkrouter,app.kubernetes.io/instance=" + router
    query = urlencode({"labelSelector": selector})
    replicas = api.request(f"/apis/apps/v1/namespaces/{ns}/replicasets?{query}")["items"]
    owners = {rs["metadata"]["uid"] for rs in replicas
              if owned_by(rs, "Deployment", deployment["metadata"]["uid"])}
    query = urlencode({"labelSelector": selector, "fieldSelector": "spec.nodeName=" + node})
    pods = api.request(f"/api/v1/namespaces/{ns}/pods?{query}")["items"]
    addresses = set()
    for pod in pods:
        spec = pod.get("spec", {})
        if spec.get("nodeName") != node or spec.get("hostNetwork"):
            continue
        if pod.get("status", {}).get("phase") not in ("Pending", "Running"):
            continue
        if not any(owned_by(pod, "ReplicaSet", uid) for uid in owners):
            continue
        address = pod.get("status", {}).get("podIP")
        if address:
            address = ipaddress.ip_address(address)
            if address.version == 4:
                addresses.add(str(address))
    return sorted(addresses)


def nft_rules(table, addresses, exclusions):
    if not table.startswith("nb_nat_") or not table[7:].isalnum():
        raise ValueError("invalid table name")
    addresses = [str(ipaddress.IPv4Address(address)) for address in addresses]
    networks = [str(ipaddress.IPv4Network(network)) for network in exclusions]
    if not networks:
        raise ValueError("non-masquerade networks must not be empty")
    commands = [
        f"add table ip {table}",
        f"add chain ip {table} postrouting {{ type nat hook postrouting priority 99; policy accept; }}",
        f"add set ip {table} routers {{ type ipv4_addr; flags timeout; timeout {ELEMENT_TTL}s; }}",
        f"flush chain ip {table} postrouting",
        f"flush set ip {table} routers",
    ]
    if addresses:
        commands.append(f"add element ip {table} routers {{ " + ", ".join(addresses) + " }")
    commands.append(f"add rule ip {table} postrouting ip saddr @routers ip daddr != {{ "
                    + ", ".join(networks) + " } udp sport 51820 counter masquerade")
    return "\n".join(commands) + "\n"


def remove_table(table):
    # Listing JSON distinguishes an absent table from permission/netlink failures.
    tables = json.loads(subprocess.check_output(["nft", "-j", "list", "tables"], text=True, timeout=10))
    if any(item.get("table", {}).get("family") == "ip"
           and item["table"].get("name") == table for item in tables["nftables"]):
        subprocess.run(["nft", "delete", "table", "ip", table], check=True, timeout=10)


def node_key(node):
    return hashlib.sha256(node.encode()).hexdigest()[:16]


def cleanup_complete(data, nodes, desired, epoch):
    registered = {key[5:]: name for key, name in data.items() if key.startswith("node.")}
    expected = set(registered) | {node_key(node) for node in nodes}
    return len(nodes) == desired and all(data.get("clean." + key) == epoch for key in expected)


def cleanup(api, namespace, name, timeout):
    ns = quote(namespace, safe="")
    control = f"/api/v1/namespaces/{ns}/configmaps/{quote(name, safe='')}"
    config = api.request(control)
    if config is None:
        raise RuntimeError("NAT control ConfigMap is missing; cleanup cannot be verified")
    revision = config["data"].get("revision", "")
    epoch = os.urandom(16).hex()
    api.request(control, {"data": {"mode": "cleanup", "epoch": epoch, "cleanupRevision": revision}})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        deployment = api.request(f"/apis/apps/v1/namespaces/{ns}/daemonsets/{quote(name, safe='')}")
        if deployment is None:
            raise RuntimeError("NAT DaemonSet is missing; cleanup cannot be verified")
        query = urlencode({"labelSelector": "app.kubernetes.io/component=" + name})
        pods = api.request(f"/api/v1/namespaces/{ns}/pods?{query}")["items"]
        nodes = {pod["spec"]["nodeName"] for pod in pods if pod.get("spec", {}).get("nodeName")}
        data = api.request(control)["data"]
        if (data.get("mode") != "cleanup" or data.get("epoch") != epoch
                or data.get("revision", "") != revision):
            raise RuntimeError("cleanup request was changed by another operation")
        status = deployment.get("status", {})
        if (status.get("observedGeneration", 0) >= deployment["metadata"]["generation"]
                and cleanup_complete(data, nodes, status.get("desiredNumberScheduled", -1), epoch)):
            print("All registered nodes acknowledged removal of the release NAT table", flush=True)
            return
        time.sleep(2)
    raise RuntimeError("NAT cleanup timed out; inspect maintenance Pods and node availability before retrying")


def maintain(api, namespace, name, router, release, node, table, exclusions):
    control = f"/api/v1/namespaces/{quote(namespace, safe='')}/configmaps/{quote(name, safe='')}"
    key = node_key(node)
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while not stopped:
            try:
                config = api.request(control)
                if config is None:
                    raise RuntimeError("NAT control ConfigMap is missing")
                data = config["data"]
                if data.get("node." + key) != node:
                    api.request(control, {"data": {"node." + key: node}})
                mode = data.get("mode", "active")
                # A successfully applied release supersedes the previous cleanup request.
                # Empty revisions keep the pre-revision cleanup protocol compatible.
                if mode == "cleanup" and data.get("cleanupRevision", "") != data.get("revision", ""):
                    mode = "active"
                if mode == "cleanup":
                    remove_table(table)
                    epoch = data["epoch"]
                    if not epoch:
                        raise RuntimeError("cleanup epoch is empty")
                    if data.get("clean." + key) != epoch:
                        api.request(control, {"data": {"clean." + key: epoch}})
                elif mode == "active":
                    addresses = router_ips(api, namespace, router, release, node)
                    subprocess.run(["nft", "-f", "-"], input=nft_rules(table, addresses, exclusions),
                                   text=True, check=True, timeout=10)
                    print(f"NAT refreshed: node={node} table={table} routerIPs={addresses}", flush=True)
                else:
                    raise RuntimeError("unrecognized NAT control mode")
                STATE.touch()
            except Exception as error:
                STATE.unlink(missing_ok=True)
                print("NAT reconciliation failed: " + str(error), file=sys.stderr, flush=True)
            for _ in range(INTERVAL):
                if stopped:
                    break
                time.sleep(1)
    finally:
        STATE.unlink(missing_ok=True)
        remove_table(table)


def main():
    if "--health" in sys.argv:
        return health()
    print("Starting NAT " + ("cleanup" if "--cleanup" in sys.argv else "maintenance"), flush=True)
    api = API()
    namespace, name = os.environ["NAMESPACE"], os.environ["NAT_NAME"]
    if "--cleanup" in sys.argv:
        cleanup(api, namespace, name, int(os.environ["CLEANUP_TIMEOUT"]))
    else:
        maintain(api, namespace, name, os.environ["ROUTER_NAME"], os.environ["RELEASE_NAME"],
                 os.environ["NODE_NAME"], os.environ["NFT_TABLE"], json.loads(os.environ["EXCLUDED_CIDRS"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
