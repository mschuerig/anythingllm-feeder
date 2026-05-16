# forage — specification

## Purpose

A command-line tool that extracts text from documents and videos into Markdown, for downstream use by a local LLM (specifically AnythingLLM). It maintains multiple **collections**, each tracking one or more **sources** (directory trees on disk) and producing a parallel Markdown tree. Operation is incremental: re-running picks up new and changed files, handles deletions, and skips unchanged work.

## Platform and dependencies

- Python 3.11+.
- Developed on macOS (Apple Silicon, M1 Max). The Python code is portable; storage paths, file locks, and the docling extractor work on macOS, Linux, and Windows.
- Video/audio transcription uses `mlx-whisper` and therefore currently requires Apple Silicon. On other platforms the `whisper` extra simply isn't installable; everything else continues to work and videos can still be queued (`--defer-video`), just not drained.
- External tools invoked as subprocesses or imported libraries:
  - `docling` — PDF and other document extraction. Cross-platform.
  - `mlx-whisper` (a.k.a. `whisper-mlx`) — video/audio transcription. Apple Silicon only.
  - `ffprobe` / `ffmpeg` — audio stream inspection and extraction for whisper input. Install via the platform's usual package manager (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Debian/Ubuntu, etc.).

No coupling to MacWhisper. mlx-whisper downloads its own models to its huggingface cache (`~/.cache/huggingface/hub/` on Unix).

## Storage layout

All forage state lives under a platform-specific data directory, hereafter `<app-support>`:

| platform                | `<app-support>` default                         |
|-------------------------|-------------------------------------------------|
| macOS                   | `~/Library/Application Support/forage/`         |
| Linux / other Unix      | `$XDG_DATA_HOME/forage/`, falling back to `~/.local/share/forage/` |
| Windows                 | `%LOCALAPPDATA%\forage\`, falling back to `~/AppData/Local/forage/` |

The `FORAGE_APP_SUPPORT` environment variable overrides the default. The test suite uses this to redirect state into a per-test temp directory.

Layout under `<app-support>`:

```
<app-support>/
├── config.json                       # global config (whisper model, defaults, etc.)
└── collections/
    └── <collection-name>/
        ├── config.json               # collection config (sources, etc.)
        ├── state.db                  # SQLite manifest + transcription queue
        ├── extract.log               # append-only log
        ├── .lock                     # file-lock sentinel (single-writer guard)
        └── output/                   # parallel Markdown hierarchy
            └── <source-name>/        # one subtree per source
                └── ...               # mirrors structure under that source's root
