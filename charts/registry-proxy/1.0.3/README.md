# Registry Proxy

使用 Caddy 提供两个独立入口，Ingress 负责对外 HTTPS：

- `registry.example.com`：转发到自选 HTTPS 仓库。启用命名空间简写时，由 Caddy 转发并改写 GET 令牌请求。
- `docker.example.com`：公共镜像代理，采用提供的四个 gh-proxy 上游和路径改写规则。镜像层 GET 请求以 307 跳转到第一项上游，由 Docker 直连下载；`/v2`、`/v2/` 直接返回 200。

默认域名均为示例，部署前必须替换。两个入口使用不同域名，分别转发到 Caddy 8080 和 8081，避免公共 ping 响应影响上游仓库认证。仓库入口当前支持上游 HTTPS 443，`upstreamHost` 只填写域名。

`gh-proxy.org` 的 Docker Hub 路径使用 `/v2/docker/...`；直接把它作为 `daemon.json` 的 `registry-mirrors` 根地址时，Docker 请求的 `/v2/library/...` 路径不能正常拉取。本 Chart 保留现有路径改写，并只让镜像层下载跳转到改写后的地址。

如果希望省略上游仓库的命名空间，可设置 `upstreamNamespace`，并填写 `auth.realmURL`。例如上游镜像是 `upstream.example.com/myteam/intelliconf:1.3.2`，将 `upstreamHost` 填为 `upstream.example.com`、`upstreamNamespace` 填为 `myteam`，就可拉取 `registry.example.com/intelliconf:1.3.2`。`auth.realmURL` 填写上游 `/v2/` 响应中 `WWW-Authenticate` 的 `realm` HTTPS 地址，必须包含路径且不带端口、查询参数或账号信息，例如 `https://dockerauth-cn-chengdu.aliyuncs.com/auth`。Caddy 将 Docker 的 GET 令牌请求转发到该地址，并把单段短仓库的 `scope` 改为完整路径；已有命名空间的完整镜像路径保持原样。该配置不处理 OAuth POST 表单中的 `scope`，也不改变上游返回的对象存储下载地址。

## Helm 安装

编辑 `values.yaml`，或通过参数覆盖：

```bash
helm upgrade --install registry-proxy ./charts/registry-proxy/1.0.3 \
  --namespace infra --create-namespace \
  --set ingress.host=registry.example.com \
  --set upstreamHost=registry-upstream.example.com \
  --set publicProxy.host=docker.example.com
```

使用命名空间简写时，再传入 `--set upstreamNamespace=myteam` 和 `--set auth.realmURL=https://auth.example.com/auth`；实际认证地址以该仓库返回的 `realm` 为准。阿里云成都的当前示例值为 `upstreamNamespace=luokuiai`、`auth.realmURL=https://dockerauth-cn-chengdu.aliyuncs.com/auth`，仓库域名仍须填写自己的 ACR 公网地址。

自动签发使用已有的 `ClusterIssuer/letsencrypt`。将两个实际域名解析到 Ingress 入口；如果签发器使用 HTTP-01，公网 80 端口需要可达。签发成功后，cert-manager 创建同命名空间的 `registry-proxy-tls` 和 `registry-proxy-public-tls` Secret。
自动签发时，两个入口最终使用的 TLS Secret 名称必须不同；留空时分别使用上述默认名称。

证书配置沿用 Komodo 的 Ingress 注解和 TLS Secret 方式。两个入口共用 `ingress.annotations`，默认包含 `traefik.ingress.kubernetes.io/router.tls: "true"`，自动签发和使用已有证书时都会启用 HTTPS 路由。可在该配置中补充 Traefik 入口等注解；证书签发统一由 `ingress.clusterIssuer` 管理，手动设置的 `cert-manager.io/issuer`、`cert-manager.io/cluster-issuer` 和 `kubernetes.io/tls-acme` 注解会被清除或覆盖。

使用已有证书时，清空 `ingress.clusterIssuer` 并指定同命名空间的 TLS Secret。若已有证书同时覆盖两个入口域名，两个入口可以填写相同的 Secret 名称：

```bash
helm upgrade --install registry-proxy ./charts/registry-proxy/1.0.3 \
  --namespace infra --create-namespace \
  --set ingress.host=registry.example.com \
  --set upstreamHost=registry-upstream.example.com \
  --set publicProxy.host=docker.example.com \
  --set-string ingress.clusterIssuer= \
  --set ingress.tls.secretName=my-existing-tls \
  --set publicProxy.tls.secretName=my-existing-public-tls
```

## Rancher 安装

本 Chart 位于 Git 仓库的 `charts/registry-proxy/1.0.3/`，无需生成 `index.yaml` 或上传 `.tgz` 包。

