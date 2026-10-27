# Magpie

Deploy the official headless Magpie gateway and Web UI with one persistent
config volume. Supports amd64 / arm64 and standard K3s local-path storage.

Enter a random Web key of at least 16 characters, or select an existing
Secret containing `MAGPIE_WEB_KEY`. Generate a key with `openssl rand -hex 16`.
Use the key to sign in at `/?k=<your-web-key>`; it grants administrative access,
including access to provider credentials. Use HTTPS or a private tunnel.

One Ingress domain serves both the Web UI at `/` and OpenAI-compatible API
at `/v1`. Add providers and sign-ins in the Web UI, then create separate
gateway API keys for clients. The Web key is not a gateway API key.

The chart retains `/config` in a PVC, including provider keys, sign-ins,
plugins, caches, and usage. It uses one replica and Recreate updates.
PVCs are retained on uninstall. Form-entered keys also remain in Helm values;
use an existing Secret if credentials must stay out of values.
