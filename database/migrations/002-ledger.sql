ALTER TABLE payments
ADD COLUMN IF NOT EXISTS ledger_required BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    payment_id UUID NOT NULL UNIQUE,
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    entry_type TEXT NOT NULL DEFAULT 'PAYMENT_AUTHORIZATION',
    posted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_posted_at
ON ledger_entries(posted_at DESC);
