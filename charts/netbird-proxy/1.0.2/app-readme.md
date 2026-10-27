# NetBird Reverse Proxy

独立部署的 NetBird Reverse Proxy，连接现有管理端。先在安装命名空间创建环境变量 Secret，放入 `NB_PROXY_MANAGEMENT_ADDRESS`、`NB_PROXY_DOMAIN`、`NB_PROXY_TOKEN` 等配置；表单只选择 Secret。自托管管理端可以与 Dashboard 共用域名，例如 `https://netbird.example.com:443`，但现有 Traefik gRPC 路由须覆盖 `/management.ProxyService/`；仅有 `/api` 路由不够。还需将旧 NetBird 入口 Traefik 的 `websecure` `transport.respondingTimeouts.idleTimeout` 设为 `0`，保持 gRPC 长连接。Token 必须是 Proxy 集群 Token，不能使用 Peer Setup Key。

Komodo 由 Ingress 控制器终止 HTTPS；此 Chart 由 NetBird Proxy 终止 HTTPS，通过 Traefik v3 `IngressRouteTCP` 透传 TLS，不使用普通 HTTP Ingress。

在“域名 / HTTPS”填写 Traefik 路由域名，例如 `proxy.example.com`，并确保与 Secret 中的 `NB_PROXY_DOMAIN` 一致；Chart 默认使用 Traefik 的 `websecure` 入口透传 TLS，Service 默认使用 `ClusterIP`。将 `proxy.example.com` 和 `*.proxy.example.com` 的 DNS 指向 Traefik，确保公网 TCP 443 可达。

- **自动签发（默认）**：选择 `acme` 和 `tls-alpn-01`，配置可用存储类或已有 PVC。NetBird 负责申请、续期证书，无需 ClusterIssuer 或 TLS Secret；证书默认保存在挂载到 `/certs` 的保留 PVC 中。
- **已有证书**：选择 `existingSecret`，从下拉框选择安装命名空间内的 Secret。列表不会过滤 Secret 类型；所选 Secret 必须包含 `tls.crt`、`tls.key`，证书覆盖实际使用的服务域名，例如 `*.proxy.example.com`；若还使用 `proxy.example.com`，也需覆盖它。NetBird 从只读挂载目录加载证书并监听更新，续期由现有流程负责。其他命名空间（包括 `cattle-system`）的 Secret 不能直接挂载。

证书挂载目录默认 `/certs`，同时传入 `NB_PROXY_CERTIFICATE_DIRECTORY`；自定义目录可在“编辑 YAML”中设置。若 Traefik 自身启用了 TLS ACME 验证器，需在其 HTTPS 入口配置 `allowACMEByPass`；这是 Traefik 配置，不是 NetBird 环境变量，具体设置见 Chart README。

内置 Traefik TCP 路由默认发送 PROXY v2，因此在环境变量 Secret 中设置 `NB_PROXY_PROXY_PROTOCOL=true`，并将 `NB_PROXY_TRUSTED_PROXIES` 设为 NetBird Proxy 实际看到的 Traefik 来源 IP/CIDR；不能照搬旧 Docker 网段。未限制 Pod 间访问时用 Traefik Pod IP，Pod 重建后更新；若信任整个 Pod 网段，应限制只有 Traefik Pod 能连接 Proxy，防止其他 Pod 伪造来源地址。还需确认公网流量到达 Traefik 时保留了原始客户端 IP，否则传给 Proxy 的仍是改写后的地址。更新 Secret 后需要重启 Deployment。

Rancher 可使用 `rancher.example.com` 和自己的证书；NetBird 使用 `proxy.example.com` 及其服务域名，默认由 NetBird 管理对应证书。Rancher 域名不能落入 Proxy 的域名范围，Chart 不修改 Rancher 的证书资源。独立负载均衡入口可关闭 Traefik 路由；`http-01` 还需要公网 TCP 80，不能搭配本 Chart 的 TCP 透传路由。K3s 上第二个占用 443 的 ServiceLB 可能冲突，应共享现有入口或使用独立负载均衡地址。

运行一个非 root 副本，升级会短暂中断流量；不提供额外 TCP/UDP 服务端口。完整环境变量映射、客户端 IP 配置与部署示例见 Chart 的 `README.md`。

Geo 数据库默认由下载 init 容器从第三方 jsDelivr CDN 获取单文件 `GeoLite2-City.mmdb.gz`，解压后再启动 Proxy。Rancher 表单可修改 `geo.downloadUrl`；地址留空则沿用 NetBird 官方下载。新 Pod 会重新下载，下载失败时 Proxy 不会启动。
