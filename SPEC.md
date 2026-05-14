# ingest — specification

## Purpose

A command-line tool that uploads the documents produced by [`forage`](../forage/) (Markdown extracts in a per-collection tree, indexed by a SQLite manifest) into a **locally running** AnythingLLM instance, idempotently and incrementally. Re-running after a `forage update` pushes only the delta: new files, content changes, and orphans (forage no longer lists a previously-uploaded document).

Forage's own SPEC explicitly leaves AnythingLLM integration out of scope. This is that integration.

## Platform and dependencies

- Python 3.11+.
- Single runtime dependency: `httpx` (>= 0.27). Stdlib for everything else (`sqlite3`, `argparse`, `logging`, `json`).
- Built and tested on macOS (Apple Silicon). Code is portable to Linux; AnythingLLM lifecycle on other platforms is not our concern.
- **Targets a local AnythingLLM only.** Installed via Homebrew on the developer's machine. There is no remote/hosted use case. The HTTP client is therefore intentionally simple: no retry/backoff loop, no TLS-specific handling, no rate-limit accommodation. If the server is down, we fail loudly with one actionable error and stop.

## Interaction with forage

- Forage's `state.db` is opened **read-only** via the `file:<path>?mode=ro` SQLite URI form. Forage runs in WAL mode (see `forage/SPEC.md`), so we never block its writes.
- Forage's storage root is located via the same algorithm forage uses, including the `FORAGE_APP_SUPPORT` env override. We never write into forage's directory tree.
- We read three fields from forage's `files` table: `(source, path)` (PK), `sha256` (content hash; our cache key), `status`, plus `output_path`, `extractor`, `extracted_at` for metadata and addressing. The full forage schema is documented in `forage/SPEC.md`.
- Only rows with `status = 'ok'` are uploaded by default. `--include-suspicious` adds `status = 'suspicious'`. Other statuses (`pending`, `failed`, `no_audio`) are never uploaded.

## Storage layout

All ingest state lives under a platform-specific data directory, hereafter `<app-support>`:

| platform           | `<app-support>` default                                         |
|--------------------|-----------------------------------------------------------------|
| macOS              | `~/Library/Application Support/ingest/`                         |
| Linux / other Unix | `$XDG_DATA_HOME/ingest/`, falling back to `~/.local/share/ingest/` |
| Windows            | `%LOCALAPPDATA%\ingest\`, falling back to `~/AppData/Local/ingest\` |

The `INGEST_APP_SUPPORT` environment variable overrides the default. The test suite uses this to redirect state into per-test temp directories.

Layout under `<app-support>`:

```
<app-support>/
├── config.json                       # global config (base URL, workspace prefix)
└── collections/
    └── <collection-name>/
        ├── uploads.db                # SQLite, our local upload-state manifest
        └── ingest.log                # append-only run log
```

The collection-name subdirectory mirrors forage's `<forage-app-support>/collections/<name>/`. Same name on both sides; resolved separately.

## Configuration

`config.json` (global):

```json
{
  "version": 1,
  "base_url": "http://localhost:3001",
  "workspace_prefix": "forage-"
}
```

Env overrides (env wins over config):

| variable                | purpose                                                 |
|-------------------------|---------------------------------------------------------|
| `ANYTHINGLLM_URL`       | Base URL of the local AnythingLLM server.               |
| `ANYTHINGLLM_API_KEY`   | **Required**. Bearer token (Settings → Developer).      |
| `INGEST_APP_SUPPORT`    | Override ingest's storage root (testing).               |
| `FORAGE_APP_SUPPORT`    | Read forage state from a non-default root (testing).    |

The API key is never persisted to disk. If unset when a network call is needed, the command fails with a clear message. `--dry-run` is the one exception: it tolerates a missing key because it does no I/O against the server.

## Data model

### `uploads.db` (SQLite)

The schema lives in `src/ingest/state.py`. WAL mode, single-writer; ingest itself is sequential and there is no concurrent process expected to touch this file.

**`meta`** — schema-version marker, single row keyed on `'schema_version'`.

**`uploads`** — one row per (collection-relative) document currently embedded in AnythingLLM by us.

| column            | type    | notes                                                                  |
|-------------------|---------|------------------------------------------------------------------------|
| `source`          | TEXT    | Forage source slug. Part of PK.                                        |
| `path`            | TEXT    | Forage source-relative path. Part of PK.                               |
| `sha256`          | TEXT    | Content hash at the time of upload (copied from forage).               |
| `anythingllm_loc` | TEXT    | The `location` string AnythingLLM returned at upload time.             |
| `workspace_slug`  | TEXT    | The workspace into which the document was embedded.                    |
| `forage_status`   | TEXT    | The forage status at upload time (`ok`, `suspicious`); diagnostic.     |
| `uploaded_at`     | TEXT    | ISO 8601 UTC timestamp of the upload.                                  |

Primary key: `(source, path)` (matches forage's PK).

The presence of a row means "we believe this document currently exists in AnythingLLM at `anythingllm_loc`." Mismatch is handled by the reconciliation pass on the next sync.

## Workspace mapping

One AnythingLLM workspace per forage collection. The workspace slug is `<prefix><collection-name>`, where `<prefix>` defaults to `forage-` and is configurable in `config.json`. The workspace is auto-created on first sync if it does not exist; afterwards it is reused.

Sources within a collection are **not** mapped to AnythingLLM folders in v1. Each document's `docSource` metadata field is `forage://<collection>/<source>/<path>`, which is sufficient to identify provenance in search results without depending on folder mechanics.

