{{- define "agentcart-shopbridge.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agentcart-shopbridge.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "agentcart-shopbridge.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "agentcart-shopbridge.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "agentcart-shopbridge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: agentcart
{{- end }}

{{- define "agentcart-shopbridge.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agentcart-shopbridge.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "agentcart-shopbridge.dbFullname" -}}
{{- printf "%s-db" (include "agentcart-shopbridge.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agentcart-shopbridge.tlsSecretName" -}}
{{- default (printf "%s-tls" (include "agentcart-shopbridge.fullname" .)) .Values.ingress.tlsSecretName }}
{{- end }}

{{- define "agentcart-shopbridge.image" -}}
{{- printf "%s@%s" .repository .digest }}
{{- end }}

{{- define "agentcart-shopbridge.publicUrl" -}}
{{- printf "https://%s" .Values.store.host }}
{{- end }}
