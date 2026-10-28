# AliDNS ClusterIssuer

A Rancher form for a Let's Encrypt DNS-01 `ClusterIssuer`. Install the DEVmachine-fr `alidns-webhook` separately; this Chart creates only the issuer and references an existing Alibaba Cloud credential Secret. It installs no Pods, CRDs, webhook, credentials, or application certificates.

## Prerequisites

- Existing cert-manager and its `cert-manager.io/v1` CRDs.
- Existing DEVmachine-fr `alidns-webhook` Chart `0.8.3`, configured with the same `groupName` entered here. Other AliDNS implementations may use incompatible solver names or configuration fields.
- An existing credential Secret in cert-manager's **cluster resource namespace**, normally `cert-manager`. If cert-manager uses `--cluster-resource-namespace`, use that namespace instead. The namespace is not chosen by a field in `ClusterIssuer`.
- An Alibaba Cloud DNS zone and RAM credentials allowed to query domains and records and add/delete validation TXT records.

Install this Chart in the cluster resource namespace so Rancher's Secret dropdown lists the correct credentials. `ClusterIssuer` itself is cluster-scoped and is available to applications in any namespace.

## Rancher form

Search for **AliDNS ClusterIssuer**, select `1.0.0`, and normally choose namespace `cert-manager`.

| Field | Value |
| --- | --- |
| ClusterIssuer name | `letsencrypt-alidns`, or a distinct unused name |
| Let's Encrypt account email | Your real contact email; required |
| Alibaba Cloud DNS zone | Your public DNS zone, for example `luokuiai.com`; required |
| AliDNS credential Secret | Select an existing Secret, normally `alidns-secrets` |
| Let's Encrypt environment | `production`, or `staging` for untrusted test certificates |
| AliDNS webhook group name | Must match the installed webhook, for example `acme.luokuiai.com` |
| AccessKey ID Secret key | `access-token`, or your Secret's actual key name |
| AccessKey Secret Secret key | `secret-key`, or your Secret's actual key name |
| Alibaba Cloud API region | `cn-beijing` |

Only Secret names and key names are saved in Helm values. Enter the actual AccessKey values when creating the Secret in Rancher, not in this Chart.

Email and DNS zone intentionally have no valid defaults. Local rendering and linting require values:

```bash
helm lint charts/cert-manager-alidns-issuer/1.0.0 --strict \
  --set acme.email=admin@example.com --set alidns.dnsZone=example.com
helm upgrade --install cert-manager-alidns-issuer ./charts/cert-manager-alidns-issuer/1.0.0 \
  --namespace cert-manager \
  --set acme.email=YOUR_EMAIL --set alidns.dnsZone=luokuiai.com
```

The selector covers the configured zone and its subdomains. Other zones require another issuer release with a distinct issuer name. cert-manager creates the ACME account Secret automatically as `<issuer-name>-<environment>-account-key`.

See the [deployment guide](../../../docs/cert-manager-alidns-issuer/deployment.md) for prerequisites, application settings, and validation. See [UPSTREAM.md](UPSTREAM.md) for the exact webhook contract.
