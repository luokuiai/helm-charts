# Casdoor

Casdoor v4.24.0 with a Rancher configuration form and an external PostgreSQL
or MySQL database. Follows this repository's versioned chart layout and
Ingress / certificate form conventions.

The form supports:

- Database host, port, username, password, database name, and PostgreSQL TLS mode.
- An existing Secret containing a `dataSourceName` connection string.
- Ingress hostname, Ingress Class, an existing TLS Secret, or cert-manager.
- A public origin override, default storage provider, image, and CPU / memory.

The chart installs one Casdoor replica by default. It installs no database,
creates no file PVC, and does not create S3 buckets or storage providers.
Configure S3 or S3-compatible storage in Casdoor and associate the provider
with the applications that upload files. Until this is configured, local
uploads are not persistent across Pod replacement.

Database credentials entered in the form are written to a Kubernetes Secret;
Helm values also retain them. Use an existing Secret to keep the connection
string out of Helm values. Existing database and object storage data remain
outside this release's lifecycle.

See the [deployment guide](../../../docs/casdoor/deployment.md) and
[database Secret example](../../../docs/casdoor/database-secret.example.yaml).
See [UPSTREAM.md](UPSTREAM.md) for provenance and
[README.upstream.md](README.upstream.md) for retained advanced settings.

Validation (dummy credentials only):

```bash
helm lint charts/casdoor/1.0.0 --strict \
  --set database.host=db.example.com \
  --set database.user=casdoor --set database.password=lint-only
uv run --with pyyaml python tests/casdoor/test_chart.py
```
