{{- define "postgres.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{/* Keep the resolved tag on PostgreSQL 18 because the data layout is fixed. */}}
{{- define "postgres.image" -}}
{{- $image := required "image.repository is required" .Values.image.repository -}}
{{- if not (contains "@" $image) -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- if regexMatch ":[^/]+$" $image -}}
{{- $tag = regexFind "[^:]+$" $image -}}
{{- else -}}
{{- $image = printf "%s:%s" $image $tag -}}
{{- end -}}
{{- if not (regexMatch "^18([.-].+)?$" $tag) -}}
{{- fail "This chart supports PostgreSQL 18 images only" -}}
{{- end -}}
{{- end -}}
{{- $image -}}
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
{{- if .Values.postgres.envSecret -}}
{{- .Values.postgres.envSecret -}}
{{- else if .Values.auth.useExistingSecret -}}
{{- required "auth.existingSecret is required when auth.useExistingSecret=true" .Values.auth.existingSecret -}}
{{- else -}}
{{- printf "%s-auth" (include "postgres.fullname" .) -}}
{{- end -}}
{{- end -}}
