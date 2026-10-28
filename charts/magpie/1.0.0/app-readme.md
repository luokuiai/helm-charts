# Magpie

Deploy the official headless Magpie gateway and Web UI with one persistent
config volume. Supports amd64 / arm64 and standard K3s local-path storage.

Select an existing environment Secret (default: `magpie-env`) containing
`MAGPIE_WEB_KEY`. Its entries become environment variables. Generate a random
Web key of at least 16 characters with `openssl rand -hex 16`.
Use the key to sign in at `/?k=<your-web-key>`; it grants administrative access,
including access to provider credentials. Use HTTPS or a private tunnel.

One Ingress domain serves both the Web UI at `/` and OpenAI-compatible API
at `/v1`. Add providers and sign-ins in the Web UI, then create separate
gateway API keys for clients. The Web key is not a gateway API key.

The chart retains `/config` in a PVC, including provider keys, sign-ins,
plugins, caches, and usage. It uses one replica and Recreate updates.
PVCs are retained on uninstall. Restart the Deployment after changing the Secret.

The image and version share one field, defaulting to the pinned
`ghcr.io/yetone/magpie:0.1.1836`.
