# Magpie

Magpie 0.1.1836 with a Rancher configuration form, one persistent gateway,
and browser-based administration. Uses the official headless Docker image,
not the desktop GUI. Supports amd64 and arm64, including K3s installations.

The form configures:

- An existing environment Secret containing `MAGPIE_WEB_KEY` and other settings.
- A `1Gi` config PVC using `local-path` by default, or an existing claim.
- Ingress hostname, Ingress Class, an existing TLS Secret, or cert-manager.
- A public URL override, image settings, and CPU / memory.

One replica and `Recreate` updates keep a single writer on the config volume.
The entire `/config` tree is persisted, including provider credentials,
sign-ins, plugins, caches, settings, and usage. The PVC is retained on uninstall.

Both the Web UI and gateway API are reachable through port `3430`, so one
Ingress hostname is sufficient. The Service also exposes the direct gateway
on port `3425` inside the cluster. Ingress is disabled by default.

The Web key grants administrative access and is separate from the gateway
keys used by API clients. Select the environment Secret in the form;
the default name is `magpie-env`. Its entries are injected as environment
variables, with `MAGPIE_WEB_KEY` required. Restart the Deployment after
changing the Secret.

The image uses one field, `image.repository`, defaulting to the pinned
`ghcr.io/yetone/magpie:0.1.1836`. Include a tag or digest in the same field.
An untagged reference falls back to `Chart.appVersion` (or a legacy `image.tag`).

See the [deployment guide](../../../docs/magpie/deployment.md),
[Secret example](../../../docs/magpie/web-secret.example.yaml), and
[upstream details](UPSTREAM.md).

Validate:

```bash
helm lint charts/magpie/1.0.0 --strict
uv run --with pyyaml python tests/magpie/test_chart.py
```
