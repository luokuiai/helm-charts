{{/* Full references take precedence over the legacy separate name and tag. */}}
{{- define "casdoor.image" -}}
{{- $image := required "image.repository is required" .Values.image.repository -}}
{{- if not (or (contains "@" $image) (regexMatch ":[^/]+$" $image)) -}}
{{- with .Values.image.name -}}
{{- $image = printf "%s/%s" $image . -}}
{{- end -}}
{{- $image = printf "%s:%s" $image (.Values.image.tag | default .Chart.AppVersion) -}}
{{- end -}}
{{- $image -}}
{{- end -}}

{{/*
Expand the name of the chart.
*/}}
{{- define "casdoor.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "casdoor.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "casdoor.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "casdoor.labels" -}}
helm.sh/chart: {{ include "casdoor.chart" . }}
{{ include "casdoor.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "casdoor.selectorLabels" -}}
app.kubernetes.io/name: {{ include "casdoor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "casdoor.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "casdoor.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the external database connection string stored in a Secret.
*/}}
{{- define "casdoor.dataSourceName" -}}
{{- if eq .Values.database.driver "mysql" -}}
{{ .Values.database.user }}:{{ .Values.database.password }}@tcp({{ .Values.database.host }}:{{ default 3306 .Values.database.port }})/
{{- else if eq .Values.database.driver "postgres" -}}
postgres://{{ .Values.database.user | urlquery | replace "+" "%20" }}:{{ .Values.database.password | urlquery | replace "+" "%20" }}@{{ .Values.database.host }}:{{ default 5432 .Values.database.port }}/{{ .Values.database.databaseName | urlquery | replace "+" "%20" }}?sslmode={{ .Values.database.sslMode }}
{{- else -}}
{{- fail "database.driver must be postgres or mysql" -}}
{{- end }}
{{- end }}

{{/*
Create dbName used in the configmap
*/}}
{{- define "casdoor.dbName" -}}
{{- if eq .Values.database.driver "mysql" -}}
{{ .Values.database.databaseName }}
{{- else if eq .Values.database.driver "postgres" -}}
{{ .Values.database.databaseName }}
{{- else if eq .Values.database.driver "cockroachdb" -}}
{{ .Values.database.databaseName }}
{{- else -}}
{{ .Values.database.databaseName }}
{{- end }}
{{- end }}

{{/*
Create EnvfromConfigmap
*/}}
{{- define "casdoor.envFromConfigmap" -}}
{{- range . -}}
- name: {{ .name }}
  valueFrom:
    configMapKeyRef:
      name: {{ .configmapName }}
      key: {{ .key }}
{{- end -}}
{{- end }}

{{- define "casdoor.databaseSecretName" -}}
{{- if .Values.casdoor.envSecret -}}
{{- .Values.casdoor.envSecret -}}
{{- else if .Values.database.useExistingSecret -}}
{{- required "database.existingSecret is required" .Values.database.existingSecret -}}
{{- else -}}
{{- printf "%s-database" (include "casdoor.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "casdoor.origin" -}}
{{- if .Values.origin -}}
{{- .Values.origin -}}
{{- else if and .Values.ingress.enabled .Values.ingress.hosts -}}
{{- $https := or (ne .Values.ingress.certificate.mode "disabled") (not (empty .Values.ingress.tls)) -}}
{{- printf "%s://%s" (ternary "https" "http" $https) (index .Values.ingress.hosts 0).host -}}
{{- end -}}
{{- end -}}

{{/*
Create EnvfromSecret
*/}}
{{- define "casdoor.envFromSecret" -}}
{{- range . -}}
- name: {{ .name }}
  valueFrom:
    secretKeyRef:
      name: {{ .secretName }}
      key: {{ .key }}
{{- end -}}
{{- end -}}

{{/*
Create Envfrom
*/}}
{{- define "casdoor.envFrom" -}}
{{- range . -}}
{{- if eq .type "configmap" -}}
- configMapRef:
    name: {{ .name }}
{{ end }}
{{- if eq .type "secret" -}}
- secretRef:
    name: {{ .name }}
{{- end -}}
{{- end -}}
{{- end -}}
