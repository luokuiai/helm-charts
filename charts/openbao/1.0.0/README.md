# OpenBao

OpenBao 2.7.2 with a Rancher configuration form, based on the official chart
0.30.5. Requires Kubernetes 1.30 or newer. See [UPSTREAM.md](UPSTREAM.md)
for provenance and [README.upstream.md](README.upstream.md) for advanced settings.

The form supports one persistent standalone node, or a 3 / 5 replica Raft HA
cluster. Each replica has its own PVC. HA replicas are scheduled on different
Kubernetes nodes using the upstream required pod anti-affinity.

Set the image repository in one field: `server.image.repository` defaults to
`openbao/openbao` on Docker Hub. For another registry, enter the full repository,
such as `quay.io/openbao/openbao` or `registry.example.com/team/openbao`.
The optional tag remains separate and defaults to `2.7.2`.

Enable domain access to set the hostname and Ingress Class. HTTPS can use an
existing TLS Secret or cert-manager with an existing Issuer / ClusterIssuer.
TLS terminates at the Ingress; the backend connection uses HTTP. DNS, the
Ingress controller, cert-manager, and issuers are managed separately.

After installation, initialize node 0 and unseal the nodes. Pods remain
unready until this is complete. Initialization and unseal keys are never
generated or stored by this chart.

See the [deployment guide](../../../docs/openbao/deployment.md) for commands,
sample values, and the required initialization procedure. Do not switch
between standalone and HA storage modes on an existing installation without
a separate data migration. PVCs are retained on uninstall and scale-down;
namespace deletion and manual PVC deletion can still remove data.

Validate locally:

```bash
helm lint charts/openbao/1.0.0 --strict
uv run --with pyyaml python tests/openbao/test_chart.py
```
