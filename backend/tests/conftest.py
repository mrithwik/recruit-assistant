import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["USE_MOCK"] = "true"


@pytest.fixture
def tmp_sqlite_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def storage(tmp_sqlite_path):
    from app.storage.local import LocalStorageBackend

    return LocalStorageBackend(tmp_sqlite_path)


@pytest.fixture
def mock_llm():
    from app.matching.llm_client import MockLLMClient

    return MockLLMClient()