```

Each source's output sits under its own named subdirectory. The source name is supplied by the user when the source is added and must match `^[a-z0-9][a-z0-9_-]*$` (lowercase slug — it doubles as a directory name and a key in the database).

Output files mirror the source tree, with the extension replaced by `.md`. Example, for a collection `news` containing a source named `archive` rooted at `~/Documents/news-archive/`:

```
source:  ~/Documents/news-archive/2025/article.pdf
output:  <app-support>/collections/news/output/archive/2025/article.md
```

## Data model

### `state.db` (SQLite)

The schema lives in `src/forage/db.py`. The database is opened in WAL mode (`PRAGMA journal_mode = WAL`), so a `sqlite3` CLI can safely read the file while a `forage` process is writing.

Three tables.

**`meta`** — schema-version marker, single row keyed on `'schema_version'`.

**`files`** — one row per source file ever seen.

| column         | type     | notes                                                                  |
|----------------|----------|------------------------------------------------------------------------|
| `source`       | TEXT     | Source name (slug). Part of PK.                                        |
| `path`         | TEXT     | Path relative to that source's root. Part of PK.                       |
| `sha256`       | TEXT     | Content hash. Computed lazily; see "Change detection".                 |
| `mtime`        | REAL     | Source file mtime as POSIX seconds.                                    |
| `size`         | INTEGER  | Source file size in bytes.                                             |
| `output_path`  | TEXT     | Output path relative to `output/` (so includes the source-name prefix).|
| `extractor`    | TEXT     | `docling`, `mlx-whisper`, ...                                          |
| `status`       | TEXT     | See "Status values".                                                   |
| `status_detail`| TEXT     | Free-form message (error text, suspicion reason, ...).                 |
| `extracted_at` | TEXT     | ISO 8601 UTC timestamp of last successful extraction.                  |
| `updated_at`   | TEXT     | ISO 8601 UTC timestamp of last row write.                              |

Primary key: `(source, path)`. The same relative path may legitimately appear under two different sources within one collection.

**`queue`** — pending and historical transcription jobs.

| column         | type     | notes                                                    |
|----------------|----------|----------------------------------------------------------|
| `source`       | TEXT     | Source name. Part of PK.                                 |
| `path`         | TEXT     | Source-relative path. Part of PK. FK to `files`.         |
| `status`       | TEXT     | `pending`, `running`, `done`, `failed`.                  |
| `error`        | TEXT     | Last error message if `failed`.                          |
| `enqueued_at`  | TEXT     | ISO 8601 UTC.                                            |
| `started_at`   | TEXT     | ISO 8601 UTC, NULL if not yet started.                   |
| `finished_at`  | TEXT     | ISO 8601 UTC.                                            |

Primary key: `(source, path)`, with a foreign key into `files(source, path)`.

All video files pass through `queue`, even when transcribed inline during `update`. This means a Ctrl-C or crash mid-transcription leaves a recoverable record.

### Status values (in `files`)

| status        | meaning                                                                   |
|---------------|---------------------------------------------------------------------------|
| `ok`          | Extracted successfully, output file exists.                               |
| `pending`     | Discovered, awaiting extraction (used for queued videos pre-transcription).|
| `failed`      | Extraction attempted and failed. `status_detail` has error text.          |
| `suspicious`  | Output written, but post-hoc heuristics flagged possible hallucination.   |
| `no_audio`    | Video has no audio stream. No output written.                             |

Orphans (source files that disappeared) are surfaced by `update` and either listed or deleted there — they are not persisted as a status. See "Orphan handling".

### `config.json` (global)

```json
{
  "version": 1,
  "whisper_model": "mlx-community/whisper-large-v3-turbo",
  "defaults": {
    "orphans": "list"
  }
}
```

### `config.json` (per collection)

```json
{
  "version": 1,
  "name": "news",
  "created_at": "2026-05-14T12:00:00Z",
  "do_ocr": true,
  "sources": [
    {
      "name": "archive",
      "path": "/home/me/Documents/news-archive",
      "created_at": "2026-05-14T12:00:00Z"
    },
    {
      "name": "drafts",
      "path": "/home/me/Documents/news-drafts",
      "created_at": "2026-05-14T12:30:00Z"
    }
  ]
}
```

Source names are unique within a collection. Each source path must be an existing directory.

`do_ocr` controls docling's OCR pass for this collection. Defaults to `true`. Set to `false` for corpora known to be entirely born-digital (PDFs, Office docs without embedded images) to speed up extraction. Edit the file directly while no `forage` process is running against the collection; the new setting takes effect on the next `forage update`.

## Extractors

### Docling (default for non-video)

- File extensions: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.txt`, `.md`. (Anything docling accepts; configurable in code but not on CLI for v1.)
- Reuse a single `DocumentConverter` instance per run to amortize model load.
- Export to Markdown via `result.document.export_to_markdown()`.
- OCR is **on by default** (safe choice — born-digital PDFs are still extracted natively; OCR is a supplementary pass that catches text in scanned pages and image regions). Each collection's `config.json` has a top-level `do_ocr` boolean (default `true`); set it to `false` to skip the OCR pass entirely, which makes runs noticeably faster on corpora with no scanned material.
- Table-structure on (docling default).
- On exception, record `status: failed` with the exception's message.

### mlx-whisper

