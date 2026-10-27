# Deploying Casdoor from Rancher

Add this Git repository to Rancher Apps and select `casdoor` version `1.0.0`.
The chart is based on the official Casdoor v4.24.0 release. It deploys one
Casdoor Pod by default and can use the existing Traefik Ingress on K3s.

## External database

Prepare an existing PostgreSQL or MySQL server and a dedicated database.
Grant the application user access to that database and permission to create
and migrate tables. Check network policies and database firewall rules so
the Casdoor Pod can reach the database. This chart does not create a database
server or manage its backups, upgrades, or data lifecycle.

In **External database**, choose the driver and database name. Then choose:

- Form credentials: enter host, port, username, and password. Port `0` means
  `5432` for PostgreSQL or `3306` for MySQL. The chart generates a Secret
  containing the connection string. Passwords are also retained in Helm
  release values, so do not commit completed values files.
- Existing Secret: enable **Use an existing database connection Secret** and
  enter its name. It must be in the installation namespace with key
  `dataSourceName`. Driver and database name still apply; host, port,
  username, password, and the form's TLS mode are ignored in this mode.

For PostgreSQL, `dataSourceName` can be a PostgreSQL URL with percent-encoded
credentials or a lib/pq connection string. The database in the connection
string must match the database name in the form. For MySQL, use
`user:password@tcp(host:3306)/`, ending with `/`. Casdoor appends the database
name itself. The generated PostgreSQL connection string handles spaces,
quotes, and URL-special characters in credentials.

Use service DNS or a database IP, not `localhost`. The chart disables
Casdoor's Docker-specific localhost rewriting so Kubernetes DNS and
credentials are used as supplied. Database names use letters, digits,
and underscores and must begin with a letter or underscore.

For PostgreSQL over an untrusted network, use TLS. `require` enables
encryption; `verify-ca` / `verify-full` also require appropriate trusted CA
configuration. Supply a connection Secret and CA mounts using the retained
`extraVolumes` / `extraVolumeMounts` settings when custom certificate paths
are needed. The form's PostgreSQL TLS setting does not configure MySQL TLS.

See [database-secret.example.yaml](database-secret.example.yaml) for an
existing Secret example. After creating it, an example installation is:

```bash
helm install casdoor charts/casdoor/1.0.0 \
  --namespace identity --create-namespace \
  --set database.driver=postgres \
  --set database.databaseName=casdoor \
  --set database.useExistingSecret=true \
  --set database.existingSecret=casdoor-database
```

Changing a generated database Secret rolls the Casdoor Pod through its
checksum annotation. After updating an existing Secret, restart the
Deployment to load its new environment variables.

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

Ingress is disabled by default. To configure Casdoor before exposing it:

```bash
kubectl -n identity port-forward svc/casdoor 8000:8000
```

Open `http://localhost:8000`, secure the administrator account, then configure
the applications and storage provider before enabling public access.

## S3 / S3-compatible uploads

Casdoor can store uploaded resources such as avatars in object storage.
The chart does not create a file PVC. External database persistence does
not persist files uploaded through a local filesystem provider.

In Casdoor's **Providers** page, create a provider in the **Storage** category:

1. Select AWS S3 for AWS, or the appropriate MinIO / S3-compatible provider
   for your object storage service.
2. Enter the bucket, region, credentials, and endpoint / public resource URL
   required by that provider. Use a bucket and credentials created separately
   with permissions appropriate to the uploaded objects.
3. Associate the provider with the applications that upload files. Check that
   browser clients can access the resource URLs returned by the provider.
4. If using Casdoor's `defaultStorageProvider` setting, enter the existing
   provider's matching value in **Default storage provider**. This selects
   a provider; it does not provision one or copy any S3 credentials.
5. Upload a test avatar and verify it is in the bucket. Verify that the URL
   continues to work after replacing the Casdoor Pod.

Provider configuration is retained in the external Casdoor database. The
database and object bucket must both be backed up appropriately. Configure
object storage before uploading files that must survive Pod replacement;
existing local files are not automatically migrated to S3.

For automatic initialization, the upstream `initData` options remain available
through advanced values, including `initData.existingSecret` for declarative
provider and application configuration. S3 access keys are not separate Helm
form fields in this chart.

Official storage documentation:
https://casdoor.ai/docs/provider/storage/overview/
