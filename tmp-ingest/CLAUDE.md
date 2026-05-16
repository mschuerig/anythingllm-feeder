# ingest — agent notes

## Where to look

`SPEC.md` is the authoritative reference for behavior, data model, CLI, AnythingLLM API contract, and acceptance scenarios. Read it before designing changes. The sibling forage project (`../forage/`) has its own `SPEC.md` describing the upstream data we read.

## What this is

A small CLI that reads a forage collection's manifest + Markdown output and pushes it into a **local** AnythingLLM (Homebrew-installed). One workspace per collection. Re-runs are incremental and idempotent.

## Conventions

- All storage paths are resolved through `src/ingest/paths.py`. No hard-coded paths elsewhere. `paths.app_support_dir()` returns the platform default (macOS → `~/Library/Application Support/ingest`), overridable via `INGEST_APP_SUPPORT`. Forage's app-support is resolved separately via `paths.forage_app_support_dir()`, honoring `FORAGE_APP_SUPPORT`.
- Forage's `state.db` is **read-only** from our side. `forage_db.open_readonly` uses the `file:?mode=ro` SQLite URI. Never write into forage's tree.
- Local DB writes go through typed functions in `src/ingest/state.py`. Don't inline SQL in commands.
- HTTP goes through `src/ingest/anythingllm.py`. All exceptions inherit from `AnythingLLMError`: `ServerUnreachable` (connect/timeout), `AuthError` (401/403), `RemoteError` (other non-2xx, carries body). The CLI catches these at the top level and prints a single-line `error: ...`.
- The server is **local**. Do not add retry/backoff loops, TLS-specific code, or rate-limit handling. If it's down, fail fast with the actionable error already in `_request`.
- Timeouts are split: connect is short (5s — server-down still fails fast) but read/write is long (300s default, overridable via `INGEST_HTTP_TIMEOUT`) because `/document/raw-text` chunks and embeds inline, and large extracts (book-sized PDFs converted to Markdown) routinely take minutes.
- `sync_collection` runs a reconciliation pass before the diff: it lists AnythingLLM's documents and deletes any whose `docSource` is `forage://<this-collection>/...` but whose `location` isn't in `uploads.db`. This cleans up phantom documents from previous runs where the upload completed on the server after our HTTP client gave up — without it, re-running sync would create duplicates. The pass is scoped to the current collection; other collections' `forage://` docs are untouched.
- Uploads use `POST /api/v1/document/raw-text`, never `/document/upload`. Forage already extracted clean Markdown; re-parsing it through AnythingLLM's Collector is wasted work.
- Sync's diff classification is in `src/ingest/sync.py::compute_diff`. The `keep_alive_keys` argument protects previously-uploaded `suspicious` documents from being deleted when the user runs without `--include-suspicious`. Don't drop this parameter without understanding the failure mode it prevents (see SPEC.md acceptance scenario 7).
- `src/ingest/storage.py` is the *only* module that knows AnythingLLM's on-disk layout (`documents/`, `lancedb/<slug>.lance/`, `vector-cache/`). Keep it that way: if you need a new storage number, extend this module rather than scattering path knowledge into commands. Resolution of the storage dir (env → config → platform default) lives in `config.resolve_anythingllm_storage_dir`. It returns `None` when the dir doesn't exist; callers must treat that as "skip, don't fail."
- Timestamps are ISO 8601 UTC strings (`config.utc_now()`), matching forage's format.
- `src/ingest/log.py` owns logging setup; one logger fans out to stderr (filtered by `-v`/`-q`) and to the collection's `ingest.log`.

## Test layout

- `tests/_helpers.py` holds the `FakeForageFile` dataclass, the `create_forage_state` builder (writes a minimal forage `state.db` + output tree), and `FakeAnythingLLM` (an in-memory stand-in for the REST API). `tests/conftest.py` exposes them as fixtures.
- For tests, point `INGEST_APP_SUPPORT` *and* `FORAGE_APP_SUPPORT` at tmp dirs. The `ingest_home` and `forage_home` fixtures in `conftest.py` do this.
- The AnythingLLM client is wired to the fake server via `httpx.MockTransport(server.handle)` injected into `AnythingLLMClient(transport=...)`. The `client_factory` fixture sets this up and also sets `ANYTHINGLLM_API_KEY=test-key` / `ANYTHINGLLM_URL=http://localhost:0`.
- Tests must never hit a real AnythingLLM. If one is running locally during a test run, the `MockTransport` short-circuits the request before any TCP happens.

## Running

- `uv sync --extra dev` — set up the venv.
- `uv run ingest --help` — CLI entrypoint.
- `uv run pytest` — full test suite. Should be fast (< 1s) and self-contained.
- `uv run ingest check` — pre-flight against a live local server. Requires `ANYTHINGLLM_API_KEY` exported.

## Things that look load-bearing but aren't

- The `workspace_prefix` setting (default `forage-`) exists so a user can run multiple ingest configs against one AnythingLLM instance without slug collisions. Default is fine for the single-user case.
- `--all` on `sync` walks every forage collection. It's a convenience; the per-collection sync is the unit of work.