- File extensions: `.mp4`, `.mov`, `.m4v`, `.mkv`, `.webm`, `.mp3`, `.wav`, `.m4a`.
- Pre-check via `ffprobe`: if no audio stream, record `status: no_audio` and skip.
- Language: probe filename and every parent directory name for two-letter or full-name hints (`de`/`deu`/`deutsch`/`german`, `en`/`eng`/`english`); default to English.
- Markdown output: a header block listing source filename, duration, and detected language, followed by section headings of the form `## MM:SS` (or `## H:MM:SS`) every 5 minutes, with all segment texts under that heading concatenated as a single paragraph. See `format_markdown` in `src/forage/extractors/whisper.py` for the canonical implementation.
- Post-hoc hallucination heuristics, run on the produced segments. Thresholds and the boilerplate phrase list are module-level constants near the top of `src/forage/extractors/whisper.py` so they're easy to tune:
  1. **Repetition**: any single segment text repeated ≥`REPETITION_THRESHOLD` (4) times consecutively → flag.
  2. **Boilerplate**: total transcript ≤`SHORT_TRANSCRIPT_CHARS` (200) AND matches (case-insensitive, substring) any phrase in `BOILERPLATE_PHRASES`. Default list covers common YouTube-style sign-offs in English and German.
  3. **Density**: for videos longer than `DENSITY_MIN_DURATION_SECONDS` (300), transcript words / video duration in seconds < `DENSITY_WORDS_PER_SECOND` (0.3) → flag.
  4. **Confidence**: if mlx-whisper exposes `avg_logprob` per segment, mean across segments < `LOGPROB_THRESHOLD` (-1.0) → flag.
- On any heuristic firing: write the Markdown anyway, set `status: suspicious`, put the triggering reason(s) in `status_detail`.

## Change detection

For each source walked, and for each file under that source's root:

1. Look up the row in `files` by `(source, relative-path)`.
2. If absent → **new**, extract.
3. If present and `(mtime, size)` matches stored → **unchanged**, skip.
4. If `(mtime, size)` differs → compute sha256.
   - If sha256 matches stored → touch the row (update `mtime`, `size`), skip.
   - If sha256 differs → **changed**, re-extract.

After the source walk, sweep `files` for rows whose `path` no longer exists under its source's root → **orphan**.

Move detection (rename): in v1, treat as delete + add. Hash-based rename detection is a nice-to-have, skipped for now.

## Orphan handling

After the change-detection pass, `update` handles orphans according to `--orphans`:

- `list` (default): print orphan source paths and their output paths. Do nothing.
- `delete`: remove the output file (if it exists) and the `files` row.
- `ignore`: silent.

When `update` is scoped to a single source via `--source`, the orphan sweep is also scoped to that source. The default (whole-collection) walk sweeps every source.

## CLI

```
forage <command> [options]
```

Global flags (accepted on any command):

- `-v`, `--verbose`: more output.
- `-q`, `--quiet`: errors only.
- `--json`: machine-readable output where it makes sense (`list`, `info`).

### Commands

#### `forage create <name> --source NAME=PATH [--source NAME=PATH ...]`

Create a new collection with one or more sources.

- The `--source` flag is repeatable; at least one is required.
- Each `NAME` is a slug matching `^[a-z0-9][a-z0-9_-]*$`, unique within the collection.
- Each `PATH` must exist and be a directory.
- Creates `<app-support>/collections/<name>/` and subdirs, one per source.
- Writes collection `config.json`, creates empty `state.db` with schema.
- Errors if a collection with that name already exists, if a source name is invalid or duplicated, or if a source path is not a directory.

#### `forage list`

List collections with one-line summaries (name, source count, source names).

With `--json`, emit a structured array including each collection's sources.

#### `forage info <name>`

Detailed status of one collection:

