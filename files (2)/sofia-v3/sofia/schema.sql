-- ===========================================================================
--  Sofia — MySQL schema
--  Target: MySQL 8.0 / MariaDB 10.5+  (cPanel default)
--  Engine: InnoDB · Charset: utf8mb4 (full Unicode, incl. ₦ and emoji)
--
--  HOW TO IMPORT ON cPANEL
--  -----------------------
--  1. cPanel → MySQL Databases → create a database (e.g. cpuser_sofia)
--     and a user, then ADD THE USER TO THE DATABASE with ALL PRIVILEGES.
--  2. cPanel → phpMyAdmin → select that database → Import tab → upload
--     this file → Go.
--  3. Put the resulting credentials in .env (see .env.example).
--
--  DO NOT create the database here. On cPanel the database name is
--  prefixed with your account name and is created through the UI, so a
--  CREATE DATABASE statement in this file will fail on import.
-- ===========================================================================

SET NAMES utf8mb4;
SET time_zone = '+00:00';
SET FOREIGN_KEY_CHECKS = 0;


-- ---------------------------------------------------------------------------
--  users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email             VARCHAR(255)    NOT NULL,
  password_hash     VARCHAR(255)    NOT NULL,
  full_name         VARCHAR(120)        NULL,
  country           CHAR(2)         NOT NULL DEFAULT 'NG',
  credits           INT             NOT NULL DEFAULT 0,
  unlimited         TINYINT(1)      NOT NULL DEFAULT 0,
  plan              VARCHAR(32)     NOT NULL DEFAULT 'free',
  email_verified_at DATETIME            NULL,
  status            ENUM('active','suspended','deleted') NOT NULL DEFAULT 'active',
  last_login_at     DATETIME            NULL,
  created_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_email (email),
  KEY ix_users_status (status),
  KEY ix_users_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  admins  — separate table on purpose. An admin is not a user with a flag;
