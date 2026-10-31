{{- define "netbird-operator-network.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | quote }}
{{- end -}}

{{- define "netbird-operator-network.natName" -}}
{{- printf "%s-nat" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "netbird-operator-network.natTable" -}}
{{- printf "nb_nat_%s" (printf "%s/%s" .Release.Namespace .Release.Name | sha256sum | trunc 12) -}}
{{- end -}}
