# 外部应用反向代理

通过已有 Traefik，将域名转发到集群外的 HTTP / HTTPS 服务。
可用于通过现有 `traefik-vpn` 访问另一台服务器上的 Magpie。

- 域名、后端 IP / 域名和端口可配置；一个实例配置一个域名与后端。
- Ingress 类、地址类型、后端协议、Host 模式、证书方式均提供下拉选择。
- 已有 TLS Secret、签发器、自定义 CA Secret 从集群资源中选择。
- 默认保留原始 Host 和业务请求头，适合后端也是 Traefik 的场景。
- HTTPS 后端支持 SNI，默认使用访问域名，并校验证书。
- 安装时选择 HTTP、已有证书或 cert-manager 自动签发；自动签发模式会创建并续期入口证书和 TLS Secret。
- 不运行额外代理容器，不创建公网 Service、节点或隧道。

安装前确保 Traefik Pod 能访问后端，业务域名的 DNS 记录仍需单独配置。
DNS 后端需在所选 Traefik 开启 `allowExternalNameServices`；HTTPS 后端
需安装 Traefik CRDs 并启用 `kubernetesCRD` provider。
