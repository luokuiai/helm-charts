# External Proxy

Use an existing Traefik to expose an external HTTP / HTTPS application through
an arbitrary domain. This chart creates routing resources, with no proxy pod,
image, PVC or application credentials. Install one release per domain/backend.

```text
VPN client -> existing VPN router -> traefik-vpn -> external backend
```

The default configuration is an example only: `proxy.example.com` routes to
`192.0.2.10:80`. Replace both before installation. DNS and network connectivity
are managed separately. This chart does not register the external host as a
Kubernetes node or create a tunnel.

Choose frontend HTTP, an existing TLS Secret, or automatic cert-manager issuance
at installation. In cert-manager mode, select an existing Issuer / ClusterIssuer;
cert-manager creates and renews the certificate and its `<release>-tls` Secret
automatically. No issuer is hardcoded. A working cert-manager installation and
issuer are prerequisites for that mode. HTTP is the initial form default.

See [the deployment guide](../../../docs/external-proxy/deployment.md) for the
Rancher form, Magpie / remote Traefik examples, and HTTPS settings.

## Behavior and prerequisites

- Choose an existing Traefik IngressClass; the default is `traefik-vpn`.
- IP backends use a selectorless ClusterIP Service and EndpointSlice. IPv6
  backends require IPv6 Services to be enabled in the cluster.
- DNS backends use ExternalName and require
  `providers.kubernetesIngress.allowExternalNameServices: true` on the selected
  Traefik release. This chart does not change that release.
- HTTPS backends require the `traefik.io/v1alpha1` ServersTransport CRD and the
  Traefik `kubernetesCRD` provider. Upstream certificates are verified. Set an
  optional SNI name and CA Secret (`ca.crt` or `tls.ca`) for private certificates.
- `original` Host mode preserves the request Host. HTTPS SNI defaults to the
  configured ingress hostname. `backend` mode uses the backend address instead.
- Authorization, API-key headers, path, query, body, streaming and WebSocket
  handling use Traefik's native proxy behavior. This chart adds no header or
  path rewriting middleware. Existing entrypoint middleware can still affect
  requests; hop-by-hop headers are managed by the proxy.
- Forwarded client IP headers follow Traefik's trust configuration. On a second
  Traefik at the backend, configure `forwardedHeaders.trustedIPs` for the actual
  upstream proxy address if the original client IP is needed. Do not blindly
  trust forwarded headers from arbitrary sources.

Any restrictions on the backend must allow the actual source seen from Traefik
(possibly a node / NAT egress address). Only HTTP / HTTPS is supported; this is
not a generic TCP / UDP tunnel. No backend health probe is installed by the chart.

## Verification

```bash
helm lint charts/external-proxy/1.0.0 --strict
uv run --with pyyaml python tests/external-proxy/test_chart.py
```
