# Registry Proxy

使用 Caddy 提供两个独立入口，Ingress 负责对外 HTTPS：

- `registry.example.com`：转发到自选 HTTPS 仓库。不保存上游账号密码，保留上游认证挑战，让 Docker 客户端使用上游凭据认证。
- `docker.example.com`：公共镜像代理，采用提供的四个 gh-proxy 上游和路径改写规则。`/v2`、`/v2/` 直接返回 200。

默认域名均为示例，部署前必须替换。两个入口使用不同域名，分别转发到 Caddy 8080 和 8081，避免公共 ping 响应影响上游仓库认证。仓库入口当前支持上游 HTTPS 443，`upstreamHost` 只填写域名。

如果上游镜像路径需要一个命名空间，而希望拉取时省略它，可设置 `upstreamNamespace`。例如上游镜像是 `upstream.example.com/myteam/intelliconf:1.3.2`，将 `upstreamHost` 填为 `upstream.example.com`、`upstreamNamespace` 填为 `myteam` 后，可执行 `docker pull registry.example.com/intelliconf:1.3.2`。此配置只作用于私有仓库入口；留空时路径原样转发。上游返回的已含命名空间路径不会重复添加前缀。它不改变镜像层下载时上游返回的对象存储跳转地址。

## Helm 安装

编辑 `values.yaml`，或通过参数覆盖：

```bash
helm upgrade --install registry-proxy ./charts/registry-proxy/1.0.0 \
  --namespace infra --create-namespace \
  --set ingress.host=registry.example.com \
  --set upstreamHost=registry-upstream.example.com \
  --set publicProxy.host=docker.example.com
```

自动签发使用已有的 `ClusterIssuer/letsencrypt`。将两个实际域名解析到 Ingress 入口；如果签发器使用 HTTP-01，公网 80 端口需要可达。签发成功后，cert-manager 创建同命名空间的 `registry-proxy-tls` 和 `registry-proxy-public-tls` Secret。
自动签发时，两个入口最终使用的 TLS Secret 名称必须不同；留空时分别使用上述默认名称。

证书配置沿用 Komodo 的 Ingress 注解和 TLS Secret 方式。两个入口共用 `ingress.annotations`，默认包含 `traefik.ingress.kubernetes.io/router.tls: "true"`，自动签发和使用已有证书时都会启用 HTTPS 路由。可在该配置中补充 Traefik 入口等注解；证书签发统一由 `ingress.clusterIssuer` 管理，手动设置的 `cert-manager.io/issuer`、`cert-manager.io/cluster-issuer` 和 `kubernetes.io/tls-acme` 注解会被清除或覆盖。

使用已有证书时，清空 `ingress.clusterIssuer` 并指定同命名空间的 TLS Secret。若已有证书同时覆盖两个入口域名，两个入口可以填写相同的 Secret 名称：

```bash
helm upgrade --install registry-proxy ./charts/registry-proxy/1.0.0 \
  --namespace infra --create-namespace \
  --set ingress.host=registry.example.com \
  --set upstreamHost=registry-upstream.example.com \
  --set publicProxy.host=docker.example.com \
  --set-string ingress.clusterIssuer= \
  --set ingress.tls.secretName=my-existing-tls \
  --set publicProxy.tls.secretName=my-existing-public-tls
```

## Rancher 安装

本 Chart 位于 Git 仓库的 `charts/registry-proxy/1.0.0/`，无需生成 `index.yaml` 或上传 `.tgz` 包。

在 Rancher 的“应用 → 仓库 → 创建”中选择 Git 仓库，填写本仓库的 Git 地址和实际分支。同步完成后，在“应用 → Charts”搜索 `registry-proxy`，选择 `1.0.0`，安装命名空间选 `infra`。

Chart 包含 `questions.yaml`，安装页面可填写私有仓库代理域名、公共镜像代理域名、上游仓库域名、Ingress Class、ClusterIssuer、TLS Secret、副本数，以及是否启用公共镜像代理。“公共镜像上游地址”列表对应 `publicProxy.upstreams`，可直接在表单中添加、删除或修改；至少保留一个 HTTPS 地址，不带路径，上游按列表顺序优先使用，且须兼容现有 gh-proxy 路径规则。CPU/内存在 `resources` 配置。

表单参照 Komodo 按“应用”“代理配置”“域名 / HTTPS”分组。两个代理域名、Ingress Class 和证书设置集中在“域名 / HTTPS”，关闭 Ingress 时隐藏对应字段；关闭公共代理时隐藏其上游、域名和证书字段。Ingress Class 和 ClusterIssuer 都使用集群资源下拉框；TLS Secret 名称与 Komodo 一样保留文本输入，以支持自动签发时的新名称及已有证书名称。使用已有证书时清空 ClusterIssuer 选择。

仓库中的域名和上游默认值均为示例，部署前必须替换。两个代理域名必须不同。

如果仓库通过 Fleet 管理，也可以让 Fleet 指向 `charts/registry-proxy/1.0.0/`。

## 行为与验证

- Caddy 监听容器内 HTTP 8080（仓库入口）和 8081（公共入口），不自行申请证书，不需要持久卷。
- 配置变化会改变 Pod 模板的校验和，由 Deployment 滚动更新加载新配置。
- readiness 使用 TCP 探测，因为未登录访问 Registry `/v2/` 通常返回 401。
- 仓库入口不修改 `WWW-Authenticate`。客户端仍需访问上游返回的认证地址；这里不提供独立、统一的 Token 服务。
- 仓库入口向上游发送不带 `:443` 的 `Host: upstreamHost`，并去掉 `X-Forwarded-For`、`X-Forwarded-Host`、`X-Forwarded-Proto`，使阿里云 ACR 等上游看到与直接拉取更一致的请求。上游日志将记录代理节点地址，而不是通过这些头获取原客户端地址。
- 仓库入口只改写指向上游仓库自身的绝对 `Location`，保留路径和查询参数；对象存储等其他域名的跳转保持原样。
- Docker 客户端仍需能访问上游返回的对象存储地址。阿里云 ACR 个人版应填写 `crpi-...personal.cr.aliyuncs.com` 公网入口；若镜像层仍跳转到 `oss-cn-chengdu-internal.aliyuncs.com`，不能直接无条件改写为公网域名，因为 OSS 签名可能绑定 `Host`。设置 `upstreamNamespace` 不会改变该下载地址。
- 仓库入口不限制 HTTP 方法，可转发推送请求；是否支持推拉取决于上游权限及实际网络环境，需要部署后验证。
- 公共入口将 `/v2/library/nginx/...` 和 `/v2/nginx/...` 改写为 `/v2/docker/nginx/...`；上游按给定顺序配置 `first` 策略及被动健康检查。
- 公共入口不需要时设置 `publicProxy.enabled=false`，对应监听端口和 Ingress 会一起移除。

部署后使用实际域名检查：

```bash
kubectl -n infra get pods,ingress,certificate
curl -i https://registry.example.com/v2/
curl -i https://docker.example.com/v2/
docker login registry.example.com
docker pull registry.example.com/namespace/image:tag
docker pull docker.example.com/library/nginx:alpine
```

仓库入口未登录返回带认证挑战的 401 属于正常流程；公共入口 `/v2/` 应返回 200。证书就绪、登录成功、公共镜像拉取以及私有镜像拉取和推送均需在实际集群验证。
