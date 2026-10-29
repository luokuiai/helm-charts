# Warpgate

Deploy Warpgate 0.30.2 with external PostgreSQL and a Rancher form.
Create a dedicated PostgreSQL database/user, then select `warpgate-env`, containing
`WARPGATE_DATABASE_URL` and `WARPGATE_ADMIN_PASSWORD`, before installation.
The initial username is `admin`; the initial credential variable does not reset an
existing account. New installations enable local session recording with a retained
`1Gi` PVC mounted at `/data`. Users, credentials and SSH keys remain in PostgreSQL.
Pod restarts reuse the PVC, recording files and retained backend TLS certificate;
native setup does not recreate an existing administrator or SSH keys.

For OIDC, enable **OpenID Connect login**, enter the provider's exact Issuer URL
and Client ID, and add `WARPGATE_OIDC_CLIENT_SECRET` to the same environment Secret.
It must contain the raw, single-line Client Secret. Casdoor is supported through
the generic OIDC provider. Register this exact redirect URI at the provider:

`https://<warpgate-hostname>/@warpgate/api/sso/return`

Automatic creation of OIDC users is optional and disabled by default. Otherwise,
bind their provider name and email to existing Warpgate users. Grant target
access with Warpgate roles separately. Administrator permissions are managed in
Warpgate, not through OIDC role mappings.

Enable Ingress, choose the Ingress Class and matching controller type, and select
an existing TLS certificate or cert-manager issuer. K3s normally uses Traefik;
its ServersTransport CRD is required. The chart configures certificate verification
for Warpgate's HTTPS backend. HTTP Ingress handles the Web UI and HTTP gateway;
SSH and database gateways use the TCP Service ports.

Recording is optional. **Enable session recording on first setup** and **Retain
local data (PVC)** are enabled by default (size `1Gi`). Turning recording off
leaves persistence enabled for configuration and certificates. Existing
databases keep their recording setting: change it
in Warpgate's admin UI. Disabling recording does not disable gateway access or OIDC.

**Persistence** controls the local data PVC for configuration, certificates,
local recordings and active S3 upload buffers. It is independent of recording
and remains configurable even when recording is disabled.

In **Session recording**, choose whether to record sessions. Leave
**Use S3 instead of local recording storage** disabled for local recordings;
enable it to show the S3 settings.

For S3 / Silo recordings, enable **Use S3 instead of local recording storage**, enter the bucket,
endpoint, region and prefix, and add `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
to the same Secret. Disable **Retain local data (PVC)** for a temporary `emptyDir`
buffer. The S3 endpoint must be reachable by playback browsers, including over a
private network or VPN; allow the Warpgate origin in bucket CORS. Completed
recordings use signed GET links; unfinished buffers can be lost with the Pod.
S3 settings are reapplied at each startup; existing recordings are not moved.

Restart the Deployment after changing the environment Secret. PostgreSQL stores
users, credentials and SSH keys; the retained PVC stores configuration, certificates
and local recordings (or active S3 buffers). Back up the selected recording store,
PostgreSQL and the environment Secret along with any credential
encryption key. This chart supports one replica and creates no database server.
