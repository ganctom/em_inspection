import json
from pathlib import Path

import numpy as np
import pytest

from em_inspection.inspection_utils_refactor import (
    CoarseData,
    cross_platform_path,
    read_coarse_mat,
)

# --- FIXTURES (Setup code) ---


@pytest.fixture
def sample_npz(tmp_path):
    """Creates a temporary .npz file for testing."""
    path = tmp_path / "test_data.npz"
    data = {
        "cx": np.array([1, 2]),
        "cy": np.array([3, 4]),
        "coarse_mesh": np.array([[10, 20], [30, 40]]),
    }
    np.savez(path, **data)
    return path, data


@pytest.fixture
def sample_json(tmp_path):
    """Creates a temporary .json file for testing."""
    path = tmp_path / "test_data.json"
    data = {"cx": [[1, 2]], "cy": [[3, 4]]}
    with open(path, "w") as f:
        json.dump(data, f)
    return path, data


# --- TESTS ---


def test_read_real_gold_standard():
    # 1. Define the path (Read-Only)
    gold_path = Path(__file__).parent / "samples" / "s477_g0" / "cx_cy_tst.json"

    # 2. Guard clause: Don't run the test if the file is missing
    assert gold_path.exists(), f"Expected gold standard file at {gold_path}"

    # 3. Execute the read (NO writing here)
    data = read_coarse_mat(gold_path)
    print(f"\n{data.cx.shape}")

    # 4. Assertions
    # We check if the data matches the known 'Gold' values
    assert data.cx.shape == (2, 2, 6)

    # Safely check for NaN in the read-only data
    # (This assumes we fixed the reader to handle NaNs)
    assert np.isnan(data.cx[0, 0, 4])

    # Define as a real Python list of lists
    x_cx = [
        [-220.0, -205.0, -211.0, -258.0, np.nan, np.nan],
        [-275.0, -206.0, -211.0, -207.0, -213.0, np.nan],
    ]

    y_cx = [
        [-31.0, -38.0, -46.0, 24.0, np.nan, np.nan],
        [27.0, -38.0, -42.0, -27.0, -30.0, np.nan],
    ]

    expected_list = [x_cx, y_cx]  # Result is (2, 2, 6)
    expected_cx = np.array(expected_list, dtype=np.float64)

    # Use atol (absolute tolerance) in addition to rtol for safer float comparison
    np.testing.assert_allclose(
        data.cx, expected_cx, equal_nan=True, rtol=1e-7, atol=1e-8
    )


def test_solid_refactor_read_coarse_mat(sample_npz):
    """Verifies the new SOLID refactor returns the correct Data Object."""
    path, expected_data = sample_npz

    # The new function returns a CoarseData object instead of a tuple
    result = read_coarse_mat(path)

    assert isinstance(result, CoarseData)
    np.testing.assert_array_equal(result.cx, expected_data["cx"])
    np.testing.assert_array_equal(result.coarse_mesh, expected_data["coarse_mesh"])


def test_json_loading(sample_json):
    """Verifies JSON loading (where mesh should be None)."""
    path, _ = sample_json
    result = read_coarse_mat(path)

    assert result.coarse_mesh is None
    assert result.cx.shape == (1, 2)


def test_cross_platform_path_empty_and_none():
    assert cross_platform_path(None) == ""
    assert cross_platform_path("") == ""
    assert cross_platform_path("   ") == ""


def test_cross_platform_path_macos_prepends_volumes(monkeypatch):
    monkeypatch.setattr(
        "em_inspection.inspection_utils_refactor.system", lambda: "Darwin"
    )

    path = "/tachyon/scratch/data/tiles/tile_001.tif"
    resolved = cross_platform_path(path)
    assert resolved == "/Volumes/tachyon/scratch/data/tiles/tile_001.tif"


def test_cross_platform_path_macos_already_has_volumes(monkeypatch):
    monkeypatch.setattr(
        "em_inspection.inspection_utils_refactor.system", lambda: "Darwin"
    )

    path = "/Volumes/tachyon/scratch/data/tiles/tile_001.tif"
    resolved = cross_platform_path(path)
    assert resolved == "/Volumes/tachyon/scratch/data/tiles/tile_001.tif"


def test_cross_platform_path_macos_local_system_path(monkeypatch):
    monkeypatch.setattr(
        "em_inspection.inspection_utils_refactor.system", lambda: "Darwin"
    )

    path = "/Users/testuser/experiments/file.tif"
    resolved = cross_platform_path(path)
    assert resolved == "/Users/testuser/experiments/file.tif"


def test_cross_platform_path_linux_strips_volumes(monkeypatch):
    monkeypatch.setattr(
        "em_inspection.inspection_utils_refactor.system", lambda: "Linux"
    )

    path = "/Volumes/tachyon/scratch/data/tiles/tile_001.tif"
    resolved = cross_platform_path(path)
    assert resolved == "/tachyon/scratch/data/tiles/tile_001.tif"


def test_cross_platform_path_custom_mount_map(monkeypatch):
    monkeypatch.setenv(
        "EM_REMOTE_MOUNT_MAP",
        '{"/remote_nas": "/Volumes/local_nas"}',
    )
    monkeypatch.setattr(
        "em_inspection.inspection_utils_refactor.system", lambda: "Darwin"
    )

    path = "/remote_nas/data/tile.tif"
    resolved = cross_platform_path(path)
    assert resolved == "/Volumes/local_nas/data/tile.tif"


def test_write_dict_to_yaml_creates_parent_and_resolves_path(tmp_path):
    from em_inspection.inspection_utils_refactor import write_dict_to_yaml

    target_file = tmp_path / "nested" / "dir" / "data.yaml"
    write_dict_to_yaml(str(target_file), {1: 1.5, 2: 2.5})

    assert target_file.exists()


def test_read_coarse_mat_with_cross_platform_path(tmp_path, sample_json, monkeypatch):
    path, _ = sample_json
    # Pass a path that resolves correctly
    result = read_coarse_mat(str(path))
    assert result.cx.shape == (1, 2)


def test_get_missing_stitched_sections_resolution(tmp_path):
    from em_inspection.inspection_utils_refactor import get_missing_stitched_sections

    stitched_dir = tmp_path / "stitched"
    stitched_dir.mkdir()
    (stitched_dir / "s0001_g0.zarr").mkdir()
    (stitched_dir / "s0002_g0.zarr").mkdir()

    missing = get_missing_stitched_sections(str(stitched_dir), [1, 2, 3, 4])
    assert missing == [3, 4]


def test_save_img_creates_directories_and_resolves(tmp_path):
    from em_inspection.inspection_utils_refactor import save_img

    target_img = tmp_path / "nested" / "thumb.jpg"
    data = np.zeros((10, 10), dtype=np.uint8)
    save_img(str(target_img), data)
    assert target_img.exists()


def test_save_coarse_mat_resolution(tmp_path):
    from em_inspection.inspection_utils_refactor import save_coarse_mat

    sec_dir = tmp_path / "s0001"
    sec_dir.mkdir()
    cxy = np.zeros((2, 2, 3, 3), dtype=np.float32)
    save_coarse_mat(cxy, str(sec_dir), file_format="json")

    cx_cy_file = sec_dir / "cx_cy.json"
    assert cx_cy_file.exists()
