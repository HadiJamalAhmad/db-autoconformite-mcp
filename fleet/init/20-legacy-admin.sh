#!/bin/sh
# Deliberate drift on pg-prod-02: a forgotten superuser role (rule R04).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -c "CREATE ROLE legacy_admin SUPERUSER NOLOGIN;"
