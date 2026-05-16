# In case of errors

Use this guide when forage's data dir was wiped, restored from a stale backup, or otherwise looks inconsistent with what's already inside AnythingLLM.

Two failure modes can co-exist and need separate fixes — work through them in this order.

---

## 1. forage's internal state

`forage` keeps a SQLite manifest (`state.db`) describing every extracted file alongside its `output/*.md`. After a partial restore or unclean process kill, the manifest may diverge from what's actually on disk.

**Start here:**

```sh
forage doctor                                # one line per collection
```

`doctor` is a read-only sweep that runs the same check as `forage repair --check`, across every collection at once. Clean output looks like `news  ok  (1234 files, 0 suspicious, 0 failed)`; anything else is a `WARN` line with the first issue printed inline.

**Per collection with anomalies:**

```sh
forage repair <name> --check                 # full issue list
forage update <name> --dry-run               # preview what update would change
forage update <name>                         # reconcile state.db with source folders
```

`forage update` walks every source folder and re-extracts whatever changed (or got lost). Files that exist in `state.db` but are missing on disk get re-extracted. Files that exist on disk but not in `state.db` get added. Sources that no longer exist on disk become orphans; the default `--orphans list` reports them and `--orphans delete` cleans them up.

If `forage doctor` reports something `repair --check` can't explain — usually integrity errors on `state.db` itself — fall back to `forage repair <name> --rebuild`, which regenerates the manifest from the on-disk `output/` tree. This is destructive of any state the manifest had that disk doesn't reflect (notably the transcription queue), so try `update` first.

**Re-transcription is the slow part.** Video transcripts are inside `state.db` and inside `output/`. If `output/` is intact and `state.db` was restored from the same point, you're fine. If `state.db` is older than `output/`, `forage update` will figure it out. If both regressed and the source videos haven't changed, you'll re-queue them and need a fresh `forage transcribe <name>` run.

---

## 2. forage ↔ AnythingLLM consistency

Once forage's state matches its on-disk output, see whether ingest's records line up. `ingest` keeps a separate manifest (`uploads.db`) describing what it has pushed to AnythingLLM. Any divergence shows up here.

```sh
ingest status <name>                         # per-collection diff
ingest status <name> -v                      # include the orphan path list
```

Every uploaded file falls into one of four buckets:

| forage's restored state for the file | What `ingest sync` will do |
|---|---|
| Same path, same sha256 as last upload | `unchanged` — skip. Safe. |
| Same path, different sha256 | `changed` — delete old AnythingLLM doc, re-upload. Safe. |
| **Not present at all** | **`orphan` — delete from AnythingLLM by default.** |

The third row is the only data-loss risk: a file you uploaded in the lost window, but whose forage row has now disappeared, will be deleted from AnythingLLM on the next sync. The fix is to make forage know about the file again — Step 1 above usually handles that automatically as long as the source file still exists on disk.

Decide per collection:

- **Orphans are legitimate** (the source file genuinely is gone): just run `ingest sync <name>`. The deletion in AnythingLLM is correct.
- **Orphans look wrong** (the file *should* still exist; the source itself got lost): restore the source folder from your own backup, `forage update <name>` again, then re-check `ingest status`.
- **You aren't sure**: `ingest sync <name> --keep-orphans` for this one run. Keeps the orphaned AnythingLLM docs in place while everything else reconciles. Review inside AnythingLLM by hand, then re-sync without `--keep-orphans` later.

Always preview with `--dry-run` first:

```sh
ingest sync <name> --dry-run
ingest sync <name>                           # or with --keep-orphans
```

---

## What not to do

- **Don't `ingest reset <name>`** unless you've also deleted the workspace inside AnythingLLM first. `reset` drops `uploads.db` and forces a full re-upload on the next sync, which creates duplicate documents inside an already-populated workspace.
- **Don't hand-edit `state.db` or `uploads.db`.** The repair/update/sync flow above covers every legitimate inconsistency.

---

## "I accidentally ran `forage purge`"

`forage purge` and `ingest purge` send the entire `anythingllm-feeder/` data directory to the system Trash (not `shutil.rmtree`). Recovery:

1. Open Finder → **Trash**.
2. Find the `anythingllm-feeder` folder; right-click → **Put Back**.
3. Confirm `forage list` and `ingest list` show your collections again.
4. Run through Step 1 and Step 2 above to confirm internal + AnythingLLM consistency.

If the Trash was emptied:

1. Restore `~/Library/Application Support/anythingllm-feeder/` from a backup (Time Machine, etc.).
2. Note the backup's age — anything you extracted or uploaded since the backup is the gap.
3. Run Step 1 (`forage doctor`, then `forage update` per collection) to bring forage's state back to current. Source folders are outside the data dir and unaffected.
4. Run Step 2 (`ingest status`, judge orphans, `ingest sync`). The orphan column tells you what was uploaded in the lost window.
