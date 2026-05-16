# anythingllm-feeder

Two small command-line tools that together turn folders of documents and videos into a searchable knowledge base inside a local [**AnythingLLM**](https://anythingllm.com/) instance.

- **`forage`** scans your source folders and extracts every document/video to Markdown.
- **`ingest`** uploads forage's Markdown into AnythingLLM and keeps the workspace in sync as you add, change, or delete files.

```
your folders
   └── forage   (extracts to Markdown — PDF/Office via docling, audio/video via mlx-whisper)
        └── ingest   (uploads to AnythingLLM, one workspace per collection)
             └── AnythingLLM workspace   (you chat with it)
```

You don't need to be a developer to follow this README — just comfortable typing commands into the Terminal app.

---

## Platform support

Both tools are developed on **macOS (Apple Silicon)** and tested there. **Linux** works for everything except video/audio transcription (`mlx-whisper` is Apple Silicon only — on Linux you can still queue videos for later). **Windows** works in principle but is not regularly tested.

`ingest` assumes AnythingLLM is running on the **same machine** — it points at `http://localhost:3001` by default and has no retry/backoff or TLS support.

---

## Why text-only uploads?

AnythingLLM can ingest PDFs, Office documents, audio, and video directly via its built-in collector — you don't strictly need anything-llm-feeder to use it. This pipeline deliberately extracts to Markdown first and uploads only the text. The trade-off, with eyes open:

**What you gain by going through forage:**

- **Better extraction for the common cases.** docling (PDF/Office) and mlx-whisper (audio/video) are purpose-built; AnythingLLM's collector is a generalist. For complex PDFs and long audio, the Markdown ends up cleaner.
- **Hallucination filtering.** Whisper invents plausible-sounding text when there's nothing to transcribe. forage runs sanity checks and flags suspect transcripts as `suspicious`, kept out of AnythingLLM unless you opt in with `--include-suspicious`.
- **Cheap re-embedding.** When you switch embedding models inside AnythingLLM (which is exactly when this trade-off matters), only the Markdown needs to be re-embedded — no re-parsing PDFs, no re-transcribing hour-long videos.
- **Incremental sync is fast.** ingest compares forage's SHA-256 hashes against `uploads.db`; payloads over the wire are small text bodies, not whole files.
- **Big files never leave the machine.** A 2 GB video stays on disk; only its transcript travels to AnythingLLM.
- **You can hand-edit before upload.** The Markdown under `<forage-data-dir>/collections/<name>/output/` is plain text; remove a junk preamble or fix a misheard name and re-run `ingest sync`. AnythingLLM picks up the change via sha256.
- **Originals stay yours.** AnythingLLM holds only derived text plus a `forage://<collection>/<source>/<path>` pointer. If you ever migrate to a different RAG backend, your source folders are untouched and forage's output is portable Markdown.

**What you give up:**

- **No original-file preview in AnythingLLM.** The workspace shows the Markdown text only. There's no "open the PDF" button, no video player, no in-place page citations.
- **Lossy extraction.** Images embedded in PDFs come through only as OCR'd text (and only if OCR ran); complex tables can flatten to bulleted lists; equations may break. AnythingLLM never sees the layout.
- **Re-tuning extraction means re-extracting.** Change docling's OCR settings or upgrade whisper to a different model and you have to `forage update` everything to benefit. With direct upload, AnythingLLM's parser improvements apply on next collection re-parse.
- **Two tools, two state directories.** More moving parts than dragging a PDF onto AnythingLLM's UI.
- **The hallucination filter is heuristic.** Real transcripts occasionally get flagged. You'll sometimes want `ingest sync --include-suspicious` and a manual look.

**When direct upload via AnythingLLM's UI makes more sense:**

- One-off documents you want AnythingLLM to keep as referenceable artifacts (with the PDF viewable in the UI).
- Documents where the original layout — not just the text — is the point (legal contracts, formatted financial reports).
- You're trying AnythingLLM out and don't want to install anything else first.

For everything else — especially a growing knowledge base of mixed PDFs and long audio/video — text-only via forage is the cheaper, faster, more controllable path.

---

## Install

You'll install three things: **AnythingLLM** (only needed if you want to use `ingest`), **ffmpeg** (only needed for `forage`'s video features), and **Python 3.11+** with **uv** (a fast Python package manager).

