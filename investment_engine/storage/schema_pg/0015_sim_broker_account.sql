-- The simulated broker serves one broker account, as a real broker connection does (Codex M4 review B9). A run
-- for one account never decides, reports or accepts another account's orders. Rows written before this script have
-- no account and are served only by an unscoped simulator, as before.

ALTER TABLE sim_broker.orders ADD COLUMN account_id TEXT;

CREATE INDEX sim_broker_orders_account ON sim_broker.orders (account_id, status);
