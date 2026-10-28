Based on the official OpenBao Helm Chart 0.30.5 (OpenBao 2.7.2).

Source: https://github.com/openbao/openbao-helm/releases/download/openbao-0.30.5/openbao-0.30.5.tgz

Archive SHA256: `d9f24bdfbfcce4418074b363b6d446a877e17397527796f270f70c765823b2b6`

Local chart version: 1.0.0. This is a locally maintained Rancher adaptation,
not an official OpenBao or Rancher release. No external chart dependencies
need to be downloaded at install time.

Retains the upstream templates, values schema, optional integrations, and
MPL-2.0 license. The original chart README is in `README.upstream.md`.

Local changes: Rancher questions and metadata; bundled official icon;
injector disabled by default; resource requests/limits; local-path data
storage; explicit PVC retention; parallel pod startup; Raft enabled for HA
with stable node IDs and retry-join addresses for all configured replicas;
Ingress certificate selection and validation. The standalone backend remains
the upstream PebbleDB default. The Rancher form supports 3 or 5 HA replicas.

Server image registry and repository are combined in one form field, defaulting
to `openbao/openbao` on Docker Hub. Server and Helm test Pods share image
resolution. Legacy `server.image.registry` values remain supported for existing
installations; a repository with an explicit registry takes precedence.

Icon: https://github.com/openbao/artwork/blob/main/color/openbao-single-color-square.png
