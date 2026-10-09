"""Fixtures compartidas para todos los tests."""
from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

# Agregar xtractor_ui al path para que los tests encuentren el paquete
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture(scope="session")
def mock_provider():
    from core.provider_mock import MockProvider
    return MockProvider()


@pytest.fixture
def tmp_cache(tmp_path):
    from core.cache import MetadataCache
    cache = MetadataCache(tmp_path / "test_cache.db")
    yield cache
    cache.close()


@pytest.fixture
def tmp_store(tmp_path):
    from core.credential_store import ProfileStore
    return ProfileStore(base_dir=tmp_path)
