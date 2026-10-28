# Silo

S3-compatible object storage from PGSTY, derived from MinIO, with the full
Web Console and a Rancher installation form.

Enter a node count from **1 to 16** directly: 1 is standalone; 2 or more use
distributed erasure coding. Each distributed Pod needs a distinct schedulable
Kubernetes node and its own data PVC. K3s `local-path` is the default storage
class, with **10Gi per node** before erasure-coding overhead.

Select an existing environment Secret (default `silo-env`) containing
`MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`. Its entries become environment
variables. Silo preserves these MinIO-compatible names. Restart the StatefulSet
after updating the Secret. Create scoped application credentials after installation.
The optional Ingress uses separate hostnames for S3 API and Console, with
independent exposure switches. Disable API Ingress to expose only the Console;
S3 remains accessible inside the cluster on port 9000. HTTP, an existing
certificate, or cert-manager issuance covers only the enabled hosts.

The image and version share one field, defaulting to
`pgsty/silo:RELEASE.2026-10-26T00-00-00Z`. The Kubernetes cluster domain is an
internal DNS suffix; keep `cluster.local` on standard K3s.

Two-node installations stop accepting writes if either node goes offline.
Node count cannot be changed on an existing pool through this chart. Migrate
to another release for a topology change; PVCs are retained on uninstall.

TLS terminates at Ingress; internal traffic uses HTTP. Resource defaults suit
small installations and need tuning for production. No external database is required.
