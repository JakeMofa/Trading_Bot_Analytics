#!/bin/bash
set -Eeuo pipefail
# Init-only foundation, not the business-schema migration runner.
# Values are loaded server-side; never placed in shell argv or evidence.
psql --username postgres --dbname tradebot_pp --no-psqlrc --set ON_ERROR_STOP=1 <<'SQL'
BEGIN;
REVOKE ALL ON DATABASE tradebot_pp FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE ROLE tradebot_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE tradebot_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 2;
CREATE ROLE tradebot_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 8;
CREATE ROLE tradebot_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 4;
DO $body$
BEGIN
  EXECUTE format('ALTER ROLE tradebot_migrator PASSWORD %L', btrim(pg_read_file('/run/secrets/migrator'), E'\n\r '));
  EXECUTE format('ALTER ROLE tradebot_app PASSWORD %L', btrim(pg_read_file('/run/secrets/application'), E'\n\r '));
  EXECUTE format('ALTER ROLE tradebot_reader PASSWORD %L', btrim(pg_read_file('/run/secrets/reader'), E'\n\r '));
END
$body$;
GRANT tradebot_owner TO tradebot_migrator;
GRANT CONNECT ON DATABASE tradebot_pp TO tradebot_migrator, tradebot_app, tradebot_reader;
ALTER ROLE tradebot_reader SET default_transaction_read_only=on;
CREATE SCHEMA raw AUTHORIZATION tradebot_owner;
CREATE SCHEMA core AUTHORIZATION tradebot_owner;
CREATE SCHEMA ops AUTHORIZATION tradebot_owner;
CREATE SCHEMA archive AUTHORIZATION tradebot_owner;
SET ROLE tradebot_owner;
CREATE TABLE ops.environment_identity (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  environment text NOT NULL CHECK (environment = 'preprod'),
  database_name text NOT NULL CHECK (database_name = 'tradebot_pp'),
  foundation_version integer NOT NULL CHECK (foundation_version = 1)
);
INSERT INTO ops.environment_identity VALUES (true, 'preprod', current_database(), 1);
GRANT USAGE ON SCHEMA raw,core,ops,archive TO tradebot_app,tradebot_reader;
GRANT SELECT ON ops.environment_identity TO tradebot_app,tradebot_reader;
COMMIT;
SQL
# Local connections also require SCRAM after bootstrap. Admin tools authenticate
# through the mounted file. No host port is published.
sed -i -E 's/^(local[[:space:]]+all[[:space:]]+all[[:space:]]+)trust/\1scram-sha-256/' "$PGDATA/pg_hba.conf"
