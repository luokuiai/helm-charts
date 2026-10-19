# NetBird Reverse Proxy

Deploys one standalone `netbirdio/reverse-proxy:0.81.2` instance connected to an existing NetBird management service.
Includes a Rancher configuration form, Secret-backed proxy token, persistent proxy-managed certificates, and Traefik TLS passthrough.
The chart provides HTTP/HTTPS service access; additional TCP/UDP service ports are not exposed or advertised.

## Rancher installation

1. Sync this Git chart repository and select **NetBird Reverse Proxy**, chart version `1.0.0`.
2. Set the management URL and proxy cluster domain from the NetBird cluster setup. The token must be a proxy token, not a peer setup key.
3. Enter the token in the form or select an existing Secret by name and key in the installation namespace.
4. Keep proxy-managed ACME enabled and choose the certificate storage settings. Certificates persist on a retained PVC mounted at `/certs` by default; no TLS Secret is required.
5. Keep the default Traefik v3 TLS passthrough route and `ClusterIP` Service. If Traefik has its own TLS challenge resolver, configure ACME bypass as described below.
6. Point the proxy domain and its wildcard DNS record at that entrypoint. Create services and configure their authentication in NetBird.

`questions.yaml` is Rancher's configuration form filename. Form fields map directly to `values.yaml`; all proxy settings are passed through environment variables.
The management endpoint must expose the `/management.ProxyService/` gRPC API. A dashboard URL that returns HTML for this path will not work.
The cluster needs outbound connectivity to the management service and the NetBird signal/relay/peer endpoints used by its networks.

## Certificate ownership and sharing Rancher's entrypoint

The default `tls.mode=acme` lets NetBird Proxy issue and renew its own certificates using `tls-alpn-01`.
The default `traefik.enabled=true` and `service.type=ClusterIP` share Traefik's public port 443; Traefik forwards TLS unchanged and NetBird Proxy terminates HTTPS.
This chart does not create or modify Rancher's certificate resources or install a certificate manager.

Use a dedicated proxy domain, such as `proxy.example.com`, while Rancher uses another domain, such as `rancher.example.com`.
Point the proxy domain and its wildcard DNS record at Traefik. The wildcard DNS record routes service hostnames; NetBird obtains certificates for individual hostnames through TLS-ALPN-01.
Public TCP 443 must reach NetBird's TLS listener unchanged for certificate issuance and renewal.

With `traefik.enabled=true`, the chart creates a Traefik v3 `IngressRouteTCP` using the existing `websecure` entrypoint.
It matches only the proxy domain and its subdomains, then passes TLS to the proxy without terminating it.
Rancher's HTTP router continues handling Rancher's separate hostname on the same IP and port 443.
Do not assign the Rancher hostname, or an ancestor of it, as the proxy cluster domain: TCP routers take precedence over HTTP routers for matching hosts.
Custom service domains outside the proxy cluster suffix need separately configured TCP routes.
This route requires the `traefik.io/v1alpha1` CRD and Traefik's Kubernetes CRD provider; it does not install another ingress controller.
If Traefik itself has an ACME resolver using TLS challenges, enable `entryPoints.websecure.allowACMEByPass=true` in its existing static configuration (CLI: `--entryPoints.websecure.allowACMEByPass=true`).
Use the actual entrypoint name if you change `traefik.entryPoint`. Without a TLS challenge resolver in Traefik, the bypass is implicit.
This is a Traefik setting, not a NetBird environment variable. Merge it into the existing Traefik configuration; preserve other settings in any existing K3s `HelmChartConfig`.
The chart creates a TCP route only. Its shared Traefik route therefore requires `tls-alpn-01`; `http-01` requires a separate HTTP challenge route and is rejected with `traefik.enabled=true`.

ACME mode creates a `1Gi` certificate PVC on `local-path`, or uses `persistence.existingClaim`.
The PVC is retained on Helm uninstall. Namespace deletion or manual PVC deletion can still remove it.
To reuse a retained claim on reinstall, set `persistence.existingClaim` to its name.
The container uses UID/GID `1000`; `fsGroup: 1000` allows ACME PVC writes.
The management URL selects the transport: HTTPS verifies the server using the image's system CA trust; HTTP uses plaintext. Prefer HTTPS.

### Optional external certificate

Set `tls.mode=existingSecret` and `tls.existingSecret` to use a certificate renewed through Rancher, cert-manager, or another existing process. This disables NetBird's ACME client.
The Secret must contain `tls.crt` and `tls.key` and be in the installation namespace; a Secret in `cattle-system` cannot be mounted from another namespace.
It must cover every service hostname, typically `proxy.example.com` and `*.proxy.example.com`. A `*.example.com` certificate does not cover `app.proxy.example.com`.
The Secret is mounted read-only as a complete directory without `subPath`, with group-readable permissions. NetBird 0.81.2 reloads changes after Kubernetes updates the mounted Secret.
Keep one renewal owner for each certificate; this optional mode also supports the Traefik TLS passthrough route.

## Environment variables

