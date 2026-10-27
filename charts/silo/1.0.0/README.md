# Silo

Locally maintained Helm Chart for [PGSTY Silo](https://github.com/pgsty/silo),
the S3-compatible MinIO fork. Pins `RELEASE.2026-10-26T00-00-00Z` and bundles
a Rancher configuration form. Requires Kubernetes 1.27+; supports K3s and
Linux amd64 / arm64.

- Enter `replicaCount` directly: `1` for standalone, any integer `2–16` for
  one distributed erasure set. Odd counts such as 3 and 5 are supported.
- Each distributed Pod requires a different schedulable Kubernetes node and
  one independent PVC. Defaults: `local-path`, `10Gi` per PVC.
- Generated or existing root credential Secret; no default password.
- Separate S3 API and Console domains, existing TLS or cert-manager.
- PVC retention, stable peer DNS, nonroot Pods, health probes, and a PDB
  for distributed installations.

Node count is an installation choice. This chart rejects count changes during
an upgrade against the live cluster; migrate to a new release to change topology.
It does not implement multi-pool expansion, automatic bucket creation, or a
MinIO operator. Use the Console or `mcli` to create buckets and scoped access keys.

Two nodes with one PVC each use `EC:1`: loss of one node stops writes; intact
existing objects may remain readable. With three nodes and default `EC:1`,
two healthy nodes can satisfy the ordinary read/write quorum. Failover still
depends on the affected objects, disks, metadata, and successful initialization.

See [the deployment guide](../../../docs/silo/deployment.md) for installation,
domain configuration, storage sizing, and maintenance.

```bash
helm lint charts/silo/1.0.0 --strict --set auth.useExistingSecret=true --set auth.existingSecret=silo-root
helm template silo charts/silo/1.0.0 --namespace storage \
  --set auth.useExistingSecret=true --set auth.existingSecret=silo-root \
  --set replicaCount=3
```
