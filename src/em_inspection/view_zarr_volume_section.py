import argparse
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np
import zarr

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("zarr_volume_viewer")


@dataclass(frozen=True)
class ZarrSectionLocation:
    """Encapsulates the resolved location metadata for a section within a Zarr volume."""

    volume_path: str
    real_path: str
    dataset_key: str
    section_number: int
    z_offset: int
    z_index: int
    volume_shape: Tuple[int, ...]
    chunk_size: Tuple[int, ...]
    chunk_z_index: int
    z_within_chunk: int
    chunk_disk_path: str
    chunk_disk_exists: bool
    dimension_separator: str
    dtype: str

    def summary(self) -> str:
        """Returns a human-readable summary of the section and chunk localization."""
        lines = [
            "=" * 70,
            "Zarr Volume Section Location Summary",
            "=" * 70,
            f"Input Volume Path    : {self.volume_path}",
            f"Real Path (Resolved) : {self.real_path}",
            f"Dataset / Level      : '{self.dataset_key}'",
            f"Target Section Num   : {self.section_number}",
            f"Volume Z-Offset      : {self.z_offset}",
            f"Calculated Z-Index   : {self.z_index} (0-based in volume, range: 0..{self.volume_shape[0] - 1})",
            f"Volume Shape (ZYX)   : {self.volume_shape}",
            f"Chunk Size (ZYX)     : {self.chunk_size}",
            f"Chunk Z-Index (Z)    : {self.chunk_z_index}",
            f"Slice Within Chunk   : {self.z_within_chunk} (offset 0..{self.chunk_size[0] - 1} inside chunk {self.chunk_z_index})",
            f"Dim Separator        : '{self.dimension_separator}'",
            f"Chunk Path on Disk   : {self.chunk_disk_path}",
            f"Chunk Path Exists    : {self.chunk_disk_exists}",
            f"Data Type (Dtype)    : {self.dtype}",
            "=" * 70,
        ]
        return "\n".join(lines)


def _inspect_zarr_metadata(
    real_path: str, dataset_key: str = "0"
) -> Tuple[Tuple[int, ...], Tuple[int, ...], str, str, str]:
    """Inspects Zarr metadata directly or via Zarr API to obtain shape, chunks, dtype, and separator."""
    # Attempt 1: Try using zarr python API
    try:
        store = zarr.open(real_path, mode="r")
        if isinstance(store, zarr.Group):
            if dataset_key not in store:
                available = list(store.keys())
                raise KeyError(
                    f"Dataset key '{dataset_key}' not found in Zarr group at {real_path}. "
                    f"Available keys: {available}"
                )
            arr = store[dataset_key]
            array_subpath = dataset_key
        else:
            arr = store
            array_subpath = ""

        shape = tuple(arr.shape)
        chunks = tuple(arr.chunks)
        dtype = str(arr.dtype)
        # Check dimension separator if available
        dim_sep = "/"
        meta_obj = getattr(arr, "metadata", None)
        if meta_obj is not None:
            if (
                hasattr(meta_obj, "dimension_separator")
                and meta_obj.dimension_separator is not None
            ):
                dim_sep = meta_obj.dimension_separator
            elif (
                hasattr(meta_obj, "chunk_key_encoding")
                and meta_obj.chunk_key_encoding is not None
            ):
                dim_sep = getattr(meta_obj.chunk_key_encoding, "separator", "/")
        elif (
            hasattr(arr, "_dimension_separator")
            and arr._dimension_separator is not None
        ):
            dim_sep = arr._dimension_separator

        return shape, chunks, dtype, dim_sep, array_subpath

    except Exception as api_err:
        logger.debug(f"Zarr API inspection fallback due to: {api_err}")

    # Attempt 2: Fallback to direct .zarray / zarr.json inspection on disk
    possible_array_dirs = [
        (os.path.join(real_path, dataset_key), dataset_key),
        (real_path, ""),
    ]

    for array_dir, subpath in possible_array_dirs:
        # Check Zarr v2 .zarray
        zarray_file = os.path.join(array_dir, ".zarray")
        if os.path.isfile(zarray_file):
            with open(zarray_file, "r") as f:
                meta = json.load(f)
            shape = tuple(meta.get("shape", []))
            chunks = tuple(meta.get("chunks", []))
            dtype = str(meta.get("dtype", ""))
            dim_sep = meta.get("dimension_separator", ".")
            return shape, chunks, dtype, dim_sep, subpath

        # Check Zarr v3 zarr.json
        zarr_json_file = os.path.join(array_dir, "zarr.json")
        if os.path.isfile(zarr_json_file):
            with open(zarr_json_file, "r") as f:
                meta = json.load(f)
            shape = tuple(meta.get("shape", []))
            chunk_grid = meta.get("chunk_grid", {})
            chunk_shape = chunk_grid.get("configuration", {}).get("chunk_shape", [])
            chunks = (
                tuple(chunk_shape) if chunk_shape else tuple(meta.get("chunks", []))
            )
            dtype = str(meta.get("data_type", ""))
            dim_sep = "/"
            return shape, chunks, dtype, dim_sep, subpath

    raise FileNotFoundError(
        f"Could not read Zarr array metadata at '{real_path}' (key '{dataset_key}'). "
        f"Ensure the path is a valid Zarr volume."
    )


