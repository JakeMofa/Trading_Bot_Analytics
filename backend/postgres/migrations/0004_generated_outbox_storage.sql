-- Generated smoke storage only. This is not a cloud receipt, raw archive or
-- retirement permit. Preserve source rows; no UPDATE/DELETE runtime grants.
CREATE TABLE archive.generated_outbox_storage (
  origin_id text NOT NULL CHECK (origin_id='generated-pp'),
  outbox_id bigint NOT NULL CHECK (outbox_id>0),
  generation_id core.generation_uuid NOT NULL,
  envelope bytea NOT NULL CHECK (octet_length(envelope) BETWEEN 1 AND 4194304),
  envelope_hash core.sha256 NOT NULL CHECK (envelope_hash=encode(sha256(envelope),'hex')),
  stored_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(origin_id,outbox_id),
  FOREIGN KEY(origin_id,generation_id) REFERENCES archive.generations(origin_id,generation_id),
  CHECK (convert_from(envelope,'UTF8')::jsonb->>'origin_id'=origin_id),
  CHECK (convert_from(envelope,'UTF8')::jsonb->>'id'=outbox_id::text),
  CHECK (convert_from(envelope,'UTF8')::jsonb->>'generation_id'=generation_id)
);
REVOKE ALL ON archive.generated_outbox_storage FROM PUBLIC,tradebot_app;
GRANT SELECT,INSERT ON archive.generated_outbox_storage TO tradebot_lifecycle;
GRANT SELECT ON archive.generated_outbox_storage TO tradebot_reader;
