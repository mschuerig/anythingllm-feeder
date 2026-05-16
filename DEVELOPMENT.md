# Development

End-user docs are in `README.md`; design specs are in `SPEC-forage.md` and `SPEC-ingest.md`; project-internal conventions are in `CLAUDE.md`. This file covers the **release flow** and one-time setup of the publishing pipeline.

## Local dev loop

```sh
uv sync --extra all --extra dev
uv run pytest                                # all tests, ~1s
uv run forage --help
uv run ingest --help
```

After touching either CLI parser, regenerate the committed man pages:

```sh
uv run python scripts/build_manpages.py      # writes man/forage.1, man/ingest.1
```

## Releasing

Releases are driven by tags. Pushing a `v*` tag to `mschuerig/anythingllm-feeder` triggers `.github/workflows/release.yml`, which:

1. Computes the source-tarball `sha256` from GitHub.
2. Checks out `mschuerig/homebrew-tap` (using a fine-grained PAT, see one-time setup below).
3. Patches `Formula/anythingllm-feeder.rb` — replaces `url` and `sha256`.
4. **Verifies** by running `brew install --build-from-source` against the patched formula on a `macos-14` (Apple Silicon) runner, then smoke-tests `forage --version`, `ingest --version`, `man forage`, `forage doctor`, etc. If install or any check fails, the workflow aborts and the tap is not updated.
5. Commits + pushes the patched formula back to the tap with a `github-actions[bot]` identity.

Subsequent end-user installs:

```sh
brew update
brew install mschuerig/tap/anythingllm-feeder
```

### Standard release flow

```sh
# 1. Bump version
$EDITOR pyproject.toml                       # version = "X.Y.Z"
git commit -am "vX.Y.Z"
git push origin main

# 2. Tag and push — this fires the workflow
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z

# 3. Watch
gh run watch                                 # or open the Actions tab
```

Expect ~10–15 minutes for the run. Most of it is `brew install` resolving the wheel for PyTorch (via docling) and friends.

### Recovering from a failed run

If the workflow fails after the tap was already updated, fix the formula directly in `mschuerig/homebrew-tap` (or bump and re-release). If it failed before the tap update, fix the issue, push to main, then either:

- **Same version** (less common): delete the tag locally and remotely, re-tag:
  ```sh
  git tag -d vX.Y.Z
  git push --delete origin vX.Y.Z
  git tag -a vX.Y.Z -m "vX.Y.Z"
  git push origin vX.Y.Z
  ```
- **Roll forward** (preferred): bump to the next patch version and re-release. Old failed tags can stay; they're harmless.

## One-time setup of the publishing pipeline

The release workflow needs write access to a *different* repo (`mschuerig/homebrew-tap`). It authenticates via a fine-grained Personal Access Token stored as a repo secret on `mschuerig/anythingllm-feeder`.

### Create the PAT

1. https://github.com/settings/personal-access-tokens → **Generate new token (fine-grained)**.
2. Name: `homebrew-tap-write` (or similar).
3. Expiration: a year is reasonable; rotate when it expires.
4. **Repository access:** Only select repositories → `mschuerig/homebrew-tap`.
5. **Repository permissions:** **Contents → Read and write**. Everything else: No access.
6. Generate, copy the token immediately.

### Store the PAT as a repo secret

1. https://github.com/mschuerig/anythingllm-feeder/settings/secrets/actions → **New repository secret**.
2. Name: `HOMEBREW_TAP_TOKEN` (must match the workflow).
3. Paste the PAT, save.

That's it; the next `v*` tag push runs the full pipeline.

## Anatomy of the workflow

`/Users/michael/Projekte/anythingllm-feeder/.github/workflows/release.yml`:

- **Trigger:** `push` events on `tags: ['v*']`.
- **Runner:** `macos-14` (Apple Silicon) — needed because the verification step installs mlx-whisper, which is arm64-only.
- **Steps:** compute meta → checkout tap → patch formula (Python regex; lambda-replacement so backslashes in URLs/sha don't get interpreted as backrefs) → verify via `brew install --build-from-source --formula <ABSOLUTE_PATH>` (the absolute path matters: a relative path containing slashes is parsed by brew as a `<tap>/<formula>` reference) → commit + push.

The tap formula at `mschuerig/homebrew-tap/Formula/anythingllm-feeder.rb` keeps placeholder `url` and `sha256` lines between releases; the workflow overwrites both per tag. Don't hand-edit those two lines for routine releases — they'll be clobbered.

If the formula's structure changes (new dependencies, different install logic, etc.), hand-edit the tap formula directly and push it to `mschuerig/homebrew-tap` before tagging — the workflow only patches `url` and `sha256`, not the rest of the file.