| Helm value | Container environment variable |
| --- | --- |
| `proxy.managementAddress` | `NB_PROXY_MANAGEMENT_ADDRESS` |
| `proxy.domain` | `NB_PROXY_DOMAIN` |
| `auth.token` or existing token Secret | `NB_PROXY_TOKEN` via `secretKeyRef` |
| `proxy.logLevel` | `NB_PROXY_LOG_LEVEL` |
| `proxy.private` | `NB_PROXY_PRIVATE` |
| `proxy.forwardedProto` | `NB_PROXY_FORWARDED_PROTO` |
| `proxy.proxyProtocol` | `NB_PROXY_PROXY_PROTOCOL` |
| `proxy.trustedProxies` | `NB_PROXY_TRUSTED_PROXIES` |
| `tls.certificateDirectory` | `NB_PROXY_CERTIFICATE_DIRECTORY`, also the volume mount path |
| `tls.mode` | `NB_PROXY_ACME_CERTIFICATES`: `false` for `existingSecret`, `true` for `acme` |
| `tls.acme.directory` | `NB_PROXY_ACME_DIRECTORY` in ACME mode |
| `tls.acme.challengeType` | `NB_PROXY_ACME_CHALLENGE_TYPE` in ACME mode |

The chart sets `NB_PROXY_ADDRESS=:8443`, `NB_PROXY_HEALTH_ADDRESS=:8080`, and `NB_PROXY_ACME_ADDRESS=:8081` (ACME only), and maps Service ports to these listeners.
External certificate mode uses `tls.crt` / `tls.key`; ACME mode uses NetBird's certificate cache layout in the mounted directory.
The chart disables custom service ports and uses `NB_PROXY_CERT_LOCK_METHOD=flock` for its single ACME replica.
Kubernetes Service environment injection is disabled to avoid accidental variable collisions. There is no configuration file or command-line override.
Use `extraEnv` in YAML for additional upstream variables or Secret references; duplicate names and chart-managed variables are rejected.

For client IP based restrictions, configure the upstream to send PROXY protocol v2, enable `proxy.proxyProtocol`, and list the actual upstream IPs or CIDRs in `proxy.trustedProxies`.
The Traefik route sends v2 when this setting is enabled. Without it, the proxy sees the upstream router's source IP.
Do not enable PROXY protocol for direct browser connections or trust arbitrary client networks.

## Helm example

Create the installation namespace and token Secret first. A placeholder token Secret is provided in `docs/netbird-proxy/secrets.example.yaml`; replace it before applying.
The default setup uses the existing Traefik v3 entrypoint and lets NetBird manage certificates; no TLS Secret is needed.

```bash
helm upgrade --install netbird-proxy charts/netbird-proxy/1.0.0 \
  --namespace netbird \
  --set proxy.managementAddress=https://netbird.example.com:443 \
  --set proxy.domain=proxy.example.com \
  --set auth.useExistingSecret=true \
  --set auth.existingSecret=netbird-proxy-auth
```

Entering a token in the form stores it in Helm release values as well as the generated Kubernetes Secret; use an existing Secret to avoid the Helm values copy.
Changing a chart-managed token restarts the Pod through a checksum annotation. After changing an existing token Secret, restart the Deployment separately:

```bash
kubectl -n netbird rollout restart deployment/netbird-proxy
```

## Dedicated endpoint with proxy-managed ACME

For a separate public endpoint, set `traefik.enabled=false`, keep `tls.mode=acme`, and expose the Service through a suitable L4 load balancer.
`LoadBalancer` needs an available load balancer implementation and dedicated address. K3s ServiceLB commonly uses host ports; a second Service on 80/443 can conflict with Traefik.
Use the shared Traefik setup above or a dedicated load balancer address instead of replacing Rancher's listener.
With `NodePort`, choose a node port or leave `0` for allocation, then forward public port 443 to that node port through an external L4 load balancer.
`ClusterIP` alone is reachable only inside the cluster.

The default `tls-alpn-01` challenge requires public TCP 443 to reach NetBird's TLS listener unchanged.
For `http-01`, the chart also exposes port 80 to container port 8081; forward public TCP 80 as well. This HTTP port serves ACME challenges, not application traffic or HTTPS redirects.
Do not terminate TLS on an ordinary HTTPS Ingress before this proxy.

The chart uses one replica with `Recreate` upgrades, so upgrades briefly interrupt traffic. Embedded client state and downloaded geolocation data are temporary; certificate data is persistent in ACME mode.

## Upstream references

- [Proxy configuration source for v0.81.2](https://github.com/netbirdio/netbird/blob/v0.81.2/proxy/cmd/proxy/cmd/root.go)
- [Official image Dockerfile](https://github.com/netbirdio/netbird/blob/v0.81.2/proxy/Dockerfile)
- [Certificate watcher](https://github.com/netbirdio/netbird/blob/v0.81.2/proxy/internal/certwatch/watcher.go)
- [Bring Your Own Proxy](https://docs.netbird.io/manage/reverse-proxy/bring-your-own-proxy)
- [Self-hosted proxy setup](https://docs.netbird.io/selfhosted/migration/enable-reverse-proxy)
- [Traefik TCP routing](https://doc.traefik.io/traefik/routing/routers/#configuring-tcp-routers)
- [Traefik entrypoint ACME bypass](https://doc.traefik.io/traefik/v3.6/reference/install-configuration/entrypoints/#allowacmebypass)

The bundled icon is converted from the favicon on the official NetBird website.
