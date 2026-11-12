# kkFileView

Locally maintained Rancher Helm Chart for kkFileView. Default image:
`harbor.luokuiai.com/kkfileview:5.0.2`. The application uses TCP port `8012`.

Kubernetes automatically schedules the Pod on an eligible node.

Select an existing image-pull Secret for private Harbor access if required, and
optionally select an existing environment Secret in the release namespace. The
image controls startup and default configuration; keep its service port at
8012. The Chart does not create persistent storage: converted files and cached
previews in the container can disappear on replacement. Configure application
settings and resource limits for your documents and workload.

Ingress is disabled by default. An optional Ingress supports a class, hostname,
existing TLS Secret, or cert-manager issuer. Protect the preview service with
appropriate network access controls and limit which document sources it can fetch.
The security status and contents of the specified Harbor image have not been
verified. Review them and verify its version and architecture before deployment.

```sh
helm lint charts/kkfileview/1.0.0 --strict
helm template kkfileview charts/kkfileview/1.0.0 --namespace files
```

See [deployment guidance](../../../docs/kkfileview/deployment.md).
