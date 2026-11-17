-- Bounded PP live writer lease. No runtime may apply this migration on startup.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM ops.writer_state WHERE collector_enabled) THEN
    RAISE EXCEPTION 'collector must be durably OFF before lease migration';
  END IF;
END $$;
ALTER TABLE ops.writer_state
  ADD COLUMN collector_session_id uuid,
  ADD COLUMN collector_lease_expires_at timestamptz,
  ADD CONSTRAINT collector_lease_complete CHECK (
    (collector_enabled AND collector_session_id IS NOT NULL AND collector_lease_expires_at IS NOT NULL)
    OR (NOT collector_enabled AND collector_session_id IS NULL AND collector_lease_expires_at IS NULL)
  );
