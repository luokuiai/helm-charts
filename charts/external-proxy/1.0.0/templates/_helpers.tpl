{{- define "external-proxy.name" -}}
{{- .Release.Name -}}
{{- end -}}

{{- define "external-proxy.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "external-proxy.tlsSecret" -}}
{{- if eq .Values.ingress.certificate.mode "existing" -}}
{{- required "ingress.certificate.existingSecret is required" .Values.ingress.certificate.existingSecret -}}
{{- else -}}
{{- default (printf "%s-tls" (include "external-proxy.name" .)) .Values.ingress.certificate.secretName -}}
{{- end -}}
{{- end -}}
