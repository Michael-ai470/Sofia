-- Sofia migration 002 — record which package a payment was for.
--
-- The payments table already had everything needed to settle a transaction
-- idempotently (unique key on provider + provider_ref). It did not record
-- WHICH package was bought, which the usage dashboard and the margin report
-- both need. Adding it here rather than inferring from the credit count,
-- because two packages could one day carry the same credits at different
-- prices and the inference would silently break.

ALTER TABLE payments
  ADD COLUMN package_id VARCHAR(32) NULL AFTER provider_ref;

ALTER TABLE payments
  MODIFY COLUMN status ENUM('initiated','successful','failed','abandoned','mismatch')
  NOT NULL DEFAULT 'initiated';
