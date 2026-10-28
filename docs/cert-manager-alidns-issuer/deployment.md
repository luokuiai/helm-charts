# AliDNS ClusterIssuer deployment

## Existing components

Reuse the existing cert-manager installation. Install the DEVmachine-fr `alidns-webhook` Chart `0.8.3` separately from its Helm repository if it is not already installed:

```text
https://devmachine-fr.github.io/cert-manager-alidns-webhook
```

For the normal `cert-manager` namespace installation, set the webhook's values to:

```yaml
groupName: acme.luokuiai.com
certManager:
  namespace: cert-manager
  serviceAccountName: cert-manager
```

Adjust the namespace and ServiceAccount to the actual cert-manager installation. The group name is an API identifier and must match the issuer's form; no DNS record is required for it. Keep webhook and issuer upgrades separate.

## Credential Secret

In Rancher, create a generic Secret in cert-manager's cluster resource namespace, normally `cert-manager`:

| Setting | Value |
| --- | --- |
| Name | `alidns-secrets` |
| Key `access-token` | Alibaba Cloud AccessKey ID |
| Key `secret-key` | Alibaba Cloud AccessKey Secret |

Use a dedicated RAM identity with the required AliDNS permissions: `alidns:DescribeDomains`, `alidns:DescribeDomainRecords`, `alidns:AddDomainRecord`, and `alidns:DeleteDomainRecord`. Do not put credential values in Git or in this Chart's values.

For a `ClusterIssuer`, the credential lookup namespace is cert-manager's cluster resource namespace. If cert-manager has a custom `--cluster-resource-namespace`, create the Secret and install this issuer release there. The Chart does not change cert-manager's namespace or flags.

## Install through Rancher

Refresh this Git repository, select **AliDNS ClusterIssuer** `1.0.0`, and install in the namespace containing the credentials. Enter your email, the Alibaba-hosted DNS zone such as `luokuiai.com`, select the credential Secret, and verify the webhook group name. Keep `letsencrypt-alidns` unless that issuer name is already in use.

The release creates one `ClusterIssuer` with no `metadata.namespace`. cert-manager creates its ACME account Secret as `<issuer-name>-<environment>-account-key`; the Chart does not own that Secret.

If a manually imported issuer already has this name, Helm will not automatically adopt it. Choose a distinct new issuer name for this release and update application references. Do not delete a working issuer to make room for this Chart.

## Connect an application

In the application's Rancher form, enable Ingress and select:

| Field | Value |
| --- | --- |
| Ingress Class | `traefik-vpn` for VPN-only access |
| Host | Your application domain, for example `komodo.luokuiai.com` |
| Certificate mode | `cert-manager` |
| Certificate issuer kind | `ClusterIssuer` |
| Certificate issuer name | The issuer created by this release |
| TLS Secret name | An application-specific name, for example `komodo-tls` |

The application Ingress and TLS Secret belong to the application's namespace. An Ingress using `cert-manager.io/cluster-issuer` and `spec.tls` triggers certificate creation. One issuer can serve applications in multiple namespaces for the configured DNS zone and its subdomains.

Private application resolution remains in NetBird DNS. Alibaba Cloud DNS hosts the `_acme-challenge` TXT validation records; DNS-01 does not require exposing the application on public ports 80 or 443. The certificate must cover a domain you control, not the internal `k3s.netbird.internal` routing record. If NetBird serves a private version of your public zone, ensure it does not hide validation TXT records from cert-manager's DNS self-check.

## Verify and maintain

Check registration in Rancher's kubectl terminal:

```bash
kubectl get clusterissuer letsencrypt-alidns
kubectl -n infra get certificates,certificaterequests
kubectl -n infra get challenges.acme.cert-manager.io
```

Replace `infra` with the application namespace. `ClusterIssuer Ready=True` confirms ACME account registration; it does not prove webhook access or AliDNS permissions. The application's `Certificate Ready=True` and the expected TLS Secret confirm successful issuance.

Keep the issuer name stable during upgrades. Staging and production use separate account Secret names, and staging certificates are not browser-trusted. Uninstalling this Chart removes the issuer and prevents new issuance or renewal through that issuer. Keep the webhook, credentials, and issuer available while applications depend on them.
