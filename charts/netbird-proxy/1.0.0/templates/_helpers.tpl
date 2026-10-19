{{- define "netbird-proxy.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "netbird-proxy.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "netbird-proxy.labels" -}}
{{ include "netbird-proxy.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "netbird-proxy.secretName" -}}
{{- if .Values.auth.useExistingSecret -}}
{{- required "auth.existingSecret is required when auth.useExistingSecret=true" .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "netbird-proxy.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "netbird-proxy.claimName" -}}
{{- .Values.persistence.existingClaim | default (printf "%s-certs" (include "netbird-proxy.fullname" .)) -}}
{{- end -}}

{{- define "netbird-proxy.validate" -}}
{{- $names := list "NB_PROXY_MANAGEMENT_ADDRESS" "NB_PROXY_DOMAIN" "NB_PROXY_TOKEN" "NB_PROXY_ADDRESS" "NB_PROXY_HEALTH_ADDRESS" "NB_PROXY_LOG_LEVEL" "NB_PROXY_PRIVATE" "NB_PROXY_FORWARDED_PROTO" "NB_PROXY_PROXY_PROTOCOL" "NB_PROXY_TRUSTED_PROXIES" "NB_PROXY_SUPPORTS_CUSTOM_PORTS" "NB_PROXY_CERTIFICATE_DIRECTORY" "NB_PROXY_CERTIFICATE_FILE" "NB_PROXY_CERTIFICATE_KEY_FILE" "NB_PROXY_CERT_LOCK_METHOD" "NB_PROXY_ACME_CERTIFICATES" "NB_PROXY_ACME_ADDRESS" "NB_PROXY_ACME_DIRECTORY" "NB_PROXY_ACME_CHALLENGE_TYPE" -}}
{{- range .Values.extraEnv -}}
{{- if has .name $names -}}
{{- fail (printf "extraEnv contains a duplicate or chart-managed variable: %s" .name) -}}
{{- end -}}
{{- $names = append $names .name -}}
{{- end -}}
{{- if and .Values.traefik.enabled (ne .Values.service.type "ClusterIP") -}}
{{- fail "Use service.type=ClusterIP with traefik.enabled=true to share the existing entrypoint" -}}
{{- end -}}
{{- if and .Values.traefik.enabled (eq .Values.tls.mode "acme") (ne .Values.tls.acme.challengeType "tls-alpn-01") -}}
{{- fail "The built-in Traefik TLS route requires tls-alpn-01; for http-01 disable traefik.enabled and provide a public port 80 route" -}}
{{- end -}}
{{- if and (eq .Values.tls.mode "acme") (eq .Values.tls.acme.challengeType "http-01") -}}
{{- if eq (int .Values.service.httpsPort) (int .Values.service.httpPort) -}}
{{- fail "service.httpsPort and service.httpPort must differ for http-01" -}}
{{- end -}}
{{- if and (eq .Values.service.type "NodePort") .Values.service.httpsNodePort (eq (int .Values.service.httpsNodePort) (int .Values.service.httpNodePort)) -}}
{{- fail "HTTPS and HTTP NodePorts must differ" -}}
{{- end -}}
{{- end -}}
{{- end -}}
