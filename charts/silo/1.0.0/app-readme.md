# Silo

S3-compatible object storage from PGSTY, derived from MinIO, with the full
Web Console and a Rancher installation form.

Enter a node count from **1 to 16** directly: 1 is standalone; 2 or more use
distributed erasure coding. Each distributed Pod needs a distinct schedulable
Kubernetes node and its own data PVC. K3s `local-path` is the default storage
class, with **10Gi per node** before erasure-coding overhead.

Set a root password or select an existing Secret with `rootUser` and
`rootPassword`. Create scoped application credentials in Silo after installation.
The optional Ingress uses separate hostnames for S3 API and Console, with
HTTP, an existing certificate, or cert-manager issuance for both hosts.

Two-node installations stop accepting writes if either node goes offline.
Node count cannot be changed on an existing pool through this chart. Migrate
to another release for a topology change; PVCs are retained on uninstall.

TLS terminates at Ingress; internal traffic uses HTTP. Resource defaults suit
small installations and need tuning for production. No external database is required.
