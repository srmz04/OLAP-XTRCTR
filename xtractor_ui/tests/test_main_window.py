"""Tests de MainWindow: signal wiring y navegacion."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from ui.main_window import MainWindow, SCREEN_PREREQ, SCREEN_EXPLORER, SCREEN_BUILDER


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp):
    from core.provider_mock import MockProvider
    w = MainWindow(provider=MockProvider())
    yield w


def test_all_screens_loaded(window):
    assert window._stack.count() == 5


def test_starts_on_prereq(window):
    assert window._stack.currentIndex() == SCREEN_PREREQ


def test_go_to_navigates(window):
    window.go_to(SCREEN_BUILDER)
    assert window._stack.currentIndex() == SCREEN_BUILDER
    window.go_to(SCREEN_PREREQ)
    assert window._stack.currentIndex() == SCREEN_PREREQ


def test_builder_has_public_api(window):
    assert callable(getattr(window._builder, 'set_executing', None))
    assert callable(getattr(window._builder, 'get_mdx', None))


def test_prereqs_ok_with_mock_goes_to_explorer(window):
    """Con MockProvider, prereqs_ok salta directo al explorer."""
    window._on_prereqs_ok()
    assert window._stack.currentIndex() == SCREEN_EXPLORER
