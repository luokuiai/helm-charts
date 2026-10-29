# Deploying Warpgate

Select `warpgate` chart version `1.0.0` in Rancher Apps. It runs the official
`ghcr.io/warp-tech/warpgate:0.30.2` image, with one replica by default and external PostgreSQL.
New installations enable local session recording and create a retained `1Gi` PVC
for recordings, configuration and certificates. K3s supports its usual
`local-path` StorageClass and Traefik
Ingress controller. The release name is editable.

## Environment and persistence

Prepare a dedicated PostgreSQL database and user with permission to create and
alter tables in its schema; Warpgate runs migrations during initialization.
The chart creates no PostgreSQL server. You can use the repository's PostgreSQL
chart or an existing instance. Then create the installation namespace and a Secret using
[env-secret.example.yaml](env-secret.example.yaml) as a private template:

```bash
kubectl create namespace access
kubectl apply -f /path/to/private/warpgate-env.yaml
helm install warpgate charts/warpgate/1.0.0 --namespace access
```

All containers import `warpgate.envSecret`, default `warpgate-env`, through
`envFrom`. Required keys are explicitly referenced, so missing keys stop startup:

| Key | Purpose |
| --- | --- |
| `WARPGATE_DATABASE_URL` | Required external PostgreSQL connection URL, e.g. `postgresql://warpgate:URL_ENCODED_CREDENTIAL@postgres.database.svc.cluster.local:5432/warpgate?sslmode=require`. |
| `WARPGATE_ADMIN_PASSWORD` | Initial administrator credential. Does not reset an existing user. |
| `WARPGATE_OIDC_CLIENT_SECRET` | Required only with OIDC enabled. Raw, single-line provider Client Secret. |
| `AWS_ACCESS_KEY_ID` | Required with chart-managed S3 recording storage. Dedicated S3 access identity. |
| `AWS_SECRET_ACCESS_KEY` | Required with chart-managed S3 recording storage. Secret key for that identity. |
| `WARPGATE_ENCRYPTION_KEY` | Required in HA; optional for one node. Generate once using `openssl rand -base64 32`, use the same key on every replica, keep it stable and include it in backups. |

