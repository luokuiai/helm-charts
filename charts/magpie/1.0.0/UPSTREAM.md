# Upstream

Application: https://github.com/yetone/magpie

Release: https://github.com/yetone/magpie/releases/tag/v0.1.1836

Official Docker documentation: https://usemagpie.ai/docs/zh/docker

This is a locally maintained Helm Chart, version 1.0.0, for the official
headless Magpie container. It is not an upstream Magpie Helm release.
It reuses this repository's Rancher form, Secret, PVC, and certificate
conventions. Magpie itself is configured through its Web UI, with mutable
state retained under `/config`; the chart does not overwrite its settings.

Image: `ghcr.io/yetone/magpie:0.1.1836` (upstream image tags omit `v`).
Verified as the latest stable release on 2026-10-28. The registry manifest
for the published version tag was verified as:

`sha256:ddb7dbeb30d99020a592754594883ca1bd351e926181c71fc03db5609e5a029e`

Platforms: `linux/amd64`, `linux/arm64`.

Runtime details are taken from this release's `Dockerfile`,
`internal/cli/healthcheck_cli.go`, `internal/cli/web_cli.go`, and
`internal/gui/web.go`:

- Run `web --addr 0.0.0.0:3430 --no-open` with UID/GID 65532.
- Persist all `/config` directories, including sign-ins and plugin caches.
- Use the native `/magpie healthcheck` command.
- Import environment variables from `magpie.envSecret`, with a required
  `MAGPIE_WEB_KEY` entry. The default Secret name is `magpie-env`.
- Route Ingress to the Web port, which also serves the gateway's client API
  paths under the gateway's separate authentication.

The image reference and version share one form field. Explicit tags and
digests take precedence over legacy `image.tag`; untagged references fall
back to `appVersion`. Legacy `auth` settings remain available through YAML
when `magpie.envSecret` is explicitly empty, following the repository's
environment Secret convention.

Official application icon:
https://github.com/yetone/magpie/blob/v0.1.1734/internal/gui/assets/icons/icon-512.png

The upstream MIT license is included in `LICENSE`.
