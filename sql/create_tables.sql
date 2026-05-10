CREATE TABLE IF NOT EXISTS bdolytics_history (
    id BIGSERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    base_price BIGINT NOT NULL,
    current_stock BIGINT NOT NULL,
    trade_volume BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (item_id, recorded_at)
);