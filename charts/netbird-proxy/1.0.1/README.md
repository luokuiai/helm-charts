# NetBird Reverse Proxy

Deploys one standalone `netbirdio/reverse-proxy:0.81.4` instance connected to an existing NetBird management service.
Includes a Rancher configuration form, an existing environment Secret, persistent proxy-managed certificates, and Traefik TLS passthrough.
The chart provides HTTP/HTTPS service access; additional TCP/UDP service ports are not exposed or advertised.

## Rancher 安装：域名 / HTTPS

Komodo 的 HTTPS 由 Ingress 控制器终止；NetBird 的 HTTPS 由 Proxy 容器终止。这里使用 Traefik `IngressRouteTCP` 透传 TLS，不创建普通 HTTP Ingress。

1. 在安装命名空间预先创建环境变量 Secret，参考 `docs/netbird-proxy/env-secret.example.yaml`。它需要包含 `NB_PROXY_MANAGEMENT_ADDRESS`、`NB_PROXY_DOMAIN`、`NB_PROXY_TOKEN`、`NB_PROXY_PROXY_PROTOCOL` 和 `NB_PROXY_TRUSTED_PROXIES`。管理端可以与 Dashboard 共用域名，例如 `https://netbird.example.com:443`，但 URL 不带 `/api`；Token 必须是 Proxy 集群 Token，不能用 Peer Setup Key。将 Secret 名称填入 Rancher 表单。
2. 在“域名 / HTTPS”填写 `proxy.domain`，例如 `proxy.example.com`，并确保它与 Secret 内的 `NB_PROXY_DOMAIN` 一致。这个表单值用于生成 Traefik 路由。Chart 默认使用 Traefik 的 `websecure` 入口透传 TLS，Service 默认使用 `ClusterIP`；将 `proxy.example.com` 与 `*.proxy.example.com` 的 DNS 指向 Traefik，并保证公网 TCP 443 可达。若集群改过 Traefik 入口名称，可在 YAML 中覆盖 `traefik.entryPoint`。
3. 证书有两种配置流程：
   - **NetBird 自动签发（默认）**：保持 `tls.mode=acme` 和 `tls-alpn-01`，选择可用的存储类或已有 PVC。NetBird 自动申请、续期证书，默认持久化到 `/certs`；无需 ClusterIssuer 或 TLS Secret。
   - **使用已有证书**：选择 `tls.mode=existingSecret`，再从 `tls.existingSecret` 下拉框选择安装命名空间内的 Secret。列表不会过滤 Secret 类型，所选项必须包含 `tls.crt`、`tls.key`，证书需覆盖实际使用的服务域名，例如 `*.proxy.example.com`；若还使用 `proxy.example.com`，也需覆盖它。NetBird 从 `/certs` 只读加载证书，续期由现有证书管理流程负责；`cattle-system` 中的 Secret 不能跨命名空间直接挂载。
4. 在 NetBird 中创建服务并配置认证。Rancher 可用 `rancher.example.com` 和自己的证书；NetBird 使用 `proxy.example.com` 及其服务域名，默认由 NetBird 管理对应证书。不要让 Rancher 域名落入 Proxy 的域名范围。

若 Traefik 自己配置了 TLS ACME 验证器，还需在其现有 HTTPS 入口启用 `allowACMEByPass`，让证书验证流量到达 NetBird；具体设置见下文。

默认 Traefik TCP 路由发送 PROXY v2。对应地，在环境变量 Secret 中设置 `NB_PROXY_PROXY_PROTOCOL=true`，并将 `NB_PROXY_TRUSTED_PROXIES` 设为 Traefik 连接 NetBird Proxy 时的来源 IP/CIDR。未限制 Pod 间访问时，可填当前 Traefik Pod IP（例如 `10.42.0.194/32`），但 Pod 重建后必须更新。若使用整个 Pod 网段（例如 `10.42.0.0/24`），应限制只有 Traefik Pod 能连接 Proxy，以免其他 Pod 伪造 PROXY 来源地址。旧 Docker subnet 不适用于 K3s。`externalTrafficPolicy: Cluster` 允许跨节点转发，某些路径会改写客户端源 IP；PROXY v2 只能传递 Traefik 实际收到的地址。

在能访问集群的终端查看 Traefik Pod 地址、节点 Pod 网段及 Traefik Service 的源 IP 策略：

```bash
kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik -o wide
kubectl get nodes -o custom-columns=NODE:.metadata.name,POD_CIDR:.spec.podCIDR
kubectl -n kube-system get svc traefik -o jsonpath='{.spec.externalTrafficPolicy}{"\n"}'
```

`questions.yaml` 是 Rancher 的配置表单。像 Komodo 一样，用户配置的 Proxy 环境变量放在同命名空间的 Secret 中，表单只选择该 Secret；路由域名、证书模式和存储等 Helm 需要生成 Kubernetes 资源的配置仍在表单中。监听地址、证书目录及 ACME 参数由 Chart 与 Service 和挂载一同设置。独立入口等配置可在“编辑 YAML”中调整。
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

