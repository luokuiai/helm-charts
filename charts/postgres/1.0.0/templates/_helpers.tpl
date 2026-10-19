{{- define "postgres.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "postgres.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "postgres.labels" -}}
{{ include "postgres.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "postgres.secretName" -}}
{{- if .Values.auth.useExistingSecret -}}
{{- required "auth.existingSecret is required when auth.useExistingSecret=true" .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "postgres.fullname" .) -}}
{{- end -}}
{{- end -}}
