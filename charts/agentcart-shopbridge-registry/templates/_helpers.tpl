{{- define "agentcart-shopbridge-registry.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agentcart-shopbridge-registry.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "agentcart-shopbridge-registry.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "agentcart-shopbridge-registry.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "agentcart-shopbridge-registry.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: agentcart
{{- end }}

{{- define "agentcart-shopbridge-registry.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agentcart-shopbridge-registry.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "agentcart-shopbridge-registry.image" -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest }}
{{- end }}

{{- define "agentcart-shopbridge-registry.indexerImage" -}}
{{- printf "%s@%s" .Values.registry.onchainEvents.rpcIndexer.image.repository .Values.registry.onchainEvents.rpcIndexer.image.digest }}
{{- end }}
