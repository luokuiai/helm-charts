# Komodo + MongoDB: Rancher Git Chart Repository

Locally maintained chart version `1.0.0`, with an English Rancher configuration form.
This version is based on antiantiops Komodo Chart `0.1.23`; see `charts/komodo/1.0.0/UPSTREAM.md`.

Directory layout:

```text
charts/komodo/1.0.0/
  Chart.yaml
  values.yaml
  questions.yaml
  app-readme.md
  templates/
docs/komodo/secrets.example.yaml
```

## 1. Add the files to Git

Place this directory's contents at the root of the Git repository and commit them.
Commit only the example Secret, never a `secrets.yaml` containing real passwords, database backups, or private keys.
The branch can be `main` or another name; the examples below use `main`.

## 2. Add the repository in Rancher

Go to **Apps → Repositories → Create**:

- Name: `komodo`
- Type: Git repository
- Git repository URL: your actual repository URL
- Branch: `main`, or your actual branch name

If the interface does not offer a Git repository type, use Rancher's YAML import to create the following ClusterRepo, replacing the URL:

```yaml
apiVersion: catalog.cattle.io/v1
kind: ClusterRepo
metadata:
  name: komodo
spec:
  gitRepo: REPLACE_GIT_REPOSITORY_URL
  gitBranch: main
```

After synchronization succeeds, search for Komodo in Charts and select version `1.0.0` from this repository.

## 3. Prepare one environment Secret

Create a single `komodo-env` Secret in your installation namespace. The migration commands below use `internal`.
It holds the complete Core environment, including the database username and password, JWT, Webhook, and OIDC settings.

Use `docs/komodo/secrets.example.yaml` to create a Generic Secret in Rancher, or replace all `REPLACE_...` placeholders before importing it.
Choose the database credentials yourself and set `KOMODO_DATABASE_USERNAME` and `KOMODO_DATABASE_PASSWORD`.
Core reads this environment Secret, and the chart maps the same two keys to MongoDB's `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD`.
There is no separate database credential Secret or username field in the form.
When reusing an initialized MongoDB volume, use its existing credentials; editing the Secret does not change the account in MongoDB.

The database address is `komodo-mongo:27017`; the default component name prefix is fixed at `komodo`.
If you change `fullnameOverride`, also update the database address in the Secret.
Reuse the existing OIDC, JWT, and Webhook credentials from the old `.env` where possible. Do not share these values in chat.
Keep `KOMODO_HOST` as `https://komodo.luokuiai.com`, the application's callback address.
If you change the hostname or HTTPS mode, update this value to the matching complete public URL yourself.

If you already created the earlier two-Secret setup, ensure `komodo-env` contains the two database credential keys before upgrading.
The default configuration no longer uses `komodo-mongo-auth`. Keep it until the migration is verified; do not delete an in-use Secret.

## 4. Start the normal Core container

Use the official CLI inside the normal Core container for migration.
In Rancher, upgrade the application with:

- Namespace: `internal`; release name: `komodo`.
- Komodo replicas: `1`.
- Shared environment Secret: `komodo-env`.
- Configuration and backup persistence: enabled, using the existing PVCs.
- Keep `KOMODO_DATABASE_DB_NAME=komodo` in the environment Secret; migration does not require renaming the database.

Wait for Core and MongoDB to be Ready.
Core may initialize records in `komodo`. The official restore upserts backup records and does not clear unrelated existing records.
Inspect any initialization records after restoration; do not assume restoration removes them. Do not use the new installation until verification is complete.

Use the same Core version as the old installation when possible. The default `moghtech/komodo-core:2` tag is floating.
Keep your already working MongoDB image version; this procedure does not change MongoDB FCV.

## 5. Export a native Komodo backup

For migrations between MongoDB versions, prefer Komodo's official backup and restore CLI.
The Core image already includes `km`; run it directly inside the normal Core container.
The examples below use namespace `internal`. Replace it if your installation uses another namespace.
Keep the target Core at one replica. Backup and configuration persistence must be enabled.

On the old Docker server, pause configuration changes and run:

```bash
docker exec -e KOMODO_CLI_BACKUPS_FOLDER=/tmp/komodo-migration-backup \
  komodo km database backup -y
```

Continue only after the backup completes successfully. Stop the old Core to prevent two instances from managing the same Periphery servers:

```bash
docker stop komodo
task_migration_dir=$(mktemp -d "$HOME/komodo-migration.XXXXXXXX")
docker cp komodo:/tmp/komodo-migration-backup/. "$task_migration_dir/backups"
docker cp komodo:/config/keys/. "$task_migration_dir/keys"
tar -C "$task_migration_dir/backups" -czf ~/komodo-backups.tar.gz .
tar -C "$task_migration_dir/keys" -czf ~/komodo-keys.tar.gz .
```

Copy both archives to the K3s host's home directory. Copy the complete native backup directory, including the top-level `Stats.gz`, not only its dated subdirectory.
These are Komodo-native backups; an existing `mongodump --archive` file cannot be passed to `km database restore`.
Retain the original MongoDB archive as a fallback.

## 6. Restore directly inside Core

