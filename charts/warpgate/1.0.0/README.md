# Warpgate

Warpgate `0.30.2` with a Rancher form, OIDC login, domain / HTTPS configuration,
and local recording storage by default. New installations enable session recording
and create a retained `1Gi` PVC for configuration, certificates and recording files.
The image is one complete reference:
`ghcr.io/warp-tech/warpgate:0.30.2`. The release name is editable.

The chart defaults to one replica using external PostgreSQL. Native initialization
migrates the database and creates the administrator and SSH keys once;
subsequent starts preserve existing accounts.
The official image provides both native initialization commands. Enabling S3
adds a short-lived PostgreSQL client init container to set the database-backed
storage configuration. Local files and recording buffers are mounted at `/data`.

Select an existing environment Secret (default `warpgate-env`) with
`WARPGATE_DATABASE_URL` and `WARPGATE_ADMIN_PASSWORD`. Create a dedicated
PostgreSQL database and user before installation. With OIDC enabled, also provide the single-line
`WARPGATE_OIDC_CLIENT_SECRET`, then enter the Issuer URL and Client ID in the
form. Client secrets stay out of Helm values and ConfigMaps. Automatic OIDC
user creation is optional; users still need target access through Warpgate roles.

Local recordings use `warpgate.recordSessions: true` and `persistence.enabled: true`
by default. Disable `warpgate.recordSessions` to install without recordings;
keep the PVC enabled to retain configuration and certificates. For an
existing database, change recording settings in the Warpgate admin UI; the setup
flag does not overwrite an existing database's recording setting.

For S3 / Silo, also enable `recordings.s3.enabled`, fill the bucket and endpoint in the
form, and add `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` to the same Secret.
Disable `persistence.enabled` to use a temporary local buffer without a PVC.
Completed recordings stay in S3. The playback browser must reach the endpoint,
over the internet, a private network or a VPN. Bucket CORS must allow your Warpgate origin.

Ingress supports Traefik and NGINX, an existing public TLS certificate or
cert-manager. The HTTPS backend certificate is generated separately, retained
on upgrades, and verified by the controller. Traefik requires its CRDs.
Native SSH / MySQL / PostgreSQL listeners can be enabled independently and
exposed with ClusterIP, NodePort, or LoadBalancer Service settings.

See the [deployment guide](../../../docs/warpgate/deployment.md),
[environment Secret example](../../../docs/warpgate/env-secret.example.yaml),
and [Casdoor OIDC example](../../../docs/warpgate/oidc-values.example.yaml).
An [S3 without PVC example](../../../docs/warpgate/s3-values.example.yaml) is also included.
For HA, enable `ha.enabled`, set `ha.replicas` (default `2`), and add a stable
`WARPGATE_ENCRYPTION_KEY` to the same environment Secret. HA uses a StatefulSet
with independent retained data PVCs and one Pod per Kubernetes node. Recordings
require either an existing RWX `ha.sharedRecordingsClaim` mounted at
`/data/recordings`, or the same S3 bucket on all replicas. PostgreSQL remains
external. Use a stable TCP load balancer for native SSH; HTTP Ingress covers the
website separately. See the [HA example](../../../docs/warpgate/ha-values.example.yaml)
and the deployment guide before switching an existing installation: stop the old
workload and migrate recording files first. Data is not moved automatically.
Source and icon provenance are in [UPSTREAM.md](UPSTREAM.md).

```bash
helm lint charts/warpgate/1.0.0 --strict
uv run --with pyyaml python tests/warpgate/test_chart.py
# Include native bootstrap, TLS, OIDC, two-node peer login and failure checks:
WARPGATE_BIN=/path/to/warpgate uv run --with pyyaml python tests/warpgate/test_chart.py
# Requires Docker, ssh-keyscan and a cached postgres:16-alpine image.
```
