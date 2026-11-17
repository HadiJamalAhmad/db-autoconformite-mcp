#!/bin/sh
# Deliberate drifts on pg-prod-02, written where a real server keeps them:
# postgresql.auto.conf (ALTER SYSTEM), not the container's command line. Command-line
# options outrank ALTER SYSTEM, so a fix applied with ALTER SYSTEM (Ansible) would be
# masked at every restart: seen in CI on 2026-11-17, the fix "worked" and the drifts came back.
set -eu
run() { psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -c "$1"; }
run "CREATE ROLE legacy_admin SUPERUSER NOLOGIN;"                     # R04
run "ALTER SYSTEM SET log_connections = 'off';"                       # R01
run "ALTER SYSTEM SET archive_mode = 'off';"                          # R02
run "ALTER SYSTEM SET password_encryption = 'md5';"                   # R03
run "ALTER SYSTEM SET idle_in_transaction_session_timeout = 0;"       # R06
