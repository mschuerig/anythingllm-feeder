# anythingllm-feeder — agent notes

This repo bundles two CLIs:

- **forage** (`src/forage/`) — extracts documents/videos to Markdown. Independent of AnythingLLM.
- **ingest** (`src/ingest/`) — uploads forage's output into a local AnythingLLM. Reads forage's `state.db` read-only; never writes into forage's tree.

Both share a small `src/_shared/` package for platform-path resolution, logging setup, and UTC timestamps.

## Where to look

- **`SPEC-forage.md`** — authoritative spec for forage's behavior, data model, CLI, and acceptance scenarios. Read before designing forage changes.
- **`SPEC-ingest.md`** — authoritative spec for ingest's behavior, data model, CLI, AnythingLLM API contract, and acceptance scenarios. Read before designing ingest changes.

## Shared conventions (both tools)

- **Storage paths** route through each tool's `paths.py`, which delegates platform resolution to `_shared.appdirs.resolve_app_support(name, env_override)`. macOS → `~/Library/Application Support/<name>/`, Linux → `$XDG_DATA_HOME/<name>/`, Windows → `%LOCALAPPDATA%\<name>\`. No hard-coded paths elsewhere.
- **Timestamps** in DB and config are ISO 8601 UTC strings via `_shared.timestamps.utc_now()`. Source-file mtimes stay POSIX float.
- **Logging** is set up via each tool's `log.py`, which delegates to `_shared.log`. One logger per tool fans out to stderr (filtered by `-v`/`-q`) and to the active collection's `*.log` file.
- **Test isolation**: every test redirects `FORAGE_APP_SUPPORT` and/or `INGEST_APP_SUPPORT` to a tmp dir via fixtures in the relevant `conftest.py`.

## forage-specific (`src/forage/`)

- DB writes go through typed functions in `src/forage/db.py`. Don't inline SQL in commands.
- Extraction outputs are atomic: write to `<path>.tmp`, fsync, rename. Centralized in `src/forage/output.py`.
- Whisper heuristic thresholds (boilerplate list, repetition count, density, logprob) live as module-level constants near the top of `src/forage/extractors/whisper.py`.
- `src/forage/extractors/` is the only place that may import heavy optional dependencies (docling, mlx-whisper). Imports are lazy via `forage.extractors.get_extractor` — `forage.extractors._REGISTRY` is monkeypatched in tests so the real libraries are never loaded.

## ingest-specific (`src/ingest/`)

- Forage's `state.db` is **read-only**. `forage_db.open_readonly` uses the `file:?mode=ro` SQLite URI.
- Local DB writes go through typed functions in `src/ingest/state.py`. Don't inline SQL in commands.
- HTTP goes through `src/ingest/anythingllm.py`. Exception hierarchy: `AnythingLLMError` (base) → `ServerUnreachable` (connect/timeout), `AuthError` (401/403), `RemoteError` (other non-2xx, carries body). The CLI catches these at the top level and prints a single-line `error: ...`.
- The server is **local**. Do not add retry/backoff loops, TLS handling, or rate-limit logic. Fail fast.
- Timeouts are split: connect 5 s (server-down fails fast), read/write 300 s (large extracts take minutes). Overridable via `INGEST_HTTP_TIMEOUT`.
- `sync_collection` runs a reconciliation pass before the diff: lists AnythingLLM's documents and deletes any whose `docSource` is `forage://<this-collection>/...` but whose `location` isn't in `uploads.db`. Cleans up phantom documents from previous runs where the upload completed on the server after our client gave up. Scoped to the current collection.
- Uploads use `POST /api/v1/document/raw-text`, never `/document/upload`. forage already produced clean Markdown.
- `compute_diff`'s `keep_alive_keys` argument protects previously-uploaded `suspicious` documents from being deleted when the user runs without `--include-suspicious`. Don't drop it (see SPEC-ingest.md acceptance scenario 7).
- `src/ingest/storage.py` is the *only* module that knows AnythingLLM's on-disk layout (`documents/`, `lancedb/<slug>.lance/`, `vector-cache/`). Resolution of the storage dir (env → config → platform default) lives in `config.resolve_anythingllm_storage_dir`; it returns `None` when the dir doesn't exist and callers must treat that as "skip, don't fail."

## Test layout

- forage: `tests/forage/`. The `app_support` fixture in `tests/forage/conftest.py` redirects `FORAGE_APP_SUPPORT`. docling/mlx-whisper extractors are stubbed via `_REGISTRY` monkeypatching.
- ingest: `tests/ingest/`. `tests/ingest/_helpers.py` holds `FakeForageFile`, `create_forage_state`, and `FakeAnythingLLM` (in-memory REST stand-in). `tests/ingest/conftest.py` exposes them as fixtures; `client_factory` wires the HTTP client via `httpx.MockTransport(server.handle)` and sets `ANYTHINGLLM_API_KEY=test-key`. Tests must never touch real AnythingLLM or real forage state.

## Running

```sh
uv sync --extra all --extra dev     # everything + pytest
uv run pytest                       # both suites; should run in <2s
uv run forage --help
uv run ingest --help
```

`uv run ingest check` exercises the live local AnythingLLM (requires `ANYTHINGLLM_API_KEY`).

## Things that look load-bearing but aren't

- ingest's `workspace_slug_for(collection)` currently returns the collection name unchanged. It exists as the single point of truth in case slug munging (lowercasing, sanitizing) is ever needed; do not bypass it.
- Per-source documents folder name: `<collection>-<source>`. Computed in `sync._target_folder`. Tracked in-memory per sync run (`ensured_folders`) so `create-folder` is called at most once per (collection, source) pair, regardless of upload count.
- `--all` on forage's `update`/`transcribe` and ingest's `sync` walks every collection. It's a convenience; per-collection is the unit of work.
