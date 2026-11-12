{{- define "warpgate.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "warpgate.image" -}}
{{- $image := required "image.repository is required" .Values.image.repository -}}
{{- if not (or (contains "@" $image) (regexMatch ":[^/]+$" $image)) -}}
{{- $image = printf "%s:%s" $image .Chart.AppVersion -}}
{{- end -}}
{{- $image -}}
{{- end -}}

{{- define "warpgate.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "warpgate.labels" -}}
{{ include "warpgate.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "warpgate.claimName" -}}
{{- default (printf "%s-data" (include "warpgate.fullname" .)) .Values.persistence.existingClaim -}}
{{- end -}}

{{- define "warpgate.backendTLSSecret" -}}
{{- default (printf "%s-backend-tls" (include "warpgate.fullname" .)) .Values.warpgate.backendTLSSecret -}}
{{- end -}}

{{- define "warpgate.backendServerName" -}}
{{- printf "%s.%s.svc" (include "warpgate.fullname" .) .Release.Namespace -}}
{{- end -}}

{{- define "warpgate.externalHost" -}}
{{- if .Values.warpgate.externalHost -}}
{{- .Values.warpgate.externalHost -}}
{{- else if .Values.ingress.enabled -}}
{{- .Values.ingress.hostname -}}
{{- end -}}
{{- end -}}

{{- define "warpgate.externalPort" -}}
{{- .Values.warpgate.externalPort | default (ternary 443 8888 .Values.ingress.enabled) -}}
{{- end -}}

{{- define "warpgate.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: [ALL]
{{- end -}}

{{- define "warpgate.environment" -}}
envFrom:
  - secretRef:
      name: {{ .Values.warpgate.envSecret | quote }}
{{- end -}}
