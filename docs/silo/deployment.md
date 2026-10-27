# Silo deployment

This chart runs PGSTY Silo `RELEASE.2026-10-26T00-00-00Z`, an S3-compatible
MinIO fork, without an operator or external database. Requires Kubernetes
1.27+ and persistent storage. The official image supports amd64 and arm64.

## Rancher installation

Sync this Git repository, then select **Apps → Charts → Silo → 1.0.0**.

1. Enter **Number of storage nodes** directly. `1` starts standalone storage;
   any integer `2–16`, including 3 and 5, starts a distributed pool.
2. Enter a root user and random password, or select an existing credential
   Secret containing `rootUser` and `rootPassword` in the same namespace.
3. Select the storage class and raw capacity **per node**. Defaults are
   `local-path` and `10Gi`. An existing PVC is supported only for one node.
4. Optionally enable Ingress, enter separate S3 API and Console hostnames,
   and choose HTTP, an existing TLS Secret, or cert-manager.
5. Tune resources per node, then install. Defaults suit small installations,
   not a production sizing recommendation.

Distributed Pods have required anti-affinity on `kubernetes.io/hostname`.
A pool of N Pods needs at least N schedulable Kubernetes nodes with matching
storage capacity, selectors, and tolerations. For example, two Pods need two
nodes, while five Pods need five. A tainted control-plane node may need an
explicit toleration; set `nodeSelector` / `tolerations` in values if required.

The headless Service publishes unready addresses and Pods start in parallel,
so all peers can resolve and format their data together. Each Pod has a stable
address and its own ReadWriteOnce claim. The default DNS suffix is
`cluster.local`; change `clusterDomain` for clusters with custom DNS domains.

## Node count and availability

This chart uses one drive per node and one erasure set. Every integer from
1 through 16 is accepted; the form is an integer input, not an enum.

For healthy, fully written objects using the default standard storage class:

| Nodes / PVCs | Default layout | Read quorum | Write quorum | Raw / approximate usable capacity at 10Gi per PVC |
| --- | --- | --- | --- | --- |
| 1 | standalone | 1 | 1 | 10Gi / 10Gi |
| 2 | EC:1, 1 data + 1 parity | 1 | 2 | 20Gi / 10Gi |
| 3 | EC:1, 2 data + 1 parity | 2 | 2 | 30Gi / 20Gi |
| 4 | EC:2, 2 data + 2 parity | 2 | 3 | 40Gi / 20Gi |
| 5 | EC:2, 3 data + 2 parity | 3 | 3 | 50Gi / 30Gi |

Two-node storage is valid, but **both nodes must be online for writes**.
If one fails, intact existing objects may remain readable; some operations
still require more metadata or a write quorum. The chart does not promise a
read-only failover mode or uninterrupted Console operation during a failure.
The two-node PDB allows zero voluntary evictions to protect write availability.
Draining either node requires a planned outage and handling the PDB explicitly.

For larger pools the PDB permits one voluntary eviction. It does not prevent
hardware failure, direct Pod deletion, or StatefulSet updates. A two-node
rolling update therefore interrupts writes. Failure tolerance depends on the
actual parity of each object and available disks, not just the configured
number of Pods. Capacity above excludes filesystem overhead and metadata.

## Storage and data safety

Each claim defaults to `10Gi` on `local-path`. An empty `storageClass` uses the
cluster's default provisioner. Data is mounted at `/data`, including Silo's
`.minio.sys` state. Pods run as UID/GID `1000` with `fsGroup: 1000`; the storage
driver must make the mounted data writable.

Standalone claims are named `<release>-data`; distributed claims are named
`data-<release>-0`, `data-<release>-1`, and so on. Claims are retained on Helm
uninstall. Keep the release name, namespace, topology, and claims together
when restoring an existing deployment.

`local-path` ties a PVC to the Kubernetes node that owns its directory. PVC
retention does not protect against losing that node or disk. Use independent
backing disks for independent failure domains, plus separate backups. Multiple
PVCs on the same shared storage appliance do not create independent disks.
Provision actual local disks/PVs if physical disk isolation is required.

