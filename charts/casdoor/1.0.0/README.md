# Casdoor

Casdoor v4.24.0 with a Rancher configuration form and an external PostgreSQL
or MySQL database. Follows this repository's versioned chart layout and
Ingress / certificate form conventions.

The form supports:

- One complete image field, default `casbin/casdoor:v4.24.0`.
- An environment Secret (default `casdoor-env`) with `dataSourceName` and
  other Casdoor variables, such as `initAdminPassword`.
- External database type and database name.
- Ingress hostname, Ingress Class, an existing TLS Secret, or cert-manager.
- Optional Caddy file proxy with its own hostname, sharing the environment Secret.
- A public origin override, default storage provider, and CPU / memory.

The chart installs one Casdoor replica by default. It installs no database,
creates no file PVC, and does not create S3 buckets. Create storage providers
in the Casdoor admin console, then associate them with applications.
Until object storage is configured, local uploads are not persistent across Pod replacement.

Environment Secret entries become environment variables. `dataSourceName` is a
required key reference; the database must already exist. Restart the Deployment
after updating the environment Secret. Optional overrides include `origin`,
`forceLanguage`, and `defaultStorageProvider`. Configure S3 credentials in the
admin console's storage provider; its settings are retained in the database. With the file
proxy enabled, add `S3_ENDPOINT` and `S3_BUCKET` there, enable Ingress and enter a
separate file hostname. The proxy allows only anonymous GET/HEAD object reads
from that bucket; keep Silo internal and grant anonymous `s3:GetObject` only on
the dedicated upload bucket. Existing TLS certificates must cover both hostnames.

For legacy database values, set `casdoor.envSecret: ""`; existing generated and
external database Secrets remain supported. Explicit full image tags and digests
win over legacy `image.name` / `image.tag` values.

See the [deployment guide](../../../docs/casdoor/deployment.md),
[environment Secret example](../../../docs/casdoor/env-secret.example.yaml).
See [UPSTREAM.md](UPSTREAM.md) for provenance and
[README.upstream.md](README.upstream.md) for retained advanced settings.

Validation:

```bash
helm lint charts/casdoor/1.0.0 --strict
uv run --with pyyaml python tests/casdoor/test_chart.py
CADDY_BIN=/path/to/caddy uv run --with pyyaml python tests/casdoor/test_storage_proxy.py
```
