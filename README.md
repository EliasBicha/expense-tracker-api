# Expense Tracker API

A REST API for personal expense tracking. Users record expenses in categories, set monthly
budgets per category, get a warning when a budget is exceeded, and view spending reports.

**Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · JWT (PyJWT) · Argon2id · pytest

The full specification, with every requirement numbered and every ambiguity resolved, is in
[docs/SPEC.md](docs/SPEC.md). Tests reference those requirement IDs (e.g. `# BAL-02`).

---

## 1. How to run the project

Requires Docker with Docker Compose.

```bash
cp .env.example .env          # then fill in POSTGRES_PASSWORD and JWT_SECRET (see below)
docker compose up --build
```

On Windows PowerShell, use `Copy-Item .env.example .env` for the first command.

`POSTGRES_PASSWORD` and `JWT_SECRET` are empty in `.env.example` on purpose: Compose refuses to
start until both are set. Generate a value for each, running the command once per variable:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

The output is URL-safe, so it also works inside the database connection URL.

The API container applies the database migrations on start-up and then serves on
**http://localhost:8000**, reachable from this machine only. Interactive API docs (Swagger UI) are
at **http://localhost:8000/docs**.

### Quick tour

The commands below use bash and curl. On Windows, the Swagger UI at `/docs` is the easiest way to
try the API: register, log in, then click **Authorize** and paste the token.

```bash
# register, then log in to get a token
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
     -d '{"email":"me@example.com","password":"a-strong-password","display_name":"Me","default_currency":"ILS"}'
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"me@example.com","password":"a-strong-password"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# list categories (7 system defaults + your own)
curl localhost:8000/categories -H "Authorization: Bearer $TOKEN"
```

### Endpoints

| Area | Endpoints |
|---|---|
| Auth / user | `POST /auth/register`, `POST /auth/login`, `GET /users/me`, `PATCH /users/me` |
| Categories | `GET /categories`, `POST /categories`, `PATCH /categories/{id}`, `DELETE /categories/{id}` |
| Expenses | `GET /expenses` (filters + pagination), `POST /expenses`, `GET/PATCH/DELETE /expenses/{id}`, `GET /expenses/export` (CSV) |
| Budgets | `PUT /budgets` (create or update), `GET /budgets`, `DELETE /budgets/{id}` |
| Reports | `GET /reports/monthly-summary`, `GET /reports/trend?months=N`, `GET /reports/budget-status` |
| Ops | `GET /health` |

All errors share one shape: `{"error": {"code", "message", "details"}}`.

## 2. How to run the tests

```bash
docker compose run --rm tests
```

The tests run against a real PostgreSQL database (`expenses_test`, created automatically the
first time the database volume is initialised). If you started the stack before that database
existed, either create it once by hand:

```bash
docker compose exec db createdb -U expenses expenses_test
```

or recreate the volume with `docker compose down -v`. **Warning:** `-v` deletes the database volume,
including all development data.

