# ingest

A small command-line tool that takes the Markdown files [forage](../forage/) has extracted and uploads them into your local **AnythingLLM** so you can chat with them.

If forage is the part that gets your documents into a clean text form, ingest is the part that hands them over to AnythingLLM. You run forage when you add or change documents, then run ingest to push the updates into AnythingLLM. Re-running ingest only sends what has changed; nothing is uploaded twice.

This README walks through the whole thing from a fresh machine: installing the prerequisites, starting AnythingLLM, installing ingest, and getting your first collection of documents searchable inside AnythingLLM. You don't need to be a developer — just comfortable typing commands into the Terminal app.

---

## How ingest fits in

A few terms used throughout this README:

- **AnythingLLM** — the local chat app you'll be feeding documents to. It runs on your Mac, holds your documents in *workspaces*, and lets you ask questions about them.
- **Collection** (forage's word) — a named bundle of source folders and their extracted Markdown. You might have a `news` collection, a `research` collection, and so on.
- **Workspace** (AnythingLLM's word) — the unit AnythingLLM searches against when you chat. ingest creates one workspace per forage collection, so each collection stays separate inside AnythingLLM.
- **Sync** — what ingest calls "look at the collection, send anything new, replace anything that changed, remove anything that's been deleted." It's the main command you'll run.

The mental picture:

```
your folders
   └── forage  (extracts to Markdown)
        └── ingest  (uploads to AnythingLLM)
             └── AnythingLLM workspace  (you chat with it)
```

forage and ingest are separate tools. You can use forage without ingest. You can't use ingest without forage — it reads forage's bookkeeping to know what to upload.

---

## Platform support

ingest is developed on **macOS (Apple Silicon)** and tested there. The code is portable to Linux. There is no Windows story.

It assumes AnythingLLM is running **on the same machine**. ingest is not designed to upload to a hosted AnythingLLM instance — there's no retry/backoff logic, no auth-token rotation, no multi-tenant support. It points at `http://localhost:3001` by default.

---

## Before you start: install the prerequisites

You'll install three things: **AnythingLLM** (the chat app), **forage** (the document extractor), and **ingest** (this tool). Plus the small set of tools forage and ingest need underneath: Python 3.11+ and **uv** (a Python package manager that keeps each tool isolated from the rest of your system).

Open a terminal:

- **macOS**: press `Cmd+Space`, type `terminal`, hit Return.
- **Linux**: open your distribution's terminal application (often `Ctrl+Alt+T`).

### Install AnythingLLM

The easiest way on macOS is Homebrew. If you don't have Homebrew yet (`brew --version` to check), install it:

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then:

```sh
brew install --cask anythingllm
```

Launch AnythingLLM once from the Applications folder so it can finish first-run setup (pick an embedder, choose where its data lives, etc.). Quit it afterwards — we'll start it again in a minute.

> If you've installed AnythingLLM another way (the official download, Docker, …), that's fine too — it just needs to be running locally and reachable over HTTP. Make a note of the URL it serves on; you'll need it later.

### Install Python and uv

On macOS:

```sh
brew install python uv
```

On Linux:

```sh
sudo apt install python3 python3-venv          # Debian / Ubuntu
# or:
sudo dnf install python3                       # Fedora
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify:

```sh
python3 --version          # 3.11 or higher
uv --version
```

### Install forage

ingest reads from forage's data directory, so forage must be installed and have at least one collection. If you haven't set forage up yet, follow [forage's README](../forage/README.md) — it covers installation and the first few collections in detail. Come back here once `forage list` shows something.

---

## Install ingest

ingest isn't published to any package index; you install it directly from this folder.

`cd` into the folder containing this README. For example:

```sh
cd ~/Projekte/ingest
```

Install:

```sh
uv sync
```

This creates a `.venv/` folder inside the project, downloads ingest's one dependency (`httpx`), and installs the `ingest` command. The install is fast — under a minute.

Verify:

```sh
.venv/bin/ingest --help
```

You should see a list of subcommands (`sync`, `status`, `list`, `check`, `reset`).

### Make `ingest` work from anywhere (optional)

To avoid typing `.venv/bin/ingest` every time, add the project's `.venv/bin` to your `PATH`. Append this line to your shell's rc file (`~/.zshrc` on macOS's default zsh, `~/.bashrc` on most Linux bash setups):

```sh
export PATH="$HOME/Projekte/ingest/.venv/bin:$PATH"
```

(Adjust the path if you installed ingest somewhere else.) Restart the terminal, or run `source ~/.zshrc`.

After this, plain `ingest --help` works from any folder.

---

## Walkthrough: from a folder of documents to chatting in AnythingLLM

This is the full path, start to finish. Skim it once, then come back and do it step by step.

We'll pretend you have a folder of PDFs at `~/Documents/news-archive` and you want to ask AnythingLLM questions about them.

### 1. Get the documents into forage

If you haven't already, create a forage collection and run the first extraction:

```sh
forage create news --source archive=~/Documents/news-archive
forage update news
```

This produces a parallel tree of `.md` files under forage's data directory. Check that it worked:

```sh
forage info news
```

You should see a per-source breakdown with files counted as `ok`.

### 2. Start AnythingLLM and create an API key

Launch AnythingLLM from the Applications folder (or however you installed it). Leave it running — we'll be talking to it over HTTP.

Inside AnythingLLM, open **Settings → Tools → Developer API** (the menu name varies a little between versions — look for "Developer" or "API Keys"). Generate a new API key and copy it to the clipboard.

> Treat the API key like a password. Anyone with it can read and write every workspace on your AnythingLLM instance. Don't paste it into chats, screenshots, or commits.

### 3. Tell ingest the API key

In your terminal, export the key as an environment variable:

```sh
export ANYTHINGLLM_API_KEY='paste-the-key-here'
```

This sets it for the current terminal session only. To make it permanent, add the same line to your shell rc file (`~/.zshrc` / `~/.bashrc`).

If AnythingLLM is running on a port other than `3001`, also set:

```sh
export ANYTHINGLLM_URL='http://localhost:WHATEVER-PORT'
```

(In AnythingLLM you can usually see the URL it's serving on in its main window's title bar or in **Settings → Tools**.)

### 4. Confirm ingest can talk to AnythingLLM

```sh
ingest check
```

Expected output:

```
AnythingLLM at http://localhost:3001: ok
workspaces: 0
```

(Or however many workspaces you already have.) If `check` fails, fix the connection before moving on — none of the other commands will work either. See [Troubleshooting](#troubleshooting) below.

### 5. See what ingest is about to do

```sh
ingest status news
```

This prints a small summary of how the forage collection compares to what ingest has already uploaded:

```
collection: news
  new:       42
  changed:   0
  unchanged: 0
  orphans:   0
```

On a first run everything is "new." Pass `-v` to see the file list.

### 6. Run the sync

```sh
ingest sync news
```

ingest creates a workspace called `forage-news` inside AnythingLLM, uploads each `.md` file as a separate document, and adds each one to the workspace's embeddings (so it can be searched). For 42 small documents this takes seconds; for hundreds it can take a couple of minutes — there's a line of output per file in verbose mode.

You'll see a final summary line:

```
news: uploaded=42 changed=0 unchanged=0 orphans_deleted=0 orphans_kept=0 failed=0
```

### 7. Chat with your documents

Switch back to AnythingLLM. You should see a new workspace called `forage-news` in the sidebar. Open it and start asking questions — AnythingLLM will pull relevant chunks from your documents and answer based on them.

### 8. Later, when you add or change documents

After dropping new files into `~/Documents/news-archive` (or editing existing ones), run the same two commands in order:

```sh
forage update news     # re-extract changed files to Markdown
ingest sync news       # push the delta to AnythingLLM
```

Files that didn't change are skipped on both sides. ingest replaces the AnythingLLM doc for any file forage re-extracted, and removes documents for files you've deleted from the source folder (if you used `forage update news --orphans delete`).

That's the whole loop.

---

## Day-to-day workflow

For a single collection:

```sh
forage update news && ingest sync news
```

For everything:

```sh
forage update --all && ingest sync --all
```

If you only want to *see* what would change without uploading, use `--dry-run`:

```sh
ingest sync news --dry-run
```

It walks the diff and prints exactly what would happen, but no documents move and no local state is written.

---

## All commands

Each command supports `-v` / `--verbose` (more progress detail) and `-q` / `--quiet` (errors only). `--json` produces machine-readable output where it makes sense.

| command                                | what it does                                                              |
|----------------------------------------|---------------------------------------------------------------------------|
| `ingest check`                         | Verify AnythingLLM is reachable and the API key works.                    |
| `ingest list`                          | List forage's collections and how many documents ingest has uploaded for each. |
| `ingest status <name>`                 | Show the diff (new / changed / unchanged / orphan) without uploading.     |
| `ingest sync <name>`                   | Sync one collection.                                                      |
| `ingest sync --all`                    | Sync every collection in turn.                                            |
| `ingest reset <name> -y`               | Delete ingest's local upload bookkeeping (does **not** touch AnythingLLM). |

Useful `sync` and `status` flags:

- `--include-suspicious` — also upload (or count) forage rows marked `suspicious`. Off by default; see [Suspicious documents](#suspicious-documents) below.
- `--keep-orphans` — don't delete from AnythingLLM the documents forage no longer has. Useful while you're figuring out what to keep.
- `--dry-run` (sync only) — compute the diff and print actions; make no changes.

---

## How ingest decides what to do

For each forage collection, ingest compares two things:

1. The current list of "good" documents in forage's `state.db` — by default that's everything marked `status = ok`.
2. The list of documents ingest has previously uploaded, kept in its own little database (`uploads.db`).

Each row falls into one of four buckets:

- **new** — in forage now, never uploaded → upload it.
- **changed** — uploaded before, but the file's content hash differs now → delete the old AnythingLLM doc, upload the new one.
- **unchanged** — uploaded before, content matches → skip.
- **orphan** — uploaded before, but forage no longer has it (file deleted, or extraction now failing) → delete it from AnythingLLM.

ingest is content-aware: it uses the SHA-256 hash forage computes per file, not modification times or file sizes. Renaming a file *will* re-upload it; modifying just its filesystem timestamps will not.

### Suspicious documents

forage runs a few sanity checks on every transcript it produces (repetition, "thanks for watching" boilerplate, low word density, low model confidence). If anything looks off, it marks the file `suspicious` instead of `ok`.

By default ingest **skips** suspicious files — they don't make it into AnythingLLM. You can opt in once with `--include-suspicious`:

```sh
ingest sync news --include-suspicious
```

If you do, the file gets uploaded. Importantly, the next time you run `ingest sync news` *without* that flag, the suspicious document is **not** deleted. ingest treats it as still-valid and just leaves it alone. (This is a small safety net so toggling the flag off doesn't silently wipe what you opted in.)

### Orphans

If you delete a file from your source folder and re-run `forage update news --orphans delete`, forage drops the row from its database. The next `ingest sync news` notices the gap and removes the corresponding document from AnythingLLM.

If you'd rather review what's about to be removed before it happens:

```sh
ingest sync news --keep-orphans     # leave them alone in AnythingLLM
ingest status news                  # see which ones are flagged
```

When you're ready, drop the flag and run a normal sync.

---

## Where ingest stores things

ingest keeps a tiny amount of bookkeeping per collection — basically a list of "what I've already uploaded and where it lives in AnythingLLM."

| platform                | path                                                  |
|-------------------------|-------------------------------------------------------|
| macOS                   | `~/Library/Application Support/ingest/`               |
| Linux                   | `$XDG_DATA_HOME/ingest/`, defaulting to `~/.local/share/ingest/` |

Override the location by setting `INGEST_APP_SUPPORT` in your environment.

Inside (substitute the path above for `<data-dir>`):

```
<data-dir>/
├── config.json                       # global settings (base URL, workspace name prefix)
└── collections/
    └── news/                         # one subfolder per collection synced
        ├── uploads.db                # SQLite — which forage files map to which AnythingLLM docs
        └── ingest.log                # plain-text run log (grows; you can delete it)
```

The actual document content lives in AnythingLLM, not here. If you delete this folder, ingest will think it has never uploaded anything and re-upload everything on the next sync — creating duplicates inside AnythingLLM. That's what `ingest reset` does, intentionally; don't delete `uploads.db` by hand unless you know what you're doing.

---

## Configuration file

`<data-dir>/config.json` is created on first run with sensible defaults:

```json
{
  "version": 1,
  "base_url": "http://localhost:3001",
  "workspace_prefix": "forage-"
}
```

- **`base_url`** — where ingest looks for AnythingLLM. Override per-shell with `ANYTHINGLLM_URL`.
- **`workspace_prefix`** — what ingest prepends to each collection name when picking a workspace slug. A collection called `news` becomes the workspace `forage-news`. Change this if you want a different naming convention; existing workspaces won't be renamed retroactively, so do it before your first sync.

The API key is read from the `ANYTHINGLLM_API_KEY` environment variable only — it's never written to disk.

---

## Troubleshooting

### `error: AnythingLLM not reachable at http://localhost:3001 — is the service running?`

The AnythingLLM app isn't running, or it's running on a different port. Launch it from Applications, then re-run `ingest check`. If it's on a different port, set `ANYTHINGLLM_URL`:

```sh
export ANYTHINGLLM_URL='http://localhost:3000'
ingest check
```

### `error: AnythingLLM rejected the API key`

Either `ANYTHINGLLM_API_KEY` is empty, or the key was revoked / regenerated in AnythingLLM's settings. Generate a fresh one in **Settings → Tools → Developer API** and `export` it again.

### `error: ANYTHINGLLM_API_KEY is not set`

You haven't exported the key in this terminal session. Run `export ANYTHINGLLM_API_KEY='…'` again, or add it to your shell rc file to make it stick.

### `error: forage state not found at …`

ingest is looking for a forage collection that doesn't exist. Check spelling against `forage list`, or check that `FORAGE_APP_SUPPORT` points where you think it does.

### A document I expected got skipped

Run `ingest status <collection> -v` to see which bucket it landed in. The most common explanations:

- It's marked `suspicious` in forage and you didn't pass `--include-suspicious`.
- forage's extraction failed for it (`forage info <collection>` lists recent failures).
- The file is in a queue waiting to be transcribed (`forage info <collection>` shows the queue depth — run `forage transcribe <collection>` to drain it).

### I uploaded too much / made a mess

Delete the workspace inside AnythingLLM's UI, then either:

- `ingest reset news -y && ingest sync news` — wipes ingest's local memory and starts fresh, or
- delete just the relevant documents in AnythingLLM and re-run `ingest sync` — but note that ingest still thinks those docs exist, so it won't re-upload them. `ingest reset` is the cleaner fix.

### Logs

Every sync appends to `<data-dir>/collections/<name>/ingest.log`. Look there for the details of a failed upload.

---

## Updating ingest

If you fetched a new version of the source code (e.g. with `git pull`), re-sync the environment:

```sh
cd ~/Projekte/ingest
uv sync
```

Your `uploads.db` and config are untouched. The next `ingest sync` picks up where the last one left off.

---

## Uninstalling

To remove ingest entirely, delete the source folder and the data directory.

**macOS:**

```sh
rm -rf ~/Projekte/ingest
rm -rf ~/Library/Application\ Support/ingest
```

**Linux:**

```sh
rm -rf ~/Projekte/ingest
rm -rf ~/.local/share/ingest          # or $XDG_DATA_HOME/ingest if you set it
```

Documents already uploaded into AnythingLLM stay there — ingest only manages the *upload bookkeeping*, not the workspace contents. To remove the documents themselves, delete the corresponding workspace inside the AnythingLLM app.

---

## For developers

If you want to hack on ingest:

```sh
uv sync --extra dev
uv run pytest
```

The test suite (24 tests, well under a second) wires the HTTP client to an in-memory fake AnythingLLM via `httpx.MockTransport`, and builds a fake forage `state.db` in a temp directory per test. No real AnythingLLM, no real forage state, no real network — everything is self-contained.

See `SPEC.md` for the design specification and `CLAUDE.md` for layout conventions.
