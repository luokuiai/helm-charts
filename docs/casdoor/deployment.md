# Deploying Casdoor from Rancher

Add this Git repository to Rancher Apps and select `casdoor` version `1.0.1`.
The chart is based on the official Casdoor v4.25.0 release. It deploys one
Casdoor Pod by default and can use the existing Traefik Ingress on K3s.

## External database

Prepare an existing PostgreSQL or MySQL server and a dedicated database.
Grant the application user access to that database and permission to create
and migrate tables. Check network policies and database firewall rules so
the Casdoor Pod can reach the database. This chart does not create a database
server or manage its backups, upgrades, or data lifecycle.

The **Casdoor image** field is one full reference, defaulting to
`casbin/casdoor:v4.25.0`. Enter a complete mirror reference or digest when needed.
The former `image.repository` / `image.name` / `image.tag` layout remains supported
in YAML when the repository is untagged; an explicit tag or digest takes precedence.

In **Environment variables**, select **Casdoor environment Secret**
(default `casdoor-env`). It must exist in the
installation namespace and contain the case-sensitive key `dataSourceName`.
All its entries become environment variables. Configure the database type with
`driverName` (`postgres` or `mysql`) and its name with `dbName` in this Secret.
Without these entries, the chart defaults to PostgreSQL and database `casdoor`.
Casdoor reads environment values before its configuration file, so entries such
as `driverName`, `dbName`, or `origin` override the app.conf defaults.

For PostgreSQL, `dataSourceName` can be a PostgreSQL URL with percent-encoded
credentials or a lib/pq connection string. Match its database to the Secret's
database name. For MySQL, use `user:password@tcp(host:3306)/`, ending with `/`;
Casdoor appends the database name. Configure TLS in the connection string.
Use Service DNS or a database IP, not `localhost`. The chart disables Casdoor's
Docker-specific localhost rewriting. Mount trusted CAs through `extraVolumes`
and `extraVolumeMounts` if the database connection requires them.

Use [env-secret.example.yaml](env-secret.example.yaml) as a private template.
It also demonstrates `initAdminPassword`, which only sets the password when
Casdoor creates its initial administrator; it does not reset an existing user.
Do not commit real credentials. An example installation is:

```bash
kubectl create namespace identity
kubectl apply -f /path/to/private/casdoor-env.yaml
helm install casdoor charts/casdoor/1.0.1 \
  --namespace identity \
  --set casdoor.envSecret=casdoor-env
```

A missing `dataSourceName` key prevents container startup. After changing this
Secret, restart with `kubectl -n identity rollout restart deployment/casdoor`.
Advanced `envFrom` sources remain supported; `casdoor.envSecret` is imported
last and wins over duplicate keys in those sources. Explicit `envFromSecret`
and `envFromConfigmap` entries still take precedence over `envFrom` entries.
The chart supplies `RUNNING_IN_DOCKER=false` and the required database reference.

To retain an existing installation's legacy database settings, set
`casdoor.envSecret: ""`. Legacy form-generated credentials and
`database.useExistingSecret` / `database.existingSecret` still work through YAML;
[database-secret.example.yaml](database-secret.example.yaml) shows the legacy
Secret format. Before switching, create `casdoor-env` with the same connection
string. A nonempty `casdoor.envSecret` takes precedence over the legacy Secret.
The YAML settings `database.driver` / `database.databaseName` remain app.conf
fallbacks for existing installations; they are no longer separate form fields.

## Domain and HTTPS

Enable Ingress, enter a hostname such as `sso.example.com`, and choose the
Ingress Class (`traefik` on a standard K3s installation). Point DNS at the
Ingress controller's external address separately.

Choose HTTPS mode `existing` for a TLS Secret in the installation namespace,
or `cert-manager` for an existing Issuer / ClusterIssuer. cert-manager must
already be installed; an Issuer must be in the same namespace. The chart
does not install an Ingress controller, cert-manager, or certificate issuers.

Example values to combine with the existing database Secret settings:

```yaml
ingress:
  enabled: true
  className: traefik
  hosts:
    - host: sso.example.com
      paths:
        - path: /
          pathType: Prefix
  certificate:
    mode: existing
    secretName: casdoor-tls
```

TLS terminates at the Ingress and its connection to Casdoor uses HTTP.
The chart derives `origin` as `http(s)://hostname` from the first Ingress
hostname and TLS mode. Use the public-origin override when TLS terminates
at another proxy or the controller redirects all HTTP traffic to HTTPS.
Keep the public origin and application redirect URIs consistent.

