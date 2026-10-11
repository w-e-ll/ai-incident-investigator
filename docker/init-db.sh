#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=app_password="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE investigator LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE incidents TO investigator;
GRANT USAGE, CREATE ON SCHEMA public TO investigator;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE incidents_test OWNER investigator;
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname incidents_test -c "CREATE EXTENSION IF NOT EXISTS vector"