Open a terminal (`Cmd+Space → terminal` on macOS, `Ctrl+Alt+T` on most Linux desktops).

### Prerequisites

**macOS** (via Homebrew — install with `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` if you don't have it yet):

```sh
brew install ffmpeg python uv
brew install --cask anythingllm     # optional, only if you want ingest
```

Launch AnythingLLM once from Applications so it can finish first-run setup, then quit.

**Linux** (Debian/Ubuntu):

```sh
sudo apt update
sudo apt install ffmpeg python3 python3-venv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:

```sh
python3 --version          # 3.11 or higher
uv --version
ffprobe -version           # only needed for forage video features
```

### Install the tools

`cd` into this folder (the one with this README), then:

```sh
uv sync --extra all        # Apple Silicon: forage + ingest + docling + mlx-whisper
# or:
uv sync --extra docling    # Linux / Intel Mac: forage + ingest + docling, no whisper
# or:
uv sync                    # ingest only (no document extractors)
```

This creates a `.venv/` inside the project, installs both `forage` and `ingest` commands, and pulls in any extras you asked for. The first install with `--extra all` can take several minutes because docling is large.

Verify:

```sh
.venv/bin/forage --help
.venv/bin/ingest --help
```

### Make the commands work from anywhere (optional)

Append this to your shell rc file (`~/.zshrc` on macOS, `~/.bashrc` on most Linux):

```sh
export PATH="$HOME/Projekte/anythingllm-feeder/.venv/bin:$PATH"
```

Either restart the terminal or `source ~/.zshrc`. After this, plain `forage` and `ingest` work from any folder.

---

## forage — quick start

You point forage at one or more folders. It scans each folder, runs every file through the right extractor (docling for documents, mlx-whisper for audio/video), and writes a `.md` file mirroring your folder structure. Re-runs only process new or changed files.

A few terms:

- **Collection** — a named bundle of source folders plus their extracted Markdown.
- **Source** — a folder belonging to a collection. A collection can have several sources.
- **Transcription queue** — videos/audio that take a long time to process. forage records them and you drain the queue in batches.

### Your first collection

```sh
forage create news --source archive=~/Documents/news-archive
forage update news                  # extract everything; first run can take a while
forage info news                    # per-source counts, queue depth, recent errors
```

Add or change files in the source folder, then re-run `forage update news`. forage figures out what changed.

### Videos and audio

Videos take a long time per file. Queue them and drain later:

```sh
forage update news --defer-video    # documents inline, videos queued
forage transcribe news --time-limit 8h    # overnight run
```

Useful `transcribe` flags: `--limit N`, `--time-limit 2h|90m|3600s`, `--retry-failed`, `--dry-run`.

### All forage commands

Each supports `-v`/`-q` and `--json` where useful.

| command | what it does |
|---|---|
| `forage create <name> --source N=P …` | Create a collection with one or more sources. |
| `forage list` | List every collection. |
| `forage info <name>` | Per-source status, totals, queue depth, recent errors. |
| `forage rename <old> <new>` | Rename a collection. |
| `forage remove <name>` | Delete a collection. Prompts about output files. |
| `forage add-source <coll> <name> <dir>` | Add another source to an existing collection. |
| `forage remove-source <coll> <name>` | Remove a source. Prompts about its output files. |
| `forage set-source <coll> <name> <new-dir>` | Tell forage that a source folder moved. |
| `forage update <name>` / `--all` | Walk sources, extract changed files, handle deletions. |
| `forage transcribe <name>` / `--all` | Drain the transcription queue. |
| `forage repair <name>` | Read-only consistency check. Add `--rebuild` to regenerate `state.db` from disk. |

Useful `update` flags: `--source <name>`, `--ext pdf,mp4`, `--orphans list|delete|ignore` (default `list`), `--defer-video`, `--dry-run`.

### Disabling OCR for a collection

`forage` runs OCR on every PDF by default. If you know a collection is entirely born-digital, edit `<data-dir>/collections/<name>/config.json` while no `forage` command is running and set `"do_ocr": false`.

### Suspicious transcripts

Whisper sometimes hallucinates. forage runs sanity checks (repetition, "thanks for watching" boilerplate, low word density, low confidence) and marks anything off as `suspicious` instead of `ok`. The Markdown is still written; `forage info` lists suspicious files.

---

## ingest — quick start

Once you have a forage collection, `ingest` uploads it into AnythingLLM. It creates one workspace per collection (named after the collection), and one **documents folder per source** named `<collection>-<source>` so files stay organized inside AnythingLLM's `storage/documents/` tree instead of piling up under `custom-documents/`.

### First sync

1. Launch **AnythingLLM** from Applications and leave it running.
2. Inside AnythingLLM, open **Settings → Tools → Developer API** and generate an API key. Copy it.
3. In your terminal, export the key:

   ```sh
   export ANYTHINGLLM_API_KEY='paste-the-key-here'
   ```

   To persist, add the same line to your shell rc file. If AnythingLLM is on a non-default port, also set `ANYTHINGLLM_URL`.

4. Verify the connection:

   ```sh
   ingest check
   # → AnythingLLM at http://localhost:3001: ok
   ```

5. Preview the diff (no upload happens):

   ```sh
   ingest status news
   # → collection: news    new: 42  changed: 0  unchanged: 0  orphans: 0
   ```

6. Sync:

   ```sh
   ingest sync news
   ```

   ingest creates a `news` workspace, uploads each `.md` as a document into a per-source folder (e.g. `news-archive/`), and embeds them. Final summary:

   ```
   news: uploaded=42 changed=0 unchanged=0 orphans_deleted=0 orphans_kept=0 failed=0
   ```

7. Switch to AnythingLLM and chat with the new workspace.

### Day-to-day loop

```sh
forage update news && ingest sync news       # one collection
forage update --all && ingest sync --all     # everything
```

`ingest sync --dry-run` walks the diff and prints actions without uploading.

### All ingest commands

| command | what it does |
|---|---|
| `ingest check` | Verify AnythingLLM is reachable and the API key works. |
| `ingest list` | List forage's collections and how many docs ingest has uploaded for each. |
| `ingest status <name>` | Show the diff (new / changed / unchanged / orphan) without uploading. |
| `ingest sync <name>` / `--all` | Upload changes; remove orphans by default. |
| `ingest reset <name> -y` | Delete ingest's local upload bookkeeping. Does **not** touch AnythingLLM. |

Useful `sync` flags: `--include-suspicious`, `--keep-orphans`, `--dry-run`.

### How ingest decides what to do

For each collection it compares forage's `state.db` (the canonical set of "good" docs) against its own `uploads.db` (what's been pushed). Each row lands in one of four buckets:

- **new** — in forage now, never uploaded → upload it.
- **changed** — uploaded before, content hash differs now → delete the old AnythingLLM doc, upload the new one.
- **unchanged** — uploaded before, content matches → skip.
- **orphan** — uploaded before, forage no longer lists it → delete from AnythingLLM (unless `--keep-orphans`).

ingest is content-aware: it uses forage's SHA-256, not mtime or size. Suspicious files are skipped unless you pass `--include-suspicious`; once opted in, they're kept on subsequent syncs as a safety net.

### Storage attribution

After your first sync, `ingest status <name>` also reports disk space the collection uses inside AnythingLLM (documents JSON, lancedb vectors, attributable total, plus the shared `vector-cache/`). On macOS desktop this is found automatically; elsewhere, set `ANYTHINGLLM_STORAGE_DIR` or `anythingllm_storage_dir` in `<data-dir>/config.json`.

---

## Where state lives

Both tools store state under platform-specific data directories. None of your source files or your AnythingLLM workspaces are touched.

| tool | macOS | Linux | Windows | env override |
|---|---|---|---|---|
| forage | `~/Library/Application Support/forage/` | `$XDG_DATA_HOME/forage/` → `~/.local/share/forage/` | `%LOCALAPPDATA%\forage\` | `FORAGE_APP_SUPPORT` |
| ingest | `~/Library/Application Support/ingest/` | `$XDG_DATA_HOME/ingest/` → `~/.local/share/ingest/` | `%LOCALAPPDATA%\ingest\` | `INGEST_APP_SUPPORT` |

forage's data dir holds your processed Markdown — back it up if you want to preserve work. ingest's data dir holds only "what I've already uploaded" bookkeeping; deleting it (or running `ingest reset`) makes ingest re-upload everything on the next sync, creating duplicates inside AnythingLLM.

Whisper model files live under `~/.cache/huggingface/hub/` (shared with other tools).

---

## Troubleshooting

### forage

- **`collection 'foo' already exists`** — use `forage list` or `forage remove foo` first.
- **`source path does not exist`** — double-check the `--source` path; use Tab-completion.
- **`collection locked: news`** — another forage process is running. Wait, or `ps aux | grep forage`.
- **A video shows `status: no_audio`** — ffprobe found no audio stream; nothing to transcribe.
- **A transcript is marked `suspicious`** — open it and decide whether to keep, edit, or delete.
- **Looks corrupted** — `forage repair news` (diagnostic) or `forage repair news --rebuild` (regenerates `state.db` from disk).

### ingest

- **`AnythingLLM not reachable at http://localhost:3001`** — start AnythingLLM, or set `ANYTHINGLLM_URL` if it's on another port.
- **`AnythingLLM rejected the API key`** — generate a fresh key in **Settings → Tools → Developer API** and `export` it again.
- **`ANYTHINGLLM_API_KEY is not set`** — `export ANYTHINGLLM_API_KEY='…'` in this terminal session.
- **`forage state not found at …`** — check spelling against `forage list`, or `FORAGE_APP_SUPPORT`.
- **A document I expected got skipped** — `ingest status <name> -v`. It's probably `suspicious` (use `--include-suspicious`), failed extraction (`forage info` shows recent failures), or waiting in the transcription queue.
- **Uploaded too much / made a mess** — delete the workspace inside AnythingLLM, then `ingest reset news -y && ingest sync news`.

### Logs

- forage: `<forage-data-dir>/collections/<name>/extract.log`
- ingest: `<ingest-data-dir>/collections/<name>/ingest.log`

Both files grow over time; safe to delete when not actively running.

---

## Updating

```sh
cd ~/Projekte/anythingllm-feeder
git pull
uv sync --extra all
```

Your collections, processed files, and upload bookkeeping are untouched.

---

## Uninstalling

```sh
# macOS
rm -rf ~/Projekte/anythingllm-feeder
rm -rf ~/Library/Application\ Support/forage
rm -rf ~/Library/Application\ Support/ingest

# Linux
rm -rf ~/Projekte/anythingllm-feeder
rm -rf ~/.local/share/forage ~/.local/share/ingest
```

Documents already uploaded into AnythingLLM stay there — ingest only manages upload bookkeeping. To remove the documents themselves, delete the corresponding workspaces inside AnythingLLM.

---

## For developers

```sh
uv sync --extra dev
uv run pytest                 # runs tests/forage + tests/ingest (~110 tests, <2s)
uv run forage --help
uv run ingest --help
```

forage's suite stubs out docling and mlx-whisper, so heavy libraries are never imported. ingest's suite wires `httpx.MockTransport` to an in-memory fake AnythingLLM and builds fake forage state in temp dirs. Neither suite touches real state directories — each test redirects `FORAGE_APP_SUPPORT` / `INGEST_APP_SUPPORT` per test.

See `SPEC-forage.md` and `SPEC-ingest.md` for the design specifications, and `CLAUDE.md` for repo-wide conventions.