def locate_zarr_section(
    volume_path: str, section_number: int, z_offset: int, dataset_key: str = "0"
) -> ZarrSectionLocation:
    """Locates the section within a Zarr volume taking chunk dimensions into account.

    Args:
        volume_path: File system path to the .zarr volume directory.
        section_number: The experimental/run section number to view (e.g. 16040).
        z_offset: The Z offset of the volume (e.g. 1240).
        dataset_key: Internal dataset / resolution key (defaults to "0").

    Returns:
        A ZarrSectionLocation instance containing all computed chunk indices and paths.

    Raises:
        FileNotFoundError: If the volume path does not exist.
        ValueError: If section_number - z_offset is outside the valid range of the volume.
    """
    expanded_path = os.path.expanduser(volume_path)
    real_path = os.path.realpath(expanded_path)

    if not os.path.exists(real_path):
        raise FileNotFoundError(
            f"Zarr volume path does not exist: {real_path} (input: {volume_path})"
        )

    shape, chunks, dtype, dim_sep, array_subpath = _inspect_zarr_metadata(
        real_path, dataset_key
    )

    if len(shape) < 3 or len(chunks) < 3:
        raise ValueError(
            f"Expected at least 3D volume (ZYX), but got shape={shape}, chunks={chunks}"
        )

    z_index = section_number - z_offset
    total_z = shape[0]

    if z_index < 0:
        raise ValueError(
            f"Calculated z_index ({z_index}) is negative! "
            f"Section number ({section_number}) cannot be smaller than z_offset ({z_offset})."
        )

    if z_index >= total_z:
        valid_max_sec = z_offset + total_z - 1
        raise ValueError(
            f"Calculated z_index ({z_index}) exceeds volume depth ({total_z}). "
            f"Valid section range for z_offset={z_offset} is [{z_offset} .. {valid_max_sec}]."
        )

    chunk_z = chunks[0]
    chunk_z_index = z_index // chunk_z
    z_within_chunk = z_index % chunk_z

    # Determine chunk disk path based on dimension separator
    array_base_path = (
        os.path.join(real_path, array_subpath) if array_subpath else real_path
    )
    if dim_sep == "/":
        # Folder per Z chunk: e.g. /path/to/zarr/0/Z
        chunk_disk_path = os.path.join(array_base_path, str(chunk_z_index))
        chunk_disk_exists = os.path.exists(chunk_disk_path)
    else:
        # Flat files: e.g. /path/to/zarr/0/Z.0.0
        first_chunk_file = os.path.join(array_base_path, f"{chunk_z_index}.0.0")
        chunk_disk_path = first_chunk_file
        chunk_disk_exists = os.path.exists(first_chunk_file) or os.path.exists(
            array_base_path
        )

    location = ZarrSectionLocation(
        volume_path=volume_path,
        real_path=real_path,
        dataset_key=dataset_key,
        section_number=section_number,
        z_offset=z_offset,
        z_index=z_index,
        volume_shape=shape,
        chunk_size=chunks,
        chunk_z_index=chunk_z_index,
        z_within_chunk=z_within_chunk,
        chunk_disk_path=chunk_disk_path,
        chunk_disk_exists=chunk_disk_exists,
        dimension_separator=dim_sep,
        dtype=dtype,
    )

    return location


