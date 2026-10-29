# Helm Charts

A repository of Helm charts that Rancher can read directly from Git.
Each application is maintained separately, with multiple chart versions supported per application.

## Repository structure

```text
helm-charts/                         # Git repository root
├── charts/                          # Chart directory scanned by Rancher
│   ├── postgres/
│   │   └── 1.0.0/                   # PostgreSQL 18 + Rancher form + PVC
│   ├── openbao/
│   │   └── 1.0.0/                   # OpenBao standalone / Raft HA + domain + Rancher form
│   ├── casdoor/
│   │   └── 1.0.0/                   # Casdoor + external database + domain + Rancher form
│   ├── magpie/
│   │   └── 1.0.0/                   # Magpie gateway + Web UI + PVC + Rancher form
│   ├── silo/
│   │   └── 1.0.0/                   # Silo S3 storage + 1-16 nodes + Rancher form
│   ├── warpgate/
│   │   └── 1.0.0/                   # Warpgate + PostgreSQL + OIDC + S3 / PVC + Rancher form
│   ├── netbird-proxy/
│   │   ├── 1.0.0/                   # Original form-based configuration
│   │   ├── 1.0.1/                   # Environment Secret + ACME certificate PVC + Rancher form
│   │   └── 1.0.2/                   # Deploy-time Geo database download
│   ├── netbird-operator-network/
│   │   └── 1.0.0/                   # Operator routing + shared VPN ingress Service + Rancher form
│   ├── cert-manager-alidns-issuer/
│   │   └── 1.0.0/                   # AliDNS DNS-01 ClusterIssuer + Rancher form
│   ├── registry-proxy/
│   │   └── 1.0.0/                   # Private registry + public image proxies + Rancher form
│   └── komodo/
│       └── 1.0.0/                   # Matches version in Chart.yaml
│           ├── Chart.yaml
│           ├── values.yaml
│           ├── questions.yaml       # Rancher configuration form
│           ├── icon.png             # Bundled application icon
│           ├── app-readme.md
│           ├── README.md
│           ├── UPSTREAM.md
│           └── templates/
├── docs/
│   ├── komodo/
│   │   ├── migration.md
│   │   └── secrets.example.yaml
│   └── netbird-proxy/
│       ├── secrets.example.yaml     # Version 1.0.0 Token Secret
│       └── env-secret.example.yaml  # Version 1.0.1 environment Secret
└── .gitignore
```

`helm-charts` is the project and Git repository name. `charts` is the top-level directory used by Rancher Git chart repositories.
This Git-based setup does not require an `index.yaml` or packaged `.tgz` files.

## Available applications

| Chart | Chart version | Contents |
| --- | --- | --- |
| komodo | 1.0.0 | Komodo Core, MongoDB, PVCs, and a Rancher configuration form |
| postgres | 1.0.0 | PostgreSQL 18.6, persistent storage, environment Secret, and a Rancher configuration form |
| openbao | 1.0.0 | OpenBao 2.7.2, persistent standalone or 3 / 5 member Raft HA, domain / HTTPS, and a Rancher configuration form |
| casdoor | 1.0.0 | Casdoor v4.24.0, external PostgreSQL / MySQL, domain / HTTPS, and a Rancher configuration form |
| magpie | 1.0.0 | Magpie 0.1.1836 gateway and Web UI, persistent config, domain / HTTPS, and a Rancher configuration form |
| silo | 1.0.0 | Silo S3 storage, 1-16 nodes with independent PVCs, API / Console domains, HTTPS, and a Rancher configuration form |
| warpgate | 1.0.0 | Warpgate 0.30.2, external PostgreSQL, OIDC, S3 / local recordings, SSH / HTTP / database gateways, HTTPS, and a Rancher configuration form |
| netbird-proxy | 1.0.2, 1.0.1, 1.0.0 | Standalone NetBird Reverse Proxy, proxy-managed certificates, deploy-time Geo database download, Traefik TLS passthrough, and a Rancher configuration form |
| netbird-operator-network | 1.0.0 | NetworkRouter and NetworkResource for an existing NetBird Operator, with a namespace-scoped VPN ingress Service dropdown and a Rancher configuration form |
| cert-manager-alidns-issuer | 1.0.0 | Let's Encrypt DNS-01 ClusterIssuer for an existing AliDNS webhook, existing credential Secret selection, and a Rancher configuration form |
| registry-proxy | 1.0.0 | Caddy proxies for an upstream registry and public images, two Traefik HTTPS domains, and a Rancher configuration form |

