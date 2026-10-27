# NetBird Reverse Proxy

Deploys one standalone `netbirdio/reverse-proxy:0.81.2` instance connected to an existing NetBird management service.
Includes a Rancher configuration form, Secret-backed proxy token, persistent proxy-managed certificates, and Traefik TLS passthrough.
The chart provides HTTP/HTTPS service access; additional TCP/UDP service ports are not exposed or advertised.

## Rancher 安装：域名 / HTTPS

Komodo 的 HTTPS 由 Ingress 控制器终止；NetBird 的 HTTPS 由 Proxy 容器终止。这里使用 Traefik `IngressRouteTCP` 透传 TLS，不创建普通 HTTP Ingress。

1. 同步 Git Chart 仓库，选择 **NetBird Reverse Proxy** `1.0.0` 和安装命名空间。自托管管理端可填写与 Dashboard 相同的域名，例如 `https://netbird.example.com:443`；NetBird Cloud 才填写 `https://api.netbird.io:443`。填写 Proxy Token，或选择同命名空间的 Token Secret；不能使用 Peer Setup Key。
2. 在“域名 / HTTPS”填写 `proxy.domain`，例如 `proxy.example.com`。Chart 默认使用 Traefik 的 `websecure` 入口透传 TLS，Service 默认使用 `ClusterIP`；将 `proxy.example.com` 与 `*.proxy.example.com` 的 DNS 指向 Traefik，并保证公网 TCP 443 可达。若集群改过 Traefik 入口名称，可在 YAML 中覆盖 `traefik.entryPoint`。
3. 证书有两种配置流程：
   - **NetBird 自动签发（默认）**：保持 `tls.mode=acme` 和 `tls-alpn-01`，选择可用的存储类或已有 PVC。NetBird 自动申请、续期证书，默认持久化到 `/certs`；无需 ClusterIssuer 或 TLS Secret。
   - **使用已有证书**：选择 `tls.mode=existingSecret`，再从 `tls.existingSecret` 下拉框选择安装命名空间内的 Secret。列表不会过滤 Secret 类型，所选项必须包含 `tls.crt`、`tls.key`，证书需覆盖实际使用的服务域名，例如 `*.proxy.example.com`；若还使用 `proxy.example.com`，也需覆盖它。NetBird 从 `/certs` 只读加载证书，续期由现有证书管理流程负责；`cattle-system` 中的 Secret 不能跨命名空间直接挂载。
4. 在 NetBird 中创建服务并配置认证。Rancher 可用 `rancher.example.com` 和自己的证书；NetBird 使用 `proxy.example.com` 及其服务域名，默认由 NetBird 管理对应证书。不要让 Rancher 域名落入 Proxy 的域名范围。

若 Traefik 自己配置了 TLS ACME 验证器，还需在其现有 HTTPS 入口启用 `allowACMEByPass`，让证书验证流量到达 NetBird；具体设置见下文。

`questions.yaml` is Rancher's configuration form filename. Form fields map directly to `values.yaml`; all proxy settings are passed through environment variables. The standard K3s form uses the existing Traefik entrypoint, TLS-ALPN challenge, certificate directory, ACME directory, and Service ports at their defaults. Dedicated endpoints and PROXY protocol settings remain available in **Edit YAML** for advanced setups.
The management endpoint must expose the `/management.ProxyService/` gRPC API. A dashboard URL that returns HTML for this path will not work. For a self-hosted installation sharing the Dashboard hostname, add ``PathPrefix(`/management.ProxyService/`)`` to the existing Traefik gRPC router for that hostname and route it to the Management service over h2c. The HTTP backend router matching `/api` alone does not cover this gRPC path. Set `websecure`'s `transport.respondingTimeouts.idleTimeout` to `0` on the existing NetBird Traefik entrypoint so the gRPC stream stays connected. The management URL is the hostname and port only, without `/api` or a gRPC path.
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
It must cover every hostname actually used by services, such as `*.proxy.example.com`; include `proxy.example.com` if you also serve that hostname. A `*.example.com` certificate does not cover `app.proxy.example.com`.
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

For client IP based restrictions, enable `proxy.proxyProtocol` in **Edit YAML** and list the actual Traefik source IPs or CIDRs in `proxy.trustedProxies`.
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
