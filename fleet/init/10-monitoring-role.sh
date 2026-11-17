#!/bin/sh
# Read-only monitoring role used by the collectors: it can read settings and catalogue
# views (pg_monitor, pg_read_all_settings) and nothing else.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE autoconformite_ro LOGIN PASSWORD '${AUTOCONF_PG_PASSWORD}';
GRANT pg_monitor, pg_read_all_settings TO autoconformite_ro;
SQL
