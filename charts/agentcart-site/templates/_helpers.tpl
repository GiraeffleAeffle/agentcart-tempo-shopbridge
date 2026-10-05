{{- define "agentcart-site.image" -}}
{{- if not (regexMatch "^sha256:[a-f0-9]{64}$" .Values.image.digest) -}}
{{- fail "image.digest must be the reviewed sha256 digest of the site image" -}}
{{- end -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- end -}}

{{- define "agentcart-site.labels" -}}
app.kubernetes.io/name: agentcart-site
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "agentcart-site.selector" -}}
app.kubernetes.io/name: agentcart-site
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}
