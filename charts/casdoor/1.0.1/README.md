# Casdoor

Casdoor v4.25.0 with a Rancher configuration form and an external PostgreSQL
or MySQL database. Follows this repository's versioned chart layout and
Ingress / certificate form conventions.

The form supports:

- One complete image field, default `casbin/casdoor:v4.25.0`.
- An **Environment variables** menu selecting a Secret (default `casdoor-env`),
  with a short required-key hint and grouped help in the field's help icon for
  `dataSourceName`, `driverName`, `dbName`, `initAdminPassword`,
  `origin`, `forceLanguage`, `defaultStorageProvider`, `S3_ENDPOINT` and `S3_BUCKET`.
- Ingress hostname, Ingress Class, an existing TLS Secret, or cert-manager.
- A **File storage** choice: external S3 (default), or local uploads on a PVC at
  `/files`. Local mode supports a new 1Gi PVC or an existing claim.
- Optional Caddy file proxy in S3 mode, with its own hostname and the same environment Secret.
- A public origin override and CPU / memory.

The chart installs one Casdoor replica by default. It installs no database or
S3 buckets. S3 mode creates no file PVC. Create the matching storage provider
in the Casdoor admin console, then associate it with applications; the chart's
storage choice does not update providers or migrate existing files.

Select `storage.mode: local` to persist uploads at `/files`. Local mode requires
one replica with autoscaling disabled and uses Recreate updates. New PVCs use
`persistence.storageClass` (default `local-path`) and `persistence.size` (default
`1Gi`); an empty storage class uses the cluster default. Set
`persistence.existingClaim` to reuse a claim in the installation namespace.
The chart defaults `fsGroup` to 1000 in local mode unless explicitly overridden.
PVCs are retained on uninstall or a switch to S3. Resize and migrate files
separately; restore the retained claim using `persistence.existingClaim`.

Environment Secret entries become environment variables. `dataSourceName` is a
required key reference; the database must already exist. Restart the Deployment
after updating the environment Secret. Set `driverName` and `dbName` there
(defaults: `postgres` and `casdoor`). Optional overrides include `origin`,
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
helm lint charts/casdoor/1.0.1 --strict
uv run --with pyyaml python tests/casdoor/test_chart.py
CADDY_BIN=/path/to/caddy uv run --with pyyaml python tests/casdoor/test_storage_proxy.py
```
