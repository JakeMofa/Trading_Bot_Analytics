-- Include acknowledged rows for bounded sealed-generation verification.
CREATE INDEX outbox_generation_id ON ops.outbox (generation_id, id);
