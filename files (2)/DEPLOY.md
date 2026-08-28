# Sofia — cPanel deployment

Target: cPanel with Setup Python App (Passenger), Python 3.11.x, MySQL/MariaDB.
Allow about 40 minutes for a first deployment.

---

## What you are deploying

A server-rendered Flask application. **There is no JavaScript build step** — no npm,
no Vite, no bundler, no hashed asset filenames. The CSS and JS are plain files
served from `app/static/`.

This is deliberate. The deployment failures on this stack have come from build
artefacts: hashed filenames that don't match, an `assets/` folder that doesn't
upload cleanly, a manifest pointing at files that aren't there. None of that can
happen here, because none of it exists. What you upload is what runs.

---

## 1 · Create the database first

cPanel → **MySQL Databases**.

1. Create a database. cPanel prefixes it with your account name, so `sofia`
   becomes something like `cpuser_sofia`. Write down the full name.
2. Create a user, with a generated password. Save it somewhere before you leave
   the page — cPanel will not show it again.
3. Add the user to the database and grant **All Privileges**.

Then cPanel → **phpMyAdmin** → select the database → **Import** → choose
`schema.sql` → **Go**.

You should see 11 tables: `users`, `admins`, `sessions`, `password_resets`,
`credit_ledger`, `jobs`, `payments`, `rulesets`, `rate_limits`, `audit_log`,
`contact_messages`.

If the import fails on collation, your MariaDB is older than the file expects.
Find and replace `utf8mb4_0900_ai_ci` with `utf8mb4_unicode_ci` throughout
`schema.sql` and import again.

---

## 2 · Upload the files

cPanel → **File Manager**. Create a folder for the application — use
`sofia_app`, **not** `public_html`. Application code should never sit in the
web root where it can be served as plain text.

Upload the ZIP into that folder and extract it there.

Do not upload a `.env` file from your machine. You will create one on the server
in step 4.

---

## 3 · Create the Python application

cPanel → **Setup Python App** → **Create Application**.

| Field | Value |
|---|---|
| Python version | 3.11.x |
| Application root | `sofia_app` |
| Application URL | your domain, or a subdomain |
| Application startup file | `passenger_wsgi.py` |
| Application Entry point | `application` |

Click Create. cPanel builds a virtualenv and shows you a command at the top of
the page that looks like `source /home/cpuser/virtualenv/sofia_app/3.11/bin/activate`.
Copy it.

Then cPanel → **Terminal**, and run:

```bash
source /home/cpuser/virtualenv/sofia_app/3.11/bin/activate
cd ~/sofia_app
pip install -r requirements.txt
```

Watch for errors on `mysql-connector-python` and `reportlab`. If either fails to
build, your host may need to enable a compiler — open a ticket rather than
working around it.

---

## 4 · Configure the environment

Copy `.env.example` to `.env` in the application root and fill it in. The values
that must be set before the app will run:

```
SOFIA_ENV=production
SOFIA_DEBUG=0
SOFIA_SECRET_KEY=       <- generate this, see below
DB_NAME=cpuser_sofia
DB_USER=cpuser_sofiauser
DB_PASSWORD=
KIMI_API_KEY=
```

Generate the secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**The app refuses to boot in production with `SOFIA_DEBUG=1`, with a wildcard
origin, or with an empty secret key.** That guard is intentional. If Passenger
reports a startup failure, read `stderr.log` before changing anything — it will
name which check failed.

You can set these as Environment Variables in Setup Python App instead of using
a `.env` file. Either works; do not do both, because it gets confusing when a
value is wrong.

---

## 5 · Create your admin account

Still in Terminal, with the virtualenv active:

```bash
cd ~/sofia_app
python manage.py create-admin
```

It will prompt for an email and password. This is the login for `/admin` — the
back office where you see jobs, users, credit balances, and rule set versions.

Other commands:

