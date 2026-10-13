# AI Tool Usage

## Tools I Used

- **Claude Code** (Anthropic, Claude Opus model) inside VS Code. Claude Code generated most of the
  implementation, the tests and the documentation, and ran the commands used to test and verify
  the project.
- **ChatGPT**, used separately to understand technical concepts, discuss design decisions, and get
  a second opinion on Claude's recommendations before I approved them.

### How I worked

My role was to guide the development process rather than to write most of the code myself:

- Before any code was written, I had Claude analyse the assignment and list every ambiguity. I made
  each decision myself; they are recorded in `docs/SPEC.md §1`.
- I reviewed and approved the specification before implementation started.
- I questioned suggestions I didn't fully understand, asking whether each change was required by
  the assignment, fixed a real problem, or was just a preference.
- I approved every change to the project step by step, including each Docker step. Nothing was
  committed or pushed without my approval.
- Small readability improvements, such as renaming a variable (`stmt` → `spending_query` in
  `budget_alert.py`), were requested by me and implemented by Claude.

I did not do a complete line-by-line manual review of the code. I reviewed the specification, the
key files (the budget alert logic, its tests and the README) and every change Claude proposed. For
the rest I relied on the automated tests and a final review that checked every assignment
requirement against the code and the tests.

## What Helped Most

1. **Finding ambiguities before coding.** Claude flagged places where the assignment can be read
   more than one way, and turned each into a decision for me to make:
   - The budget alert says "the current month". Does a backdated expense count against its own
     month or against today's? I chose the expense's own month.
   - "Budget of zero → track but not limit" conflicts with a literal "spent > budget" check, which
     would warn on every expense. I decided that a zero budget never warns.
   - "Store amounts in the user's default currency" with no conversion raises the question of what
     happens when the user changes currency. I decided to block the change once expenses exist,
     and later extended it to expenses or budgets after an independent review pointed out that
     budget amounts are in the user's currency too.

   Without this step, those would have been silent guesses in the code.

2. **A test suite tied to the spec.** Each requirement has an ID, and the tests reference those IDs.
   That made it easy to check that every business rule and edge case is covered, especially the
   budget arithmetic: the exact example from the assignment (500 budget, 523.50 spent, exceeded by
   23.50) and a check that `0.1 + 0.2` comes out as exactly `0.3`.

3. **A final requirements review.** Before submitting, I asked for every requirement to be checked
   against the actual files, functions and tests. It confirmed full coverage, found a few
   untested behaviours (health check, secret length, request logging), and I approved adding tests
   for them.

## What I Had to Fix

1. **Budget warnings on update.** The first version of the spec followed the assignment literally
   and only checked budgets when an expense was created. I questioned whether updating an expense
   should also return a warning, since changing its amount, category or date can push a month over
   budget too. I discussed the implications with ChatGPT and then approved the resulting design:
   `PATCH /expenses/{id}` runs the same check and returns the same `{expense, budget_warning}`
   shape as creation, including when an expense moves to another category or month.

2. **Questioning changes before accepting them.** For example:
   - When some implementation details were added to the spec, I asked whether each was required,
     a real fix, or a preference before approving them.
   - Before accepting the new test dependency `httpx2`, I asked for its source and its
     compatibility with our Starlette version to be verified.
   - Before running Docker, I asked for a security review of the Docker files. It found that the
     placeholder secrets in `.env.example` were long enough to actually work. They are now empty,
     so Compose refuses to start until real secrets are set.

3. **Bugs found through AI-assisted review and testing.** These were not found by my own manual
   inspection of the code. Claude found them while reviewing its own code, running the tests
   against a real PostgreSQL database, and running the server end to end. My part was to
   understand each fix and approve it.
   - **SQL query:** the monthly summary query joined the `categories` table to itself and would
     have failed at runtime. It needed `select_from(Expense)`.
   - **Password handling:** a global "strip whitespace" setting would also have trimmed passwords,
     silently changing them. Separately, FastAPI's default validation error echoes the submitted
     value, so a rejected password would have been sent back in the response. Both were fixed and
     are covered by tests.
   - **PATCH validation:** sending `null` for a required field (e.g. `{"amount": null}`) would
     have caused a 500 error at the database. It now returns a 422.
   - **Timezones:** timestamps came back in the database server's local time zone once reloaded,
     but in UTC right after creation. The database connection now uses UTC.
   - **Alembic:** all tests passed, but the `alembic` command that the container runs on start-up
     couldn't import the application, so the container would have crashed. Running the server end
     to end exposed this. It was fixed with one line in `alembic.ini`.

## What AI Struggled With

- **Very recent library versions.** The project uses current releases (FastAPI 0.143,
  Starlette 1.7), and Claude wasn't sure how some of them behave. Examples: whether the database
  session stays open while a CSV export is streamed, and the switch from `httpx` to `httpx2` for
  the test client. These were settled by running small experiments rather than trusting
  assumptions.
- **The Windows environment.** Several shell commands had to be adjusted for Windows PowerShell.
  One check of the empty-secret protection gave a false pass because of a PowerShell quirk. Claude
  noticed and re-ran it properly.
- **Its own test mistakes.** One generated test used a date that the app's own 7-day rule rejects.
  The app was right, and the test was corrected.
- **Docker.** Docker wasn't installed on my machine at first, so the code was first verified against
  a temporary local PostgreSQL. I then installed WSL 2 and Docker Desktop, and the whole project ran
  in Docker: the image built, the migrations ran, the API and database were healthy, and the full
  test suite passed inside Docker: **131 passed, 0 failed, 0 skipped**.

## What I Learned

- **Specification first.** Writing down every requirement and resolving ambiguities before coding
  made the implementation easier to check and to explain, and it turned guesses into decisions I
  can defend.
- **Question AI suggestions.** Asking "is this required, does it fix a real problem, or is it a
  preference?" kept the project close to the assignment and avoided unnecessary changes.
- **Security reviews are worth doing explicitly.** The placeholder-secret problem and the password
  echo in error messages weren't obvious. They were only found because security was reviewed on
  purpose.
- **Passing tests aren't the same as a working deployment.** The Alembic start-up crash only
  appeared when the real server was run. Testing in a realistic environment (a real PostgreSQL
  database, then Docker) found problems the unit tests couldn't.
