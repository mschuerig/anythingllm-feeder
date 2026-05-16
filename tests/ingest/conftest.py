from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

# Make `from _helpers import ...` work without forcing tests/ to be a package.
sys.path.insert(0, str(Path(__file__).parent))

from _helpers import FakeAnythingLLM, FakeForageFile, create_forage_state


@pytest.fixture(autouse=True)
def _no_real_trash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``send2trash`` with ``shutil.rmtree`` for the whole ingest suite."""
    import shutil

    def _fake_send2trash(path: str | Path) -> None:
        shutil.rmtree(path)

    monkeypatch.setattr(
        "ingest.commands.purge.send2trash", _fake_send2trash
    )


@pytest.fixture
def app_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ANYTHINGLLM_FEEDER_APP_SUPPORT to a per-test toolkit root."""
    target = tmp_path / "anythingllm-feeder"
    target.mkdir()
    monkeypatch.setenv("ANYTHINGLLM_FEEDER_APP_SUPPORT", str(target))
    return target


# Back-compat aliases — both return the toolkit root. Existing tests that
# constructed paths from these still work after a local fix-up.
@pytest.fixture
def ingest_home(app_support: Path) -> Path:
    return app_support


@pytest.fixture
def forage_home(app_support: Path) -> Path:
    return app_support


@pytest.fixture
def make_forage_collection(forage_home: Path):
    def _make(collection: str, files: list[FakeForageFile]) -> None:
        create_forage_state(forage_home, collection, files)

    return _make


@pytest.fixture
def fake_server() -> FakeAnythingLLM:
    return FakeAnythingLLM()


@pytest.fixture
def client_factory(
    fake_server: FakeAnythingLLM, monkeypatch: pytest.MonkeyPatch
):
    from ingest.anythingllm import AnythingLLMClient

    monkeypatch.setenv("ANYTHINGLLM_API_KEY", "test-key")
    monkeypatch.setenv("ANYTHINGLLM_URL", "http://localhost:0")

    def _make() -> AnythingLLMClient:
        return AnythingLLMClient(
            base_url="http://localhost:0",
            api_key="test-key",
            transport=httpx.MockTransport(fake_server.handle),
        )

    return _make
