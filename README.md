# forage

A small command-line tool that turns folders of documents and videos into folders of Markdown files, so a local LLM (like AnythingLLM) can read them.

This README walks through everything you need: installing the prerequisites, getting forage onto your computer, and using it day-to-day. You don't need to be a developer to follow it — just comfortable typing commands into the Terminal app.

---

## What forage does

You point forage at one or more folders on your Mac. forage scans each folder, runs every file through the right text-extraction tool (PDFs and Office docs through *docling*, audio/video through *mlx-whisper*), and writes a `.md` file (a plain text/Markdown file) for each one into its own private storage area. The Markdown files mirror your folder structure, so a PDF called `2025/article.pdf` becomes `2025/article.md`.

The next time you run forage, it remembers what it already did. Only new or changed files get re-processed. If you delete a file from your source folder, forage will offer to delete the matching Markdown file too.

A few terms used throughout this README:

- **Collection** — a named bundle of source folders plus their extracted Markdown. Think of it as a single "library." You might have one collection for news clippings, another for research papers.
- **Source** — a folder on your Mac that belongs to a collection. A collection can have several sources; each one shows up as its own subfolder in the extracted output.
- **Transcription queue** — videos and audio files take a long time to process, so forage records them in a queue and you can transcribe them in batches (overnight, say).

---

## Before you start: install the prerequisites

You will install four things, in order. Each one is a single command in Terminal.

Open Terminal: press `Cmd+Space`, type `terminal`, hit Return.

### 1. Homebrew

Homebrew is the standard Mac package manager. If you already have it (you can check by running `brew --version`), skip this step.

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

When it finishes, follow the on-screen instructions to add Homebrew to your shell — it usually tells you to run two `echo … >> ~/.zprofile` commands and then `eval "$(/opt/homebrew/bin/brew shellenv)"`. Do those.

### 2. ffmpeg

forage uses `ffmpeg` (specifically its `ffprobe` companion) to check whether a video has any audio before transcribing it.

```sh
brew install ffmpeg
```

### 3. Python 3.11 or newer

```sh
brew install python
```

Verify:

```sh
python3 --version
```

You should see `Python 3.11.x` or later.

### 4. uv

`uv` is a modern Python package manager. It handles installing forage and its dependencies in an isolated environment so it can't break anything else on your computer.

```sh
brew install uv
```

Verify:

```sh
uv --version
```

---

## Install forage

forage isn't published to any package index yet; you install it directly from the source folder.

Open Terminal and `cd` into the folder containing this README. For example:

```sh
cd ~/Projekte/forage
```

Then install everything:

```sh
uv sync --extra all
```

This creates a `.venv/` folder inside the project, downloads forage's dependencies into it, and installs the `forage` command itself. The `--extra all` flag pulls in *docling* (for documents) and *mlx-whisper* (for audio/video). The first install can take several minutes because docling and whisper are large.

Verify that forage is callable:

```sh
.venv/bin/forage --help
```

You should see a list of subcommands.

### Make `forage` work from anywhere (optional)

To avoid typing `.venv/bin/forage` every time, add the project's `.venv/bin` to your `PATH`. Append this line to `~/.zshrc`:

```sh
export PATH="$HOME/Projekte/forage/.venv/bin:$PATH"
```

(Adjust the path if you installed forage somewhere else.) Then either restart Terminal or run `source ~/.zshrc`.

After this, plain `forage --help` will work from any folder.

---

## Quick start: your first collection

Let's pretend you have a folder of PDFs at `~/Documents/news-archive` and you want forage to keep an up-to-date Markdown copy of all of them.

### 1. Create the collection

```sh
forage create news --source archive=~/Documents/news-archive
```

- `news` is the collection's name.
- `archive` is the name you're giving to this particular source. Source names must be lowercase letters, digits, hyphens, or underscores (e.g. `archive`, `old-articles`, `2024_notes`).
- After `=` comes the actual folder path.

You can add more sources up front by repeating `--source`:

```sh
forage create news \
  --source archive=~/Documents/news-archive \
  --source drafts=~/Documents/news-drafts
```

### 2. Run the first extraction

```sh
forage update news
```

This walks each source and converts every supported file to Markdown. It can take a while the first time — docling has to load its models. Output goes here:

```
~/Library/Application Support/forage/collections/news/output/archive/...
~/Library/Application Support/forage/collections/news/output/drafts/...
```

### 3. See what happened

```sh
forage info news
```

This prints a short summary: how many files were processed per source, how many failed, how many videos are waiting in the transcription queue.

### 4. From now on, just re-run

Any time you add or modify files in your source folders, run `forage update news` again. forage will figure out what's new, what changed, what got deleted, and only do the work it needs to.

---

## Working with videos and audio

Documents are processed inline when you run `forage update`. Videos and audio, however, can take a long time per file. By default forage *also* transcribes them inline — but for big batches you usually want to queue them first and transcribe in a separate run.

### Queue without transcribing

```sh
forage update news --defer-video
```

This processes documents normally, but for each new video/audio file it just adds an entry to the transcription queue. `forage info news` will show you the queue depth.

### Drain the queue

```sh
forage transcribe news
```

Useful flags:

- `--limit 10` — only do up to 10 items, then stop.
- `--time-limit 2h` — stop after 2 hours of wall time. Accepts `4h`, `90m`, `3600s`. Great for overnight runs.
- `--retry-failed` — also re-attempt items that previously failed.
- `--dry-run` — just list what would be processed.

You can re-run `forage transcribe news --time-limit 2h` every night until the queue is empty.

### Suspicious transcripts

