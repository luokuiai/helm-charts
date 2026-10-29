# Deploying Warpgate

Select `warpgate` chart version `1.0.0` in Rancher Apps. It runs the official
`ghcr.io/warp-tech/warpgate:0.30.2` image, with one replica and external PostgreSQL.
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
| `WARPGATE_ENCRYPTION_KEY` | Optional upstream credential encryption key. Generate using `openssl rand -base64 32`, keep it stable and include it in backups. |

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
packet-capture data. The default local recording configuration is:

```yaml
warpgate:
  recordSessions: true
persistence:
  enabled: true
  size: 1Gi
```

To install without recording or a PVC, set both `warpgate.recordSessions` and
`persistence.enabled` to `false`. Recording settings subsequently live in
Warpgate's database; manage them in the admin UI. Setting
`warpgate.recordSessions: false` does not disable recording in
an already initialized database. If upgrading such an installation without a
PVC, disable recording in the admin UI first and preserve any old recording files.
Recordings can exhaust a small volume; choose a suitable initial size and resize
existing claims using the StorageClass's supported procedure. Back up the full
PostgreSQL database and data volume consistently, together with the environment
Secret and encryption keys. The chart does not support multiple replicas.

After updating environment variables, restart the Deployment:

```bash
kubectl -n access rollout restart deployment/warpgate
```

The ConfigMap owns the generated Warpgate configuration. Each Pod start copies
it onto the data volume, so make file configuration changes through chart values.
Targets, users and roles managed in the database are retained. With S3 enabled,
the chart reapplies its recording storage settings at startup as described below.

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
containing `<release>.<namespace>.svc`. Restart the Deployment after changing an
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
