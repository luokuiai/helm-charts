# Redis

Redis 单副本，Service 仅在集群内开放 6379。默认不设置密码，务必限制可连接的工作负载。
如需密码或自定义配置，在同一命名空间创建 Secret，添加键 `redis.conf`：

```conf
requirepass "替换为你的强密码"
maxmemory 512mb
maxmemory-policy noeviction
```

在 Rancher 表单选择该 Secret。Redis 的内存上限应小于容器内存上限，预留进程开销。
默认禁用 AOF 和 RDB，不创建 PVC；Pod 重建后数据丢失，适用于可重建的缓存。
独立安装时可在表单启用持久化，使用新建或已有 PVC 并开启 AOF。
已创建的 StatefulSet 不支持直接修改 PVC 模板；切换持久化方式需规划迁移，
并保留已有 PVC 和备份。使用 local-path 时数据位于节点本地。
更新配置 Secret 后需重启 Pod，并在修改密码时同步更新客户端。TCP 探针不验证认证或读写。
默认使用官方 Redis 8 镜像；当前版本不提供高可用。
