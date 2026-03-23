"""Tests for PaginationCheckpoint — save/load/resume."""
import json
import pytest
import tempfile
from pathlib import Path
from core.browser.checkpoint import PaginationCheckpoint


@pytest.fixture
def tmp_checkpoint():
    """Create a temp checkpoint path."""
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    # Remove the file so we start fresh
    Path(path).unlink(missing_ok=True)
    yield path
    Path(path).unlink(missing_ok=True)


class TestCheckpoint:
    def test_no_file_exists_false(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        assert cp.exists() is False

    def test_save_creates_file(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        cp.save(
            items=[{'text': 'a'}, {'text': 'b'}],
            pages_processed=1,
            last_url='https://example.com/page/1',
        )
        assert Path(tmp_checkpoint).exists()

    def test_save_and_load_roundtrip(self, tmp_checkpoint):
        items = [{'text': f'item_{i}'} for i in range(10)]

        cp = PaginationCheckpoint(tmp_checkpoint, '.product', 'next_button')
        cp.save(items=items, pages_processed=3, last_url='https://x.com/3', retries_used=2)

        # Load in a new instance
        cp2 = PaginationCheckpoint(tmp_checkpoint, '.product', 'next_button')
        assert cp2.exists() is True

        state = cp2.load()
        assert state['pages_processed'] == 3
        assert state['total_items'] == 10
        assert state['retries_used'] == 2
        assert state['last_url'] == 'https://x.com/3'
        # items are stored in JSONL, loaded separately
        loaded_items = cp2.load_items()
        assert len(loaded_items) == 10

    def test_incompatible_selector_not_found(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item-a', 'next_button')
        cp.save(items=[{'x': 1}], pages_processed=1)

        # Different selector = incompatible
        cp2 = PaginationCheckpoint(tmp_checkpoint, '.item-b', 'next_button')
        assert cp2.exists() is False

    def test_incompatible_mode_not_found(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        cp.save(items=[{'x': 1}], pages_processed=1)

        # Different mode = incompatible
        cp2 = PaginationCheckpoint(tmp_checkpoint, '.item', 'infinite_scroll')
        assert cp2.exists() is False

    def test_clear_removes_file(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        cp.save(items=[{'x': 1}], pages_processed=1)
        assert Path(tmp_checkpoint).exists()

        cp.clear()
        assert not Path(tmp_checkpoint).exists()

    def test_incremental_save(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')

        # Page 1
        cp.save(items=[{'page': 1}], pages_processed=1)
        state = cp.load()
        assert state['pages_processed'] == 1

        # Page 2
        cp.save(items=[{'page': 1}, {'page': 2}], pages_processed=2)
        state = cp.load()
        assert state['pages_processed'] == 2
        assert state['total_items'] == 2

        # created_at should be preserved from first save
        assert state['created_at'] is not None

    def test_load_empty_returns_defaults(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        state = cp.load()
        assert state['pages_processed'] == 0
        assert state['total_items'] == 0
        assert cp.load_items() == []

    def test_corrupted_file_exists_false(self, tmp_checkpoint):
        Path(tmp_checkpoint).write_text("not json at all!", encoding='utf-8')
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        assert cp.exists() is False

    def test_stopped_reason_saved(self, tmp_checkpoint):
        cp = PaginationCheckpoint(tmp_checkpoint, '.item', 'next_button')
        cp.save(
            items=[{'x': 1}],
            pages_processed=5,
            stopped_reason='error: connection reset',
        )
        state = cp.load()
        assert state['stopped_reason'] == 'error: connection reset'