- Created-at timestamp, output directory.
- Per-source breakdown: name, path, file counts by status, output size on disk.
- Total file counts by status.
- Pending transcription queue depth.
- Storage usage: total bytes under the collection directory, with a breakdown
  for the `output/` tree, `state.db`, and `extract.log`. Human output formats
  these in IEC units (KiB/MiB/...); `--json` reports raw bytes under
  `storage_bytes`.
- Recent failures (last N, e.g. 10).
- Suspicious transcripts (last N).

With `--json`, emit a structured object.

#### `forage update <name>`

Walk the collection's sources, extract new/changed files, handle orphans.

Options:

- `--source <name>`: scope discovery (and orphan sweep) to a single source. Without it, every source is walked.
- `--ext pdf,mp4,...`: only process files with these extensions in this run. Comma-separated, no dots. Affects discovery only; orphan detection still considers the full set.
- `--orphans list|delete|ignore` (default: `list`).
- `--defer-video`: discover videos and enqueue them as `pending`, but skip inline transcription. Without this flag, videos are transcribed inline.
- `--dry-run`: report what would happen, write nothing.

Behavior for videos with `--defer-video`:
- New/changed videos: insert into `files` with `status: pending`, insert into `queue` with `status: pending`. No transcription.

Behavior for videos without `--defer-video`:
- New/changed videos: insert into `files` with `status: pending`, insert into `queue` with `status: pending`. Then immediately attempt transcription, updating both rows on completion.

Existing `pending` queue entries are **not** drained by `update`. Only `transcribe` drains them. (Confirmed user preference.)

#### `forage update --all [options]`

Run `update` on every collection in sequence. Same options.

#### `forage transcribe <name>`

Drain the transcription queue.

Options:

- `--limit N`: process at most N items.
- `--time-limit DURATION`: stop after DURATION (e.g. `4h`, `90m`, `3600s`).
- `--retry-failed`: also process items with `status: failed` (default: skip them).
- `--dry-run`: list what would be processed, do nothing.

Processes oldest-enqueued first. Updates both `queue` and `files` rows on completion or failure.

#### `forage transcribe --all [options]`

Across all collections, oldest-first.

#### `forage add-source <collection> <name> <dir>`

Add a new source to an existing collection.

- Validates the source name and that `<dir>` exists and is a directory.
- Errors if the source name already exists in the collection.
- Creates the corresponding `output/<name>/` subdirectory.

#### `forage remove-source <collection> <name>`

Remove a source from a collection.

- Prompts interactively: "Delete output files for source `<name>`? [y/N]"
- `--delete-files`: skip prompt, delete the source's `output/<name>/` subtree.
- `--keep-files`: skip prompt, keep outputs (they remain on disk under `output/<name>/` but are no longer tracked).
- `--yes`/`-y` paired with `--delete-files` or `--keep-files` is the non-interactive form.

Removes all `files` and `queue` rows for that source.

#### `forage set-source <collection> <name> <new-dir>`

Update the directory of a named source. Validates the new path exists. Does not move or re-extract anything; assumes the user moved the directory and wants forage to follow.

#### `forage repair <name>`

Recovery operations.

Options (mutually exclusive):

