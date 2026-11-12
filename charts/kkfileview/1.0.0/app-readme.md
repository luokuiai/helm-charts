# kkFileView

默认镜像为 `harbor.luokuiai.com/kkfileview:5.0.2`，服务端口为 8012。
工作负载由 Kubernetes 自动选择可调度节点。
私有 Harbor 需要认证时，选择已有的镜像拉取 Secret。

默认只创建集群内部 Service。按需启用 Ingress，选择入口类并配置证书。
Chart 不创建 PVC；Pod 替换时，容器里的预览文件和缓存可能丢失。

指定 Harbor 镜像的内容和安全状态尚未验证。部署前请核实镜像，并限制访问和
可预览的文件来源。