## Upload payload

We use `POST /api/v1/document/raw-text`, never `POST /api/v1/document/upload`. Forage has already extracted clean Markdown; routing it back through AnythingLLM's Collector (which re-parses files) is wasted work and an extra error surface.

Request body:

```json
{
  "textContent": "<contents of the .md file>",
  "metadata": {
    "title": "<source>/<filename-without-.md>",
    "docSource": "forage://<collection>/<source>/<path>",
    "description": "extractor=<docling|mlx-whisper>; sha256=<hash>"
  }
}
```

The response includes a `documents` array; we keep `documents[0].location`. That `location` is what `/workspace/.../update-embeddings` and `/system/remove-documents` take.

## Sync algorithm

For each invocation of `ingest sync <collection>`:

1. **Locate forage state.** Compute `<forage-app-support>/collections/<name>/state.db`. Open read-only. Fail with `forage state not found at <path>` if missing.
2. **Open local state.** Open or create `<app-support>/collections/<name>/uploads.db` and run the schema migration (idempotent `CREATE TABLE IF NOT EXISTS`).
3. **Read forage rows.** Two queries against `files`:
   - `in_scope` — `status = 'ok'` (and `'suspicious'` if `--include-suspicious`). These are the rows we will consider for upload.
   - `keep_alive` — `status IN ('ok', 'suspicious')`, *unconditionally*. Their `(source, path)` keys are used to protect previously-uploaded suspicious documents from being deleted when the user runs without `--include-suspicious`. See `compute_diff` in `src/ingest/sync.py`.
4. **Compute diff** against the local `uploads` table:
   - **new** — in `in_scope`, not in `uploads`.
   - **changed** — in both, `sha256` differs.
   - **unchanged** — in both, `sha256` matches.
   - **orphan** — in `uploads`; key is in neither `in_scope` nor `keep_alive`. These are documents forage no longer trusts (status flipped to `failed`/`pending`/`no_audio`, or the source file was deleted).
5. **If `--dry-run`** — log the diff (one line per item under verbose) and return. No HTTP, no state writes.
6. **Ensure workspace.** `GET /api/v1/workspaces`; if no slug matches `<prefix><collection>`, `POST /api/v1/workspace/new {"name": "<prefix><collection>"}`.
7. **For each `new` row:**
   - Read the `.md` file at `<forage-app-support>/collections/<name>/output/<output_path>`.
   - `POST /api/v1/document/raw-text` with the body above. Capture `documents[0].location`.
   - `POST /api/v1/workspace/<slug>/update-embeddings {"adds": [location]}`.
   - Insert a row into `uploads`.
8. **For each `changed` (row, prior) pair:**
   - `POST /api/v1/workspace/<slug>/update-embeddings {"deletes": [prior.location]}`.
   - `DELETE /api/v1/system/remove-documents {"names": [prior.location]}`.
   - Upload + embed the new version as in step 7. Upsert (replace) the `uploads` row.
9. **For each `orphan` upload:**
   - If `--keep-orphans`: log and skip.
   - Else: same delete sequence as the "changed" pre-step, then `DELETE FROM uploads`.
10. **Summarize.** Per-collection counts of `uploaded`, `changed`, `unchanged`, `orphans_deleted`, `orphans_kept`, `failed`. Exit code is `0` iff `failed == 0`.

Per-document failures are caught and counted; the sync continues for the remaining documents. `ForageStateError`, `ServerUnreachable`, and `AuthError` are *not* per-document — they abort the run immediately.

## CLI

```
ingest <command> [options]
```

Global flags (accepted on any command):