- `--check` (default): run `PRAGMA integrity_check` on `state.db`; reconcile `files` rows against the actual source and output trees; report discrepancies (rows with missing source files, rows whose output file is missing, output files with no row, db rows whose source is no longer in the collection's config). Read-only.
- `--rebuild`: drop `state.db` and recreate it by walking each source plus the output tree. Output files are assumed correct; sha256 is recomputed from source. Items in the previous queue are lost (acceptable — they'll re-enter as `pending` on next `update` if the source still exists).

#### `forage rename <old-name> <new-name>`

Rename a collection. Renames the directory under `collections/`. Updates the collection's `config.json`. No db changes needed.

#### `forage remove <name>`

Remove a collection's metadata and (optionally) outputs.

- Prompts interactively: "Delete output files too? [y/N]"
- `--delete-files`: skip prompt, delete the whole collection directory.
- `--keep-files`: skip prompt, remove only metadata (`config.json`, `state.db`, `extract.log`, `.lock`) while leaving the `output/` tree on disk.
- `--yes`/`-y` paired with `--delete-files` or `--keep-files` is the non-interactive form.

## Logging

Each collection has an `extract.log` (append-only) recording:

- Run start/end with command-line invocation.
- Each file processed: path, status, duration.
- Each error with stack trace.

Log lines are plain text, one event per line, timestamped. No log rotation in v1 — the user can delete or truncate manually.

Stdout output is human-readable progress: a line per file processed in verbose mode, a summary at the end always.

## Concurrency and atomicity

- Sequential processing throughout. No worker pool.
- Each extraction writes to `<output>.tmp`, then renames to `<output>` on success. Interrupts leave no partial output files.
- DB writes are per-file transactions. Crash mid-run leaves the db in a consistent state with that file still marked `pending` (or its previous status).
- A simple file lock (`fcntl.flock` on Unix-likes, `msvcrt.locking` on Windows, both held against the collection's `.lock` sentinel) prevents two `forage` processes from operating on the same collection simultaneously. Other collections can run in parallel.

## Implementation notes

A few decisions that the spec leaves open but the code has chosen:

- **CLI parser**: `argparse` from the stdlib. Per-subcommand flags plus a small set of global flags. Each subcommand handler lives in `src/forage/commands/`.
- **Logging**: stdlib `logging`. `src/forage/log.py` sets up one logger with a stderr handler (filtered by `-v`/`-q`) and adds a per-collection file handler for the duration of any command that writes (`update`, `transcribe`, `repair`).
- **Progress for long transcribes**: per-file, not per-segment. Each queue entry emits a single log line on completion (`running`, then `ok` / `suspicious` / `no_audio` / `failed`). For finer detail set `-v` or read the segment log emitted by `mlx-whisper` itself.
- **mlx-whisper API**: invoked as `mlx_whisper.transcribe(path, path_or_hf_repo=model, language=lang, verbose=False)`; the returned dict's `segments` key is expected to contain `start`, `end`, `text`, optionally `avg_logprob` per segment.

## Out of scope for v1

- Watch-mode / automatic re-runs (manual trigger is fine).
- Time Machine / Spotlight exclusion of the output directory (deferred per user).
- Concurrency across multiple files in one collection.
- Move detection via content hash.
- Log rotation.
- AnythingLLM upload integration (forage produces Markdown; uploading is a separate concern).

## Acceptance scenarios

1. **Create and first sync.** `forage create news --source archive=~/news`. `forage update news`. All PDFs become Markdown under `output/archive/`. `forage info news` shows per-source and total counts.

2. **Incremental.** Add one new PDF to the source. Re-run `forage update news`. Only the new file is processed.

3. **Update detection.** Modify an existing PDF (touch is not enough — content must change). Re-run. The file is re-extracted, output replaced.

4. **Orphan.** Delete a source PDF. Re-run `forage update news`. The output is listed as orphan (default). Re-run with `--orphans delete`. Output file and db row are gone.

5. **Bulk video deferral.** Drop 30 new tutorial videos into a music collection. `forage update music --defer-video`. Documents processed, videos queued. `forage info music` shows queue depth 30. Run `forage transcribe music --time-limit 2h` overnight repeatedly until drained.

6. **Suspicious transcript.** Transcribe a silent music demo. Heuristics fire. Markdown is written, status is `suspicious`. `forage info music` lists it.

7. **Recovery.** Corrupt or delete `state.db`. `forage repair news --rebuild` reconstructs the db from disk.

8. **Multiple sources.** `forage create research --source papers=~/Papers --source notes=~/Notes`. `forage update research` produces `output/papers/...` and `output/notes/...`. `forage add-source research drafts ~/Drafts` adds a third source; a subsequent `forage update research` processes only the new source's files. `forage remove-source research notes --delete-files` removes the source from config, drops its rows, and clears `output/notes/`.