On the K3s host, create an isolated directory for the imported backup and copy both archives into the normal Core Pod:

```bash
sudo k3s kubectl -n internal exec deployment/komodo -- mkdir -p /backups/migration /config/keys
sudo k3s kubectl -n internal exec -i deployment/komodo -- \
  tar -xzf - -C /backups/migration < ~/komodo-backups.tar.gz
sudo k3s kubectl -n internal exec -i deployment/komodo -- \
  tar -xzf - -C /config/keys < ~/komodo-keys.tar.gz
```

The restore target is the original database name, `komodo`. There is no database-name switch.
Confirm that this is the new installation's database; retain the old server and backup files.
The CLI reads credentials from the container environment populated by `komodo-env`:

```bash
sudo k3s kubectl -n internal exec deployment/komodo -- sh -c '
  export KOMODO_CLI_BACKUPS_FOLDER=/backups/migration
  export KOMODO_CLI_DATABASE_TARGET_ADDRESS="$KOMODO_DATABASE_ADDRESS"
  export KOMODO_CLI_DATABASE_TARGET_DB_NAME=komodo
  export KOMODO_CLI_DATABASE_TARGET_USERNAME="$KOMODO_DATABASE_USERNAME"
  export KOMODO_CLI_DATABASE_TARGET_PASSWORD="$KOMODO_DATABASE_PASSWORD"
  exec km database restore -y
'
```

This restores the most recent native snapshot in the imported directory. To select a specific snapshot,
append `--restore-folder YYYY-MM-DD_HH-MM-SS`, using its actual directory name.
Native restoration upserts records and does not clear unrelated documents already in the target database.
Both Core and the restore CLI use `komodo`. Keep the new installation unused during restoration.
Continue only if the restore completes without errors.

Official reference: https://komo.do/docs/setup/backup

## 7. Restart Core and verify the migration

Keep `KOMODO_DATABASE_DB_NAME=komodo` in the `komodo-env` Secret. Do not change the database name or credentials.
Restart the normal Core deployment to load the copied keys:

```bash
sudo k3s kubectl -n internal rollout restart deployment/komodo
sudo k3s kubectl -n internal rollout status deployment/komodo --timeout=180s
```

Keep Core replicas at `1`.
Verify the original accounts, resources, OIDC login, and Periphery connections before allowing new changes.
Review any extra initialization records: the official restore does not remove documents absent from the backup.
If restoration reports errors, preserve the files and inspect the errors before retrying or deleting data.
Retain the old server and original MongoDB archive until verification succeeds.

To expose the application by domain, use the **Domain / HTTPS** form group:

- Enable domain access (Ingress).
- Hostname: `komodo.luokuiai.com`, without a URL scheme or path.
- Ingress class: typically `traefik` on K3s. Leave empty only when a suitable default ingress class exists.
- HTTPS mode: `existing` for a TLS Secret already present in the installation namespace, or `cert-manager` for automatic issuance and renewal.
- TLS Secret name: the existing Secret, or the target name for cert-manager to create (default `komodo-tls`).
- In cert-manager mode, choose `ClusterIssuer` or `Issuer`, then select an existing resource from the **Certificate issuer name** dropdown.
  cert-manager must be installed and the issuer ready. An Issuer must be in the installation namespace; a ClusterIssuer can be shared.
  An Issuer in `cattle-system` cannot be directly referenced from another namespace.
  Issuer options are limited to the installation namespace. If no suitable issuer is listed, create one first.
  Rancher must support `reference[...]` questions and allow listing the resources; otherwise it may show a text fallback.

Configure DNS separately to point the hostname to the ingress endpoint.
For Let's Encrypt HTTP-01 validation, public port 80 must reach the ingress and the issuer must use a suitable ingress class.
The chart creates the Ingress and issuer annotation; cert-manager creates the Certificate and TLS Secret.
It does not install cert-manager or create an Issuer / ClusterIssuer.
The Rancher hostname's certificate does not automatically cover this hostname.
If you choose `disabled`, use an HTTP URL in `KOMODO_HOST`, unless HTTPS is provided by your existing external proxy.
When configuring TLS directly in YAML, leave `certificate.mode` as `disabled` and set `komodo.ingress.tls` instead.

Keep the existing PVCs when updating access settings.
Check that Core and MongoDB are Ready, the existing application data is present, and local login, OIDC login, and Periphery connections work.
The application Service is `komodo` on port `9120/TCP`. If Ingress remains disabled, continue using your existing external access setup.

## Rollback boundaries

If a problem occurs, first scale the new Core to `0` replicas and retain the PVCs, original dump, and old keys.
Confirm the new Core has stopped before restoring the old service.
If new writes have reached the new database, reconcile the old and new data before switching back.
These instructions do not uninstall the chart, delete PVCs, or clean up the old server.

## Validation

Local checks cover chart rendering and shell-command syntax. The commands in this guide use the normal Core deployment and the official CLI; they have not been run against your databases.
No connection to your Rancher was made. Live form interactions, DNS, certificate issuance, image pulls, OIDC login, and database restoration have not been tested.
See the delivery notes for local check results. Live cluster validation must be completed after deployment.
