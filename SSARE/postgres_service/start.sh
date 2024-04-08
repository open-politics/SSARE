#!/usr/bin/env bash

# Write database environment variables to ini file
# Pfad zur Konfigurationsdatei
CONFIG_FILE="core/configs/config.conf"

# Funktion zum Ersetzen von Werten in der Konfigurationsdatei
replace_config() {
    local key=$1
    local value=$2
    local file=$3

    # Nur ersetzen, wenn der Wert nicht leer ist
    if [ ! -z "$value" ]; then
        # Verwenden von sed, um den Wert zu ersetzen
        # -i für inplace-Bearbeitung, s für Substitution
        # Benutzt Regex, um den Wert nach dem Gleichheitszeichen zu ersetzen, ignoriert Leerzeichen
        sed -i "s/\($key\s*=\s*\).*\$/\1$value/" $file
    fi
}

# Überprüfen und Ersetzen der Werte aus den Umgebungsvariablen
replace_config "postgres_user" "$POSTGRES_USER" "$CONFIG_FILE"
replace_config "postgres_host" "$POSTGRES_HOST" "$CONFIG_FILE"
replace_config "postgres_db" "$POSTGRES_DATABASE" "$CONFIG_FILE"
replace_config "postgres_password" "$POSTGRES_PASSWORD" "$CONFIG_FILE"

uvicorn main:app --host 0.0.0.0 --port 5434