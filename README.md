# Helm Charts

A repository of Helm charts that Rancher can read directly from Git.
Each application is maintained separately, with multiple chart versions supported per application.

## Repository structure

```text
helm-charts/                         # Git repository root
├── charts/                          # Chart directory scanned by Rancher
│   ├── postgres/
│   │   └── 1.0.0/                   # PostgreSQL 18 + Rancher form + PVC
│   ├── netbird-proxy/
│   │   ├── 1.0.0/                   # Original form-based configuration
│   │   ├── 1.0.1/                   # Environment Secret + ACME certificate PVC + Rancher form
│   │   └── 1.0.2/                   # Deploy-time Geo database download
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
| postgres | 1.0.0 | PostgreSQL 18, persistent storage, password Secret, and a Rancher configuration form |
| netbird-proxy | 1.0.2, 1.0.1, 1.0.0 | Standalone NetBird Reverse Proxy, proxy-managed certificates, deploy-time Geo database download, Traefik TLS passthrough, and a Rancher configuration form |
| registry-proxy | 1.0.0 | Caddy proxies for an upstream registry and public images, two Traefik HTTPS domains, and a Rancher configuration form |

Komodo optionally creates an Ingress through the Rancher form, with an existing TLS Secret or cert-manager certificate issuance.
Ingress is disabled by default. DNS, cert-manager installation, and Issuer / ClusterIssuer creation are managed separately.
See the [Komodo migration guide](docs/komodo/migration.md) for installation and migration steps.
Secret examples are available in [secrets.example.yaml](docs/komodo/secrets.example.yaml).

See the [PostgreSQL README](charts/postgres/1.0.0/README.md) for PostgreSQL 18 installation and data volume details.

See the [NetBird Reverse Proxy README](charts/netbird-proxy/1.0.2/README.md) for environment Secret settings, Geo downloads, certificate ownership, and sharing Rancher's Traefik entrypoint.

See the [Registry Proxy README](charts/registry-proxy/1.0.0/README.md) for the two proxy domains, upstream authentication, and certificate configuration.

## Adding an application

Place a complete chart under `charts/<app>/<chart-version>/`.
The existing charts are located at `charts/komodo/1.0.0/`, `charts/postgres/1.0.0/`, `charts/netbird-proxy/1.0.2/`, and `charts/registry-proxy/1.0.0/`.

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

After the repository syncs, search for `komodo`, `postgres`, `netbird-proxy`, or `registry-proxy` and select the desired chart version.
