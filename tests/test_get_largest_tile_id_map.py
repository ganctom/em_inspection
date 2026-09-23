import numpy as np
import pytest
from numpy.testing import assert_array_equal

from em_inspection.inspection_utils_refactor import compute_tile_id_map
import tests.test_get_largest_tile_id_map as this_module


@pytest.fixture
def sample_processor():
    """Create a minimal fake instance with controlled behavior"""
    class MockConfig:
        grid_shape = (7, 5)

    class TestProcessor:
        def __init__(self):
            self.config = MockConfig()

        def get_unique_tile_ids(self):
            return {1, 2, 3}

        def get_largest_tile_id_map(self):
            grid_shape = self.config.grid_shape
            unique_tile_ids = sorted(list(self.get_unique_tile_ids()))
            return compute_tile_id_map(grid_shape, unique_tile_ids)

    return TestProcessor()


def test_calls_compute_tile_id_map_with_sorted_unique_ids(sample_processor, monkeypatch):
    """Verify that compute_tile_id_map is called with expected arguments"""
    fake_tile_ids = {3, 1, 8, 42, 7}
    expected_sorted = [1, 3, 7, 8, 42]

    sample_processor.get_unique_tile_ids = lambda: fake_tile_ids

    calls = []

    def fake_compute_tile_id_map(shape, tids):
        calls.append((shape, tids))
        return np.zeros(shape, dtype=np.int32)

    monkeypatch.setattr(this_module, "compute_tile_id_map", fake_compute_tile_id_map)

    sample_processor.get_largest_tile_id_map()

    assert len(calls) == 1
    shape_arg, tids_arg = calls[0]
    assert shape_arg == (7, 5)
    assert tids_arg == expected_sorted


def test_returns_result_from_compute_tile_id_map(sample_processor, monkeypatch):
    """Sanity check: returns whatever compute_tile_id_map returns"""
    expected_result = np.random.randint(0, 100, size=(7, 5), dtype=np.uint16)

    sample_processor.get_unique_tile_ids = lambda: {10, 20, 30}

    monkeypatch.setattr(
        this_module,
        "compute_tile_id_map",
        lambda shape, tids: expected_result
    )

    result = sample_processor.get_largest_tile_id_map()
    assert_array_equal(result, expected_result)


@pytest.mark.parametrize("grid_shape, n_tiles", [
    ((1, 1), 1),
    ((4, 4), 1),
    ((6, 8), 10),
    ((12, 12), 3),
])
def test_various_grid_shapes(sample_processor, grid_shape, n_tiles):
    sample_processor.config.grid_shape = grid_shape

    fake_tile_ids = set(range(0, n_tiles))
    sample_processor.get_unique_tile_ids = lambda: fake_tile_ids

    result = sample_processor.get_largest_tile_id_map()

    assert result.size <= np.prod(grid_shape)


def test_unique_tile_ids_are_sorted(sample_processor, monkeypatch):
    seen_tids = []

    def capture_tids(shape, tids):
        seen_tids.extend(tids)
        return np.zeros(shape, dtype=np.int32)

    monkeypatch.setattr(this_module, "compute_tile_id_map", capture_tids)

    sample_processor.get_unique_tile_ids = lambda: {55, 2, 199, 17, 4}

    sample_processor.get_largest_tile_id_map()

    assert seen_tids == [2, 4, 17, 55, 199], "tile ids should be sorted"