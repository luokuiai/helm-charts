# Upstream references

This is a local Rancher Chart for PGSTY Silo, not an official Silo Helm release.
The templates follow this repository's application charts; they are not a
vendored copy of the upstream Helm Chart.

- Project: https://github.com/pgsty/silo
- Server source: https://github.com/pgsty/silo/tree/RELEASE.2026-10-26T00-00-00Z
- Source commit: `c3ad836aed0d8a7d23c2e44a5eaa3009d08525e3`
- Image: `docker.io/pgsty/silo:RELEASE.2026-10-26T00-00-00Z`
- Verified published manifest: `sha256:7bb2aff6b89efe1cb1303c10fc21d579447434ed06649ac9ec05a5e2dbf30ad7`
- Image architectures verified: `linux/amd64`, `linux/arm64`.
- Official image build: `Dockerfile.goreleaser` in the pinned source.
- Official distributed examples: `docs/distributed/README.md` and `helm/silo/`.
- Erasure set sizes: `cmd/endpoint-ellipses.go` accepts 2 through 16 drives.
- Default parity: `internal/config/storageclass/storage-class.go`.
- Equal data/parity layouts require one additional write vote:
  `cmd/erasure-metadata.go`, `objectQuorumFromMeta`.
- Health endpoints: `cmd/healthcheck-router.go`, `cmd/healthcheck-handler.go`.
- Icon: https://github.com/pgsty/silo.pgsty.com/blob/main/static/favicon.png
- Bundled `LICENSE`: the server's AGPL-3.0 license, preserved from the pinned source.

Verified on 2026-10-28. The chart executes `/usr/bin/silo` directly with
`HOME=/tmp`. It preserves Silo's `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
`MINIO_BROWSER_REDIRECT_URL`, `/minio/health/*`, and `.minio.sys` interfaces.
It does not change the server's storage format or erasure-coding defaults.

The form combines repository and version into one full image reference.
Untagged references retain support for legacy `image.tag` and fall back to
`appVersion`; explicit tags and digests take precedence.

`ingress.apiEnabled` and `ingress.consoleEnabled` independently select the
domain routes. Both default to true to preserve earlier values when the main
Ingress switch is enabled. TLS contains only enabled hosts, and the Console
redirect is set only when its route is enabled. The embedded Console uses a
loopback API endpoint by default (`consoleMinIOServerEnv` in `cmd/common-main.go`),
so a Console route does not require exposing the S3 API route.

One PVC is attached to each distributed Pod. Distinct Kubernetes hostnames are
required by Pod anti-affinity. This creates separate node failure domains;
independence of the backing disks remains the storage administrator's responsibility.
Cluster-internal traffic is HTTP; optional TLS is terminated by Ingress.
