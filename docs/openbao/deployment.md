# Deploying OpenBao from Rancher

Add this Git repository to Rancher Apps and select `openbao` version `1.0.0`.
The default server image is `openbao/openbao:2.7.2`; Kubernetes 1.30 or newer is required.

## Choose the image

The form has one **OpenBao image** field, defaulting to
`openbao/openbao:2.7.2` on Docker Hub. Include the version in the same field,
such as `quay.io/openbao/openbao:2.7.2` or
`registry.example.com/team/openbao:2.7.2`. A reference without a tag uses the
chart's pinned version, `2.7.2`. The default pull policy is `IfNotPresent`.

Old values with `server.image.registry` and `server.image.tag` remain supported
when the corresponding parts are omitted from the full image reference.
If reusing earlier values, enter `docker.io/openbao/openbao:2.7.2` to explicitly
override both legacy fields, or remove the old overrides from the release values.

## Choose the deployment mode

For one persistent node, leave **Enable multi-node Raft cluster** disabled.
The StatefulSet has one replica and uses the upstream PebbleDB backend.

For HA, enable that option and enter **3** or **5** replicas. The chart uses
integrated Raft storage, stable pod-based node IDs, retry-join addresses,
and a PodDisruptionBudget. Each replica requires a separate schedulable
Kubernetes node because the chart retains required pod anti-affinity.
Three replicas tolerate one unavailable voting member; five tolerate two.

Select the storage class and initial capacity per replica. `local-path` is
the default, matching the other charts in this repository. Its data remains
on the assigned Kubernetes node; it does not replicate a volume. Raft
replicates data between HA members. Leave the class empty to use the
cluster's default class instead. Requests and limits apply to each replica.

Choose the storage mode before initializing. Standalone and HA use different
backends. Do not change modes on an existing release as a migration shortcut.
Take a backup and plan a separate storage migration. Resize existing PVCs
through Kubernetes and the storage provider; changing the initial size can
fail because StatefulSet volume claim templates are immutable.

## Configure the domain

Enable **Domain / HTTPS**, enter a hostname such as `bao.example.com`, and
select an existing Ingress Class (`traefik` is common on K3s). Point the DNS
record to the Ingress controller's external address.

Choose an HTTPS mode:

- `disabled`: no TLS configuration is added. Use only on a trusted test network.
- `existing`: provide the name of an existing TLS Secret in the release namespace.
- `cert-manager`: select an existing, ready Issuer or ClusterIssuer and provide
  a TLS Secret name for cert-manager to create. An Issuer must be in the release
  namespace. cert-manager and the issuer must already be installed.

This setup terminates TLS at the Ingress. The OpenBao API listener and
Ingress backend use HTTP inside the cluster. If end-to-end TLS or client
certificate authentication is required, configure the upstream listener,
mounts, retry-join TLS options, and controller settings separately through
advanced YAML. Setting only `global.tlsDisable=false` is insufficient.

In HA mode the Ingress routes to the active service. Initialize and unseal
through `kubectl exec` first; the Ingress may return 503 until a leader is ready.
Afterward the UI is at `https://bao.example.com/ui/` and the API at `/v1/`.

Example values for a new HA release:

```yaml
server:
  ha:
    enabled: true
    replicas: 3
  dataStorage:
    storageClass: local-path
    size: 10Gi
  ingress:
    enabled: true
    ingressClassName: traefik
    hosts:
      - host: bao.example.com
        paths: ["/"]
    certificate:
      mode: existing
      secretName: openbao-tls
```

For standalone, set `server.ha.enabled: false`; the domain options are identical.

## Initialize and unseal

The following commands assume release name `openbao` and namespace `secrets`.
If you use another release name, find the StatefulSet pod names with
`kubectl -n secrets get pods` and substitute them below.

```bash
helm install openbao charts/openbao/1.0.0 \
  --namespace secrets --create-namespace

# Run exactly once, on node 0. Store the output securely outside the cluster.
kubectl -n secrets exec -it openbao-0 -- bao operator init

# Repeat this command with different unseal keys until the threshold is met.
# The interactive prompt avoids putting keys in shell history.
kubectl -n secrets exec -it openbao-0 -- bao operator unseal
```

For HA, install with `--set server.ha.enabled=true` (or the example values).
Initialize only `openbao-0`, then unseal it. Retry-join brings the other nodes
into the same cluster. Unseal each remaining pod with the same keys:

```bash
kubectl -n secrets exec -it openbao-1 -- bao operator unseal
kubectl -n secrets exec -it openbao-2 -- bao operator unseal
# For five replicas, also unseal openbao-3 and openbao-4.
```

Repeat unseal per pod until the threshold is met. If a peer has not joined,
allow retry-join to complete and retry unsealing. Do not run `operator init`
on the other nodes: that would create independent clusters.
Check pod readiness and `bao status` on each member. To inspect membership,
log in interactively on node 0 and run:

```bash
kubectl -n secrets exec -it openbao-0 -- bao login
kubectl -n secrets exec -it openbao-0 -- bao operator raft list-peers
```

The default seal requires manual unsealing again after each pod restart.
Auto-unseal is an advanced upstream setting and is outside this form.
Helm/Rancher may report a readiness timeout before you finish initialization;
pods are still created and can be initialized with the commands above.

## Upgrades and data retention

The upstream StatefulSet uses `OnDelete` updates. After a Helm upgrade,
restart and unseal one member at a time, verify it rejoins, and preserve
Raft quorum. Do not restart all members together.

PVC retention is explicitly set to `Retain` on uninstall and scale-down.
Back up data before upgrades, removal, or membership changes. Retained PVCs
must be managed manually; deleting a namespace can delete them too.
Scaling down an initialized Raft cluster requires deliberate Raft membership
maintenance and is not handled automatically by editing the replica count.
The form is intended for choosing the initial 3 / 5 member topology.