```bash
python manage.py check-db        # verifies connection and lists tables
python manage.py grant-credits   # add credits to a user by email
python manage.py check-kimi      # sends one cheap test call to Moonshot
```

---

## 6 · Restart and verify

Setup Python App → **Restart**.

Then check, in this order:

1. `https://yourdomain/health` — should return JSON with `"database": "ok"`.
   If it returns 503, the database credentials are wrong. This is the fastest
   diagnostic on the whole site; check it first, always.
2. `https://yourdomain/` — the tool grid should render with styled cards. If you
   get unstyled text, static files aren't being served; see Troubleshooting.
3. `https://yourdomain/tool/cv-analysis` — paste any CV text and run it. This is
   free and anonymous, so it tests the full path — form, extraction, Kimi call,
   render — without needing an account.
4. `https://yourdomain/admin` — log in with the account from step 5.

---

## Troubleshooting

**500 error, no detail in the browser.** By design — stack traces are never sent
to the client. The real error is in `~/sofia_app/stderr.log`. Read that.

**Site renders as unstyled HTML.** Passenger is intercepting `/static`. The
`app/static/.htaccess` in this package tells Passenger to serve those files
directly. Confirm it survived the upload — File Manager hides dotfiles until you
enable "Show Hidden Files" in Settings.

**`ModuleNotFoundError` after a successful pip install.** You installed into the
system Python instead of the virtualenv. Re-run the `source .../activate` command
and install again.

**Changes don't appear.** Passenger caches the application. Restart from Setup
Python App, or `touch tmp/restart.txt` in the application root.

**Kimi calls time out.** Some shared hosts block outbound HTTPS to non-allowlisted
hosts. Test with `python manage.py check-kimi`. If it hangs, ask your host to
allow outbound traffic to `api.moonshot.ai` on 443.

---

## Before you take payments

This build has authentication, credits, and job history wired end to end.
Payments are stubbed — the `payments` table and the Paystack environment
variables exist, but no gateway is connected. `/account/buy` renders the packages
and stops there.

Two things must also be true before the tax tools come off `soon`:

1. The `rulesets` table holds a Nigerian rule set that a qualified practitioner
   has verified, with `verified_on` set. The tax engine reads rates from that
   table and will refuse to compute without it — it never recalls a rate from
   the model.
2. Every user-facing string has been checked for the word *file*. Sofia prepares
   returns. It does not file them, and it is not an accredited tax agent.

---

## 7 · Add the job sweeper cron

Tool runs happen on a background thread, so a process restart mid-generation
can strand a job at `running` with the user already charged. A cron job returns
those credits.

cPanel → **Cron Jobs** → every five minutes:

```
cd ~/sofia_app && /home/cpuser/virtualenv/sofia_app/3.11/bin/python manage.py sweep-jobs
```

Substitute your real virtualenv path — it's shown at the top of Setup Python App.

Without this, a stranded job never resolves and the user never gets their
credits back. It is the only cron the application needs.

### Worker sizing

`SOFIA_WORKER_THREADS` (default 4) is how many tool runs execute at once.
**Keep it at or below `DB_POOL_SIZE`** (default 5). A worker borrows a database
connection to write its result, and if the pool is exhausted at that moment a
finished job fails on the last step — the most expensive possible place to fail.

If you raise one, raise both.

## 8 · Verify the async path

After restarting, run a paid tool and watch the network tab:

1. `POST /api/run/<slug>` should return **202** in well under a second, with a `jobId`.
2. `GET /api/job/<jobId>` should return `{"status":"running"}` while it works.
3. It should flip to `{"status":"success"}` with the result and download links.

If step 1 takes thirty seconds, the deployment is still running the old
synchronous code — restart the app.

## 9 · Running the tests

The suite needs a MySQL it is allowed to wipe between tests. Never point it at
production; `conftest.py` truncates tables on every test.

