# NetBird Operator Network

Configure an existing NetBird Operator to route VPN clients to a shared private ingress Service. This Chart creates a `NetworkRouter` and a `NetworkResource`; the Operator starts the actual routing client Pods and maintains the Service DNS record.

Install the official NetBird Operator and its CRDs first. In NetBird, create the custom DNS zone, destination groups, and an access policy. The defaults use `k3s.netbird.internal`, destination group `k3s-web`, and one routing client replica. Distribute DNS to authorized client devices and allow their group to reach `k3s-web` over TCP 443.

Install in `infra-system`, where the existing `traefik-vpn` **ClusterIP Service** is located. The **VPN ingress Service** dropdown selects that shared entrypoint, not Komodo or another business application. Applications keep their own namespaces and select `ingressClassName: traefik-vpn`.

With the defaults, the Operator-managed DNS record is `traefik-vpn.infra-system.k3s.netbird.internal`. Add application CNAMEs pointing to this record in NetBird DNS. Manage application Ingress and HTTPS certificates separately.

Keep the NetworkRouter name unchanged during upgrades because the resource's router reference is immutable. To change routers, create a new release with distinct resource names and plan the cutover. Uninstalling this Chart removes the routing configuration and can interrupt access to every application using this VPN entrypoint.

Version `1.0.1` optionally adds an outbound NAT workaround for Flannel fully-random SNAT. It is disabled by default. When enabled, a host-network DaemonSet with `NET_ADMIN` matches only this release's routing Pod IPv4 addresses and UDP source port `51820`. It opens no public inbound port and does not change NetBird's listener. Confirm the excluded Pod and Service CIDRs match your cluster. The maintenance image repository can be changed to a mirror.

Normal uninstall, upgrade, and disabling wait for registered nodes to acknowledge removal of this release's NAT table. Offline nodes or failed cleanup block the checked operation. Forced deletion, namespace deletion, and skipped hooks can leave rules behind; cleanup cannot be guaranteed in those cases. The agent refreshes every 60 seconds; source-address set entries expire after 90 seconds without refresh. This is a custom Chart extension, not an official Operator feature; see the README for permissions, limitations, and acceptance checks.
