# NetBird Reverse Proxy

独立部署的 NetBird Reverse Proxy，连接现有管理端。自托管管理端可以与 Dashboard 共用域名，例如 `https://netbird.example.com:443`，但现有 Traefik gRPC 路由须覆盖 `/management.ProxyService/`；仅有 `/api` 路由不够。还需将旧 NetBird 入口 Traefik 的 `websecure` `transport.respondingTimeouts.idleTimeout` 设为 `0`，保持 gRPC 长连接。先填写管理端 URL 和 Proxy Token；Token 从 Kubernetes Secret 读取，不能使用 Peer Setup Key。所有 Proxy 配置通过官方环境变量传入。

Komodo 由 Ingress 控制器终止 HTTPS；此 Chart 由 NetBird Proxy 终止 HTTPS，通过 Traefik v3 `IngressRouteTCP` 透传 TLS，不使用普通 HTTP Ingress。

在“域名 / HTTPS”填写代理域名，例如 `proxy.example.com`；Chart 默认使用 Traefik 的 `websecure` 入口透传 TLS，Service 默认使用 `ClusterIP`。将 `proxy.example.com` 和 `*.proxy.example.com` 的 DNS 指向 Traefik，确保公网 TCP 443 可达。

- **自动签发（默认）**：选择 `acme` 和 `tls-alpn-01`，配置可用存储类或已有 PVC。NetBird 负责申请、续期证书，无需 ClusterIssuer 或 TLS Secret；证书默认保存在挂载到 `/certs` 的保留 PVC 中。
- **已有证书**：选择 `existingSecret`，从下拉框选择安装命名空间内的 Secret。列表不会过滤 Secret 类型；所选 Secret 必须包含 `tls.crt`、`tls.key`，证书覆盖实际使用的服务域名，例如 `*.proxy.example.com`；若还使用 `proxy.example.com`，也需覆盖它。NetBird 从只读挂载目录加载证书并监听更新，续期由现有流程负责。其他命名空间（包括 `cattle-system`）的 Secret 不能直接挂载。

证书挂载目录默认 `/certs`，同时传入 `NB_PROXY_CERTIFICATE_DIRECTORY`；自定义目录可在“编辑 YAML”中设置。若 Traefik 自身启用了 TLS ACME 验证器，需在其 HTTPS 入口配置 `allowACMEByPass`；这是 Traefik 配置，不是 NetBird 环境变量，具体设置见 Chart README。

默认无需配置 PROXY Protocol 或可信上游 IP，它们只影响 NetBird 获取真实访客 IP，不影响 TLS 透传和证书。若需要基于客户端 IP 的限制，可在“编辑 YAML”中同时配置 `proxy.proxyProtocol` 和 `proxy.trustedProxies`；可信范围必须是实际 Traefik 来源，不能照搬 Docker 示例网段。

Rancher 可使用 `rancher.example.com` 和自己的证书；NetBird 使用 `proxy.example.com` 及其服务域名，默认由 NetBird 管理对应证书。Rancher 域名不能落入 Proxy 的域名范围，Chart 不修改 Rancher 的证书资源。独立负载均衡入口可关闭 Traefik 路由；`http-01` 还需要公网 TCP 80，不能搭配本 Chart 的 TCP 透传路由。K3s 上第二个占用 443 的 ServiceLB 可能冲突，应共享现有入口或使用独立负载均衡地址。

运行一个非 root 副本，升级会短暂中断流量；不提供额外 TCP/UDP 服务端口。完整环境变量映射、客户端 IP 配置与部署示例见 Chart 的 `README.md`。
