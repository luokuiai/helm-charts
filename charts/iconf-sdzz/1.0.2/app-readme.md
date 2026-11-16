# iconf-sdzz

默认镜像为 `harbor.luokuiai.com/iconf-sdzz:1.0.0`。先在安装命名空间创建 `iconf-sdzz-config` ConfigMap，
以 `application-prod.yml` 配置数据库、Redis、加密密钥及 S3，挂载至
`/app/config/`。修改后需重启工作负载。

默认启用 Spring 的 `prod` 环境，文件使用 S3。服务端口为 8080，
可选配置 Ingress。

可选择部署内置 Redis。启用后应用自动连接该 Redis；不启用时使用配置文件中的外部 Redis。
