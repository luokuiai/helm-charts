{{- define "silo.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "silo.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "silo.labels" -}}
{{ include "silo.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "silo.secretName" -}}
{{- if .Values.auth.useExistingSecret -}}
{{- required "auth.existingSecret is required when auth.useExistingSecret=true" .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-root" (include "silo.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "silo.claimName" -}}
{{- default (printf "%s-data" (include "silo.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}

{{- define "silo.consoleURL" -}}
{{- $https := ne .Values.ingress.certificate.mode "disabled" -}}
{{- printf "%s://%s" (ternary "https" "http" $https) .Values.ingress.consoleHost -}}
{{- end -}}
