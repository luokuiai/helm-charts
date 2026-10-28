# Casdoor

Deploy Casdoor v4.24.0 with an external PostgreSQL or MySQL database.
The image uses one complete field: `casbin/casdoor:v4.24.0`.
Create a dedicated database first, then select the environment Secret
(default `casdoor-env`) containing `dataSourceName` and other Casdoor variables.
Use `initAdminPassword` for a new installation's initial administrator password;
it does not reset an existing account. Restart the Deployment after updating
its environment Secret.

Use **Domain / HTTPS** to configure the hostname, Ingress Class, and an
existing TLS Secret or cert-manager issuer. The public origin is derived from
Ingress unless an override is supplied.

For uploads, configure an S3 / MinIO provider in Casdoor, or enable
**Initialize providers from a Secret** and select a Secret containing
`init_data.yaml`. Silo uses the MinIO provider type. The initialization file
contains provider settings and S3 access keys; associate the provider with the
applications that upload files. Provider settings are stored in the external
database. No file PVC or bucket is created. Returned file URLs must be accessible
to browsers; an internal S3 endpoint alone does not provide public file access.

Enable **Caddy file proxy** to serve the dedicated bucket through a separate
**File proxy hostname**, sharing the existing Ingress Class and HTTPS settings.
Both containers read `casdoor-env`; add `S3_ENDPOINT` and `S3_BUCKET` for Caddy.
Place `init_data.yaml` in that same Secret and select it for provider initialization
to configure the provider without using the admin console. Its Domain is the
file proxy origin; its bucket and Path prefix match `S3_BUCKET`.
Keep Silo's API internal and grant anonymous `s3:GetObject` only on the dedicated
upload bucket. Caddy permits object GET/HEAD only. An existing certificate must
cover both the Casdoor and file hostnames.
