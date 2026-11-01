# 在 Rancher 配置外部应用代理

本 Chart 复用已有 `traefik-vpn` 或公网 Traefik。后端服务器无需加入 K3s，
但 Traefik Pod 必须能通过现有网络访问它。

## 安装

1. 将本仓库作为 Git Chart 仓库加入 Rancher，刷新后搜索 **External Proxy**。
2. 选择 `1.0.0`，填写实例名和命名空间。一个实例对应一个域名与后端，
   可以重复安装，例如 `magpie-remote`、`other-app`。
3. 在 **访问入口** 配置域名，从下拉列表选择 `traefik-vpn`。
4. 在 **后端连接** 选择地址类型、协议、Host 模式，填写地址和端口。
5. 在 **域名证书** 下拉选择 `disabled`（HTTP）、`existing`（已有证书）或
   `cert-manager`（自动签发）。已有证书模式从下拉选择 TLS Secret；自动签发
   模式从下拉选择 Issuer / ClusterIssuer，由 cert-manager 创建并续期证书，
   Secret 默认命名为 `<安装实例名>-tls`，无需提前生成证书。
6. 在现有私有 DNS 中，将该域名指向共享 VPN 入口；不要把它解析到 B 的公网地址。

Chart 只创建 Ingress、Service、IP 后端所需的 EndpointSlice，以及 HTTPS
后端所需的 ServersTransport；不创建代理 Pod、NodePort 或 LoadBalancer。

自动签发入口证书的前提是集群已安装 cert-manager，所选签发器 Ready 且
能验证该域名。VPN 私有入口建议复用现有 DNS-01 签发器，不需要开放公网
80 / 443。B 的后端证书由 B 自己的 Traefik / cert-manager 管理，本 Chart
不会跨服务器修改 B 的证书配置。

## B 也是 Traefik

假设希望通过 `remote.example.com` 访问 B。B 的 Traefik 中也配置该域名的
Ingress；本 Chart 的 Host 模式选择 `original`，让 B 识别同一个域名。

```yaml
ingress:
  host: remote.example.com
  className: traefik-vpn
  certificate:
    mode: cert-manager
    issuerKind: ClusterIssuer
    issuerName: letsencrypt-alidns
backend:
  addressType: IPv4
  address: 192.0.2.10 # 替换为集群可达的 B 地址
  port: 443
  scheme: https
  hostHeader: original
```

此时 TLS SNI 自动使用 `remote.example.com`，并校验 B 的证书。若 B 的证书
使用不同名称，在表单填写后端 TLS 证书域名。若使用私有 CA，选择含
`ca.crt` 或 `tls.ca` 的 Secret。Secret 与 Chart 安装在同一命名空间。

Authorization、x-api-key 等业务头按 Traefik 原生行为透传，不需要逐项配置。
两层 TLS 分别终止；这不是原样转发 TLS 字节流。客户端证书认证不会自动穿透。

若 B 需要真实客户端 IP，在 B 的 Traefik `forwardedHeaders.trustedIPs`
信任它实际看到的上游代理来源；仅靠保留 Host 不会自动建立可信代理链。

## B 直接运行 Magpie

如果直接转发 B 的 Magpie Web / API 共用端口，可使用：

```yaml
backend:
  addressType: IPv4
  address: 192.0.2.10
  port: 3430
  scheme: http
  hostHeader: original
```

端口以 B 的实际监听配置为准。B 的安全组 / 防火墙只允许集群实际出口访问
该端口。认证由 B 的 Magpie 自身控制，Chart 不保存或生成 Magpie Key。

集群内其他应用也可以通过生成的 Service 地址访问后端，例如
`http://magpie-remote.infra.svc.cluster.local:3430`，不必依赖 VPN 客户端 DNS。

## 后端是域名

选择 `DNS`，地址只填后端域名。须先在所选 Traefik 的 Helm Values 开启：

```yaml
providers:
  kubernetesIngress:
    allowExternalNameServices: true
```

这是 Traefik provider 的全局设置，影响该控制器处理的 ExternalName Service。
本 Chart 不修改其他 Helm release。默认 IP 后端不依赖此设置。

## 验证

连接现有 VPN 后，访问配置的业务域名，并在 B 的 Traefik 确认 Host 路由命中。
测试受保护的 API 时，使用 B 实际接受的认证头；不要把真实 Key 写入 Git。

还需实际检查 HTTPS、SSE / WebSocket（如应用使用）和后端来源白名单。
本地 Helm 渲染测试不代表已经验证了实际网络、DNS 或证书签发。
