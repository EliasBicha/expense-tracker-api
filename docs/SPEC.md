# Expense Tracker API — Specification

Status: **APPROVED (r3)**.

This spec turns the assignment into numbered, testable requirements. Every test in `tests/`
references the requirement ID(s) it verifies (e.g. `# EXP-04`), so each requirement can be traced to a test.

**Revision history**
- r1: initial draft.
- r2: budget alert also runs on expense update (D-16, EXP-10, BAL-01..06, test plan).
- r3: documents behaviour settled during implementation, without changing business logic: RPT-05
  (year and month together); EXP-05 (empty description stored as null; receipt URL stored in normalized
  form); test plan updated.
- r4: fixes from an independent code review: D-05 / USR-03 (a budget also blocks a currency change);
  EXP-05 (the 2048 limit applies to the normalized URL); EXP-07 / EXP-08 (upper bounds on `offset`
  and the amount filters); architecture list and test plan brought up to date.

---

## 1. Decisions (resolved ambiguities)

| ID | Decision | Rationale |
|----|----------|-----------|
| D-01 | Stack: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (sync), Alembic, PostgreSQL 16, PyJWT, argon2-cffi, pytest. | Small, explicit, and well known. Sync code avoids async complexity that this workload doesn't need. |
| D-02 | Tests run against **PostgreSQL** (a separate test database), via `docker compose`. | Tests exercise the same SQL as production (date functions, `NUMERIC`, constraints). |
| D-03 | The budget alert checks the budget for the **month of the expense's date**. | A budget belongs to a month, so a backdated expense affects that month's budget. Spec wording: "the current month". |
| D-04 | A budget of **0 never triggers `budget_warning`**. In budget status it is reported with `has_limit: false`. | Spec: zero budget = "track but not limit". |
| D-05 | `expense.currency` is **set by the server** from the user's default currency and is not accepted as input. Changing `default_currency` is **rejected (409) if the user has any expenses or budgets**. | Spec: amounts are stored in the user's default currency and there is no conversion. Budget amounts are in that currency too, so this guarantees that reports and budget checks never mix currencies. |
| D-06 | Another user's resources return **404**, not 403. | Doesn't reveal that the resource exists. |
| D-07 | Category name uniqueness ignores case and trims whitespace, and also checks system category names. | Prevents a confusing "food" next to the system "Food". |
| D-08 | Expense amount must be `> 0`. Budget amount must be `>= 0`. Both have max `999999999.99` and at most 2 decimal places. | Spec edge cases 4, 5, 7. Zero is rejected for expenses because a 0 expense is meaningless. |
| D-09 | Amounts are stored as `NUMERIC(12,2)`, handled as `Decimal`, and serialized as **JSON numbers**. | Exact arithmetic. JSON numbers match the spec's example. Values up to 999,999,999.99 are exact in IEEE-754 doubles. |
| D-10 | "Today" and "current month" are **UTC** calendar dates. | Users have no time-zone field. |
| D-11 | Pagination uses `limit` / `offset` and returns `total`. Default limit 20, max 100. | Simple, and works for UIs that page through results. |
| D-12 | Nice-to-haves built: Swagger/OpenAPI docs and CSV export. **Not built:** soft delete. Expenses are hard-deleted. | Avoids extra complexity that the spec doesn't require. |
| D-13 | Request bodies **reject unknown fields** (422). | Catches client typos and mass-assignment attempts (e.g. sending `user_id` or `currency`). |
| D-14 | Supported currencies: `USD, EUR, ILS, GBP, CAD, AUD, CHF`. | All use 2 decimal places, which is consistent with D-08. |
| D-15 | Date sanity bounds: expense dates and budget years are on or after `2000-01-01` / year 2000. Budget year is at most 2100. | Rejects obvious typos (e.g. year 0202). |
| D-16 | The budget alert also runs on `PATCH /expenses/{id}`, and PATCH returns the same `{expense, budget_warning}` shape as POST. | This goes beyond the assignment, which only asks for the alert on creation. Requested by the project owner so that create and update behave the same way. An update to amount, category or date can push a month over budget just like a new expense. |

---

## 2. Data model

All IDs are UUIDv4. Timestamps are `TIMESTAMPTZ` (UTC).

### users
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| email | VARCHAR(320) | NOT NULL, UNIQUE, stored lowercased |
| password_hash | VARCHAR(255) | NOT NULL (Argon2id) |
| display_name | VARCHAR(100) | NOT NULL |
| default_currency | CHAR(3) | NOT NULL, default `USD` |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL |

