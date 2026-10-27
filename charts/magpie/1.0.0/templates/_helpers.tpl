{{- define "magpie.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "magpie.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "magpie.labels" -}}
{{ include "magpie.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "magpie.secretName" -}}
{{- if .Values.auth.useExistingSecret -}}
{{- required "auth.existingSecret is required when auth.useExistingSecret=true" .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-web" (include "magpie.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "magpie.claimName" -}}
{{- default (printf "%s-config" (include "magpie.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}

{{- define "magpie.publicURL" -}}
{{- if .Values.magpie.publicURL -}}
{{- trimSuffix "/" .Values.magpie.publicURL -}}
{{- else if and .Values.ingress.enabled .Values.ingress.hosts -}}
{{- $https := or (ne .Values.ingress.certificate.mode "disabled") (not (empty .Values.ingress.tls)) -}}
{{- printf "%s://%s" (ternary "https" "http" $https) (index .Values.ingress.hosts 0).host -}}
{{- end -}}
{{- end -}}
