# kkFileView deployment

Install **kkFileView 1.0.0** from Rancher Apps after syncing this repository.

1. Keep `harbor.luokuiai.com/kkfileview:5.0.2`, or supply another complete image
   reference. For private Harbor, choose an existing image-pull Secret in the same
   namespace. Verify the mirror supports the cluster nodes' architectures.
2. Select an existing environment Secret (default `kkfileview-env`) or clear the
   field if not using one. Environment settings are
   loaded at Pod startup; restart the Deployment after changing the Secret. Do not
   change the application port from 8012 through this Secret.
3. By default, access is cluster-internal. Optionally enable Ingress and configure
   its class, hostname and certificate. Restrict access to authorized clients and
   configure trusted document sources.

Kubernetes automatically schedules the Pod on an eligible node.

The Chart creates one Deployment and one ClusterIP Service. It does not create a
PVC; preview files and cached data in the container are lost on replacement.
File conversion requires writable runtime storage and sufficient CPU and memory.

For local diagnostic access without Ingress:

```sh
kubectl -n <namespace> port-forward svc/<release> 8012:8012
```

Visit `http://localhost:8012`. This runs on the machine where kubectl is executed.

The requested Harbor mirror image has not been inspected or security-verified.
Avoid unrestricted public access and untrusted preview sources. A TCP probe only
checks whether the application's port is listening, not whether conversion works.
