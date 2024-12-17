{{/*
Return the full name of the resource
*/}}
{{- define "opol.fullname" -}}
{{ include "opol.name" . }}-{{ .Chart.Name }}
{{- end }}

{{/*
Return the name of the resource
*/}}
{{- define "opol.name" -}}
{{ .Release.Name }}
{{- end }}