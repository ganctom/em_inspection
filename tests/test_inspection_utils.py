import pytest
import numpy as np
import json
from pathlib import Path

# Import both old and new names from your module
# (Assuming you kept the old one briefly to compare)
from em_inspection.inspection_utils import read_coarse_mat_new, read_coarse_mat, CoarseData


# --- FIXTURES (Setup code) ---

@pytest.fixture
def sample_npz(tmp_path):
    """Creates a temporary .npz file for testing."""
    path = tmp_path / "test_data.npz"
    data = {
        'cx': np.array([1, 2]),
        'cy': np.array([3, 4]),
        'coarse_mesh': np.array([[10, 20], [30, 40]])
    }
    np.savez(path, **data)
    return path, data


@pytest.fixture
def sample_json(tmp_path):
    """Creates a temporary .json file for testing."""
    path = tmp_path / "test_data.json"
    data = {'cx': [[1, 2]], 'cy': [[3, 4]]}
    with open(path, 'w') as f:
        json.dump(data, f)
    return path, data


# --- TESTS ---

def test_original_read_coarse_mat(sample_npz):
    """Verifies the old function still works as expected."""
    path, expected_data = sample_npz
    mesh, cx, cy = read_coarse_mat_new(path)

    np.testing.assert_array_equal(cx, expected_data['cx'])
    np.testing.assert_array_equal(mesh, expected_data['coarse_mesh'])