`origin`, `forceLanguage`, and `defaultStorageProvider` can also be entries in the environment Secret.
For example, add these fields to `stringData` in the existing `casdoor-env` Secret,
keeping its required `dataSourceName` and other entries:

```yaml
origin: https://auth.example.com
forceLanguage: "zh"
defaultStorageProvider: storage-silo
```

`origin` overrides the form's public origin, including an automatically derived
Ingress origin. `forceLanguage` is supplied through the Secret rather than a
separate form field; leave it unset for Casdoor's normal language selection.
`defaultStorageProvider` selects an existing admin-owned storage provider by
name for default avatars; create it in the admin console first. It does not
associate providers with applications automatically.
Environment variable names are case-sensitive. Restart the Deployment after
changing the environment Secret.

The environment Secret entries used by this chart are:

| Key | When to set it | Purpose |
|---|---|---|
| `dataSourceName` | Required | Complete external database connection string |
| `driverName` | When changing the default | `postgres` (default) or `mysql` |
| `dbName` | When changing the default | Database name; defaults to `casdoor`. Match the PostgreSQL connection string |
| `initAdminPassword` | Recommended on first installation | Password used only when creating the initial administrator |
| `origin` | Optional | Override the public Casdoor URL |
| `forceLanguage` | Optional | Set the interface language, such as `zh` |
| `defaultStorageProvider` | Optional | Name of an existing admin-owned default avatar provider |
| `S3_ENDPOINT` | Required with Caddy | Internal Silo / S3 API origin, including scheme and port |
| `S3_BUCKET` | Required with Caddy | Dedicated bucket served by the file proxy |

Database type, database name and the default avatar provider are configured
through the environment Secret rather than separate form fields.
Set S3 access keys in the Casdoor admin console's storage provider.

Ingress is disabled by default. To configure Casdoor before exposing it:

```bash
kubectl -n identity port-forward svc/casdoor 8000:8000
```

Open `http://localhost:8000`, secure the administrator account, then configure
the applications and storage provider before enabling public access.

## Local file uploads

Under **File storage**, choose `local` to persist uploaded files at `/files`.
Select an existing PVC in the installation namespace, or leave the selection
empty to create one. New PVCs default to `1Gi` and Storage Class `local-path`;
an empty Storage Class uses the cluster default. For example:

```yaml
storage:
  mode: local
persistence:
  existingClaim: ""
  storageClass: local-path
  size: 1Gi
```

Local mode requires `replicaCount: 1` and `autoscaling.enabled: false`. Updates
use Recreate so the old Pod releases its volume before its replacement starts.
The chart supplies `podSecurityContext.fsGroup: 1000` unless explicitly overridden;
existing volumes must be writable by Casdoor. The K3s `local-path` provisioner
keeps files on the assigned node, so back up the volume separately from PostgreSQL.

