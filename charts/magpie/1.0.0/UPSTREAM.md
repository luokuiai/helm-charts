# Upstream

Application: https://github.com/yetone/magpie

Release: https://github.com/yetone/magpie/releases/tag/v0.1.1734

Official Docker documentation: https://usemagpie.ai/docs/zh/docker

This is a locally maintained Helm Chart, version 1.0.0, for the official
headless Magpie container. It is not an upstream Magpie Helm release.
It reuses this repository's Rancher form, Secret, PVC, and certificate
conventions. Magpie itself is configured through its Web UI, with mutable
state retained under `/config`; the chart does not overwrite its settings.

Image: `ghcr.io/yetone/magpie:0.1.1734` (upstream image tags omit `v`).
At implementation time the registry manifest was verified as:

`sha256:2f51feb42d29a1ab12a6de3583bd966c81e2d3a3dcc8711f57e8cd5e1f547ed9`

Platforms: `linux/amd64`, `linux/arm64`.

Runtime details are taken from this release's `Dockerfile`,
`internal/cli/healthcheck_cli.go`, `internal/cli/web_cli.go`, and
`internal/gui/web.go`:

- Run `web --addr 0.0.0.0:3430 --no-open` with UID/GID 65532.
- Persist all `/config` directories, including sign-ins and plugin caches.
- Use the native `/magpie healthcheck` command.
- Read a stable `MAGPIE_WEB_KEY` from a Secret.
- Route Ingress to the Web port, which also serves the gateway's client API
  paths under the gateway's separate authentication.

Official application icon:
https://github.com/yetone/magpie/blob/v0.1.1734/internal/gui/assets/icons/icon-512.png

The upstream MIT license is included in `LICENSE`.
