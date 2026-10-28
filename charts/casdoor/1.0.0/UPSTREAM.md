Based on the official chart source shipped with Casdoor **v4.24.0**:

https://github.com/casdoor/casdoor/tree/v4.24.0/manifests/casdoor

Upstream templates Git tree: `78911e280c2ae8efc30a4e14111533f119884511`.
The upstream source has `0.0.0` version placeholders filled by its release
workflow. This adaptation sets local chart version `1.0.0` and application
version `v4.24.0`. It is not an official Casdoor or Rancher release.

The old https://github.com/casdoor/casdoor-helm repository is deprecated in
favor of the above location. Original documentation is in `README.upstream.md`;
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
- No file PVC. Configure an S3 / MinIO provider in Casdoor or use the
  retained upstream `initData` integration for declarative configuration.

Icon: https://cdn.casdoor.com/static/favicon.png

- Image form unified as `casbin/casdoor:v4.24.0`; legacy name/tag values remain
  supported for untagged references.
- Default `casdoor.envSecret: casdoor-env` imports environment entries and requires
  `dataSourceName`. Clear it to retain legacy database credential settings.
- Form selectors for existing provider initialization Secrets, with a Silo example.

Verified against the official v4.24.0 source: `conf/conf.go` (environment priority),
`object/init.go` (initial admin password), `object/init_data.go` (provider import),
`object/avatar.go` (default provider name), `storage/minio_s3.go` and
`object/storage.go` (MinIO credentials, endpoints and resource URL paths).
GitHub's latest stable release was v4.24.0 when checked on 2026-10-28.

- Optional stock Caddy `2.11.7-alpine` container in the Casdoor Pod, using the
  same environment Secret and a separate Ingress hostname. It forwards only
  anonymous object GET/HEAD for `S3_BUCKET`, strips credentials and query
  parameters, and does not expose other buckets or the Silo administration API.
  The shared certificate includes both hostnames. Caddy v2.11.7 was verified
  against the official stable release published on 2026-10-03.