As a safety guard, the test suite only runs against a database whose name ends in `_test`, because
it resets the schema before running. The schema is built by running the Alembic migrations (so
they're tested too). Each test runs
inside a transaction that is rolled back afterwards, so tests are isolated and fast. "Today" is
frozen to 2026-06-15 so that month boundaries and the 7-day future-date rule are deterministic.

| File | Covers |
|---|---|
| `test_auth.py` | register/login/profile flow, email normalisation, hashing, invalid/expired/forged tokens, no credential leaks |
| `test_users.py` | profile updates, currency change rule |
| `test_categories.py` | system + own listing, duplicates, read-only system categories, ownership, delete rules |
| `test_expenses.py` | CRUD, amount/date/URL validation, filters, pagination, cross-user isolation |
| `test_budget_alert.py` | budget warning math on create **and** update, including moving an expense between categories/months |
| `test_budgets.py` | upsert, validation, listing, ownership |
| `test_reports.py` | monthly summary, trend, budget status, data isolation |
| `test_export.py` | CSV content and formula-injection protection |
| `test_ops.py` | health check, minimum JWT secret length, request-ID echo and request logging |
| `test_database_guard.py` | the suite refuses to reset any database whose name doesn't end in `_test` |

## 3. Design decisions

### Decision 1: Budget totals are always a fresh `SUM` over stored rows

The budget warning (on create and on update) and the reports never keep a running "spent"
counter. After an expense is written, `spent` is computed with one indexed query:

```sql
SELECT COALESCE(SUM(amount), 0) FROM expenses
WHERE user_id = ? AND category_id = ? AND expense_date >= :month_start AND expense_date < :next_month_start
```

**Why:** A stored counter would have to be adjusted correctly on every create, delete, amount
change, category change and date change. Moving an expense between categories or months would
require subtracting from one counter and adding to another, which is easy to get wrong and hard to
keep consistent under concurrent requests. A `SUM` over the saved data is correct by construction
for all of those cases. It stays fast because of the composite index
`(user_id, category_id, expense_date)`, and the date filter is a half-open range rather than
`EXTRACT(MONTH …)` so the index can be used. For a personal tracker (hundreds of expenses per
month at most) a denormalised counter would add complexity with no measurable benefit.

### Decision 2: One currency per user, enforced rather than converted

The assignment says amounts are stored in the user's default currency and that conversion is out
of scope. So `expense.currency` is **set by the server** from the user's default currency (clients
can't send it), and changing the default currency is **rejected with 409 once the user has
expenses or budgets**. Budgets have no currency column of their own: their amounts are read in the
user's currency, so a change would silently turn a 500 USD budget into a 500 EUR one.

**Why:** The alternatives produce wrong numbers without any error. If users could change currency
freely, reports and budget checks would add up USD and EUR amounts as if they were the same unit.
Filtering reports by the current currency would instead make old expenses silently disappear.
Blocking the change keeps the invariant "all of a user's amounts share one currency" true, so every
report and budget calculation is a plain sum. The `currency` column is still stored on each
expense, so currency conversion could be added later without a data migration.

### Interpretation: which month the budget warning checks

The assignment says to check the budget "in the current month". For an expense dated today, that's
unambiguous. For an expense dated in another month, it isn't. The 7-day rule allows that in both
directions: a backdated expense, or one dated a few days into next month.

**The warning checks the budget of the month the expense is dated in** (decision D-03). For
example, on 13 October, recording an expense dated 28 September checks September's budget.

**Why:** budgets are defined per month (Month/Year in the data model), and the assignment allows
budgets for past months "for retroactive tracking". If only today's month were checked, a
backdated expense could push September over budget without any warning, and a retroactive budget
could never trigger one. The same rule applies when an expense is updated and its date moves to
another month.

### Other decisions

Other decisions (404 rather than 403 for other users' data, a zero budget meaning "track but don't
limit", strictly-greater-than for "exceeded", and so on) are listed with their rationale in
[docs/SPEC.md §1](docs/SPEC.md#1-decisions-resolved-ambiguities).

---

## Project structure

```
app/
  main.py            app factory, middleware, error handlers
  config.py          settings from environment variables
  db.py, models.py   SQLAlchemy engine/session and models
  security.py        Argon2id hashing, JWT
  deps.py            auth + DB dependencies
  errors.py          domain errors, mapped to the error envelope
  dates.py           UTC "today" and month arithmetic
  logging_config.py  JSON logs, per-request log line
  schemas/           request/response models (validation lives here)
  services/          business logic and queries (no HTTP code)
  routers/           thin HTTP layer
migrations/          Alembic schema + system category seed
tests/               pytest suite (real PostgreSQL)
docs/SPEC.md         specification
```

## Security notes

- Passwords are hashed with Argon2id. Login runs a hash check even for unknown emails, so response
  timing doesn't reveal which accounts exist.
- JWTs are HS256 with the algorithm pinned on decode. The secret comes from the environment and must
  be at least 32 characters, otherwise the app refuses to start.
- Every query on user data filters by the authenticated user's id. Another user's records return 404.
- Request bodies reject unknown fields, so clients can't set `user_id`, `currency` and similar
  server-controlled fields.
- Validation errors never echo submitted values back. Logs contain request metadata only.
- CSV export escapes cells that spreadsheets would execute as formulas.
- The container runs as a non-root user, and the database port isn't published.

## Known limitations / out of scope

Currency conversion, refresh tokens and logout (tokens are valid until they expire), password
reset, rate limiting on login, and soft delete. These are listed in [docs/SPEC.md §8](docs/SPEC.md#8-out-of-scope).

**Registration reveals whether an email is already registered.** `POST /auth/register` answers
`409 email_taken`, so the protection against account discovery on login (same message and the same
hashing time for unknown emails) doesn't extend to registration. This is a deliberate usability
trade-off that most applications make: a user who already has an account needs to be told. Fully
closing it would need an email-verification flow ("if this address is new, we've sent a link"),
which is out of scope. Rate limiting, also out of scope, would be the usual mitigation against
bulk probing.
