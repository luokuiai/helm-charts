# NetBird Operator Network deployment

This Chart connects a shared private Kubernetes ingress controller to an existing NetBird network. Keep the official Operator and ingress controller as separate installations.

## Prepare the existing installations

1. Install the official NetBird Operator and configure its management URL and PAT Secret. A PAT used through a Pod Secret reference must be in the Operator Pod's namespace. Renew it before expiry and restart the Operator after updating its environment-backed Secret.
2. Install the private ingress controller, for example `traefik-vpn`, in `infra-system`. Its Service must be `ClusterIP`, with no separate public entrypoint. Confirm the actual Service name in Rancher before selecting it.
3. Configure each ingress controller to accept only its intended Ingress Class. In this example, the public controller accepts `traefik`, and the private controller accepts `traefik-vpn`.

## Prepare NetBird

Create the following in the NetBird dashboard before installing this Chart:

| Item | Example | Configuration |
| --- | --- | --- |
| Client device group | `k3s-clients` | Add the computers authorized to access private applications |
| Destination group | `k3s-web` | Create an empty group for the shared ingress Service resource |
| Custom DNS zone | `k3s.netbird.internal` | Distribute to `k3s-clients`; leave records for the Operator to maintain |
| Access policy | `k3s-web-access` | Allow source `k3s-clients` to destination `k3s-web`, TCP 443 |

Clients must use NetBird-managed DNS. Check existing broad policies as well: assigning a destination group alone does not revoke access already allowed by other policies.

## Install the Chart

In Rancher, refresh this Git repository and install **NetBird Operator Network** version `1.0.0` in **`infra-system`**. Select the existing `traefik-vpn` Service from the **VPN ingress Service** dropdown. Keep the defaults if they match the NetBird preparation above.

The release creates:

- `NetworkRouter/vpn-entry` in the release namespace, requesting one routing client replica.
- `NetworkResource/traefik-vpn` in the release namespace, referencing the router and Service in that same namespace, and the `k3s-web` group by name.

The form only selects the shared ingress Service. Komodo and other applications retain their own Services and Ingress resources; they select `traefik-vpn` as their Ingress Class.

## Add application DNS and HTTPS

With the example values, the Operator manages:

```text
traefik-vpn.infra-system.k3s.netbird.internal
```

This record points to the ingress Service's ClusterIP. Add a custom NetBird zone for your application domain, distribute it to the authorized clients, and create application CNAME records targeting that full name. Use your own domain; for example, `komodo.example.com` can be a CNAME in the `example.com` NetBird zone. The CNAME remains stable when the Operator updates the Service record after a ClusterIP change.

Configure each application's native Ingress with `spec.ingressClassName: traefik-vpn`, its application hostname, backend Service, and TLS settings. Keep the application Ingress in the same namespace as its backend Service. Certificate issuance remains separate; for private applications, cert-manager can use DNS-01 against your public DNS provider without exposing the application publicly.

Remove any public route to applications intended to be VPN-only. A DNS record or Class name alone does not establish network isolation.

## Verify

Check the custom resource status, not just the Helm release status:

```bash
kubectl -n infra-system get networkrouter vpn-entry
kubectl -n infra-system get networkresource traefik-vpn
kubectl -n infra-system get pods,services
```

Both custom resources should become Ready. If either remains unready, inspect its status and Events and the Operator logs. A missing DNS zone, Service, group, or policy must be corrected in the relevant system; a successful Helm install does not prove VPN connectivity.

From an authorized computer, verify that the application resolves and works over HTTPS with VPN connected. Disconnect VPN and verify that the application cannot be reached. Also force the hostname against the public ingress IP to verify that the public controller cannot route to the application. Use HTTPS connectivity as the acceptance test; Service ClusterIP is not an ICMP ping endpoint.

## Upgrade and uninstall

- Change `router.replicas` through Rancher when adding nodes. Multiple routing clients allow failover, but the ingress controller and application also need their own availability configuration.
- Keep `router.name` unchanged during normal upgrades. The upstream CRD makes `NetworkResource.spec.networkRouterRef` immutable, so changing the name in place is not a supported Helm update. Plan a separate release with distinct resource names for a router migration.
- Changing the Service name changes the NetworkResource name and the Operator-managed DNS record; plan updates to application CNAMEs and expect a cutover.
- Do not install another release with the same resource names in the same namespace. Manually imported resources are not automatically adopted by this Chart.
- Uninstalling deletes both custom resources. The Operator cleans up their managed NetBird resources, and routing access through this entrypoint is removed. Use another management path if Rancher itself relies on this VPN route.
- Uninstall this configuration Chart before removing the Operator so the Operator can complete resource cleanup.
