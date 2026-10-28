# OpenBao

Deploy one persistent standalone node or a 3 / 5 replica Raft cluster.
Requires Kubernetes 1.30+. HA requires one schedulable Kubernetes node and
one data PVC per replica. Default storage class: `local-path`; size: `10Gi`.

The image repository is one field, defaulting to `openbao/openbao` on Docker Hub.
Enter a full registry/repository path for a mirror; the tag is configured separately.

Use **Domain / HTTPS** to configure a hostname, Ingress Class, and certificate.
Choose an existing TLS Secret or an existing cert-manager Issuer / ClusterIssuer.
Configure DNS separately. HTTPS terminates at the Ingress; the backend uses HTTP.

After installing, initialize only node 0 and unseal each node with the same
unseal keys. Pods stay unready until initialized and unsealed. Keep unseal
keys and the initial root token securely outside the cluster.

Choose standalone or HA before installation. Switching an existing installation
between these storage backends requires a separate data migration.
Data PVCs are retained on uninstall and scale-down.
