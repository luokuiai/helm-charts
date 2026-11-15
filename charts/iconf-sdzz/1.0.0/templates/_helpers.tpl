{{- define "iconf-sdzz.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "iconf-sdzz.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "iconf-sdzz.labels" -}}
{{ include "iconf-sdzz.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}