### categories
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| name | VARCHAR(50) | NOT NULL |
| icon | VARCHAR(50) | NOT NULL |
| color | CHAR(7) | NOT NULL, `#RRGGBB` |
| is_system | BOOLEAN | NOT NULL |
| user_id | UUID | FK users, NULL for system categories |

- CHECK `is_system = (user_id IS NULL)`.
- Unique index `(user_id, lower(name)) WHERE user_id IS NOT NULL`.
- Unique index `(lower(name)) WHERE user_id IS NULL`.
- The service layer checks for clashes with system names (D-07). The DB index is the backstop if two requests race.
- Seeded by a migration with: Food, Transport, Entertainment, Shopping, Bills, Health, Other.

### expenses
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK users, NOT NULL |
| category_id | UUID | FK categories **ON DELETE RESTRICT**, NOT NULL |
| amount | NUMERIC(12,2) | NOT NULL, CHECK `amount > 0` |
| currency | CHAR(3) | NOT NULL |
| expense_date | DATE | NOT NULL |
| description | VARCHAR(500) | NULL |
| receipt_url | VARCHAR(2048) | NULL |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL |

- Index `(user_id, expense_date)`: used by listing, date filters, and reports.
- Index `(user_id, category_id, expense_date)`: used by the budget check, category deletion count, and category filter.

### budgets
| Column | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| user_id | UUID | FK users, NOT NULL |
| category_id | UUID | FK categories **ON DELETE CASCADE**, NOT NULL |
| amount | NUMERIC(12,2) | NOT NULL, CHECK `amount >= 0` |
| year | SMALLINT | NOT NULL, CHECK 2000–2100 |
| month | SMALLINT | NOT NULL, CHECK 1–12 |
| created_at / updated_at | TIMESTAMPTZ | NOT NULL |

- UNIQUE `(user_id, category_id, year, month)`.
- Budgets cascade on category deletion because the spec only blocks deletion when *expenses* exist. A budget for a category with no expenses is removed together with the category.

---

## 3. Cross-cutting conventions

- **Auth:** `Authorization: Bearer <JWT>` on every endpoint except register, login, health, and docs.
- **Error envelope** (all non-2xx responses):
  ```json
  { "error": { "code": "category_in_use", "message": "Human readable text", "details": { } } }
  ```
  For `422 validation_error`, `details` is a list of `{ "field": "amount", "message": "..." }`.
- **Status codes:**
  - 200 OK, 201 Created, 204 No Content.
  - 401 missing or invalid token / bad credentials.
  - 403 modifying a system category.
  - 404 not found or not owned.
  - 409 conflict (duplicate or in use).
  - 422 validation error.
- **Strings:** trimmed. Fields that must not be empty are rejected if empty after trimming.

---

## 4. Functional requirements

### 4.1 Authentication & users

| ID | Requirement |
|---|---|
| AUTH-01 | `POST /auth/register` body `{email, password, display_name, default_currency?}` → **201** with user profile (no password data). |
| AUTH-02 | Email must be valid. It is lowercased before storage and lookup. An existing email → **409** `email_taken`. |
| AUTH-03 | Password is 8–128 characters and is stored only as an Argon2id hash. |
| AUTH-04 | `POST /auth/login` body `{email, password}` → **200** `{access_token, token_type: "bearer", expires_in}`. |
| AUTH-05 | Wrong email *or* wrong password → **401** with the same generic message. When the email is unknown, the server still runs a hash verification so response timing doesn't reveal which emails exist. |
| AUTH-06 | JWT is HS256 with claims `sub` (user id), `iat`, `exp`. Default expiry is 60 minutes (configurable). Decoding pins `algorithms=["HS256"]`. |
| AUTH-07 | Missing, malformed, expired, or wrongly signed token, or a token whose user no longer exists → **401**. |
| USR-01 | `GET /users/me` → current user profile `{id, email, display_name, default_currency, created_at, updated_at}`. |
| USR-02 | `PATCH /users/me` body `{display_name?, default_currency?}`. Only these fields can be changed. |
| USR-03 | Changing `default_currency` to a different value while the user has ≥1 expense or ≥1 budget → **409** `currency_change_blocked` (D-05). |

### 4.2 Categories

