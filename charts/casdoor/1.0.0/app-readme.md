# Casdoor

Deploy Casdoor v4.24.0 with an external PostgreSQL or MySQL database.
Create a dedicated database first. Enter connection details in the form,
or select an existing Secret with a `dataSourceName` key.

Database credentials are mounted through a Secret-backed environment variable.
Form passwords are also retained in Helm values; use an existing Secret to
keep credentials out of release values.

Use **Domain / HTTPS** to configure the hostname, Ingress Class, and an
existing TLS Secret or cert-manager issuer. DNS, ingress controllers, and
cert-manager are managed separately. The public origin is derived from
Ingress unless an override is supplied.

Uploads can use S3 / MinIO. Configure the storage provider in Casdoor and
associate it with applications; the optional default-provider field does
not create a provider or bucket. No file PVC is created. Configure object
storage before uploading files that must survive Pod replacement.
