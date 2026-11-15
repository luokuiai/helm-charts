# iconf-sdzz

填写已发布的镜像地址。先在安装命名空间创建 `iconf-sdzz-config` ConfigMap，
以 `application-prod.yml` 配置数据库、Redis、加密密钥及 S3，挂载至
`/app/config/`。修改后需重启工作负载。

默认启用 Spring 的 `prod` 环境，文件使用 S3。服务端口为 8080，
可选配置 Ingress。
