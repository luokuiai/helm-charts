# Provenance

Application release: Warpgate **v0.30.2**, the official stable release published
on 2026-10-26 and checked on 2026-10-29.

- Source: https://github.com/warp-tech/warpgate/tree/v0.30.2
- Image: `ghcr.io/warp-tech/warpgate:0.30.2`, matching the official Helm values.
- Official Helm reference: `helm/warpgate` in that release.
- License: Apache-2.0, retained in `LICENSE`.
- Icon: `warpgate-web/public/assets/favicon.svg` from that release, rendered to
  the bundled `icon.png` without altering the upstream artwork.

This is a local chart, version **1.0.0**, following the existing repository's
Rancher forms, complete image references, environment Secrets, persistent
volumes and certificate choices. It is not an official Warpgate chart release.

Verified upstream behavior:

- `warpgate/src/commands/internal_install_files.rs` copies projected ConfigMap /
  Secret files, substitutes explicitly named environment variables and sets
  file permissions. The image is distroless; the chart uses native commands.
- `warpgate/src/commands/setup.rs` supports
  `unattended-setup --if-config-exists=bootstrap` without resetting an existing
  administrator. The data volume and the backend certificate are installed
  before setup, following upstream's initialization order.
- `warpgate-common/src/config/mod.rs` defines listeners, `external_host`,
  `http.external_port` and forwarding-header settings.
- `warpgate-core/src/db/mod.rs` connects using `database_url` and runs database
  migrations; the official image includes the PostgreSQL driver. The chart
  substitutes `WARPGATE_DATABASE_URL` from the existing environment Secret.
- `warpgate-sso/src/config.rs` defines custom OIDC providers, scopes, optional
  auto-created users and access-role mappings nested under `provider`.
- `warpgate-protocol-http/src/api/sso_provider_detail.rs` constructs the
  `/@warpgate/api/sso/return` callback using the external host and port.
- `warpgate/src/commands/healthcheck.rs` probes the native HTTPS API.
- `warpgate-aws/src/s3.rs` defines S3 storage, environment-based AWS credentials
  and presigned reads. `warpgate-core/src/recordings/storage.rs` buffers active
  recordings locally and streams multipart uploads to S3.
- `warpgate-db-entities/src/Parameters.rs` stores recording storage as JSON in
  `parameters.recordings_storage`. No native file-config field configures S3 in
  this release. An optional `psql` init container sets only that column, using
  quoted psql variables; credentials remain in the environment. This SQL is
  verified against the pinned application version and must be checked on upgrade.

The chart defaults to one Deployment replica. Optional HA uses an OrderedReady
StatefulSet, independent retained data PVCs, required host anti-affinity, a headless
peer Service and a disruption budget. `POD_IP` advertises each node's direct peer
address; `warpgate-core/src/cluster.rs` uses the HTTPS listener for peer traffic.
`warpgate-db-migrations/src/lib.rs` locks PostgreSQL migrations; native bootstrap
preserves existing users/keys. Ordered startup completes initial setup before
starting the next replica. HA requires a shared recordings PVC (RWX) or S3 and a
common `WARPGATE_ENCRYPTION_KEY` from the existing environment Secret. Changing
workload mode requires stopping the previous workload and migrating files first.
S3 supports temporary `emptyDir` buffers without a PVC in single-node mode only.
The chart does not bundle PostgreSQL or a TCP load balancer.
Administrator role mappings are empty; OIDC access-role mappings are optional.

Traefik's `ServersTransport.rootCAsSecrets` is used for compatibility with
existing K3s Traefik CRDs (supported, deprecated in favor of `rootCAs` in newer
Traefik releases). Both supported controllers verify the backend certificate
using `ca.crt` and the release's Service DNS name.
