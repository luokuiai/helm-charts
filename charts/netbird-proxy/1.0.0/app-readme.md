# NetBird Reverse Proxy

A standalone NetBird Reverse Proxy connected to an existing management service, with a Rancher configuration form.

- Set the management URL, proxy cluster domain, and proxy token from your NetBird cluster setup. A peer setup key is not a proxy token.
- All proxy configuration is injected through official environment variables. The token is read from a Kubernetes Secret.
- NetBird Proxy issues and renews certificates by default using ACME TLS-ALPN-01. No TLS Secret is required.
- Certificates persist on a retained PVC mounted at `/certs` by default. The mount path is also passed as `NB_PROXY_CERTIFICATE_DIRECTORY`.
- The default Traefik v3 TLS passthrough route shares port 443 with a `ClusterIP` Service. Traefik forwards encrypted traffic to NetBird, which handles HTTPS and ACME challenges.
- Use a dedicated proxy domain that does not contain the Rancher hostname beneath it. Point that domain and its wildcard DNS record at Traefik; public TCP 443 must reach NetBird unchanged.
- If Traefik has its own TLS challenge resolver, enable `allowACMEByPass` on its HTTPS entrypoint in the existing Traefik configuration. This is not a NetBird environment variable. See the chart README for the exact setting.
- Rancher keeps its own domain and certificate resources. This chart does not modify them or install a certificate manager.
- External certificates remain optional with `tls.mode=existingSecret`; provide a TLS Secret covering every service hostname in the installation namespace and renew it through your existing process.
- For a dedicated endpoint, disable the Traefik route and expose the Service through an L4 load balancer. `http-01` additionally requires public TCP 80 and is unavailable with the chart's TCP-only Traefik route.
- A second K3s ServiceLB on port 443 can conflict with Traefik; use the shared route or a dedicated load balancer address.
- Runs one non-root replica. Upgrades briefly interrupt traffic; additional TCP/UDP service ports are not provided by this chart.

For full environment variable mappings, client IP handling, and deployment examples, see the chart's `README.md`.