Configure the matching Local File System provider in Casdoor and associate it
with the applications that upload files. Follow the official
[Local File System provider guide](https://casdoor.ai/docs/provider/storage/localFileSystem/).
Local file URLs use Casdoor's domain; no Caddy proxy or separate file domain is needed.

The chart retains its PVC on uninstall or a switch to S3. To reuse a retained
claim, enter its name in `persistence.existingClaim`. Resize existing PVCs
separately. Changing storage mode does not copy files, rewrite URLs or update
provider settings in the database. Back up or migrate files before switching
away from local storage. Local mode ignores any retained S3 proxy form values.

## S3 / S3-compatible uploads

Casdoor can store uploaded resources such as avatars in object storage.
Select `s3` under **File storage** (the default). This mode creates no file PVC.
External database persistence does not persist local uploaded files; use local
mode above when uploading to the local filesystem.

In Casdoor's **Providers** page, create a provider in the **Storage** category:

1. Select AWS S3 for AWS, or the appropriate MinIO / S3-compatible provider
   for your object storage service.
2. Enter the bucket, region, credentials, and endpoint / public resource URL
   required by that provider. Use a bucket and credentials created separately
   with permissions appropriate to the uploaded objects.
3. Associate the provider with the applications that upload files. Check that
   browser clients can access the resource URLs returned by the provider.
4. If using Casdoor's `defaultStorageProvider` setting, enter the existing
   provider's matching name in the environment Secret. This selects
   a provider; it does not provision one or copy any S3 credentials.
5. Upload a test avatar and verify it is in the bucket. Verify that the URL
   continues to work after replacing the Casdoor Pod.

Provider configuration is retained in the external Casdoor database. The
database and object bucket must both be backed up appropriately. Configure
object storage before uploading files that must survive Pod replacement;
existing local files are not automatically migrated to S3.

### Silo storage and Caddy file proxy

In the Casdoor admin console, create a provider with these settings:

| Field | Example |
|---|---|
| Owner | `admin` |
| Name | `storage-silo` |
| Category | `Storage` |
| Type | `MinIO` |
| Client ID / Client secret | Scoped Silo access key / secret key |
| Region | `us-east-1` |
| Endpoint | `http://silo.storage.svc.cluster.local:9000` |
| Bucket | `casdoor` |
| Domain | `https://files.example.com` |
| Path prefix | `casdoor` |

The endpoint is Silo's internal API URL, using port `9000`, not the Console's
`9001`. Bucket and Path prefix both match the dedicated bucket name, so browser
URLs use `/casdoor/<object>` while the provider removes that prefix from the
stored object key. Domain matches the scheme and **File proxy hostname**.

In the [environment Secret example](env-secret.example.yaml), uncomment
`S3_ENDPOINT` and `S3_BUCKET` and match them to the provider's Endpoint and Bucket.
These two environment variables configure Caddy; they do not create or configure
Casdoor providers. Caddy needs no access keys. Enable the proxy and Ingress,
and point both DNS names at the Ingress controller:

```yaml
casdoor:
  envSecret: casdoor-env
storage:
  mode: s3
storageProxy:
  enabled: true
  hostname: files.example.com
ingress:
  enabled: true
  className: traefik
  hosts:
    - host: auth.example.com
      paths:
        - path: /
          pathType: Prefix
  certificate:
    mode: cert-manager
    issuerName: letsencrypt
```

Caddy runs in the same Pod as Casdoor, using the pinned image
`caddy:2.11.7-alpine`. The two containers share `casdoor.envSecret`. Casdoor's
domain routes to the application port; the separate file domain routes to Caddy
on port `8080`. No separate release or file PVC is needed. With Ingress disabled,
the chart exposes only the Service's `files` port; configure an external route
yourself, or port-forward that port for testing. Gateway API file routes are
not generated automatically.

The file domain shares the Ingress Class and HTTPS settings. cert-manager
requests a certificate covering both hostnames. In `existing` mode, supply a
certificate valid for both. For advanced `ingress.tls` lists, include the file
hostname in the matching TLS entry yourself. The proxy's domain is configured in
Ingress and in the provider's `domain`; it is not a separate Casdoor environment
setting. Restart the Deployment after changing environment variables.

Keep Silo API Ingress disabled. Caddy allows only GET/HEAD for
`/<S3_BUCKET>/<object>`, rejects other buckets, bucket listings and write requests,
and strips query parameters and S3 authorization headers. It needs no S3 keys.
Casdoor uses the scoped provider credentials for uploads over the internal API.

Create a dedicated bucket for these public resources and give anonymous users
only `s3:GetObject` on its objects. Other Silo buckets stay private. In the Silo
Console, open **Buckets → casdoor → Summary → Access Policy → Custom**, paste
this policy and save (do not choose the broader **Public** policy):

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"AWS": ["*"]},
    "Action": ["s3:GetObject"],
    "Resource": ["arn:aws:s3:::casdoor/*"]
  }]
}
```

The policy grants no bucket listing, upload, or delete permission. Files in this
dedicated bucket are readable without login through the proxy; keep private
documents in another bucket. Verify an avatar URL such as
`https://files.example.com/casdoor/<object>` and confirm a different bucket's
path returns 404. Browser reads still require this anonymous object-read policy;
the proxy does not sign requests to a private bucket.

Select `storage-silo` in the relevant applications' provider lists, preserving
their existing sign-in providers.
The optional `defaultStorageProvider` selects an `admin`-owned provider by its
name, such as `storage-silo`, for Casdoor's default avatar storage; it does not
replace application provider associations or create the provider.

Provider settings and credentials are stored in Casdoor's external database.
The chart no longer imports provider initialization files. Previously imported
providers remain in the database and can be maintained in the admin console.
Remove the unused initialization file from the environment Secret when upgrading.
Arbitrary `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` variables do not configure
a Casdoor storage provider; configure it in the admin console.

Official storage documentation:
https://casdoor.ai/docs/provider/storage/overview/
