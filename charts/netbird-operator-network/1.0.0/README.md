# NetBird Operator Network

A configuration Chart for the official NetBird Kubernetes Operator, with a Rancher installation form. It creates exactly one `NetworkRouter` and one `NetworkResource` using the `netbird.io/v1alpha1` API verified against Operator `0.8.0`.

The Operator starts the routing client Pods and reconciles the NetBird network, resource, and Service DNS record. This Chart does not install the Operator, NetBird server, Traefik, or application workloads.

## Prerequisites

- An existing NetBird Operator with its `NetworkRouter` and `NetworkResource` CRDs, connected to the intended management server. The PAT Secret belongs to that Operator installation, not this Chart.
- An existing ClusterIP Service for the shared VPN ingress controller. Install this Chart in the **same namespace as that Service**; the example uses `infra-system` and Service `traefik-vpn`.
- An existing NetBird custom DNS zone distributed to the authorized client device groups, existing destination groups, and an enabled access policy permitting the required traffic.
- The chosen resource names must not already belong to another Helm release. For an initial install, use names that have not already been manually deployed.

## Rancher installation

Sync this Git repository, search for **NetBird Operator Network**, and select `1.0.0`. Choose namespace `infra-system` and release name `netbird-operator-network`.

| Form field | Default | Meaning |
| --- | --- | --- |
| VPN ingress Service | `traefik-vpn` | Dropdown of existing Services in the installation namespace; select the shared ingress controller's ClusterIP Service |
| NetBird destination groups | `k3s-web` | Existing NetBird group names for the destination resource, not the client device groups |
| NetBird DNS zone | `k3s.netbird.internal` | Existing custom zone where the Operator creates the Service record |
| NetworkRouter name | `vpn-entry` | Name of the router created by this release; keep stable on upgrades |
| Routing client replicas | `1` | Number of routing client Pods, separate from the Operator replica count |

The Service dropdown is namespace-scoped and does not filter by Service type. Confirm that the selected Service is `ClusterIP`. This Chart does not query the NetBird API from the form, so DNS zones and group names are entered as text.

Applications behind this shared ingress controller do not need additional copies of this Chart. They use their own Ingress resources with the VPN controller's Ingress Class and an application-domain CNAME targeting the Operator-managed Service record.

## Helm installation

```bash
helm upgrade --install netbird-operator-network ./charts/netbird-operator-network/1.0.0 \
  --namespace infra-system \
  --set resource.serviceName=traefik-vpn \
  --set router.dnsZone=k3s.netbird.internal
```

See the [deployment guide](../../../docs/netbird-operator-network/deployment.md) for NetBird setup, DNS aliases, acceptance checks, and lifecycle behavior. See [UPSTREAM.md](UPSTREAM.md) for the upstream API references.