| ID | Requirement |
|---|---|
| CAT-01 | `GET /categories` → the 7 system categories plus the user's own categories. System categories come first, then all are sorted by name. Never includes other users' categories. |
| CAT-02 | `POST /categories` body `{name, icon, color}` → **201**. name is 1–50 characters. icon is 1–50 characters matching `^[a-z0-9_-]+$`. color matches `^#[0-9A-Fa-f]{6}$`. |
| CAT-03 | Duplicate name (case-insensitive, trimmed) with the user's own categories or a system category → **409** `category_name_taken`. Different users may use the same name. |
| CAT-04 | `PATCH /categories/{id}` partial update of name/icon/color. The duplicate rule from CAT-03 applies. |
| CAT-05 | Updating or deleting a system category → **403** `system_category_readonly`. |
| CAT-06 | Updating or deleting another user's category, or a non-existent one → **404**. |
| CAT-07 | `DELETE /categories/{id}` with ≥1 expense → **409** `category_in_use`. `details.expense_count` holds the count, and the message suggests moving the expenses to another category first. |
| CAT-08 | `DELETE /categories/{id}` with no expenses → **204**. Budgets for the category are removed. |

### 4.3 Expenses

| ID | Requirement |
|---|---|
| EXP-01 | `POST /expenses` body `{amount, category_id, date, description?, receipt_url?}` → **201** `{expense, budget_warning}`. |
| EXP-02 | `category_id` must be a system category or one of the user's own. Otherwise → **404** `category_not_found`. |
| EXP-03 | `amount` is > 0 and ≤ 999999999.99 with at most 2 decimals. Negative, zero, too large, too precise, NaN, or Infinity → **422**. |
| EXP-04 | `date` must be ≥ 2000-01-01 and ≤ today (UTC) + 7 days. Later → **422**. Exactly +7 days is allowed. |
| EXP-05 | `description` is ≤ 500 characters after trimming. An empty or whitespace-only description is stored as `null`, the same as omitting it. `receipt_url` is an `http`/`https` URL of ≤ 2048 characters, stored in the URL parser's normalized form: the scheme and host are lowercased, and a bare domain gets a trailing `/`. For example, `HTTPS://Example.COM` is stored as `https://example.com/`. The 2048-character limit applies to this normalized form, because normalization can lengthen a URL (a space becomes `%20`); a URL that would exceed it → **422**. |
| EXP-06 | `currency` is set from the user's default currency (D-05). Sending `currency`, `user_id`, or any unknown field → **422** (D-13). |
| EXP-07 | `GET /expenses` returns `{items, total, limit, offset}` sorted by `date DESC, created_at DESC`. `offset` is at most 2^63 − 1 (PostgreSQL's BIGINT maximum); larger → **422**. |
| EXP-08 | Filters, all optional and inclusive: `date_from`, `date_to`, `category_id`, `min_amount`, `max_amount`. `min_amount` / `max_amount` accept values from 0 to 999999999.99 with at most 2 decimal places; anything else → **422**. `date_from > date_to` or `min_amount > max_amount` → **422**. |
| EXP-09 | `GET /expenses/{id}` → **200**. If not owned or missing → **404**. |
| EXP-10 | `PATCH /expenses/{id}`: partial update of `amount, category_id, date, description, receipt_url`, with the same validation as create. Setting `description`/`receipt_url` to `null` clears them. → **200** `{expense, budget_warning}`, the same response shape as EXP-01, with the warning computed by BAL-05 (D-16). |
| EXP-11 | `DELETE /expenses/{id}` → **204** (hard delete). If not owned or missing → **404**. |
| EXP-12 | `GET /expenses/export` takes the same filters as EXP-08 and returns a `text/csv` attachment with columns `id,date,amount,currency,category,description,receipt_url`, streamed. Cells starting with `= + - @` or tab/CR are prefixed with `'` to prevent spreadsheet formula injection. |

### 4.4 Budget alert (business logic)

The same check runs after both `POST /expenses` and `PATCH /expenses/{id}` (D-16). Both responses share one schema: `{expense, budget_warning}`.

| ID | Requirement |
|---|---|
| BAL-01 | After an expense is created or updated, the server computes `spent` = the sum of the user's expenses in the expense's **current** category for the **calendar month of its current date** (D-03). `spent` is a SQL `SUM` over the saved state, so it includes the created/updated expense at its new amount. |
| BAL-02 | If a budget exists for (user, category, year, month) **and** `budget > 0` **and** `spent > budget` (strictly greater), the response includes `budget_warning = {category, budget, spent, exceeded_by}`, where `exceeded_by = spent - budget`. |
| BAL-03 | Otherwise `budget_warning` is `null`. This covers no budget, a budget of 0 (D-04), and `spent == budget` exactly. |
| BAL-04 | The warning is reported every time a create or update leaves the month over budget, not only on the change that first crosses the limit. For example, a PATCH that only edits `description` still warns if that month is already over budget, the same way a small new expense in an over-budget month does. |
| BAL-05 | Applies to updates of `amount`, `category_id`, or `date`, alone or combined. The check uses the values after the update is applied. |
| BAL-06 | **Moving** an expense (new category and/or a date in a different month): the old category/month total no longer includes the expense, and the new category/month total includes it. This holds because totals always come from a fresh `SUM` over saved rows and are never adjusted incrementally. Reports and budget status for both the old and the new category/month show the change immediately. The warning covers only the **new** category/month. Removing an expense from the old one can only lower its total, so the update cannot cause a new overspend there. |

### 4.5 Budgets

| ID | Requirement |
|---|---|
| BUD-01 | `PUT /budgets` body `{category_id, year, month, amount}` creates (**201**) or updates the amount (**200**) for the unique key (user, category, year, month). |
| BUD-02 | `category_id` follows the same rule as EXP-02. |
| BUD-03 | `amount` is ≥ 0 and ≤ 999999999.99 with at most 2 decimals. 0 is allowed. |
| BUD-04 | Past and future months are allowed. `year` is 2000–2100 and `month` is 1–12. |
| BUD-05 | `GET /budgets?year=&month=` (both optional filters) → list of `{id, category_id, category_name, year, month, amount}`, sorted by year desc, month desc, then category name. |
| BUD-06 | `DELETE /budgets/{id}` → **204**. If not owned or missing → **404**. |

### 4.6 Reports

All report amounts are in the user's default currency (guaranteed by D-05). `year`/`month` default to the current UTC month. Totals are computed in SQL (`SUM … GROUP BY`), not by loading rows into Python.

| ID | Requirement |
|---|---|
| RPT-01 | `GET /reports/monthly-summary?year=&month=` → `{year, month, currency, total, by_category: [{category_id, category_name, total}]}`. Only categories with spending are listed, sorted by total desc. A month with no expenses → `total: 0, by_category: []`. |
| RPT-02 | `GET /reports/trend?months=N` (N is 1–24, default 6) → `{currency, months: [{year, month, total, change_amount, change_percent}]}`. The list runs from oldest to newest and ends with the current month. Months with no spending are filled with `0`. `change_*` compares with the previous month in the list. Both are `null` for the first month, and `change_percent` is `null` when the previous total is 0. |
| RPT-03 | `GET /reports/budget-status?year=&month=` → `{year, month, currency, items: [{category_id, category_name, budget, spent, remaining, percent_used, exceeded, has_limit}]}`, one item per budget the user has in that month. `remaining = budget - spent` (negative when over). `percent_used` is rounded to 2 decimals. `exceeded = spent > budget`. For a 0 budget: `has_limit = false`, `exceeded = false`, `percent_used = null` (D-04). |
| RPT-04 | Reports only ever include the requesting user's data. |
| RPT-05 | For monthly-summary and budget-status, `year` and `month` must be given together, or both omitted to use the current month. Only one of them → **422**. |

### 4.7 Operational

| ID | Requirement |
|---|---|
| OPS-01 | `GET /health` → **200** `{status: "ok"}` after checking the database connection. Used by the docker-compose healthcheck. |
| OPS-02 | OpenAPI docs are served at `/docs`. |

---

## 5. Non-functional requirements

| ID | Requirement |
|---|---|
| SEC-01 | Secrets and configuration come from environment variables (`DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `LOG_LEVEL`). The app refuses to start if `JWT_SECRET` is missing or shorter than 32 characters. `.env` is git-ignored, and `.env.example` is committed. |
| SEC-02 | Every query on user-owned data filters by `user_id` from the token. IDs from the client are never trusted for ownership. |
| SEC-03 | Passwords, password hashes, tokens, and `Authorization` headers are never logged or returned. |
| SEC-04 | The Docker image runs as a non-root user. |
| LOG-01 | Logs are structured JSON on stdout. Each request is logged once with `request_id`, `method`, `path`, `status`, `duration_ms`, and `user_id` (if authenticated). `X-Request-ID` is accepted or generated and echoed back in the response. |
| PERF-01 | Indexes are as in §2. Listing is paginated. Reports and the budget check use a constant number of aggregate queries regardless of data size. CSV export is streamed. |
| DB-01 | The schema is managed only by Alembic migrations. The API container runs `alembic upgrade head` on startup. |

---

## 6. Architecture

```
app/
  main.py            app factory, middleware, exception handlers
  config.py          settings from env (pydantic-settings)
  db.py              engine / session
  dates.py           UTC "today" and month arithmetic
  logging_config.py  JSON log formatter, request-logging middleware
  security.py        password hashing, JWT encode/decode
  deps.py            get_db, get_current_user
  errors.py          AppError hierarchy → error envelope
  models.py          SQLAlchemy models
  schemas/           Pydantic request/response models (per resource)
  services/          business logic + queries (per resource) — no HTTP concerns
  routers/           thin HTTP layer: parse → call service → shape response
migrations/          Alembic (schema + system category seed)
tests/
```

- Routers contain no business logic, and services don't know about HTTP.
- Services raise domain errors (`NotFound`, `Conflict`, …), which a single handler maps to the error envelope.
- `utc_today()` lives in one place so tests can freeze the date.

---

## 7. Test plan

Each test is isolated: it runs inside a transaction that is rolled back afterwards. Migrations run once per session, so the migrations themselves are tested too.

| Area | Tests (→ requirement IDs) |
|---|---|
| Auth flow | register → login → `/users/me` (AUTH-01, 04, USR-01); duplicate email, case-insensitive (AUTH-02); wrong password and unknown email give the same 401 (AUTH-05); no, garbage, expired, or wrongly signed token → 401 (AUTH-07); password not in any response (SEC-03) |
| Users | update name/currency (USR-02); currency change blocked once expenses or budgets exist, allowed again when neither does (USR-03) |
| Categories | list = system + own, never others' (CAT-01); duplicates incl. case and system names (CAT-03); system category is read-only (CAT-05); other user's category → 404 (CAT-06); delete in use → 409 with count (CAT-07); delete unused removes its budgets (CAT-08) |
| Expenses CRUD | create/get/update/delete (EXP-01, 09–11); other user's category → 404 (EXP-02); negative / zero / > max / 3 decimals → 422 (EXP-03); +7 days OK, +8 → 422 (EXP-04); `currency` field rejected (EXP-06); non-http URLs rejected, empty description stored as null, receipt URL normalized, 2048 limit checked after normalization (EXP-05); filters + pagination + `total`, out-of-range `offset` / amount filters → 422 (EXP-07, 08); cross-user access → 404 (SEC-02) |
| Budget alert (create) | under budget → null; exactly at budget → null; over → exact `exceeded_by` math; budget 0 → null; no budget → null; backdated expense checked against its own month; other categories/months/users don't count (BAL-01..04) |
| Budget alert (update) | PATCH raising `amount` over budget → warning with exact math; PATCH lowering `amount` back under → null; PATCH changing `category_id` into an over-budget category → warning for the new category; PATCH changing `date` into another month → checked against that month's budget; after a move, budget-status/monthly-summary show the old category/month without the expense and the new one with it; PATCH of `description` only in an already over-budget month → warning; PATCH response shape matches POST (EXP-10, BAL-01..06) |
| Budgets | upsert 201 then 200 (BUD-01); past month allowed (BUD-04); zero allowed, negative rejected (BUD-03); cross-user delete → 404 (BUD-06) |
| Reports | summary totals + by-category math with exact decimals (RPT-01); trend zero-fill, ordering, change math, null percent after a 0 month (RPT-02); budget status remaining/percent/exceeded incl. zero budget (RPT-03); no data leaks between users (RPT-04); only one of year/month → 422 (RPT-05) |
| Export | CSV content + formula-injection escaping (EXP-12) |
| Operations (`test_ops.py`) | health check without auth (OPS-01); JWT secret under 32 characters refused (SEC-01); request-ID echo, unsafe IDs replaced, one log line per request (LOG-01) |
| Test-database guard (`test_database_guard.py`) | the suite refuses to reset any database whose name doesn't end in `_test`, before any migration or connection; the password is never shown |

---

## 8. Out of scope

Currency conversion, income tracking, soft delete, refresh tokens / logout / token revocation, password change / reset, rate limiting, user deletion, multi-currency per user.