Komodo optionally creates an Ingress through the Rancher form, with an existing TLS Secret or cert-manager certificate issuance.
Ingress is disabled by default. DNS, cert-manager, and DNS webhook installations are managed separately. AliDNS ClusterIssuers can be created through the `cert-manager-alidns-issuer` Chart.
See the [Komodo migration guide](docs/komodo/migration.md) for installation and migration steps.
Secret examples are available in [secrets.example.yaml](docs/komodo/secrets.example.yaml).

See the [PostgreSQL README](charts/postgres/1.0.0/README.md) for PostgreSQL 18 installation and data volume details.

See the [OpenBao deployment guide](docs/openbao/deployment.md) for single-node / multi-node installation, domain configuration, initialization, and unsealing. Requires Kubernetes 1.30+.

See the [Casdoor deployment guide](docs/casdoor/deployment.md) for external database Secrets, domain / HTTPS, and S3 / MinIO upload configuration. Casdoor creates no database server or file PVC.

See the [Magpie deployment guide](docs/magpie/deployment.md) for Web administration keys, persistent config, domain / HTTPS, and gateway client setup.

See the [Silo deployment guide](docs/silo/deployment.md) for single-node / distributed object storage, numeric node counts, per-node PVCs, and separate S3 API / Console domains.

See the [Warpgate deployment guide](docs/warpgate/deployment.md) for external PostgreSQL, environment Secrets, OIDC / Casdoor login, persistent recordings, domain / HTTPS, and native TCP protocol exposure.

See the [NetBird Reverse Proxy README](charts/netbird-proxy/1.0.2/README.md) for environment Secret settings, Geo downloads, certificate ownership, and sharing Rancher's Traefik entrypoint.

See the [NetBird Operator Network deployment guide](docs/netbird-operator-network/deployment.md) for routing a shared private ingress Service through NetBird, DNS aliases, and access policies. Install the official Operator separately and install this configuration Chart in the ingress Service's namespace.

See the [AliDNS ClusterIssuer deployment guide](docs/cert-manager-alidns-issuer/deployment.md) for a Rancher form to configure DNS-01 issuance, existing credential Secrets, webhook compatibility, and application certificate settings.

See the [Registry Proxy README](charts/registry-proxy/1.0.0/README.md) for the two proxy domains, upstream authentication, and certificate configuration.

## Adding an application

Place a complete chart under `charts/<app>/<chart-version>/`.
The existing charts are located at `charts/komodo/1.0.0/`, `charts/postgres/1.0.0/`, `charts/openbao/1.0.0/`, `charts/casdoor/1.0.0/`, `charts/magpie/1.0.0/`, `charts/silo/1.0.0/`, `charts/warpgate/1.0.0/`, `charts/netbird-proxy/1.0.2/`, `charts/netbird-operator-network/1.0.0/`, `charts/cert-manager-alidns-issuer/1.0.0/`, and `charts/registry-proxy/1.0.0/`.

- The `name` in `Chart.yaml` must match the application directory name.
- The version directory must match `version` in `Chart.yaml`.
- `appVersion` identifies the application version and is maintained separately from the chart version.
- Provide `questions.yaml` for a Rancher configuration form, with fields mapped to paths in `values.yaml`.
- Bundle the upstream application icon as `icon.png`. For this Git repository, set `icon` in `Chart.yaml` to `file://charts/<app>/<chart-version>/icon.png` so Rancher reads it from the repository.
- Place operating instructions and configuration examples under `docs/<app>/`.
- Never commit real passwords, private keys, or data backups to Git.

## Publishing a new version

Copy the previous chart into a new version directory, then update its `Chart.yaml` and templates.
For example, use `charts/komodo/1.0.1/`. Keep previously published versions to avoid replacing releases already in use.

Example local checks:

```bash
helm lint charts/komodo/1.0.0 --strict
helm template komodo charts/komodo/1.0.0 --namespace prod
```

## Adding the repository to Rancher

In Rancher, go to **Apps → Repositories → Create**, select a Git repository, and enter:

- Repository name: `helm-charts`
- Git repository URL: `https://github.com/luokuiai/helm-charts.git`
- Branch: `main`

Configure Git credentials if the repository is private.

After the repository syncs, search for `komodo`, `postgres`, `openbao`, `casdoor`, `magpie`, `silo`, `warpgate`, `netbird-proxy`, `netbird-operator-network`, `cert-manager-alidns-issuer`, or `registry-proxy` and select the desired chart version.

For new installations, the release name is editable; these charts do not force
`catalog.cattle.io/release-name`. Installed Helm releases keep their original
name during upgrades. A separate release can use another name; configure any
shared resource names and environment Secret references for that installation.
