from pathlib import Path

import pytest
import numpy as np
import json
from em_inspection.inspection_utils_refactor import read_coarse_mat, CoarseData


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


def test_read_real_gold_standard():
    # 1. Define the path (Read-Only)
    json_path = "/Users/ganctoma/SW/_projects/em_inspection/tests/samples/s477_g0/cx_cy_tst.json"
    gold_path = Path(json_path)

    # 2. Guard clause: Don't run the test if the file is missing
    assert gold_path.exists(), f"Expected gold standard file at {gold_path}"

    # 3. Execute the read (NO writing here)
    data = read_coarse_mat(gold_path)
    print(f"\n{data.cx[0][0][0][3]}")

    # 4. Assertions
    # We check if the data matches the known 'Gold' values
    assert data.cx.shape == (2, 1, 2, 6)

    # Safely check for NaN in the read-only data
    # (This assumes we fixed the reader to handle NaNs)
    assert np.isnan(data.cx[0, 0, 0, 4])

    # Define as a real Python list of lists
    x_cx = [[
        [-220.0, -205.0, -211.0, -258.0, np.nan, np.nan],
        [-275.0, -206.0, -211.0, -207.0, -213.0, np.nan]
    ]]

    y_cx = [[
        [-31.0, -38.0, -46.0, 24.0, np.nan, np.nan],
        [27.0, -38.0, -42.0, -27.0, -30.0, np.nan]
    ]]

    expected_list = [x_cx, y_cx]  # Result is (2, 1, 2, 6)
    expected_cx = np.array(expected_list, dtype=np.float64)

    # Use atol (absolute tolerance) in addition to rtol for safer float comparison
    np.testing.assert_allclose(data.cx, expected_cx, equal_nan=True, rtol=1e-7, atol=1e-8)


def test_solid_refactor_read_coarse_mat(sample_npz):
    """Verifies the new SOLID refactor returns the correct Data Object."""
    path, expected_data = sample_npz

    # The new function returns a CoarseData object instead of a tuple
    result = read_coarse_mat(path)

    assert isinstance(result, CoarseData)
    np.testing.assert_array_equal(result.cx, expected_data['cx'])
    np.testing.assert_array_equal(result.coarse_mesh, expected_data['coarse_mesh'])


def test_json_loading(sample_json):
    """Verifies JSON loading (where mesh should be None)."""
    path, _ = sample_json
    result = read_coarse_mat(path)

    assert result.coarse_mesh is None
    assert result.cx.shape == (1, 2)