ACME mode creates a `128Mi` certificate PVC on `local-path` by default, or uses `persistence.existingClaim`.
Set `persistence.size` in the Rancher form for new claims. Existing PVCs cannot be shrunk; keep their original size when upgrading.
The PVC is retained on Helm uninstall. Namespace deletion or manual PVC deletion can still remove it.
To reuse a retained claim on reinstall, set `persistence.existingClaim` to its name.
The container uses UID/GID `1000`; `fsGroup: 1000` allows ACME PVC writes.
The management URL selects the transport: HTTPS verifies the server using the image's system CA trust; HTTP uses plaintext. Prefer HTTPS.

### Optional external certificate

Set `tls.mode=existingSecret` and `tls.existingSecret` to use a certificate renewed through Rancher, cert-manager, or another existing process. This disables NetBird's ACME client.
The Secret must contain `tls.crt` and `tls.key` and be in the installation namespace; a Secret in `cattle-system` cannot be mounted from another namespace.
It must cover every hostname actually used by services, such as `*.proxy.example.com`; include `proxy.example.com` if you also serve that hostname. A `*.example.com` certificate does not cover `app.proxy.example.com`.
The Secret is mounted read-only as a complete directory without `subPath`, with group-readable permissions. NetBird 0.81.4 reloads changes after Kubernetes updates the mounted Secret.
Keep one renewal owner for each certificate; this optional mode also supports the Traefik TLS passthrough route.

## 环境变量

先在安装命名空间创建 `netbird-proxy-env` Secret（或在表单选择已有 Secret），字段示例见 `docs/netbird-proxy/env-secret.example.yaml`。Deployment 使用 `envFrom.secretRef` 导入。至少配置管理端 URL、Proxy 集群域名、Proxy Token，以及使用内置 Traefik 路由时的 PROXY v2 和可信来源。`NB_PROXY_DOMAIN` 必须与表单的 `proxy.domain` 一致。更新 Secret 后需重启 Deployment，Kubernetes 不会自动更新已运行容器的环境变量。

Chart 仍设置与 Kubernetes 资源绑定的环境变量：`NB_PROXY_ADDRESS=:8443`、`NB_PROXY_HEALTH_ADDRESS=:8080`、`NB_PROXY_SUPPORTS_CUSTOM_PORTS=false`、证书目录和 ACME 选项。其中 `tls.certificateDirectory` 同时决定挂载路径和 `NB_PROXY_CERTIFICATE_DIRECTORY`；`tls.mode` 决定证书 Secret/PVC 挂载及 `NB_PROXY_ACME_CERTIFICATES`。不要在环境变量 Secret 中另设这些 Chart 管理的字段，因为显式 `env` 会覆盖 `envFrom` 的同名字段。

内置 Traefik 路由始终向 NetBird Proxy 发送 PROXY v2；环境变量 Secret 中的 `NB_PROXY_PROXY_PROTOCOL` 应设为 `true`。若关闭内置路由并改用不发送 PROXY v2 的独立入口，应在 Secret 中设为 `false`。`NB_PROXY_TRUSTED_PROXIES` 填实际 Traefik 来源，勿信任任意客户端网段。`extraEnv` 只用于 YAML 中的额外环境变量，不能覆盖 Chart 管理的监听和证书字段。

## Helm example

先创建安装命名空间，再按 `docs/netbird-proxy/env-secret.example.yaml` 创建环境变量 Secret，替换其中的 URL、域名、Token 和可信来源地址。默认使用已有 Traefik v3 入口，由 NetBird 管理证书，无需 TLS Secret。

```bash
helm upgrade --install netbird-proxy charts/netbird-proxy/1.0.1 \
  --namespace netbird \
  --set proxy.domain=proxy.example.com \
  --set proxy.envSecret=netbird-proxy-env
```

从 1.0.0 升级前，先创建新环境变量 Secret；旧 Chart 的 `auth.token` 或 `auth.existingSecret` 不再读取。若旧 Token Secret 由 Chart 创建，升级时会被删除，因此新 Secret 必须先包含真实 Token。更新 Secret 后需重启 Deployment：

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

- [Proxy configuration source for v0.81.4](https://github.com/netbirdio/netbird/blob/v0.81.4/proxy/cmd/proxy/cmd/root.go)
- [Official image Dockerfile](https://github.com/netbirdio/netbird/blob/v0.81.4/proxy/Dockerfile)
- [Certificate watcher](https://github.com/netbirdio/netbird/blob/v0.81.4/proxy/internal/certwatch/watcher.go)
- [Bring Your Own Proxy](https://docs.netbird.io/manage/reverse-proxy/bring-your-own-proxy)
- [Self-hosted proxy setup](https://docs.netbird.io/selfhosted/migration/enable-reverse-proxy)
- [Traefik TCP routing](https://doc.traefik.io/traefik/routing/routers/#configuring-tcp-routers)
- [Traefik entrypoint ACME bypass](https://doc.traefik.io/traefik/v3.6/reference/install-configuration/entrypoints/#allowacmebypass)

The bundled icon is converted from the favicon on the official NetBird website.