def get_zarr_section_data(location: ZarrSectionLocation, as_numpy: bool = True) -> Any:
    """Fetches the 2D section data slice corresponding to the resolved ZarrSectionLocation.

    Args:
        location: Resolved ZarrSectionLocation.
        as_numpy: If True, reads slice into a NumPy ndarray.

    Returns:
        2D NumPy ndarray or array slice.
    """
    store = zarr.open(location.real_path, mode="r")
    if isinstance(store, zarr.Group):
        arr = store[location.dataset_key]
    else:
        arr = store

    logger.info(
        f"Reading 2D slice at z_index={location.z_index} "
        f"(section {location.section_number}, chunk {location.chunk_z_index}, slice {location.z_within_chunk})..."
    )
    slice_2d = arr[location.z_index, :, :]

    if as_numpy and not isinstance(slice_2d, np.ndarray):
        slice_2d = np.asarray(slice_2d)

    return slice_2d


def view_zarr_volume_section(
    volume_path: str,
    section_number: int,
    z_offset: int,
    dataset_key: str = "0",
    show_full_volume: bool = False,
    info_only: bool = False,
) -> Optional[ZarrSectionLocation]:
    """Locates and views a section from a .zarr volume in Napari.

    Args:
        volume_path: Path to the .zarr volume directory.
        section_number: Section number (e.g. 16040).
        z_offset: Volume Z offset (e.g. 1240).
        dataset_key: Dataset/resolution tier inside Zarr (default: "0").
        show_full_volume: If True, opens the entire 3D volume with the viewer slider set to z_index.
                          If False (default), loads only the targeted 2D section slice.
        info_only: If True, only prints location diagnostics without opening Napari viewer.

    Returns:
        The resolved ZarrSectionLocation.
    """
    location = locate_zarr_section(
        volume_path=volume_path,
        section_number=section_number,
        z_offset=z_offset,
        dataset_key=dataset_key,
    )

    # Print diagnostic information
    print(location.summary())

    if info_only:
        return location

    try:
        import napari
    except ImportError:
        logger.error(
            "napari is required to view sections interactively. Please install napari (e.g. pip install napari)."
        )
        raise

    viewer = napari.Viewer()

    if show_full_volume:
        store = zarr.open(location.real_path, mode="r")
        arr = store[location.dataset_key] if isinstance(store, zarr.Group) else store
        vol_name = f"{Path(location.volume_path).name} (3D volume)"
        viewer.add_image(arr, name=vol_name, colormap="gray")
        # Position slider to the target slice
        viewer.dims.set_point(0, location.z_index)
        logger.info(
            f"Loaded 3D volume in Napari. Point set to z={location.z_index} (section {section_number})."
        )
    else:
        section_data = get_zarr_section_data(location, as_numpy=True)
        layer_name = (
            f"Section {section_number} "
            f"(z={location.z_index}, chunk_z={location.chunk_z_index}, sub_z={location.z_within_chunk})"
        )
        viewer.add_image(section_data, name=layer_name, colormap="gray")
        logger.info(f"Loaded 2D section '{layer_name}' in Napari.")

    napari.run()
    return location


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Locate and view a specific section from a 3D Zarr volume based on section number and z_offset."
    )
    parser.add_argument(
        "--volume",
        "-v",
        type=str,
        required=True,
        help="Path or realpath to the .zarr volume directory.",
    )
    parser.add_argument(
        "--section",
        "-s",
        type=int,
        required=True,
        help="The section number to view (e.g. 16040).",
    )
    parser.add_argument(
        "--z-offset",
        "-z",
        type=int,
        default=0,
        help="The Z offset of the volume (default: 0).",
    )
    parser.add_argument(
        "--dataset-key",
        "-k",
        type=str,
        default="0",
        help="Zarr dataset / resolution level (default: '0').",
    )
    parser.add_argument(
        "--full-volume",
        action="store_true",
        default=False,
        help="If set, opens the full 3D volume and sets the slice slider to the resolved section.",
    )
    parser.add_argument(
        "--info-only",
        action="store_true",
        default=False,
        help="If set, only locates and prints chunk/section metadata without opening Napari.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    view_zarr_volume_section(
        volume_path=args.volume,
        section_number=args.section,
        z_offset=args.z_offset,
        dataset_key=args.dataset_key,
        show_full_volume=args.full_volume,
        info_only=args.info_only,
    )