**Choose node count at installation. Do not scale a formatted pool using
`replicaCount`, `kubectl scale`, or an autoscaler.** An upgrade against a live
cluster rejects a changed replica count. Offline Helm rendering cannot check
an existing StatefulSet. This chart does not implement Silo's separate
multi-pool expansion workflow. To change topology, deploy a new release with
fresh claims, migrate objects and IAM using Silo-supported tools, validate the
new deployment, then switch clients. Do not attach a standalone volume to a
new distributed pool or swap one claim between distributed Pods.

Claim size and storage class in a StatefulSet's volume templates are immutable.
Plan capacity before installation. Editing `persistence.size` is not a resize
or a storage migration; expand existing PVCs through the storage provider's
supported procedure when available.

## Credentials and CLI installation

Use [root-secret.example.yaml](root-secret.example.yaml) as a local template.
Replace the placeholder before applying it; do not commit real credentials.

```bash
kubectl create namespace storage
kubectl apply -f /path/to/private/silo-root.yaml
helm upgrade --install silo charts/silo/1.0.0 --namespace storage \
  --set auth.useExistingSecret=true \
  --set auth.existingSecret=silo-root \
  --set replicaCount=3
```

For standalone installation set `replicaCount=1`; for two nodes set it to `2`.
All peers use the same Secret. When chart-managed credentials change, a checksum
rolls Pods. After updating an externally managed Secret, restart the StatefulSet
manually with `kubectl -n storage rollout restart statefulset/silo`.
Account for two-node write downtime. Chart-managed password values are stored
in Helm release records; an existing Secret keeps them out of values.

## Domains and HTTPS

```yaml
auth:
  useExistingSecret: true
  existingSecret: silo-root
replicaCount: 3
ingress:
  enabled: true
  className: traefik
  apiHost: s3.example.com
  consoleHost: silo.example.com
  certificate:
    mode: cert-manager
    secretName: silo-tls
    issuerKind: ClusterIssuer
    issuerName: letsencrypt
```

Point both DNS records at the Ingress controller. `apiHost` serves S3 on port
9000; `consoleHost` serves the Web Console on port 9001. Both paths are `/`.
The chart sets `MINIO_BROWSER_REDIRECT_URL` from the Console hostname and
certificate mode. S3 clients use the API endpoint, without a `/v1` suffix.

With `mode: existing`, provide a TLS Secret covering **both hostnames**.
With `mode: cert-manager`, install cert-manager and a ready `Issuer` or
`ClusterIssuer` first. One certificate covers both names. `disabled` uses HTTP.
TLS terminates at Ingress; peer and Service traffic remains HTTP inside the
cluster. The chart does not provision internal TLS.

S3 signatures depend on the request Host and path. Preserve both at the
proxy and avoid path rewrites. If the controller limits body size, request
duration, or WebSockets, configure it for the workload. For ingress-nginx,
`nginx.ingress.kubernetes.io/proxy-body-size: "0"` removes its upload size
limit; Traefik uses its own middleware and timeout settings. No controller
specific CRDs are required by this chart.

Without Ingress, use `kubectl -n storage port-forward svc/silo 9001:9001` for
the Console at `http://127.0.0.1:9001`. For cluster-local applications use
`http://silo.storage.svc.cluster.local:9000` as the S3 endpoint.

## First use and maintenance

Log in to the Console, create a bucket, and create a scoped application user
or access key. Use that key in Casdoor or other S3 clients. Select path-style
addressing when the client requires it; wildcard bucket DNS is not configured.
The official image includes `mcli` for administration.

Back up objects, IAM configuration, and any external encryption keys separately.
Read the Silo release notes before changing images and verify recovery before
production use. The chart validates rendered manifests; actual disk semantics,
cluster scheduling, upload traffic, recovery, and failover require cluster tests.