--            keeping them apart means a bug in the user path can never
--            escalate someone into the admin panel.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS admins (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email          VARCHAR(255)    NOT NULL,
  password_hash  VARCHAR(255)    NOT NULL,
  full_name      VARCHAR(120)        NULL,
  role           ENUM('owner','staff','support') NOT NULL DEFAULT 'staff',
  totp_secret    VARCHAR(64)         NULL,
  status         ENUM('active','suspended') NOT NULL DEFAULT 'active',
  last_login_at  DATETIME            NULL,
  last_login_ip  VARCHAR(45)         NULL,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_admins_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  sessions — server-side session store. Lets you revoke a session from the
--             admin panel, which a signed cookie alone cannot do.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
  id            CHAR(64)        NOT NULL,          -- sha256 of the raw token
  subject_type  ENUM('user','admin') NOT NULL,
  subject_id    BIGINT UNSIGNED NOT NULL,
  ip            VARCHAR(45)         NULL,
  user_agent    VARCHAR(255)        NULL,
  expires_at    DATETIME        NOT NULL,
  revoked_at    DATETIME            NULL,
  created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_sessions_subject (subject_type, subject_id),
  KEY ix_sessions_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  password_resets — hashed, single-use, expiring
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_resets (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id      BIGINT UNSIGNED NOT NULL,
  token_hash   CHAR(64)        NOT NULL,
  expires_at   DATETIME        NOT NULL,
  used_at      DATETIME            NULL,
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reset_token (token_hash),
  KEY ix_reset_user (user_id),
  CONSTRAINT fk_reset_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  credit_ledger — append-only. The user's balance is a cached column on
--                  users; this table is the truth you reconcile against.
--                  Never UPDATE a row here. Only INSERT.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS credit_ledger (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id       BIGINT UNSIGNED NOT NULL,
  delta         INT             NOT NULL,          -- negative = charge
  balance_after INT             NOT NULL,
  reason        VARCHAR(64)     NOT NULL,          -- 'tool:cv_rewrite', 'topup', 'refund', 'grant'
  job_id        BIGINT UNSIGNED     NULL,
  reference     VARCHAR(128)        NULL,          -- payment ref, admin note
  created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_ledger_user_time (user_id, created_at),
  KEY ix_ledger_reason (reason),
  CONSTRAINT fk_ledger_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  jobs — one row per tool run. This is the operational spine: it carries
--         the credit hold, the model used, the token spend, and the result.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  public_id      CHAR(22)        NOT NULL,         -- URL-safe, non-enumerable
  user_id        BIGINT UNSIGNED     NULL,         -- NULL = anonymous free run
  engine         VARCHAR(8)      NOT NULL,         -- 'E1' … 'E7'
  tool           VARCHAR(64)     NOT NULL,         -- catalog slug
  status         ENUM('pending','running','succeeded','failed','refunded')
                                 NOT NULL DEFAULT 'pending',
  credits_charged INT            NOT NULL DEFAULT 0,
  model          VARCHAR(64)         NULL,
  tokens_in      INT                 NULL,
  tokens_out     INT                 NULL,
  tokens_cached  INT                 NULL,
  cost_usd       DECIMAL(10,6)       NULL,
  duration_ms    INT                 NULL,
  ruleset_id     VARCHAR(32)         NULL,         -- E4/E5: which ruleset produced this
  ruleset_version VARCHAR(32)        NULL,
  input_json     JSON                NULL,
  output_json    JSON                NULL,
  error_code     VARCHAR(64)         NULL,
  error_id       CHAR(12)            NULL,         -- shown to user; joins to logs
  ip             VARCHAR(45)         NULL,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at   DATETIME            NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_jobs_public (public_id),
  KEY ix_jobs_user_time (user_id, created_at),
  KEY ix_jobs_tool_time (tool, created_at),
  KEY ix_jobs_status (status),
  CONSTRAINT fk_jobs_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  payments
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id        BIGINT UNSIGNED NOT NULL,
  provider       ENUM('paystack','monnify','manual') NOT NULL,
  provider_ref   VARCHAR(128)    NOT NULL,
  package_id     VARCHAR(32)         NULL,
  amount_minor   BIGINT          NOT NULL,         -- kobo / cents. NEVER float.
  currency       CHAR(3)         NOT NULL DEFAULT 'NGN',
  credits        INT             NOT NULL,
  status         ENUM('initiated','successful','failed','abandoned','mismatch')
                                 NOT NULL DEFAULT 'initiated',
  raw_payload    JSON                NULL,
  created_at     DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  settled_at     DATETIME            NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pay_provider_ref (provider, provider_ref),
  KEY ix_pay_user (user_id, created_at),
  CONSTRAINT fk_pay_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  rulesets — E4 tax / E5 contract rules. Versioned data, never model memory.
--             `verified_on` and `verified_by` are not decoration: nothing
--             ships to a user computation without them set.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rulesets (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ruleset_id      VARCHAR(32)     NOT NULL,        -- 'NG-NTA2025'
  version         VARCHAR(32)     NOT NULL,        -- '2026.03'
  jurisdiction    CHAR(2)         NOT NULL,
  effective_from  DATE            NOT NULL,
  effective_to    DATE                NULL,
  status          ENUM('draft','verified','superseded') NOT NULL DEFAULT 'draft',
  verified_on     DATE                NULL,
  verified_by     VARCHAR(160)        NULL,        -- practitioner name + licence
  rules_json      JSON            NOT NULL,
  notes           TEXT                NULL,
  created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_ruleset_version (ruleset_id, version),
  KEY ix_ruleset_lookup (jurisdiction, effective_from, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  rate_limits — DB-backed so it survives the Passenger worker recycling
--                that makes in-memory limiting useless on cPanel.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rate_limits (
  bucket      VARCHAR(160)    NOT NULL,            -- 'login:203.0.113.9'
  window_start DATETIME       NOT NULL,
  hits        INT             NOT NULL DEFAULT 1,
  PRIMARY KEY (bucket, window_start),
  KEY ix_rl_window (window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  audit_log — who did what in the admin panel
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  actor_type   ENUM('admin','system') NOT NULL,
  actor_id     BIGINT UNSIGNED     NULL,
  action       VARCHAR(64)     NOT NULL,
  target_type  VARCHAR(32)         NULL,
  target_id    VARCHAR(64)         NULL,
  detail       JSON                NULL,
  ip           VARCHAR(45)         NULL,
  created_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_audit_time (created_at),
  KEY ix_audit_actor (actor_type, actor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ---------------------------------------------------------------------------
--  contact_messages — the public contact form
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contact_messages (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name        VARCHAR(120)    NOT NULL,
  email       VARCHAR(255)    NOT NULL,
  subject     VARCHAR(200)        NULL,
  body        TEXT            NOT NULL,
  handled_at  DATETIME            NULL,
  ip          VARCHAR(45)         NULL,
  created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_contact_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
--  Seed: credit packages are in code (config.py), not here, so pricing can
--  change without a migration. The only seed row needed is the first admin,
--  and it is created by `python manage.py create-admin` so the password is
--  hashed properly and never sits in plaintext in a .sql file you might
--  later paste into a support ticket.
-- ---------------------------------------------------------------------------
