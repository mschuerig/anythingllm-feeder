# forage — agent notes

## Where to look

`SPEC.md` is the authoritative reference for behavior, data model, CLI, and acceptance scenarios. Read it before designing changes.

## Conventions

- All storage paths are resolved through `src/forage/paths.py`. No hard-coded paths elsewhere. `paths.app_support_dir()` returns the platform-appropriate root (macOS → `~/Library/Application Support/forage`, Linux → `$XDG_DATA_HOME/forage`, Windows → `%LOCALAPPDATA%/forage`), overridable via `FORAGE_APP_SUPPORT`.
- DB writes go through typed functions in `src/forage/db.py`. Don't inline SQL in commands.
- All extraction outputs are atomic: write to `<path>.tmp`, fsync, rename. Centralized in `src/forage/output.py`.
- Timestamps in DB and config are ISO 8601 UTC strings (`datetime.now(UTC).isoformat(timespec="seconds")`); source mtime stays POSIX float.
- Whisper heuristic thresholds live as module-level constants near the top of `src/forage/extractors/whisper.py` (boilerplate list, repetition count, density, logprob).
- `src/forage/log.py` owns logging setup; one logger fans out to stdout (filtered by `-v`/`-q`) and to the collection's `extract.log`.

## Test layout override

For tests, point `FORAGE_APP_SUPPORT` at a tmp dir. `paths.py` honors it; the `app_support` fixture in `tests/conftest.py` does this per-test.

The docling and mlx-whisper extractors are registered lazily via `forage.extractors.get_extractor`. Tests monkeypatch `forage.extractors._REGISTRY` with stubs so the real (heavy) libraries are never imported during the suite.
