from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

# Make `from _helpers import ...` work without forcing tests/ to be a package.
sys.path.insert(0, str(Path(__file__).parent))

from _helpers import FakeAnythingLLM, FakeForageFile, create_forage_state


@pytest.fixture
def ingest_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "ingest"
    target.mkdir()
    monkeypatch.setenv("INGEST_APP_SUPPORT", str(target))
    return target


@pytest.fixture
def forage_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "forage"
    target.mkdir()
    monkeypatch.setenv("FORAGE_APP_SUPPORT", str(target))
    return target


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
