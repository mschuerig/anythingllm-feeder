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

> **If something looks wrong** — your data dir got wiped, restored from backup, or AnythingLLM and forage disagree about what exists — start with [`IN_CASE_OF_ERRORS.md`](./IN_CASE_OF_ERRORS.md). It walks you through the diagnostic and recovery commands.

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

The fastest path on **macOS (Apple Silicon)** is Homebrew via a personal tap. Anything else — Intel Mac, Linux, Windows, or a development checkout — uses `uv` from source. Both options are documented below.

### Install via Homebrew (macOS Apple Silicon)

```sh
brew install mschuerig/tap/anythingllm-feeder
forage install-extras                          # optional, see below
```

The first command pulls in `ffmpeg`, installs `forage` and `ingest` into an isolated virtualenv, drops zsh and bash completions, and installs man pages (`man forage`, `man ingest`). The install itself is small and fast — just `httpx`, `send2trash`, `shtab`, and the project.

The second command (`forage install-extras`) is what brings in the heavy lifting: [`docling`](https://github.com/docling-project/docling) for PDF/Office extraction and [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper) for audio/video transcription. It runs pip against the formula's venv and downloads roughly **3–5 GB** (PyTorch is the bulk). Why isn't it bundled into the brew install? Because Homebrew's post-install Mach-O relocator doesn't play nicely with some of the wheels these libraries pull in, and the source-build workaround needs Cargo, which Homebrew's build sandbox blocks. Running pip outside the sandbox sidesteps both problems.

You can skip `install-extras` if you only want `ingest` (uploading already-extracted Markdown to AnythingLLM) or if you'll run `forage` against pre-extracted output.

A few things to know up front:

- **Apple Silicon only.** `mlx-whisper` requires the Apple Neural Engine, so the formula refuses to install on Intel Macs and Linux. On those platforms use the source install below.
- **Re-run `forage install-extras` after `brew upgrade`** — each version installs into a fresh venv.
- **AnythingLLM is separate.** Install via `brew install --cask anythingllm` if you want to use `ingest`.
- **State lives outside the keg.** Your collections, extracted Markdown, and upload bookkeeping live in `~/Library/Application Support/anythingllm-feeder/` and survive `brew upgrade` and `brew uninstall`. See **Uninstalling** below for a clean wipe.

### Install from source (everything else, or for development)

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

Append this to your shell rc file (`~/.zshrc` on macOS, `~/.bashrc` on most Linux), replacing the placeholder with wherever you cloned the repo:

```sh
export PATH="$HOME/path/to/anythingllm-feeder/.venv/bin:$PATH"
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
| `forage doctor` | Run the read-only consistency check across **every** collection; one line of output per collection, non-zero exit on any anomaly. See [`IN_CASE_OF_ERRORS.md`](./IN_CASE_OF_ERRORS.md). |
| `forage install-extras` | Install docling and mlx-whisper into the venv this `forage` is running in. Needed once after a Homebrew install (or after `brew upgrade`). No-op if both are already importable. |
| `forage purge -y` | Move the entire `anythingllm-feeder/` data root (forage **and** ingest state) to Trash. Refuses while a collection is in use. See **Uninstalling**. |

Useful `update` flags: `--source <name>`, `--ext pdf,mp4`, `--orphans list|delete|ignore` (default `list`), `--defer-video`, `--dry-run`, `--ocr` / `--no-ocr` (force OCR on/off for this run without touching the collection's saved setting).

`forage transcribe` also accepts `--whisper-model MODEL` to use a non-default Hugging Face mlx-whisper model id for a single run (otherwise the `whisper_model` value in `<forage-data-dir>/config.json` is used, falling back to the built-in default).

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
| `ingest reset <name> -y` | Delete ingest's local upload bookkeeping for one collection. Does **not** touch AnythingLLM. |
| `ingest purge -y` | Synonym for `forage purge` — moves the entire `anythingllm-feeder/` data root to Trash. Does **not** touch AnythingLLM. See **Uninstalling**. |

Useful `sync` flags: `--include-suspicious`, `--keep-orphans`, `--dry-run`.

### Connection flags (all ingest subcommands)

Every `ingest` subcommand accepts the following global flags, which override the matching environment variable or `config.json` setting. Precedence is always **CLI flag > env var > `config.json` > built-in default**.

| flag                  | replaces                                            |
|-----------------------|-----------------------------------------------------|
| `--url URL`           | `ANYTHINGLLM_URL` (default `http://localhost:3001`) |
| `--api-key KEY`       | `ANYTHINGLLM_API_KEY` — prints a one-line stderr note since the key ends up in shell history and `ps`; use `--api-key-file` for sensitive runs |
| `--api-key-file PATH` | same as `--api-key` but reads the key from a file (trailing whitespace trimmed); fails clearly if the file is missing or empty |
| `--storage-dir DIR`   | `ANYTHINGLLM_STORAGE_DIR` (for the storage report)  |
| `--http-timeout SEC`  | `INGEST_HTTP_TIMEOUT` (read/write timeout; default 300 s) |

Useful for ad-hoc invocations against a non-default instance, for example:

```sh
ingest --url http://localhost:3010 --api-key-file ~/.config/anythingllm.key sync news
```

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

Both tools share one data directory. None of your source files or your AnythingLLM workspaces are touched.

| platform | data root |
|---|---|
| macOS | `~/Library/Application Support/anythingllm-feeder/` |
| Linux | `$XDG_DATA_HOME/anythingllm-feeder/` → `~/.local/share/anythingllm-feeder/` |
| Windows | `%LOCALAPPDATA%\anythingllm-feeder\` |

Override with `ANYTHINGLLM_FEEDER_APP_SUPPORT` (mainly used by the test suite).

Inside the data root:

```
anythingllm-feeder/
├── forage/config.json                # whisper_model, defaults
├── ingest/config.json                # AnythingLLM url, storage_dir
└── collections/<name>/
    ├── forage/{state.db, output/, …} # forage's slice
    └── ingest/{uploads.db, …}        # ingest's slice
```

forage's slice holds your processed Markdown — back it up if you want to preserve work. ingest's slice holds only "what I've already uploaded" bookkeeping; deleting it (or running `ingest reset`) makes ingest re-upload everything on the next sync, creating duplicates inside AnythingLLM.

Whisper model files live under `~/.cache/huggingface/hub/` (shared with other tools).

If things ever look inconsistent — restored from backup, partial state, accidental wipe — start with [`IN_CASE_OF_ERRORS.md`](./IN_CASE_OF_ERRORS.md).

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
- **`forage state not found at …`** — check spelling against `forage list`, or `ANYTHINGLLM_FEEDER_APP_SUPPORT`.
- **A document I expected got skipped** — `ingest status <name> -v`. It's probably `suspicious` (use `--include-suspicious`), failed extraction (`forage info` shows recent failures), or waiting in the transcription queue.
- **Uploaded too much / made a mess** — delete the workspace inside AnythingLLM, then `ingest reset news -y && ingest sync news`.

### Logs

- forage: `<data-dir>/collections/<name>/forage/extract.log`
- ingest: `<data-dir>/collections/<name>/ingest/ingest.log`

Both files grow over time; safe to delete when not actively running.

---

## Updating

```sh
cd ~/path/to/anythingllm-feeder           # wherever you cloned this repo
git pull
uv sync --extra all
```

Your collections, processed files, and upload bookkeeping are untouched.

---

## Uninstalling

`brew uninstall` and `rm -rf` only remove the binaries. Your collections and upload bookkeeping live in a separate data directory (see **Where state lives**) and are intentionally preserved across reinstalls. Wipe them explicitly with `forage purge` and `ingest purge` while the binaries are still installed.

`forage purge` and `ingest purge` are synonyms in the current layout: both move the entire `anythingllm-feeder/` data root to the system Trash. Recover via Finder → Trash → Put Back if you change your mind.

### Homebrew install (macOS)

```sh
forage purge                              # moves the data root to Trash
brew uninstall anythingllm-feeder
```

Pass `-y` to skip the confirmation prompt.

### Source install

```sh
.venv/bin/forage purge -y                 # moves the data root to Trash
rm -rf ~/path/to/anythingllm-feeder       # the clone of this repo
```

If the project directory is already gone, fall back to deleting the data dir by hand:

```sh
# macOS
rm -rf ~/Library/Application\ Support/anythingllm-feeder

# Linux
rm -rf ~/.local/share/anythingllm-feeder
```

Documents already uploaded into AnythingLLM stay there — ingest only manages upload bookkeeping. To remove the documents themselves, delete the corresponding workspaces inside AnythingLLM.

### Downloaded model weights

forage's docling and mlx-whisper extractors download their model weights via Hugging Face Hub on first use. Those weights cache under `~/.cache/huggingface/hub/`, which is the standard Hugging Face cache location — **shared** with any other tool on your machine that uses the same models (Jupyter notebooks running whisper, a different transcription app, etc.). Because the cache might not be ours to throw away, `brew uninstall` and `forage purge` both leave it alone.

If you're certain no other tool on this machine needs that cache, free the space with:

```sh
rm -rf ~/.cache/huggingface/hub
```

A whisper model is typically 1–3 GB; docling's models are smaller. If something else does need them, leave the cache alone — those tools will silently re-download otherwise.

---

## For developers

```sh
uv sync --extra dev
uv run pytest                 # runs tests/forage + tests/ingest (~110 tests, <2s)
uv run forage --help
uv run ingest --help
```

forage's suite stubs out docling and mlx-whisper, so heavy libraries are never imported. ingest's suite wires `httpx.MockTransport` to an in-memory fake AnythingLLM and builds fake forage state in temp dirs. Neither suite touches real state directories — each test redirects `ANYTHINGLLM_FEEDER_APP_SUPPORT` per test, and an autouse fixture monkeypatches `send2trash` to `shutil.rmtree` so `purge`-path tests never reach the user's actual Trash.

See `SPEC-forage.md` and `SPEC-ingest.md` for the design specifications, `CLAUDE.md` for repo-wide conventions, and `DEVELOPMENT.md` for the release workflow.
