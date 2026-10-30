Based on the official chart source shipped with Casdoor **v4.24.0**:

https://github.com/casdoor/casdoor/tree/v4.24.0/manifests/casdoor

Upstream templates Git tree: `78911e280c2ae8efc30a4e14111533f119884511`.
The upstream source has `0.0.0` version placeholders filled by its release
workflow. This adaptation sets local chart version `1.0.1` and application
version `v4.25.0`. It is not an official Casdoor or Rancher release.
The chart template base remains v4.24.0; the default application image is
`casbin/casdoor:v4.25.0`, released on 2026-10-30. Its Dockerfile retains UID 1000
and the `/` working directory, and its PostgreSQL driver remains lib/pq.

The old https://github.com/casdoor/casdoor-helm repository is deprecated in
favor of the above location. Upstream documentation is in `README.upstream.md`,
with the unsupported declarative initialization section removed;
the Apache-2.0 license is retained in `LICENSE`.

Local changes:

- Rancher metadata, bundled icon, questions, and values validation.
- External PostgreSQL / MySQL only; no bundled database or SQLite storage.
- Database connection strings are generated into a Secret or read from an
  existing Secret, and supplied through Casdoor's `dataSourceName` environment
  variable. ConfigMaps do not contain database credentials.
- PostgreSQL URL encoding preserves special characters in credentials.
- Disable Casdoor's Docker-specific localhost rewriting in Kubernetes.
- Production run mode, resource defaults, public origin selection, and
  the optional `defaultStorageProvider` setting.
- Existing TLS Secret / cert-manager certificate choices, following the
  Komodo chart in this repository.
- Correct the upstream optional full-config Secret to use `stringData`.
- Choose S3 / MinIO or local file storage. Local mode retains a PVC at `/files`.
  Configure the matching provider in the Casdoor admin console.
- Remove upstream declarative initialization values, Secrets, and file mounts.

Icon: https://cdn.casdoor.com/static/favicon.png

- Image form unified as `casbin/casdoor:v4.25.0`; legacy name/tag values remain
  supported for untagged references.
- Default `casdoor.envSecret: casdoor-env` imports environment entries and requires
  `dataSourceName`. Clear it to retain legacy database credential settings.
- The Environment variables form lists database, initial admin, origin, language,
  default avatar provider and Caddy variables. Set `driverName`, `dbName` and
  `defaultStorageProvider` in the environment Secret; their duplicate form fields
  are removed. YAML defaults remain compatible with existing installations.

Verified against the official v4.24.0 source: `conf/conf.go` (environment priority),
`object/init.go` (initial admin password),
`object/avatar.go` (default provider name), `storage/minio_s3.go` and
`object/storage.go` (MinIO credentials, endpoints and resource URL paths).
GitHub's latest stable release was v4.24.0 when checked on 2026-10-28.

- Optional stock Caddy `2.11.7-alpine` container in the Casdoor Pod, using the
  same environment Secret and a separate Ingress hostname. It forwards only
  anonymous object GET/HEAD for `S3_BUCKET`, strips credentials and query
  parameters, and does not expose other buckets or the Silo administration API.
  The shared certificate includes both hostnames. Caddy v2.11.7 was verified
  against the official stable release published on 2026-10-03.
- Retain `NET_BIND_SERVICE` in the proxy's capability bounding set because the
  official image applies `cap_net_bind_service=+ep` to `/usr/bin/caddy`. Dropping
  it makes exec fail with `Operation not permitted`, even on port 8080.
  Non-root execution, no privilege escalation and a read-only root filesystem
  remain enabled.