- `-v`, `--verbose`
- `-q`, `--quiet`
- `--json`: machine-readable output for `status` and `list` (and `check`'s output).

### Commands

#### `ingest sync <name> [options]`

Run the sync algorithm for one collection.

Options:

- `--include-suspicious` — also upload rows with `status = 'suspicious'`. Off by default.
- `--keep-orphans` — log orphans but do not delete them from AnythingLLM. Off by default.
- `--dry-run` — compute and log the diff, issue no HTTP, write nothing to `uploads.db`.

#### `ingest sync --all [options]`

Run `sync` against every forage collection in sequence. Same options.

#### `ingest status <name> [--include-suspicious] [--json]`

Compute the diff against the current `uploads.db` and print it. No HTTP, no state writes.

#### `ingest list [--json]`

List every forage collection (anything with a `config.json` under `<forage-app-support>/collections/`) and our per-collection upload row count.

#### `ingest check [--json]`

Verify the AnythingLLM server is reachable and the API key works:

1. Resolve settings (env + config). Fail if `ANYTHINGLLM_API_KEY` is missing.
2. `GET /api/v1/auth`.
3. `GET /api/v1/workspaces` and print the count + slugs.

Returns 0 on success, 1 on any failure with a single-line error message. JSON form is suitable for use as a CI / pre-flight gate.

#### `ingest reset <name> -y`

Delete ingest's local `uploads.db` for `<name>`. The next `ingest sync` will re-discover everything as `new` and re-upload, producing duplicates in AnythingLLM (AnythingLLM does not deduplicate by content). The `-y` confirmation is required — without it the command prints a warning and exits non-zero.

This does **not** touch documents already in AnythingLLM. Use this only when the local state has drifted past the point of useful reconciliation.

## Error model

`src/ingest/anythingllm.py` defines:

| exception          | when it fires                                                      |
|--------------------|--------------------------------------------------------------------|
| `ServerUnreachable`| `httpx.ConnectError` or `httpx.TimeoutException` on any request.   |
| `AuthError`        | Response status 401 or 403.                                        |
| `RemoteError`      | Any other non-2xx status. Carries `status`, `url`, and `body`.     |

All three subclass `AnythingLLMError`. The CLI catches them at the top level and exits 1 with a single-line `error: ...` message — no stack trace.

`forage_db.ForageStateError` is the equivalent for missing or unreadable forage state.

## Concurrency

Sequential throughout. One sync run per collection at a time. No file lock — `uploads.db` writes are per-row, and ingest is not expected to run concurrently with itself against the same collection (forage's WAL means *its* writes are safe to read concurrently; ours just don't overlap).

## Logging

Each collection has an `ingest.log` (append-only). Each sync run emits:

- One INFO line at start with the diff counts.
- One INFO line per upload/replace/orphan-delete with the action and remote `location`.
- One ERROR line per per-document failure.
- One INFO line at end with the result summary.

Console output mirrors the file at INFO by default; `-v` raises it to DEBUG, `-q` lowers to ERROR. `src/ingest/log.py` owns the setup; same pattern as forage's `log.py`.

## Out of scope for v1

- Mapping forage sources to AnythingLLM folders (cosmetic; `move-files` API is deferred). Workspace mapping is what matters for RAG.
- Non-Markdown upload paths (PDF passthrough via `/document/upload`). Not useful while forage already produces clean Markdown.
- Watch mode. Manual `forage update && ingest sync` is fine.
- Concurrency.
- Renaming/moving collections inside AnythingLLM when the forage collection is renamed.
- A `repair` command that diffs AnythingLLM's actual contents against `uploads.db` (useful, but not blocking).
- Multi-tenant / remote AnythingLLM. Authentication design is single-key, single-server.

## Acceptance scenarios

1. **First sync.** A forage collection `demo` has 3 `ok` documents. `ingest sync demo`. The workspace `forage-demo` is created. Three raw-text uploads happen, each followed by `update-embeddings`. `uploads.db` has three rows.
2. **Idempotent.** Run `ingest sync demo` again. Zero uploads, three unchanged. No `raw-text` POST is issued (verify via the AnythingLLM access log or the test transport's request list).
3. **Change detection.** Edit one source file, `forage update demo` rewrites the Markdown, sha256 changes. `ingest sync demo`. One replace (old remote doc deleted, new one uploaded), two unchanged.
4. **Orphan.** Delete a source file, `forage update demo --orphans delete` drops the row. `ingest sync demo`. The previously-uploaded doc is deleted from AnythingLLM and from `uploads.db`.
5. **Keep orphans.** Same as (4) with `--keep-orphans`. The doc remains in AnythingLLM; the local `uploads` row also remains.
6. **Suspicious gate.** A `suspicious` row exists in forage. `ingest sync demo` skips it. `ingest sync demo --include-suspicious` uploads it.
7. **Suspicious safety.** After (6) (with the suspicious doc uploaded), re-run `ingest sync demo` *without* `--include-suspicious`. The suspicious doc must remain in AnythingLLM — it is protected by `keep_alive_keys`, not treated as an orphan.
8. **Status-flip cleanup.** A previously-uploaded doc's forage status flips to `failed` (re-extraction failed). The next `ingest sync` deletes it from AnythingLLM (it's no longer in the unconditional keep-alive set).
9. **Dry-run.** `ingest sync demo --dry-run` after any change reports the diff and writes nothing. The fake/real server sees zero requests.
10. **Server down.** Stop the AnythingLLM service. `ingest sync demo` exits 1 with `error: AnythingLLM not reachable at <URL> — is the service running? ...` and `uploads.db` is unchanged.
11. **Bad key.** Run with a wrong API key. The first auth-required request returns 401; the command exits 1 with the "Generate a fresh key" hint.
12. **Reset.** `ingest reset demo -y` deletes `uploads.db`. The next `ingest sync demo` re-uploads everything as `new`, producing duplicates in AnythingLLM (documented; that's why the command requires `-y`).
