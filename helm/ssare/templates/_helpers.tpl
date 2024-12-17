{{/*
Return the full name of the resource
*/}}
{{- define "ssare.fullname" -}}
{{ include "ssare.name" . }}-{{ .Chart.Name }}
{{- end }}

{{/*
Return the name of the resource
*/}}
{{- define "ssare.name" -}}
{{ .Release.Name }}
{{- end }}