# Contributing to CCNA Lab Tracker

This is a small local-first web app — `Robyn` (Python) backend + Alpine.js
frontend + SQLite. The bar for new dev to running app is **<30 minutes**;
if you hit a wall, that's a docs bug, please open an issue.

## Quick dev setup

```powershell
# Windows (PowerShell)
git clone <this-repo>; cd CCNA-Lab-Tracker
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

```bash
# Linux / macOS
git clone <this-repo> && cd CCNA-Lab-Tracker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Browser at http://localhost:8080. The app boots with 51 seeded labs;
drop `.pka` files via the **Import** tab to attach them.

## Architecture (5 lines)

`app.py` boots Robyn + loads cached static assets. Routers in `routers/`
parse HTTP and delegate to `services/`. Services own DB access via
`aiosqlite` + the singleton in `database/connection.py`. The frontend
is a single SPA shell (`public/index.html` + `app.js` + `style.css`)
read once at startup and held in memory. SQLite (`database/labs.db`)
holds labs, attempts, and progress.

## Folder map

| Folder | Purpose |
|--------|---------|
| `core/` | Cross-cutting helpers: logging setup, response helpers, constants |
| `routers/` | Robyn `SubRouter`s — one file per resource (`labs`, `progress`, `launcher`, `stats`, `importer`) |
| `services/` | Business logic — DB access, file I/O, Packet Tracer launching |
| `database/` | Connection singleton, schema, seed data |
| `public/` | Frontend (HTML / Alpine.js / CSS — no build step) |
| `scripts/` | One-off utilities (e.g. `split_pdf.py` for per-lab PDFs) |
| `docs/` | Per-lab PDFs (gitignored, generated locally) |
| `labs/` | Imported `.pka` files (gitignored) |

## Conventions

- **Async-first.** All route handlers and services are `async`. Don't
  block the event loop with sync I/O on the hot path. The one exception
  is `import_single_file` (uses `shutil.copy2` — documented inline).
- **Error responses go through `core.responses.err()`.** Robyn 0.64
  needs a 3-tuple with an empty headers dict; `err(body, status)` is
  the only safe way to return 4xx/5xx. See the docstring in
  `core/responses.py` for why.
- **Logging via loguru only.** `core/logging_config.py` hijacks stdlib
  `logging` so Robyn's noise gets formatted consistently. Don't import
  `logging` directly. Use `logger.bind(name="...")` to tag the
  subsystem (`http`, `db`, `app`, `config`, ...).
- **SQL parameters always bind via `?` placeholders** — never
  f-string-format user input into queries.
- **No comments that restate code.** Add a comment only when the *why*
  is non-obvious (a workaround, a hidden constraint, a framework quirk).

## Where to start contributing

Open a few of these and start at the smallest:

- **TODOs** in `core/logging_config.py:11-14` — `.bind(name=...)` is
  inconsistently applied across services.
- **MEDIUM/LOW review findings** still open: see the project plan
  file for the full list (fetch timeout, modal focus trap, schema
  versioning, ruff/black, GitHub Actions, etc.).
- **Tests** — `tests/` contains pytest setup and a few smoke tests.
  Adding more is always welcome: extract_lab_id boundaries, timer
  race conditions, path validation, schema migrations.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests use in-memory SQLite — no real DB I/O. End-to-end runtime should
stay under 5 seconds; if a test takes longer, prefer mocking over real
filesystem.

## Pull requests

- One change per PR. A PR that bundles "fix bug + refactor + new
  feature" is harder to review and harder to revert.
- Run the app locally and click through the affected feature before
  pushing — type checking and tests verify code correctness, not
  feature correctness.
- Keep commit messages tight: `<type>(<scope>): <what>`. Types:
  `feat`, `fix`, `refactor`, `docs`, `test`, `chore`. Body explains
  the *why* if non-obvious.
- Don't push to `main` directly. Open a PR and request review.

## Deployment notes

The app launches Cisco Packet Tracer as a desktop process — it is
designed to run on the same machine as the user's PT install. A future
multi-player / leaderboard mode (deployed to ESXi) will decouple
score tracking from PT launching, but that's out of scope for now.

## Questions?

File an issue. The project is small enough that "ping the maintainer
in the issue tracker" is the entire support channel.
