# Redis

默认不设置密码，应用通过集群内 Service 的 6379 端口连接。如需密码，可选择
包含 `redis.conf` 文件的 Secret，通过 `requirepass` 设置。默认启用 AOF 并使用
PVC，单副本不提供高可用。Secret 更新后需重启 Pod。
