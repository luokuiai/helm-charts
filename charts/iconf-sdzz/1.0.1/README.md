# iconf-sdzz

The default image is `harbor.luokuiai.com/iconf-sdzz` (the `latest` tag).
Select an existing ConfigMap named
`iconf-sdzz-config` in the release namespace. Put the application's Spring
configuration in the ConfigMap under the key `application-prod.yml`. It is mounted
read-only at `/app/config/application-prod.yml`, which the Dockerfile loads alongside
the packaged configuration. Configure the database, Redis, S3, application
encryption keys and other settings there. The chart activates the `prod` profile
and sets `STORAGE_TYPE=s3`.

ConfigMaps do not hide passwords or keys from users allowed to read them. Preserve
encryption keys across restarts and upgrades. Restart the Deployment after updating
the ConfigMap. The chart does not create a PVC; logs under `/app/logs` and local
temporary files are not persisted.

For example, create a ConfigMap whose `application-prod.yml` key contains:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/iconf_sdzz
    username: replace-me
    password: replace-me
  data:
    redis:
      host: redis
      port: 6379
storage:
  s3:
    bucket: replace-me
    region: us-east-1
    endpoint: https://s3.example.com
    access-key: replace-me
    secret-key: replace-me
    path-style-access: true
```

Add the encryption keys and other required settings for your deployment; do not
replace existing keys when migrating an application with encrypted data.

The image listens on 8080 and exposes `/health`. Ingress is optional. The image
reference and application startup have not been verified by this chart.
