-- Disposable PostgreSQL approximation of the Storage RLS surface. This is
-- not Supabase Storage HTTP and cannot prove actual API operation mapping.
DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
END $roles$;
CREATE SCHEMA auth;
CREATE SCHEMA storage;
CREATE SCHEMA test_fixture;
CREATE TABLE auth.users (
  id uuid PRIMARY KEY,email text NOT NULL,role text NOT NULL,
  raw_app_meta_data jsonb NOT NULL);
INSERT INTO auth.users VALUES
 ('00000000-0000-4000-8000-0000000000aa','pp-storage-archive@example.invalid',
  'authenticated','{"tradebot_role":"pp_storage_archive","tradebot_origin":"pp-live-pp"}');
GRANT USAGE ON SCHEMA auth,storage TO anon,authenticated;
GRANT USAGE ON SCHEMA test_fixture TO anon,authenticated;

CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $fn$
  SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid
$fn$;
CREATE FUNCTION storage.allow_only_operation(value text) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
  SELECT current_setting('storage.operation',true)=value
$fn$;

CREATE TABLE storage.buckets (id text PRIMARY KEY,public boolean NOT NULL);
INSERT INTO storage.buckets VALUES ('market-raw',false),('knowledge',false);
CREATE TABLE storage.objects (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bucket_id text NOT NULL REFERENCES storage.buckets(id),
  name text NOT NULL UNIQUE,
  owner_id text);
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
GRANT SELECT,INSERT,UPDATE,DELETE ON storage.objects TO anon,authenticated;
GRANT USAGE ON SEQUENCE storage.objects_id_seq TO anon,authenticated;

CREATE FUNCTION test_fixture.object_key(digest text DEFAULT repeat('a',64),
    origin_hash text DEFAULT '6157f7800b12255ab48111b5c6258a444712a38baca54d3b0929ede8994b2ae8')
RETURNS text LANGUAGE sql IMMUTABLE AS $fn$
  SELECT 'raw-v1/'||origin_hash||'/00000000-0000-4000-8000-000000000001/'||
         digest||'.jsonl.gz'
$fn$;

CREATE FUNCTION test_fixture.expect_insert_denied(bucket text,key text)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
BEGIN
  BEGIN
    INSERT INTO storage.objects(bucket_id,name) VALUES (bucket,key);
  EXCEPTION WHEN insufficient_privilege THEN RETURN;
  END;
  RAISE EXCEPTION 'unapproved Storage insert succeeded';
END $fn$;
CREATE FUNCTION test_fixture.assert_visible(key text,expected bigint)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM storage.objects WHERE name=key;
  IF n<>expected THEN RAISE EXCEPTION 'Storage visibility mismatch'; END IF;
END $fn$;
CREATE FUNCTION test_fixture.assert_update_denied(key text)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE n bigint;
BEGIN
  UPDATE storage.objects SET name=key||'.moved' WHERE name=key;
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'Storage update succeeded'; END IF;
END $fn$;
CREATE FUNCTION test_fixture.assert_delete_denied(key text)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $fn$
DECLARE n bigint;
BEGIN
  DELETE FROM storage.objects WHERE name=key;
  GET DIAGNOSTICS n=ROW_COUNT;
  IF n<>0 THEN RAISE EXCEPTION 'Storage delete succeeded'; END IF;
END $fn$;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA test_fixture TO anon,authenticated;
