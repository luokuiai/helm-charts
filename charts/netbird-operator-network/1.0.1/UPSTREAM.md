# Upstream compatibility

Chart version: `1.0.1`. API reference: NetBird Kubernetes Operator `0.8.0`.
`appVersion` denotes the Operator release used to verify the resource API; the Operator is installed separately.

- [Official Operator Chart](https://github.com/netbirdio/kubernetes-operator/tree/v0.8.0/charts/netbird-operator)
- [NetworkRouter CRD](https://github.com/netbirdio/kubernetes-operator/blob/v0.8.0/config/crd/bases/netbird.io_networkrouters.yaml)
- [NetworkResource CRD](https://github.com/netbirdio/kubernetes-operator/blob/v0.8.0/config/crd/bases/netbird.io_networkresources.yaml)
- [Official Service routing and DNS guide](https://docs.netbird.io/use-cases/kubernetes/route-to-a-kubernetes-service)

The bundled icon reuses the NetBird logo already present in this repository's `netbird-proxy` Chart.

The optional NAT DaemonSet is maintained by this repository, not the upstream Operator. It follows the `NetworkRouter -> Deployment -> ReplicaSet -> Pod` owner chain and the routing Deployment name/labels used by Operator `0.8.0`. Recheck this integration when upgrading the Operator.

- [Operator routing Deployment builder](https://github.com/netbirdio/kubernetes-operator/blob/v0.8.0/internal/controller/networkrouter_controller.go)
- [NetBird outbound NAT guidance](https://docs.netbird.io/about-netbird/ports-and-firewalls)
- [nftables NAT priority and conntrack behavior](https://wiki.nftables.org/wiki-nftables/index.php/Performing_Network_Address_Translation_(NAT))
- [Netshoot v0.14 image contents](https://github.com/nicolaka/netshoot/blob/v0.14/Dockerfile)
