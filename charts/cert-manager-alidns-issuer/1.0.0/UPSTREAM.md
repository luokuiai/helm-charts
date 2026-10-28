# Upstream compatibility

Chart version: `1.0.0`. `appVersion: 0.8.3` identifies the separately installed DEVmachine-fr AliDNS webhook Chart whose configuration contract was verified. It is not a bundled dependency or a cert-manager version.

- [Webhook repository and ClusterIssuer example](https://github.com/DEVmachine-fr/cert-manager-alidns-webhook)
- [Webhook configuration decoder and Secret lookup](https://github.com/DEVmachine-fr/cert-manager-alidns-webhook/blob/master/main.go)
- [Webhook values and group name](https://github.com/DEVmachine-fr/cert-manager-alidns-webhook/blob/master/charts/alidns-webhook/values.yaml)
- [cert-manager issuer and ClusterIssuer scope](https://cert-manager.io/docs/concepts/issuer/)
- [cert-manager DNS-01 solver selection](https://cert-manager.io/docs/configuration/acme/dns01/)
- [cert-manager Ingress integration](https://cert-manager.io/docs/usage/ingress/)

The solver name is `alidns-solver`; its config references `accessTokenSecretRef`, `secretKeySecretRef`, and `regionId`. `accessTokenSecretRef` contains Alibaba Cloud AccessKey ID, despite the upstream token terminology. Secrets are loaded from the challenge's resource namespace.

The bundled icon is an original certificate and verification-check design.
Its editable source is `icon.svg`; `icon.png` is rendered at 512 × 512 for Rancher.
