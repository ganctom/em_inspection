import numpy as np
import pytest
from numpy.testing import assert_array_equal

import em_inspection.experiment_configs as cfg
from em_inspection.coarse_offset_processor import CoarseOffsetProcessor
from em_inspection.inspection_utils_refactor import compute_tile_id_map

# Assuming these are your real imports — adjust as needed
# from your_module import YourClass, utils


@pytest.fixture
def sample_processor():
    """Create a minimal fake instance with controlled behavior"""

    # Get actual config
    configs = cfg.get_experiment_configurations()
    exp_config = configs[cfg.ExperimentName.ROLI_F1]

    # Initialize CoarseOffsetProcessor and read coarse offsets
    co_processor = CoarseOffsetProcessor(exp_config)
    co_processor.load_all_offsets_and_tile_id_maps_from_npz()

    class TestProcessor:
        def __init__(self):
            self.config = exp_config

        def get_largest_tile_id_map(self):
            grid_shape = self.config.grid_shape
            unique_tile_ids = sorted(list(co_processor.get_unique_tile_ids()))
            largest_tid_map = compute_tile_id_map(grid_shape, unique_tile_ids)
            return largest_tid_map

    return TestProcessor()


# ────────────────────────────────────────────────
#                Actual test cases
# ────────────────────────────────────────────────

def test_calls_compute_tile_id_map_with_sorted_unique_ids(sample_processor, monkeypatch):
    """Verify that utils.compute_tile_id_map is called with expected arguments"""
    fake_tile_ids = {3, 1, 8, 42, 7}
    expected_sorted = [1, 3, 7, 8, 42]

    sample_processor.get_unique_tile_ids = lambda: fake_tile_ids

    calls = []

    def fake_compute_tile_id_map(shape, tids):
        calls.append((shape, tids))
        # return something with correct shape
        return np.zeros(shape, dtype=np.int32)

    monkeypatch.setattr("utils.compute_tile_id_map", fake_compute_tile_id_map)

    sample_processor.get_largest_tile_id_map()

    assert len(calls) == 1
    shape_arg, tids_arg = calls[0]
    assert shape_arg == (7, 5, 4)
    assert tids_arg == expected_sorted


def test_returns_result_from_compute_tile_id_map(sample_processor, monkeypatch):
    """Sanity check: returns whatever compute_tile_id_map returns"""
    expected_result = np.random.randint(0, 100, size=(7, 5, 4), dtype=np.uint16)

    sample_processor.get_unique_tile_ids = lambda: {10, 20, 30}

    monkeypatch.setattr(
        "utils.compute_tile_id_map",
        lambda shape, tids: expected_result
    )

    result = sample_processor.get_largest_tile_id_map()
    assert_array_equal(result, expected_result)


@pytest.mark.parametrize("grid_shape, n_tiles", [
    ((1, 1, 1), 1),
    ((4, 4, 4), 0),  # empty case
    ((6, 8, 9), 64),
    ((12, 12, 12), 3),
])
def test_various_grid_shapes(sample_processor, grid_shape, n_tiles):
    sample_processor.config.grid_shape = grid_shape

    fake_tile_ids = set(range(100, 100 + n_tiles)) if n_tiles > 0 else set()
    sample_processor.get_unique_tile_ids = lambda: fake_tile_ids

    result = sample_processor.get_largest_tile_id_map()

    assert result.shape == grid_shape
    assert result.size == np.prod(grid_shape)
    if n_tiles == 0:
        assert np.all(result == 0)  # or whatever sentinel your function uses
    else:
        assert result.min() >= 0
        # you can add more domain-specific assertions here


def test_unique_tile_ids_are_sorted(sample_processor, monkeypatch):
    seen_tids = []

    def capture_tids(shape, tids):
        seen_tids.extend(tids)
        return np.zeros(shape, dtype=np.int32)

    monkeypatch.setattr("utils.compute_tile_id_map", capture_tids)

    # unsorted input
    sample_processor.get_unique_tile_ids = lambda: {55, 2, 199, 17, 4}

    sample_processor.get_largest_tile_id_map()

    assert seen_tids == [2, 4, 17, 55, 199], "tile ids should be sorted"