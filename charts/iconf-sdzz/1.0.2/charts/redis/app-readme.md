# Redis

Redis 单副本，默认不设置密码。如需密码，可选择包含 `redis.conf` 的 Secret，
通过 `requirepass` 设置。服务仅在集群内部开放 6379。
默认禁用磁盘持久化，Pod 重建后数据丢失；独立安装可选启用 PVC 和 AOF。
更新配置 Secret 后需重启 Pod。