```bash
mysql -e "CREATE DATABASE sofia_test"
mysql sofia_test < schema.sql
pip install pytest
python -m pytest tests/ -q
```

29 tests covering credit deduction under concurrency, refund idempotency, the
full job lifecycle, ownership checks on polling and downloads, and export file
validity. Run them before every deploy.

---

## 10 · AI provider routing

Sofia routes by *role*, not by model. Engines ask for "scoring" or "writing";
`app/ai/providers.py` decides who serves it. Switching the writer is one env
var, never an edit to engine code.

```
SOFIA_ROLE_SCORING=deepseek:deepseek-v4-flash
SOFIA_ROLE_WRITING=moonshot:kimi-k2.6
SOFIA_ROLE_REASONING=deepseek:deepseek-v4-pro
SOFIA_ROLE_FALLBACK=anthropic:claude-sonnet-4-6
SOFIA_AI_FALLBACK=1

KIMI_API_KEY=
DEEPSEEK_API_KEY=
ANTHROPIC_API_KEY=
```

**Migrate one role at a time.** Move scoring first — it is structured
extraction, the lowest-risk work and the biggest proportional saving. Read a
dozen outputs. Only then move writing, which is where the money is but also
where a quality drop is visible to users.

### The quality gate

Every writing response is checked before it reaches the user: not empty, not
truncated mid-structure, and **no hedged figures**. A response containing
"approximately ₦4,000,000" is rejected and retried on the fallback, because
that phrasing misrepresents how solid the number is and the whole Evidence
Tiering Protocol rests on it not appearing.

If the fallback also fails the gate, the prompt is at fault rather than the
provider — the job fails and the user is refunded rather than handed a
document that hedges.

Watch the fallback rate in the admin panel after switching. A rate above a few
percent means the cheaper model is not clearing the bar on your real inputs,
and the honest response is to move that role back rather than ship worse
documents.

## 11 · Payments

Two gateways, routed by the user's country:

```
MONNIFY_API_KEY=            MONNIFY_SECRET_KEY=
MONNIFY_CONTRACT_CODE=      MONNIFY_BASE_URL=https://api.monnify.com
PAYSTACK_SECRET_KEY=        PAYSTACK_PUBLIC_KEY=
SOFIA_USD_NGN=1580
```

`MONNIFY_BASE_URL` defaults to the **sandbox**. Point it at the live host
before taking real money.

Register both webhook URLs in the provider dashboards:

```
https://yourdomain/webhooks/monnify
https://yourdomain/webhooks/paystack
```

**Credits are granted by the webhook, never by the browser redirect.** A user
who closes the tab after paying still gets what they bought. The redirect page
verifies with the gateway so it can tell the truth to someone watching, but
the webhook is the record.

Both handlers verify an HMAC-SHA512 signature before reading the body, compare
the amount against our own stored intent, and settle through a status
transition only one caller can win. A retried webhook is a no-op. There are
tests for each of those.

### Before going live

1. Run `mysql yourdb < migrations/002_payments_package.sql` if you deployed
   the earlier schema.
2. Test a real transaction on each gateway, including closing the tab
   immediately after paying — credits must still arrive.
3. Send a webhook with a deliberately wrong signature and confirm a 400.

## 12 · Credit costs and packages

Credit costs per tool live in `app/catalog.py`. Packages, gateway fees and
margin maths live in `app/pricing.py`. Neither is in `config.py` and neither
is hardcoded in a template.

Current costs follow the June 2026 financial analysis: CV rewrite 3, cover
letter 2, business plan 8, candidate ranking 2 per CV, free signup grant 3.

**These were priced against Claude's rates.** Once traffic moves to Kimi and
DeepSeek the real cost per credit falls by roughly 5×, and the admin dashboard
computes the measured figure from job telemetry rather than assuming. Revisit
the credit costs once you have two weeks of real provider data — you may be
charging more credits than the work now costs, which shows up as conversion
drag rather than as a bug.
