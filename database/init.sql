CREATE TABLE payments (
    id BIGSERIAL PRIMARY KEY,
    payment_id UUID NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    merchant_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    status TEXT NOT NULL,
    provider_reference TEXT,
    failure_code TEXT,
    failure_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payment_events (
    id BIGSERIAL PRIMARY KEY,
    payment_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    event_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE webhook_deliveries (
    id BIGSERIAL PRIMARY KEY,
    payment_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_http_status INTEGER,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_payments_status_created
ON payments(status, created_at DESC);

CREATE INDEX idx_payment_events_payment
ON payment_events(payment_id, created_at);

CREATE INDEX idx_webhook_delivery_status
ON webhook_deliveries(delivery_status, updated_at);
