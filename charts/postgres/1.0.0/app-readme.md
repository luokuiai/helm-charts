# PostgreSQL 18

A single PostgreSQL 18 instance with an English configuration form, password Secret, ClusterIP Service, and persistent storage.

- Default image: `postgres:18`.
- On first installation, enter the initial administrator password or select an existing Secret in the same namespace.
- Defaults to the `local-path` storage class with a `10Gi` request; no manual PV creation is needed.
- The PVC is mounted at `/var/lib/postgresql`, with the data directory fixed at `/var/lib/postgresql/18/docker`.
- Runs one database instance. Multiple replicas alone do not configure replication or high availability.
- Does not configure a domain or expose ports outside the cluster.

For a release named `postgres` in namespace `prod`, the cluster-internal connection address is
`postgres.prod.svc.cluster.local:5432`.

The username, database name, and password are used only to initialize an empty data directory.
Changing the form does not update existing database accounts.
Check the directory layout before reusing a PostgreSQL 18 volume; PostgreSQL 17 or earlier data files cannot be used directly.

PVCs are retained by default, but do not select PVC deletion during uninstall.
`local-path` stores data on one node without replication across nodes.
`10Gi` is a storage request, not an enforced disk quota. Back up important data separately.

See the chart's `README.md` for full instructions and host volume path inspection.
