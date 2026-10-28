# AliDNS ClusterIssuer

Create a Let's Encrypt DNS-01 issuer through a Rancher form. Existing cert-manager and the DEVmachine-fr AliDNS webhook are required. This Chart creates one cluster-wide `ClusterIssuer`; it does not install or upgrade either controller.

Install in cert-manager's cluster resource namespace, normally `cert-manager`. Select the existing AliDNS credential Secret, containing `ACCESS_TOKEN` for AccessKey ID and `SECRET_KEY` for AccessKey Secret. These key names are fixed; no key-name fields are required. Enter your email and the public DNS zone hosted by Alibaba Cloud. Match the required webhook group name to the existing webhook installation; it has no prefilled default. Let's Encrypt production is always used. Application domains can remain private in NetBird DNS; Alibaba Cloud is used to publish validation TXT records.

Applications use issuer kind `ClusterIssuer` and the name configured here, normally `letsencrypt-alidns`. VPN applications continue using Ingress Class `traefik-vpn`. Certificates and TLS Secrets are created separately in each application's namespace.

If an issuer with this name was already imported manually, choose a different name and update applications to use the new issuer. Do not install another owner over an existing resource. Keep the issuer installed while applications rely on it for issuance and renewal.
