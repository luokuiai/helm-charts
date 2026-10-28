# Deploying Magpie from Rancher

Select `magpie` version `1.0.0` from this Git chart repository. This deploys
the official Magpie 0.1.1836 headless container, with gateway and Web management.
It does not run a desktop window or install agents on client machines.
The published image supports Linux amd64 and arm64.

## Image

The form has one **Magpie image** field, defaulting to
`ghcr.io/yetone/magpie:0.1.1836`. Include the version in the same field when
using a mirror, for example `registry.example.com/team/magpie:0.1.1836`.
Digest references are also supported. Untagged references fall back to
the chart's pinned version; an explicit tag or digest takes precedence
over the legacy separate `image.tag` value.

## Environment Secret and Web administration key

Generate a random stable Web key:

```bash
openssl rand -hex 16
```

The accepted characters are letters, digits, `- . _ ~`, with at least 16
characters. Create an environment Secret in the installation namespace,
using `MAGPIE_WEB_KEY` as the field name. In **Environment**, select that
Secret; its default name is `magpie-env`. All its entries are injected as
environment variables, and `MAGPIE_WEB_KEY` is required.

See [web-secret.example.yaml](web-secret.example.yaml). Replace its placeholder
before applying it:

```bash
kubectl apply -f docs/magpie/web-secret.example.yaml
```

Keep the completed Secret out of Git. The form stores only the Secret name.

For an existing `magpie-env` Secret in namespace `ai`:

```bash
helm install magpie charts/magpie/1.0.0 \
  --namespace ai \
  --set magpie.envSecret=magpie-env
```

`MAGPIE_ADDR` is set by the chart for its gateway port. The chart also sets
`MAGPIE_PUBLIC_URL` and `MAGPIE_WEB_URL` when a public URL is configured;
these explicit values take precedence over entries in the environment Secret.
Other Magpie environment variables can be added directly to the Secret.

For an existing installation using `auth.webKey` or `auth.existingSecret`,
reuse the same Web key in the environment Secret. To retain the old YAML
configuration instead, explicitly set `magpie.envSecret: ""`; the legacy
`auth` values and generated-Secret checksum continue to work in that mode.

The Web key grants administrative access, including access to provider
credentials. The application's startup log also includes a keyed login
link; restrict log access accordingly. Chart installation notes do not
print the actual key.

## Storage

The chart mounts one ReadWriteOnce PVC at `/config`, defaults to `local-path`
and `1Gi`, and runs as UID/GID `65532`. Kubernetes sets the volume group to
`65532`; the storage driver must support the required write permissions.
Select another storage class if the cluster does not provide `local-path`.
An empty class selects the cluster's default class.

The whole tree is retained: Magpie settings and provider keys under
`/config/magpie`, account sign-ins under `/config/home`, caches and optional
provider CLIs under `/config/cache`, plus usage and other state. There is
no separate external database to configure for this deployment.

An existing PVC must be in the release namespace, contain compatible Magpie
data, and be writable by UID/GID 65532. In this mode the chart creates no PVC.
Do not switch claims without migrating the complete config tree.

This chart fixes the replica count at one and uses `Recreate` updates, so
the existing Pod stops before its replacement starts. Updates briefly
interrupt service. Do not scale this workload to multiple replicas sharing
the same config tree. Resize existing PVCs separately if supported by the
storage class; editing the initial size is not a storage migration.

PVCs created by the chart are retained on Helm uninstall. Back up the entire
config volume securely: it contains credentials. Namespace or manual PVC
deletion can remove data. When reinstalling against a retained claim, set
**Existing config PVC** to its name, normally `<release>-config`.
`local-path` data remains on the assigned Kubernetes node; it does not move
the data automatically to another node after node failure.

## Domain and HTTPS

Enable **Domain / HTTPS**, enter a hostname such as `magpie.example.com`,
and select the Ingress Class (`traefik` on a standard K3s installation).
Configure DNS to point to the Ingress controller's external address.

Choose HTTPS mode `existing` to use a TLS Secret in the installation
namespace, or `cert-manager` to request a certificate using an existing
Issuer / ClusterIssuer. cert-manager and the issuer must already exist;
an Issuer must be in the release namespace. `disabled` omits TLS and is
intended for trusted test networks or a separate TLS proxy.

Example values to combine with the existing Web Secret settings:

```yaml
ingress:
  enabled: true
  className: traefik
  hosts:
    - host: magpie.example.com
      paths:
        - path: /
          pathType: Prefix
  certificate:
    mode: existing
    secretName: magpie-tls
```

The Ingress forwards `/` to the Web port `3430`, which also serves client
API paths such as `/v1`. Keep the root prefix without a path rewrite.
One hostname therefore supports:

- Web management: `https://magpie.example.com/`
- OpenAI-compatible base URL: `https://magpie.example.com/v1`
- Anthropic / Gemini clients: `https://magpie.example.com`

TLS terminates at the Ingress; connections to the Pod use HTTP. The chart
derives `MAGPIE_PUBLIC_URL` and `MAGPIE_WEB_URL` from the first Ingress
hostname and TLS mode. Use **Public base URL override** if a different
external proxy handles TLS or uses a nonstandard public port. Set only
the external base URL, without `/v1` or a subpath. The Service also exposes
the direct gateway on port `3425` inside the cluster.

## First sign-in and API access

Without Ingress, open a private port-forward:

```bash
kubectl -n ai port-forward svc/magpie 3430:3430
```

Open `http://localhost:3430/?k=<your-web-key>` locally, or
`https://magpie.example.com/?k=<your-web-key>` through Ingress. Magpie exchanges
the key for a browser cookie. Keep keyed links private; they are credentials.

Add providers and subscription sign-ins in the Web UI. For OAuth sign-ins
that redirect your browser to `localhost`, follow Magpie's remote sign-in
flow: copy the complete callback URL into the Web UI. This chart does not
publish subscription callback ports.

Create a separate gateway key per client in **Gateway → Gateway keys** or
through the CLI:

```bash
kubectl -n ai exec -it deploy/magpie -- /magpie gateway-key add "Laptop"
```

API clients must use an enabled gateway key, not the Web administration
key. Provider credentials and generated gateway keys are kept in the config
PVC and are not managed by Helm. Configure routing and limits in Magpie.

Some subscription providers require optional vendor CLIs, which are not
bundled in the Magpie image. Install them using Magpie's own provider flow;
the persisted cache keeps them across Pod replacement. Increase CPU,
memory, and storage if needed for the chosen plugins and provider tools.

## Updates

Use Helm and the full image reference to update the application. The default
image version is fixed. Back up `/config` first. After changing the environment
Secret, restart the Deployment to reload its environment variables:

```bash
kubectl -n ai rollout restart deployment/magpie
```

Official Docker documentation: https://usemagpie.ai/docs/zh/docker
