import os
import shutil
import tempfile
import pytest
import numpy as np
import zarr

from scratch.zarr.zarr_view.view_zarr_volume_section import (
    locate_zarr_section,
    get_zarr_section_data,
    ZarrSectionLocation,
)


@pytest.fixture
def temp_zarr_stores():
    temp_dir = tempfile.mkdtemp()

    # Store 1: Zarr v2 Group (like OME-Zarr), chunk size (1, 64, 64) with "/" separator, shape (100, 64, 64)
    store1_path = os.path.join(temp_dir, "test_chunk1.zarr")
    z1 = zarr.group(store=store1_path, zarr_format=2)
    arr1 = z1.create_array(
        name="0",
        shape=(100, 64, 64),
        chunks=(1, 64, 64),
        dtype="uint8",
        chunk_key_encoding={"name": "v2", "separator": "/"},
        overwrite=True,
    )
    # Fill slice 40 with value 42
    arr1[40, :, :] = 42

    # Store 2: Zarr v2 Group, chunk size (196, 196, 196) with "/" separator, shape (500, 196, 196)
    store2_path = os.path.join(temp_dir, "test_chunk196.zarr")
    z2 = zarr.group(store=store2_path, zarr_format=2)
    arr2 = z2.create_array(
        name="0",
        shape=(500, 196, 196),
        chunks=(196, 196, 196),
        dtype="uint8",
        chunk_key_encoding={"name": "v2", "separator": "/"},
        overwrite=True,
    )
    # Fill slice 392 (chunk 2, offset 0) and slice 400 (chunk 2, offset 8)
    arr2[392, :, :] = 99
    arr2[400, :, :] = 123

    # Store 3: Root-level array with flat "." separator, shape (50, 32, 32), chunks (10, 32, 32)
    store3_path = os.path.join(temp_dir, "test_root_array.zarr")
    arr3 = zarr.create_array(
        store=store3_path,
        shape=(50, 32, 32),
        chunks=(10, 32, 32),
        dtype="float32",
        zarr_format=2,
        chunk_key_encoding={"name": "v2", "separator": "."},
        overwrite=True,
    )
    arr3[25, :, :] = 3.14

    yield {
        "temp_dir": temp_dir,
        "store1": store1_path,
        "store2": store2_path,
        "store3": store3_path,
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_locate_chunk_1(temp_zarr_stores):
    store_path = temp_zarr_stores["store1"]
    z_offset = 1240
    section_number = 1280  # z_index = 40

    loc = locate_zarr_section(
        volume_path=store_path,
        section_number=section_number,
        z_offset=z_offset,
        dataset_key="0",
    )

    assert loc.z_index == 40
    assert loc.chunk_size == (1, 64, 64)
    assert loc.chunk_z_index == 40
    assert loc.z_within_chunk == 0
    assert loc.volume_shape == (100, 64, 64)
    assert os.path.basename(loc.chunk_disk_path) == "40"
    assert loc.chunk_disk_exists is True

    # Test reading data
    data = get_zarr_section_data(loc, as_numpy=True)
    assert data.shape == (64, 64)
    assert np.all(data == 42)


def test_locate_chunk_196(temp_zarr_stores):
    store_path = temp_zarr_stores["store2"]
    z_offset = 100

    # Section 492 -> z_index = 392 -> chunk_z_index = 392 // 196 = 2, z_within = 0
    loc1 = locate_zarr_section(
        volume_path=store_path,
        section_number=492,
        z_offset=z_offset,
        dataset_key="0",
    )
    assert loc1.z_index == 392
    assert loc1.chunk_size == (196, 196, 196)
    assert loc1.chunk_z_index == 2
    assert loc1.z_within_chunk == 0
    assert os.path.basename(loc1.chunk_disk_path) == "2"
    assert loc1.chunk_disk_exists is True

    data1 = get_zarr_section_data(loc1, as_numpy=True)
    assert data1.shape == (196, 196)
    assert np.all(data1 == 99)

    # Section 500 -> z_index = 400 -> chunk_z_index = 400 // 196 = 2, z_within = 8
    loc2 = locate_zarr_section(
        volume_path=store_path,
        section_number=500,
        z_offset=z_offset,
        dataset_key="0",
    )
    assert loc2.z_index == 400
    assert loc2.chunk_z_index == 2
    assert loc2.z_within_chunk == 8

    data2 = get_zarr_section_data(loc2, as_numpy=True)
    assert np.all(data2 == 123)


def test_locate_root_array(temp_zarr_stores):
    store_path = temp_zarr_stores["store3"]
    z_offset = 0
    section_number = 25  # z_index = 25 -> chunk_z_index = 25 // 10 = 2, z_within = 5

    loc = locate_zarr_section(
        volume_path=store_path,
        section_number=section_number,
        z_offset=z_offset,
        dataset_key="",
    )
    assert loc.z_index == 25
    assert loc.chunk_z_index == 2
    assert loc.z_within_chunk == 5
    assert loc.dimension_separator == "."

    data = get_zarr_section_data(loc, as_numpy=True)
    assert data.shape == (32, 32)
    assert np.isclose(data[0, 0], 3.14)


def test_out_of_bounds_errors(temp_zarr_stores):
    store_path = temp_zarr_stores["store1"]

    # Negative z_index (section_number < z_offset)
    with pytest.raises(ValueError, match="cannot be smaller than z_offset"):
        locate_zarr_section(store_path, section_number=100, z_offset=200)

    # Exceeds total depth (total depth is 100)
    with pytest.raises(ValueError, match="exceeds volume depth"):
        locate_zarr_section(
            store_path, section_number=350, z_offset=200
        )  # z_index = 150 >= 100


def test_nonexistent_volume():
    with pytest.raises(FileNotFoundError):
        locate_zarr_section(
            "/path/does/not/exist/vol.zarr", section_number=10, z_offset=0
        )
