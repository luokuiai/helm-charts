# Komodo + MongoDB

Includes Komodo Core, MongoDB, persistent storage, and a Rancher configuration form.

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
This address assumes release name `komodo`; a release named `komodo-a` uses
`komodo-a-mongo:27017`. Update `KOMODO_DATABASE_ADDRESS` in its environment
Secret to match. `fullnameOverride` can retain an explicit resource name prefix.

Optional domain access is available in the Rancher form under **Domain / HTTPS**.
Ingress is disabled by default. Enable it, enter the hostname, and select the ingress class
(usually `traefik` on K3s, or leave it empty to use the cluster default).
Keep `KOMODO_HOST` in `komodo-env` consistent with the complete public URL; the chart does not rewrite this Secret.

HTTPS modes:

- `disabled`: HTTP only, unless custom `komodo.ingress.tls` values are supplied in YAML.
- `existing`: use the named TLS Secret in the installation namespace. It must contain a certificate for the hostname.
- `cert-manager`: request and renew a certificate through an existing Issuer or ClusterIssuer.
  cert-manager must already be installed, and the issuer must be ready. An Issuer must be in the installation namespace;
  a ClusterIssuer can be shared. The chart creates the Ingress with the issuer annotation and target TLS Secret name;
  cert-manager creates the certificate and Secret. The chart does not install cert-manager or create issuers.

In cert-manager mode, select the issuer kind and choose an existing resource from the **Certificate issuer name** dropdown.
ClusterIssuers are listed across the cluster; Issuers are limited to the installation namespace.
The selector requires Rancher support for `reference[...]` question types and permission to list these resources.
If the list is empty, create a suitable issuer first. If the resource type is unavailable, Rancher may show a text fallback.

Create the DNS record separately, pointing the hostname to the ingress endpoint.
For Let's Encrypt HTTP-01 validation, the issuer must use a suitable ingress class and public port 80 must reach the ingress.
The Rancher hostname's certificate does not automatically cover Komodo's hostname.
Advanced YAML users can retain the existing `hosts`, `annotations`, and `tls` configuration.
Use either `certificate.mode` or the custom `tls` list for HTTPS, not both.

Add the Git repository containing this chart to Rancher before installation.
See `docs/komodo/migration.md` in the repository for detailed migration commands.
See this chart's `UPSTREAM.md` for its upstream source and local maintenance details.