The chart uses Warpgate's native `internal-install-files` and
`unattended-setup --if-config-exists=bootstrap` commands. No shell is needed.
Enabling S3 adds a PostgreSQL client init container to apply its
database-backed settings, described below. Database URL and OIDC Client Secret substitution use literal YAML scalars
to preserve quotes, backslashes, colons, dollar signs and other single-line
characters. Do not supply multiline values. Percent-encode reserved characters
in the URL's username and credential. Set `sslmode` for the database endpoint:
use TLS when available (`require` encrypts transport; `verify-full` also validates
the server's trusted certificate and hostname); use `disable` only for a trusted
non-TLS connection. Secrets are written only into `/data/warpgate.yaml` on the
local volume, with restricted file permissions, and stay out of rendered ConfigMaps.

PostgreSQL stores users, targets, credentials, SSH keys and settings. The PVC
stores configuration, backend certificate files and local recordings. New volumes use
`local-path` by default, or the selected StorageClass. An existing PVC must be
writable by UID/GID `1000`. The Deployment uses one replica and `Recreate` because
recordings use local storage. The PVC is kept on uninstall; changing its name
does not migrate files. Changing the database URL selects another database and
does not migrate existing accounts or settings.

Normal Pod restarts reuse this PVC and retain recording files. Backend TLS is
generated on the first installation and retained in its Kubernetes Secret;
restarting a Pod copies the same certificate/key rather than generating new ones.
Native setup leaves an initialized database, administrator and SSH keys intact.

Session recording is enabled on a newly initialized database. Normal gateway
access and OIDC do not require it. For SSH, recording stores timed terminal
input/output events as NDJSON rather than MP4; database traffic recordings use
packet-capture data. The form has two independent groups:

- **Persistence** configures the local data volume for configuration,
  certificates, local recordings and active S3 upload buffers. These settings
  remain available when recording is disabled.
- **Session recording** contains the recording switch and **Use S3 instead of
  local recording storage**. Leave S3 disabled for local recordings; enabling
  it shows the S3 settings.

The default local recording configuration is:

```yaml
warpgate:
  recordSessions: true
persistence:
  enabled: true
  size: 1Gi
```

To install without recording, set `warpgate.recordSessions: false` and keep
`persistence.enabled: true` to retain configuration and certificates. To also
omit the PVC, explicitly set `persistence.enabled: false`. Recording settings subsequently live in
Warpgate's database; manage them in the admin UI. Setting
`warpgate.recordSessions: false` does not disable recording in
an already initialized database. If upgrading such an installation without a
PVC, disable recording in the admin UI first and preserve any old recording files.
Recordings can exhaust a small volume; choose a suitable initial size and resize
existing claims using the StorageClass's supported procedure. Back up the full
PostgreSQL database and data volume consistently, together with the environment
Secret and encryption keys. HA has additional shared-storage requirements below.

After updating environment variables, restart the Deployment:

```bash
kubectl -n access rollout restart deployment/warpgate
```

The ConfigMap owns the generated Warpgate configuration. Each Pod start copies
it onto the data volume, so make file configuration changes through chart values.
Targets, users and roles managed in the database are retained. With S3 enabled,
the chart reapplies its recording storage settings at startup as described below.

## HA deployment

Enable **HA deployment** and enter a positive **Warpgate replicas** count.
The default HA count is `2`; setting `1` retains the HA StatefulSet and its PVCs
for maintenance but provides no redundancy. With HA disabled, the original
single-replica Deployment and data PVC are unchanged.

Use [ha-values.example.yaml](ha-values.example.yaml) for shared file recordings:

```yaml
ha:
  enabled: true
  replicas: 2
  sharedRecordingsClaim: warpgate-recordings
persistence:
  enabled: true
  storageClass: local-path
  size: 1Gi
```

Create the shared recordings claim first in the installation namespace, using
storage supporting `ReadWriteMany`, such as NFS. Its root is mounted at
`/data/recordings` on every Pod and must be writable by UID/GID `1000`.
K3s `local-path` is node-local and cannot provide this shared filesystem.
For an existing database, verify **Config > Global parameters > Session recordings**
uses the Disk backend with path `/data/recordings`; chart values do not reset an
existing database's local recording path or recording switch. The shared claim
is required without chart-managed S3 even when `warpgate.recordSessions` is false,
because the initial setup switch does not disable recording in an existing DB.
The chart checks a claim's RWX access mode when Helm can read it from the cluster;
offline rendering cannot validate an existing claim's access modes.

Alternatively enable `recordings.s3.enabled` and set the same S3 bucket, endpoint
and prefix for all replicas. Then `ha.sharedRecordingsClaim` is unused. S3 keeps
the existing private-bucket / presigned-playback behavior described below;
enabling HA does not proxy S3 playback through Warpgate.

All replicas use the same external PostgreSQL and environment Secret. Add one
stable `WARPGATE_ENCRYPTION_KEY` to that Secret before enabling HA. Never replace
an existing key merely to enable HA. PostgreSQL deployment and PostgreSQL HA are
outside this chart's scope.

HA uses a StatefulSet with OrderedReady startup: Pod 0 completes native setup and
becomes ready before Pod 1 starts. Upstream PostgreSQL migration locking also
protects concurrent migration attempts. Each Pod gets its own retained `data`
PVC (`data-<release>-0`, `data-<release>-1`, ...), containing configuration,
backend TLS files and S3 upload buffers. `persistence.existingClaim` is single-node
only; `persistence.enabled` must remain true in HA. Scaling down or deleting the
StatefulSet retains these claims. Resize existing claims separately; changing a
StatefulSet's volume claim template requires a planned StatefulSet recreation.
The backend TLS Secret remains shared and retained; restarts do not regenerate it.

Required Pod anti-affinity places each replica on a different Kubernetes node;
the chosen node selectors and tolerations must allow enough nodes. Fewer eligible
nodes leave extra replicas Pending. `local-path` works for each Pod's private PVC,
but a failed node's local volume cannot move to another node. Other replicas
continue serving; use movable persistent storage if that Pod must also recover
automatically on another node. Shared recordings storage is itself a dependency
and must stay available for recording access.

The main container gets `POD_IP` through the Downward API. Peers advertise that IP
and must reach one another directly on HTTPS port `8888`; permit this in any
existing NetworkPolicies. Every Pod must also reach the target SSH servers.
If the environment Secret sets an outbound HTTP(S) proxy, include
`warpgate-cluster.internal` in both `NO_PROXY` and `no_proxy`, alongside your
existing exclusions; upstream uses this TLS SNI name with direct Pod-IP resolution.
HA adds a headless peer Service and a PodDisruptionBudget allowing one planned
eviction at a time when there are at least two replicas. StatefulSet updates
replace Pods one at a time; replacing a Pod still ends its active connections.

For native SSH, use a stable VPN-reachable TCP load balancer in front of the
Service: either a functioning `LoadBalancer` implementation or an existing TCP
load balancer forwarding to multiple K3s NodePorts. A single node's IP remains a
single point of failure even when Warpgate has multiple replicas. The chart does
not install a load balancer or provision a VPN address. HTTP Ingress continues
to serve the website; it does not expose raw SSH. If a Warpgate instance fails,
its established SSH connections end; reconnect through the same entry point.

After changing the shared environment Secret or backend TLS Secret, restart HA:

```bash
kubectl -n access rollout restart statefulset/warpgate
```

### Switching an existing installation between single-node and HA

Changing `ha.enabled` changes the workload kind and data PVC layout. Plan a
maintenance window; the chart does not copy files or migrate storage automatically.

1. Back up PostgreSQL, existing data/recording volumes and the environment / TLS
   Secrets. Keep the same database URL, encryption key and retained backend TLS
   Secret. Prepare the shared RWX claim or S3 bucket and ensure the database's
   selected recording backend/path matches the destination.
2. Stop the current workload and wait for all its Pods to terminate:

   ```bash
   kubectl -n access scale deployment/warpgate --replicas=0
   kubectl -n access wait --for=delete pod -l app.kubernetes.io/instance=warpgate,app.kubernetes.io/name=warpgate --timeout=120s
   ```

3. For file recordings, copy the **contents** of the old data PVC's `recordings/`
   directory to the **root** of the shared recordings claim, preserving paths and
   UID/GID `1000` access. Use a temporary copy Pod appropriate to your storage;
   a node-local source PVC requires that Pod on its original node. Do not copy
   only database rows: recording files must also exist at the new location.
   For S3, keep the same bucket/prefix, or migrate existing objects separately.
4. Upgrade with `ha.enabled=true` and the desired HA values. On a cluster-connected
   upgrade, the chart refuses a mode switch while the previous workload has
   nonzero desired or reported replicas. With offline GitOps, stop the previous
   workload and apply the mode change as separate operations; live lookup cannot
   protect it.
5. Verify administrator login, unchanged SSH host keys, target access and playback
   of an old recording before ending maintenance. Keep the original PVC for
   rollback until migration is verified.

To return to the single-node Deployment, first scale the **StatefulSet** to `0`,
wait for its Pods to terminate, and copy any new file recordings back into the
original single-node PVC's `recordings/` directory before disabling `ha.enabled`.
If retaining S3, keep its chart settings enabled in both modes. Normal changes to
`ha.replicas` do not change the workload kind and retain per-Pod PVCs.

## S3 / Silo recording storage without a PVC

Use [s3-values.example.yaml](s3-values.example.yaml) and add S3 credentials to
the same environment Secret. Create the recordings bucket and a dedicated access
identity first. Scope its read, write, delete and multipart-upload permissions
to the chosen bucket / prefix. The chart does not change bucket policies or create buckets.

```yaml
warpgate:
  recordSessions: true
recordings:
  s3:
    enabled: true
    bucket: warpgate-recordings
    endpoint: https://s3.example.com
    region: us-east-1
    prefix: warpgate
    pathStyle: true
persistence:
  enabled: false
  size: 1Gi
```

For AWS, leave `endpoint` empty and normally disable `pathStyle`. For Silo /
MinIO, use the S3 API endpoint with `pathStyle: true`. Completed recordings live
in S3. Configuration, certificates and in-progress upload buffers use `/data`
in an `emptyDir` when persistence is disabled; there is no PVC in this mode.
Deleting a Pod loses these buffers, which can affect unfinished recordings.
The size limit must accommodate active recording buffers. Keeping persistence
enabled retains a local volume for those files.

Warpgate 0.30.2 stores S3 settings in PostgreSQL, not the YAML config file.
After native setup, an init container using `recordings.s3.setupImage` (default
`postgres:18.6-alpine`) applies the chart's S3 settings to that row. It runs `psql`
directly and uses safely quoted variables, without a shell or background sidecar.
Only recording storage is changed; administrator identity and other settings
are preserved. Credentials use the AWS environment chain and are not written
into that JSON, Helm values or ConfigMaps. This version-specific SQL must be
revalidated when changing the Warpgate application version.

With S3 enabled, chart values overwrite storage changes made in the admin UI
at each Pod initialization. Changing the bucket or prefix affects existing
playback: move existing objects to the corresponding paths first. Disabling
the chart's S3 option stops managing the stored setting; it does not change
the database back to local disk. To return to disk storage, enable persistence,
select local storage in Warpgate's admin settings, and copy recordings as needed.

Playback follows a temporary, signed GET URL directly from the browser to S3.
The endpoint must be reachable by both Warpgate and that browser; it can be
on a private network or VPN and does not need a public internet address.
A cluster-only Service DNS name cannot be used by an external browser.
For HTTPS Warpgate pages, use an HTTPS endpoint to avoid mixed-content blocking.
Allow the Warpgate page origin in the bucket's CORS policy, with GET / HEAD and
the Range request header; expose range-related response headers such as
Content-Range, Accept-Ranges and Content-Length. The bucket remains private.
The signed URL grants access to its object until expiry, so treat it as a
temporary credential. This upstream playback path does not proxy S3 through Warpgate.

## Hostname and HTTPS

Enable Ingress, enter a hostname, select the Ingress Class and the matching
controller type (`traefik` for a typical K3s installation). Point the hostname's
DNS at the controller separately. Public HTTPS can use an existing TLS Secret
or an already installed cert-manager Issuer / ClusterIssuer.

```yaml
ingress:
  enabled: true
  controller: traefik
  className: traefik
  hostname: access.example.com
  certificate:
    mode: cert-manager
    secretName: warpgate-tls
    issuerKind: ClusterIssuer
    issuerName: letsencrypt
```

Warpgate's backend on port `8888` is always HTTPS. The chart generates a separate
self-signed backend certificate, copies it into the data volume, and configures
the controller to trust it using the Service DNS name. Traefik requires the
`traefik.io/v1alpha1` ServersTransport CRD and its Kubernetes CRD provider.
The chart also supports the NGINX Ingress controller with HTTPS backend and
certificate-verification annotations. This does not install an Ingress controller
or cert-manager, and no cluster-wide verification bypass is required.

The backend TLS Secret is retained and reused by a cluster-connected Helm upgrade.
Plain `helm template` cannot read the installed Secret and generates a fresh one.
For GitOps or repeated offline rendering, provide `warpgate.backendTLSSecret`
instead: its keys must be `tls.crt`, `tls.key` and `ca.crt`, with a certificate SAN
containing `<release>.<namespace>.svc`. Restart the workload after changing an
external backend TLS Secret. The public Ingress certificate is separate.

Without Ingress, access the native HTTPS endpoint through a tunnel:

```bash
kubectl -n access port-forward svc/warpgate 8888:8888
```

Open `https://localhost:8888/@warpgate` and accept the self-signed certificate
for this local test. The initial administrator is `admin`. For a separate HTTPS
proxy or direct Service access with OIDC, set `warpgate.externalHost` to the bare
public hostname and `warpgate.externalPort` to its public HTTPS port. With Ingress,
these default to its hostname and port `443`; direct access defaults to `8888`.

## OIDC, including Casdoor

Use [oidc-values.example.yaml](oidc-values.example.yaml) as a starting point.
The provider is installed directly in Warpgate's configuration; no manual
provider creation in the Warpgate backend is required.

1. Register an OAuth / OIDC application in Casdoor or another OIDC provider,
   supporting the Authorization Code flow and PKCE with `S256`.
2. Read its discovery document and copy the exact `issuer` to **OIDC Issuer URL**.
   For a usual Casdoor installation this is `https://auth.example.com`.
   Warpgate must reach the discovery, token and JWKS endpoints; the browser must
   reach the provider's authorization endpoint.
3. Enter the application's Client ID in **OIDC Client ID** and put its Client
   Secret into `WARPGATE_OIDC_CLIENT_SECRET` in `warpgate-env`.
4. Enable OIDC and register the exact redirect URI at the provider:

   ```text
   https://access.example.com/@warpgate/api/sso/return
   ```

   Include a nonstandard external port when configured. The callback is shared
   by providers and does not contain the `oidc.name` value. The sign-in button
   appears at `https://access.example.com/@warpgate`.
5. Keep **Automatically create OIDC users** disabled to bind each existing
   user's SSO credential to the provider name and email first. Enable it to
   create users after successful authentication. Warpgate requires an email
   claim and rejects an explicitly unverified email, so configure the provider
   to supply it. Default scopes are `openid`, `email` and `profile`.
6. Grant access to targets with Warpgate roles. Account creation alone does not
   grant administrator or target access; normal default-role grants still apply.

Install after preparing the Secret and your values file:

```bash
helm install warpgate charts/warpgate/1.0.0 \
  --namespace access \
  --values /path/to/private/warpgate-values.yaml
```

`oidc.name` is the stable provider identifier used in SSO credential bindings;
`oidc.label` is the login button text. Keep the name stable after users bind it.
The public hostname must match the hostname users actually open. For advanced
group mapping, use the claim your provider actually emits:

```yaml
oidc:
  rolesClaim: groups
  roleMappings:
    operators: [servers, databases]
    developers: [development]
```

Grant those Warpgate roles access to the intended targets. When `rolesClaim` is
empty, upstream uses `warpgate_roles`; optional mappings translate its values.
This chart leaves administrator role mappings empty: manage administrator
permissions explicitly in Warpgate. Group claims must be supplied by the IdP;
setting the claim name in the chart does not create them.

## Native SSH and database protocols

The default Service is internal (`ClusterIP`). These listener switches and
ports are configurable in the form:

| Listener | Default port | Exposure |
| --- | --- | --- |
| HTTPS UI / HTTP gateway | 8888 | HTTPS Ingress or Service |
| SSH gateway | 2222 | TCP Service |
| MySQL gateway | 33306 | TCP Service |
| PostgreSQL gateway | 55432 | TCP Service |

The PostgreSQL gateway listener is independent of Warpgate's own application
database configured by `WARPGATE_DATABASE_URL`. Disabling the gateway does not
disable the application's connection to PostgreSQL.

HTTP Ingress does not expose SSH or database protocols. Use a private network,
TCP proxy, NodePort or LoadBalancer Service. For example:

```yaml
service:
  type: NodePort
  httpsNodePort: 30888
protocols:
  ssh:
    enabled: true
    nodePort: 30222
  mysql:
    enabled: false
  postgres:
    enabled: false
```

NodePort `0` requests an automatically assigned port. Values must fit the
cluster's configured NodePort range. For direct HTTPS NodePort access with
OIDC, set `warpgate.externalPort` to that externally visible port. With a normal
Ingress hostname, leave it at `0` to use `443`.

## Validation

The focused tests cover rendering, forms, environment Secret references, TLS
trust settings, protocol exposure and invalid configuration. The optional native
test uses the official binary, a disposable `postgres:16-alpine` Docker container
and a local OIDC discovery service to verify configuration parsing, literal
database URL / Client Secret substitution, PostgreSQL migrations and first initialization,
repeated setup preserving the admin identity, TLS hostname verification, health
checks and the generated authorization URL / callback with PKCE. It also applies
the rendered S3 SQL with an unprivileged PostgreSQL client, checks punctuation
handling and confirms reapplication is idempotent. Restart checks compare the
configuration, certificate/key and an existing recording file byte-for-byte.
This does not exercise actual
S3 uploads / browser playback, a Casdoor account, token exchange, Kubernetes
storage or a live Ingress controller.
