# PostgreSQL 18

A locally maintained, single-instance chart starting at version `1.0.0`, using the official PostgreSQL image `postgres:18`.
`questions.yaml` is the filename Rancher uses for the configuration form.

## Installing in Rancher

1. Sync this Git chart repository, then search for `postgres` or `PostgreSQL 18`.
2. Select a namespace, such as `prod`, and a release name, such as `postgres`.
3. Enter the initial username, database name, and password in the form. Alternatively, select an existing Secret and specify its name and password key.
4. Storage defaults to `local-path` and `10Gi`. Leave the existing PVC name empty to provision a PVC and PV automatically.
5. Adjust CPU and memory settings for the expected workload, then install.

By default, the chart creates a StatefulSet, a ClusterIP Service, a headless Service, a password Secret, and a data PVC.
It runs a single instance; increasing replicas does not configure PostgreSQL replication.
It does not create an Ingress, domain, or certificate.

## Data volume

The official PostgreSQL 18 image uses a different data layout from PostgreSQL 17 and earlier:

```text
PVC root
└── 18/
    └── docker/                  # PGDATA: database files are stored here

PVC mount: /var/lib/postgresql
PGDATA:    /var/lib/postgresql/18/docker
```

The chart mounts the entire parent directory without `subPath`. PGDATA is not exposed as a form option.
For a release named `postgres`, the generated PVC is `data-postgres-0`.
The Pod reuses the same PVC when deleted and recreated. Under the default StatefulSet PVC retention behavior,
uninstalling the application also retains this volume.
Do not select additional PVC deletion options during uninstall or manually delete the corresponding PV or node directory.

The storage provisioner allocates the host directory for `local-path`; it is not a directory entered in the chart.
In Rancher, open **Storage → PersistentVolumeClaims**, find the PV bound to the PVC, and open that PV to inspect its actual path.
Alternatively, run the following on the K3s server, adjusting the release name and namespace as needed:

```bash
sudo k3s kubectl -n prod get pvc data-postgres-0
PG_PV=$(sudo k3s kubectl -n prod get pvc data-postgres-0 -o jsonpath='{.spec.volumeName}')
sudo k3s kubectl get pv "$PG_PV" -o yaml
```

Check the PV's `spec.hostPath.path` or `spec.local.path`; use the actual output as the source of truth.
`local-path` data belongs to that node and is not replicated when nodes are added.
A `10Gi` request does not enforce a hard quota on the local disk.

## Using an existing PVC

Set `persistence.existingClaim` to a PVC in the same namespace. The chart will not create a new PVC
and will ignore `persistence.storageClass` and `persistence.size`.
Stop the old instance using the volume before starting this instance.

Existing PostgreSQL 18 data must be located under `18/docker/` inside the PVC; otherwise, the instance may initialize a separate empty database.
If the old Pod used a different mount point or PGDATA, inspect the actual directory structure inside the PVC before migration.
PostgreSQL 17 or earlier data files cannot be started directly with PostgreSQL 18. Use a logical backup and restore or perform a supported major-version upgrade.

The StatefulSet storage template used to create PVCs cannot be changed directly.
After installation, do not switch the existing PVC name or storage class, or attempt to expand storage by changing the chart's capacity value.
Before expansion, check StorageClass support, back up the data, and handle the PVC separately.
The default `local-path` provisioner does not provide standard online volume expansion.
Reinstalling with a different release name generates a different PVC name. To reuse the original data, specify the original PVC name and use the original password.

## Passwords and initialization

- `auth.username` defaults to `postgres`. This initialization user has superuser privileges; create regular application users separately in PostgreSQL.
- Unless using an existing Secret, set `auth.password` through the Rancher form or a local values file that is not committed to Git.
- To use an existing Secret, set `auth.useExistingSecret: true`, `auth.existingSecret`, and `auth.secretKey`.
- The username, database name, and password apply only when the data directory is empty. Updating a Secret or Helm values does not change the password in an initialized database; change it within PostgreSQL.
- The password form field only masks its display. A directly entered password is still stored in the Helm release configuration and a Kubernetes Secret.
  Choose an existing Secret to keep the password out of Helm values. Base64 encoding in Kubernetes Secrets is not encryption.
- If initialization fails, inspect the logs first. Do not delete a PVC containing existing data without investigating.

## Connecting and checking status

For a release named `postgres` in namespace `prod`, the cluster-internal address is
`postgres.prod.svc.cluster.local:5432`. This Service is not exposed to the public internet.

```bash
sudo k3s kubectl -n prod get pods,pvc,svc -l app.kubernetes.io/instance=postgres
sudo k3s kubectl -n prod logs postgres-0
sudo k3s kubectl -n prod exec -it postgres-0 -- psql -U postgres -d postgres
```

Adjust the username and database name in the last command to match your settings.
Startup, readiness, and liveness probes use `pg_isready` to check the TCP listener.
The startup probe allows approximately 10 minutes for initialization.

Local validation using a placeholder password:

```bash
helm lint charts/postgres/1.0.0 --strict --set-string auth.password=lint-only-placeholder
helm template postgres charts/postgres/1.0.0 --namespace prod --set-string auth.password=lint-only-placeholder
```

## References

- [Official PostgreSQL image documentation, including PostgreSQL 18 PGDATA and volume changes](https://github.com/docker-library/docs/blob/master/postgres/README.md)
- [Kubernetes StatefulSet storage and PVC lifecycle](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [K3s storage](https://docs.k3s.io/storage)
