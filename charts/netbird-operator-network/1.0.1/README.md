# NetBird Operator Network

A configuration Chart for the official NetBird Kubernetes Operator, with a Rancher installation form. By default it creates exactly one `NetworkRouter` and one `NetworkResource` using the `netbird.io/v1alpha1` API verified against Operator `0.8.0`. Version `1.0.1` adds an optional, disabled-by-default node NAT workaround.

The Operator starts the routing client Pods and reconciles the NetBird network, resource, and Service DNS record. This Chart does not install the Operator, NetBird server, Traefik, or application workloads.

## Prerequisites

- An existing NetBird Operator with its `NetworkRouter` and `NetworkResource` CRDs, connected to the intended management server. The PAT Secret belongs to that Operator installation, not this Chart.
- An existing ClusterIP Service for the shared VPN ingress controller. Install this Chart in the **same namespace as that Service**; the example uses `infra-system` and Service `traefik-vpn`.
- An existing NetBird custom DNS zone distributed to the authorized client device groups, existing destination groups, and an enabled access policy permitting the required traffic.
- The chosen resource names must not already belong to another Helm release. For an initial install, use names that have not already been manually deployed.

## Rancher installation

Sync this Git repository, search for **NetBird Operator Network**, and select `1.0.1`. Choose namespace `infra-system` and release name `netbird-operator-network`.

| Form field | Default | Meaning |
| --- | --- | --- |
| VPN ingress Service | `traefik-vpn` | Dropdown of existing Services in the installation namespace; select the shared ingress controller's ClusterIP Service |
| NetBird destination groups | `k3s-web` | Existing NetBird group names for the destination resource, not the client device groups |
| NetBird DNS zone | `k3s.netbird.internal` | Existing custom zone where the Operator creates the Service record |
| NetworkRouter name | `vpn-entry` | Name of the router created by this release; keep stable on upgrades |
| Routing client replicas | `1` | Number of routing client Pods, separate from the Operator replica count |
| Enable NetBird outbound NAT workaround | `false` | Optional node-level IPv4 SNAT exception for this router only; requires host networking and `NET_ADMIN` |

The Service dropdown is namespace-scoped and does not filter by Service type. Confirm that the selected Service is `ClusterIP`. This Chart does not query the NetBird API from the form, so DNS zones and group names are entered as text.

Applications behind this shared ingress controller do not need additional copies of this Chart. They use their own Ingress resources with the VPN controller's Ingress Class and an application-domain CNAME targeting the Operator-managed Service record.

## Helm installation

```bash
helm upgrade --install netbird-operator-network ./charts/netbird-operator-network/1.0.1 \
  --namespace infra-system \
  --set resource.serviceName=traefik-vpn \
  --set router.dnsZone=k3s.netbird.internal
```

See the [deployment guide](../../../docs/netbird-operator-network/deployment.md) for NetBird setup, DNS aliases, acceptance checks, and lifecycle behavior. See [UPSTREAM.md](UPSTREAM.md) for the upstream API references.

## Optional Flannel NAT workaround

Enable `natWorkaround.enabled` only when Flannel fully-random SNAT interferes with NetBird UDP hole punching. This is a custom extension of this Chart, not a NetBird Operator setting, and does not guarantee P2P through every remote network.

The DaemonSet runs on Linux nodes with host networking and only the `NET_ADMIN` capability. The namespace must permit this security context. It does not require `privileged: true`, host filesystem mounts, a ClusterRole, a host port, or a public inbound firewall exception. It reads namespaced router, Deployment, ReplicaSet, and Pod metadata; the only API write permission patches its own control ConfigMap. The pinned Netshoot image already includes Python and nftables. The image uses one field, `natWorkaround.image.repository`, defaulting to `ghcr.io/nicolaka/netshoot:v0.14`. Include a tag or digest in the same field when using a mirror. Untagged references use the legacy `image.tag` if supplied, otherwise `v0.14`; an explicit tag or digest takes precedence.

For each node, the agent verifies this release's NetworkRouter and its Deployment/ReplicaSet owner chain, then selects only that router's locally scheduled, non-host-network Pod IPv4 addresses. It never matches the entire Pod CIDR. The exception applies only to UDP source port `51820`; excluded destinations default to the K3s Pod CIDR, Service CIDR, and multicast range. Change `natWorkaround.excludedCIDRs` for clusters with other CIDRs. Enabling the feature does not change the routing Pod template or NetBird listener configuration.

The agent refreshes an exclusive nftables table every 60 seconds, before normal source NAT at priority `99`. Source-address set entries expire after 90 seconds without a successful refresh. Selection follows Kubernetes Pod updates asynchronously; it is not a packet-level identity check. Existing conntrack mappings are deliberately left intact. Changes to the NAT table do not reset existing connections.

### Upgrade, disable, and uninstall

- Normal uninstall first puts all agents in cleanup mode. Each agent removes only this release's nftables table and acknowledges removal. The Helm pre-delete Job waits for every registered node and every currently scheduled agent; an unavailable node, failed cleanup, or missing agent blocks verified completion and produces a failed Job instead of reporting success.
- Upgrading an existing enabled installation, including setting `natWorkaround.enabled=false`, runs the same cleanup before changing or removing the resources. The pre-upgrade hook is rendered by looking up the previous control ConfigMap. The Helm identity performing the upgrade must be allowed to read that ConfigMap. Client-only `helm template` cannot discover an existing installation and therefore cannot demonstrate this upgrade hook.
- Do not use `--no-hooks` or force-delete the namespace if verified cleanup is required. Hook Jobs cannot run after their namespace, permissions, or control resources have been removed. Power loss, forced deletion, and unreachable/removed nodes can leave an empty or stale table; the 90-second element expiry bounds new matches while the node clock runs but does not remove the table or clear existing conntrack entries.
- If cleanup fails, restore the affected node/agent and retry the Helm operation. Inspect the `<release>-nat-cleanup` Job logs and the `<release>-nat` ConfigMap. Do not remove registered node records merely to make the check pass.

To inspect the rules, read `NFT_TABLE` from the maintenance Pod environment and run `nft list table ip <table>` in that Pod's shell. Compare the `routers` set with the current routing Pods on that node, verify another application's IP is absent, and check `netbird status -d` from the client after a fresh connection. After a normal disable/uninstall, confirm that the named table is absent on every node. Image startup, live P2P behavior, and lifecycle hooks must be verified on the target cluster before relying on the workaround.