在 Rancher 的“应用 → 仓库 → 创建”中选择 Git 仓库，填写本仓库的 Git 地址和实际分支。同步完成后，在“应用 → Charts”搜索 `registry-proxy`，选择 `1.0.3`，安装命名空间选 `infra`。已有 `1.0.0`、`1.0.1` 或 `1.0.2` 安装时，在“已安装的应用”中升级到 `1.0.3`；若填写了上游命名空间，同时补齐“上游令牌认证地址”，并确认升级页面 YAML 中的 `image.tag` 为 `2.11.7-alpine`（Rancher 可能沿用旧版保存的 `2.11-alpine`）。公共代理启用时，把拉取机器可以直连的 HTTPS 上游放在“公共镜像上游地址”第一项。

Chart 包含 `questions.yaml`，安装页面可填写私有仓库代理域名、公共镜像代理域名、上游仓库域名、上游命名空间、上游令牌认证地址、Ingress Class、ClusterIssuer、TLS Secret、副本数，以及是否启用公共镜像代理。“公共镜像上游地址”列表对应 `publicProxy.upstreams`，可直接在表单中添加、删除或修改；至少保留一个 HTTPS 地址，不带路径，且须兼容现有 gh-proxy 路径规则。第一项用于镜像层直连下载，其他请求按列表顺序选择上游。CPU/内存在 `resources` 配置。

表单参照 Komodo 按“应用”“代理配置”“域名 / HTTPS”分组。两个代理域名、Ingress Class 和证书设置集中在“域名 / HTTPS”，关闭 Ingress 时隐藏对应字段；关闭公共代理时隐藏其上游、域名和证书字段。Ingress Class 和 ClusterIssuer 都使用集群资源下拉框；TLS Secret 名称与 Komodo 一样保留文本输入，以支持自动签发时的新名称及已有证书名称。使用已有证书时清空 ClusterIssuer 选择。

仓库域名默认值为示例，部署前必须替换。两个代理域名必须不同。公共上游默认第一项是 `https://gh-proxy.org`，拉取机器须能直连该地址。

## 行为与验证

- Caddy 监听容器内 HTTP 8080（仓库入口）和 8081（公共入口），不自行申请证书，不需要持久卷。
- 配置变化会改变 Pod 模板的校验和，由 Deployment 滚动更新加载新配置。
- readiness 使用 TCP 探测。未登录访问 Registry `/v2/` 通常返回 401。
- 未设置上游命名空间时，仓库入口保留上游 `WWW-Authenticate` 认证挑战；设置后，Caddy 将挑战中的认证地址指向自身，再把 GET 令牌请求转发到上游，并改写短仓库 `scope`。原有 `service` 值保持不变。
- 默认 Caddy 镜像固定为 `2.11.7-alpine`，以包含 `uri query` 定向改写参数的修复。
- 仓库入口向上游发送不带 `:443` 的 `Host: upstreamHost`，并去掉 `X-Forwarded-For`、`X-Forwarded-Host`、`X-Forwarded-Proto`，使阿里云 ACR 等上游看到与直接拉取更一致的请求。上游日志将记录代理节点地址，而不是通过这些头获取原客户端地址。
- 仓库入口只改写指向上游仓库自身的绝对 `Location`，保留路径和查询参数；对象存储等其他域名的跳转保持原样。
- Docker 客户端仍需能访问上游返回的对象存储地址。阿里云 ACR 个人版应填写 `crpi-...personal.cr.aliyuncs.com` 公网入口；若镜像层仍跳转到 `oss-cn-chengdu-internal.aliyuncs.com`，不能直接无条件改写为公网域名，因为 OSS 签名可能绑定 `Host`。设置 `upstreamNamespace` 不会改变该下载地址。
- 仓库入口可转发推送请求。命名空间简写只改写 GET 令牌请求；使用 OAuth POST 表单获取令牌的客户端需使用完整镜像路径。推拉权限仍取决于上游授权。
- 公共入口将 `/v2/library/nginx/...` 和 `/v2/nginx/...` 改写为 `/v2/docker/nginx/...`。镜像层 GET 请求返回 307，Docker 直接从 `publicProxy.upstreams` 第一项下载，镜像层字节不经过本 Chart 的 Caddy；清单、HEAD 等请求仍走 Caddy，按列表顺序使用上游和被动健康检查。
- 直连下载要求拉取机器能访问第一项上游的镜像层地址。该跳转不会使用 Caddy 的其他上游故障切换；对私有镜像或需要跨域传递认证头的上游不适用。当前默认上游对 `Range: bytes=0-0` 返回完整层文件，因此下载中断后可能从头重下，反复中断可能导致拉取失败。
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

配置 `upstreamNamespace` 和 `auth.realmURL` 后，再用 `docker pull registry.example.com/image:tag` 检查省略命名空间的拉取。仓库入口未登录返回带认证挑战的 401 属于正常流程；公共入口 `/v2/` 应返回 200。证书就绪、登录成功、公共镜像拉取以及私有镜像拉取和推送均需在实际集群验证。
