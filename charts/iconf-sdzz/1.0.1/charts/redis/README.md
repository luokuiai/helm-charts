# Redis

Redis 单副本，Service 仅在集群内开放 6379，AOF 数据写入 PVC 的 `/data`。
默认不设置密码，务必限制可连接的工作负载。若需要密码或自定义配置，在同一
命名空间创建 Secret，添加一个键 `redis.conf`，内容例如：

```conf
requirepass "替换为你的强密码"
maxmemory 512mb
maxmemory-policy noeviction
```

在 Rancher 表单选择该 Secret，客户端使用其中设置的密码。请使用兼容 Redis
配置文件语法的密码；不要将真实密码提交到 Git。Chart 强制监听 6379、使用
`/data` 和开启 AOF。Redis 内存上限要小于容器内存上限，为进程开销和 AOF
重写预留空间。

选择已有 PVC 或新建 PVC。StatefulSet 新建的 PVC 默认在卸载时保留，
`local-path` 数据位于节点本地，节点故障无法自动迁移；删除 PVC 会删除数据。
更新配置 Secret 后需手动重启 Pod；更改密码后也需同步更新客户端。
TCP 探针只检查端口是否可连接，不验证认证和数据读写。单机不提供高可用，
PVC 和 AOF 不替代备份。默认镜像需集群能从 Docker Hub 拉取，也可填写私有镜像。