Whisper sometimes hallucinates — making up text when there's nothing to transcribe. forage runs a handful of sanity checks on every transcript (repetition, boilerplate phrases like "thanks for watching," very low word density, very low model confidence). If anything looks off, the file is marked `suspicious` instead of `ok`. The Markdown is still written; `forage info` lists suspicious files at the bottom so you can review them.

---

## All commands

Each command supports `-v` / `--verbose` (more progress detail) and `-q` / `--quiet` (errors only). `--json` produces machine-readable output where it makes sense.

### Managing collections

| command                                  | what it does                                        |
|------------------------------------------|-----------------------------------------------------|
| `forage create <name> --source N=P …`    | Create a collection with one or more sources.       |
| `forage list`                            | List every collection.                              |
| `forage info <name>`                     | Per-source status, totals, queue depth, recent errors. |
| `forage rename <old> <new>`              | Rename a collection.                                |
| `forage remove <name>`                   | Delete a collection. Prompts about output files.    |

### Managing sources

| command                                       | what it does                                      |
|-----------------------------------------------|---------------------------------------------------|
| `forage add-source <coll> <name> <dir>`       | Add another source to an existing collection.     |
| `forage remove-source <coll> <name>`          | Remove a source. Prompts about its output files.  |
| `forage set-source <coll> <name> <new-dir>`   | Tell forage that a source folder moved.           |

### Processing

| command                          | what it does                                                            |
|----------------------------------|-------------------------------------------------------------------------|
| `forage update <name>`           | Walk sources, extract changed files, handle deletions.                  |
| `forage update --all`            | Run `update` on every collection in turn.                               |
| `forage transcribe <name>`       | Drain the transcription queue.                                          |
| `forage transcribe --all`        | Same, across every collection.                                          |

Useful `update` flags:

- `--source <name>` — only walk this one source within the collection.
- `--ext pdf,mp4` — only consider files with these extensions this run. (Doesn't affect orphan detection.)
- `--orphans list|delete|ignore` — what to do about source files that disappeared. Default is `list`.
- `--defer-video` — queue videos instead of transcribing them inline.
- `--dry-run` — report only, write nothing.

### Recovery

| command                          | what it does                                                            |
|----------------------------------|-------------------------------------------------------------------------|
| `forage repair <name>`           | Read-only consistency check between the database and what's on disk.    |
| `forage repair <name> --rebuild` | Rebuild the database from disk (use if `state.db` got corrupted).       |

---

## Where forage stores things

Everything lives under `~/Library/Application Support/forage/`. That folder is the right thing to back up if you want to preserve your processed Markdown.

```
~/Library/Application Support/forage/
├── config.json                    # global settings (whisper model, defaults)
└── collections/
    └── news/                      # one folder per collection
        ├── config.json            # this collection's sources
        ├── state.db               # SQLite database tracking files + queue
        ├── extract.log            # plain-text run log (grows; you can delete it)
        └── output/
            ├── archive/...        # one subfolder per source, full Markdown tree
            └── drafts/...
```

Whisper model files live separately under `~/.cache/huggingface/hub/`. The first transcription downloads one (gigabytes); subsequent runs reuse it.

---

## Day-to-day workflow

A typical week might look like:

```sh
# Friday afternoon — drop new things in your source folders, sync.
forage update news --defer-video
forage info news                   # see how many videos got queued

# Friday evening — start the queue draining; come back to it later.
forage transcribe news --time-limit 8h
```

If the time limit hits before the queue is empty, just run it again the next night.

```sh
forage info news                   # check progress
forage transcribe news --time-limit 4h
```

---

## Troubleshooting

### `error: collection 'foo' already exists`

You tried to create a collection that's already there. Use `forage list` to see what exists, or `forage remove foo` first.

### `error: source path does not exist`

The folder you pointed `--source` at doesn't exist or isn't a directory. Double-check the path (use Tab-completion in Terminal to avoid typos).

### `error: collection locked: news`

Another `forage` process is running against the same collection. Wait for it to finish, or check `ps aux | grep forage` if you think a previous run got stuck.

### A video shows `status: no_audio`

ffprobe reported no audio stream in the file. forage skipped it on purpose — there's nothing to transcribe. Check the file in another player to confirm.

### A transcript is marked `suspicious`

One of the hallucination heuristics fired — likely repetition, a stock "thanks for watching" outro, or unusually low word density. The Markdown was still written; open it and decide whether to keep, edit, or delete it.

### Something looks corrupted

```sh
forage repair news               # read-only diagnostic
forage repair news --rebuild     # rebuild state.db from disk
```

`--rebuild` is safe in the sense that it doesn't touch your source files or your output Markdown — it just throws away forage's bookkeeping database and reconstructs it from what's on disk.

### Logs

Every run appends a line per file to `~/Library/Application Support/forage/collections/<name>/extract.log`. If something failed, look there for the stack trace.

---

## Updating forage

If you fetched a new version of the source code (e.g. with `git pull`), re-sync the environment:

```sh
cd ~/Projekte/forage
uv sync --extra all
```

That's it. Your collections and processed files are untouched.

---

## Uninstalling

To remove forage entirely:

```sh
rm -rf ~/Projekte/forage              # the source code
rm -rf ~/Library/Application\ Support/forage   # collections, output, database
```

The whisper models in `~/.cache/huggingface/hub/` are shared with other tools; remove them only if you're sure nothing else uses them.

---

## For developers

If you want to hack on forage:

```sh
uv sync --extra dev    # core + pytest; no docling/whisper
uv run pytest
```

The test suite (~80 tests) stubs out docling and mlx-whisper, so it runs in well under a second and never touches your real state directory (`FORAGE_APP_SUPPORT` is redirected to a temp folder per test).

See `SPEC.md` for the design specification and `CLAUDE.md` for layout conventions.
