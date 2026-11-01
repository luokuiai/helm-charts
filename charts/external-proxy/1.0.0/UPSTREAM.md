# References

This is a configuration chart for an existing Traefik, not a packaged proxy app.

- Kubernetes Services without selectors and EndpointSlice:
  https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors
- Traefik Kubernetes Ingress provider, service annotations and ExternalName:
  https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/ingress/
- Traefik ServersTransport, SNI and custom CA Secrets:
  https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/crd/http/serverstransport/
- ServersTransport API types:
  https://github.com/traefik/traefik/blob/master/pkg/provider/kubernetes/crd/traefikio/v1alpha1/serverstransport.go
- Forwarded headers trust:
  https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/
- Automatic ingress certificate and Secret creation:
  https://cert-manager.io/docs/usage/ingress/

Compatibility: Kubernetes 1.26+ and Traefik v3 with EndpointSlice access. HTTPS
upstreams additionally require Traefik CRDs and the kubernetesCRD provider.
