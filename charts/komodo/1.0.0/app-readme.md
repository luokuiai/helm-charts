# Komodo + MongoDB

Includes Komodo Core, MongoDB, persistent storage, and an English Rancher configuration form.

Normal installations start one Core replica.

Configuration and backup PVCs are retained when Helm uninstalls the application.
Upgrade an existing installation to this chart before uninstalling it to apply this policy.
Retained PVCs must be managed or deleted manually after uninstall; namespace deletion still removes them.
Optional repository-cache PVCs are disposable and are removed during uninstall.

For migration, use the official `km` CLI inside the normal Core container and keep the database name `komodo`.
Copy the native backup and original keys, run the restore, and restart Core to load the copied keys.
The restore upserts backup records; it does not clear unrelated records already in the database.
Check any records created during first startup rather than assuming the restore removes them.

Create one `komodo-env` Secret in the installation namespace.
Include `KOMODO_DATABASE_USERNAME`, `KOMODO_DATABASE_PASSWORD`, and the existing JWT, Webhook, and OIDC settings.
Both MongoDB and Core read the database credentials from this Secret; enter its name in the installation form.
Choose the username and password yourself. When reusing an initialized MongoDB volume, use its existing credentials.
Reuse the existing environment settings, including OIDC and JWT credentials. Set the database address to `komodo-mongo:27017`.

Optional domain access is available in the **Domain / HTTPS** form group.
Enable Ingress, enter the hostname, and select the ingress class (usually `traefik` on K3s).
Choose HTTPS mode `existing` for a TLS Secret in the installation namespace,
or `cert-manager` to request and renew a certificate through an existing Issuer or ClusterIssuer.
cert-manager and a ready issuer must already exist; an Issuer must be in the installation namespace.
Choose the issuer kind, then select an existing resource from the **Certificate issuer name** dropdown.
Issuer options are limited to the installation namespace. If no suitable issuer is listed, create one first.
The chart does not install cert-manager, create issuers, or configure DNS.
Point DNS to the ingress endpoint and keep `KOMODO_HOST` in `komodo-env` consistent with the complete public URL.
Ingress is disabled by default; enable it after restoring the database and restarting Core.
