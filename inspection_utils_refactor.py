import re
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter_ns
import subprocess
from collections import OrderedDict
from os.path import join

import cv2
import numpy as np
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Type, Union, Iterable, Sequence, Mapping, Any, Tuple, List, Callable
from platform import system
from re import compile
from glob import glob
import os
from zipfile import BadZipFile

import pandas as pd
import skimage
import yaml
import zarr
import matplotlib
matplotlib.use('Agg')  # Must be called before importing pyplot
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from tqdm import tqdm
from scipy.interpolate import CloughTocher2DInterpolator
from statistics import mean, stdev
import gc

UniPath = Union[str, Path]
TileXY = tuple[int, int]
TileCoord = Union[tuple[int, int, int, int], tuple[int, int]]  # (c, z, y, x)
TileMap = Mapping[TileXY, np.ndarray]
MaskMap = Dict[TileXY, Optional[np.ndarray]]
Vector = Union[tuple[int, int], tuple[int, int, int]]  # [z]yx order
GridXY = tuple[Any, Any, Any]

### Set up logging
# logging.basicConfig(level=logging.DEBUG)
# logging.basicConfig(level=logging.INFO)
# logging.basicConfig(level=logging.WARNING)

# 1. Standardized Data Model (Interface Segregation)
@dataclass(frozen=True)
class CoarseData:
    cx: np.ndarray[np.float32]
    cy: np.ndarray[np.float32]
    coarse_mesh: Optional[np.ndarray] = None


# 2. Abstract Base Strategy (Dependency Inversion)
class CoarseDataReader(ABC):
    @abstractmethod
    def read(self, path: Path) -> CoarseData:
        pass

# 3. Concrete Strategies (Single Responsibility)
class NpzReader(CoarseDataReader):
    def read(self, path: Path) -> CoarseData:
        with np.load(str(path)) as data:
            return CoarseData(
                cx=data['cx'],
                cy=data['cy'],
                coarse_mesh=data['coarse_mesh']
            )

class JsonReader(CoarseDataReader):
    def read(self, path: Path) -> CoarseData:
        with open(path, 'r') as f:
            content = f.read().replace('NaN', 'null')
            data = json.loads(content)

            cx = np.array(data.get('cx', []), dtype=np.float32)
            cy = np.array(data.get('cy', []), dtype=np.float32)
            if cx.ndim == 4:
                cx = cx[:, 0, ...]
                cy = cy[:, 0, ...]
            if cx.ndim == 5:
                cx = cx[:, 0, 0, ...]
                cy = cy[:, 0, 0, ...]

            return CoarseData(cx=cx, cy=cy)

# 4. The Factory (Open/Closed Principle)
class CoarseDataFactory:
    _readers: Dict[str, Type[CoarseDataReader]] = {
        '.npz': NpzReader,
        '.json': JsonReader
    }

    @classmethod
    def get_reader(cls, path: Path) -> CoarseDataReader:
        reader_class = cls._readers.get(path.suffix)
        if not reader_class:
            raise ValueError(f"Unsupported format: {path.suffix}")
        return reader_class()

# 5. The Facade (Clean API)
def read_coarse_mat(path: Path) -> CoarseData:
    """
       Return contents of a coarse shifts data file (either npz or json).

       :param path: path to the data file (cx_cy.npz or cx_cy.json)
       :return:
           coarse_mesh: contents of coarse_mesh (only if .npz file is read) or None
           cx: coarse shifts between horizontal neighbors
           cy: coarse shifts between vertical neighbors
       """
    path = Path(path)
    try:
        reader = CoarseDataFactory.get_reader(path)
        return reader.read(path)
    except Exception as e:
        logging.error(f"Failed to load coarse data from {path}: {e}")
        raise  # Better to raise in a library, let the caller handle it


def write_dict_to_yaml(file_path: str, data: Union[Dict[int, float], Iterable[int]]):
    """
    Write a dictionary with integer keys and float values, or an iterable of integers, to a YAML file.

    :param file_path: Path to the YAML file.
    :param data: Dictionary or iterable to be written to the file.
    """

    if isinstance(data, dict):
        # Convert NumPy types to native Python types, if any
        converted_data = {int(k): float(v) for k, v in data.items()}
    elif isinstance(data, Iterable):
        converted_data = [int(item) for item in data]
    else:
        raise ValueError(
            "The 'data' parameter must be a dictionary with integer keys and float values, or an iterable of integers."
        )
    try:
        with open(file_path, "w") as file:
            yaml.dump(converted_data, file, default_flow_style=False)
    except Exception as e:
        print(f"An error occurred while writing to the file: {e}")


def cross_platform_path(path: str) -> str:

    OS_WIN = 'Windows'
    OS_UX = 'Linux'
    OS_MAC = "Darwin"
    FS = r'/tungstenfs'
    TACH = "/tachyon/"

    TUNGSTEN_PREFIX = r'\\nas.company.internal\tungsten'
    TACHYON_PREFIX = r'\\storage.company.internal\tachyon'
    TACHYON_PREFIX_MAC = "/Volumes/storage/groups/"

    PREFIXES = FS, TUNGSTEN_PREFIX, TACHYON_PREFIX

    def_ret_val = ''

    def win_to_ux_path(win_path: str, remove_substring=None) -> str:
        if remove_substring:
            win_path = win_path.replace(remove_substring, FS)
        linux_path = win_path.replace('\\', '/')
        linux_path = linux_path.replace('//', '', 1)
        return linux_path

    def ux_to_win_path(ux_path: str, remove_substring=None) -> str:
        if remove_substring:
            ux_path = ux_path.replace(remove_substring, TACHYON_PREFIX)
        win_path = ux_path.replace('/', '\\')
        return win_path

    # Get the operating system name
    os_name = system()

    # Early return
    if path is None:
        return def_ret_val

    path = str(path)

    if os_name == OS_MAC and "Volumes" not in path:
        p_new = path.replace(TACH, TACHYON_PREFIX_MAC)
        return str(p_new)

    if os_name == OS_WIN and "/" in path:
        # Running on Windows but path in UX style
        path = ux_to_win_path(path, remove_substring=FS)
        return path

    prefix = None
    for p in PREFIXES:
        if p in path:
            prefix = p
            break

    if prefix is None:
        return path

    if os_name == OS_WIN:
        path = path.replace(prefix, "W:")
        path = path.replace('\\', '/')
    elif os_name == OS_UX and "\\" in path:
        # Running on UX but path in WinOS style
        path = win_to_ux_path(path, prefix)
    return path


def process_dirs(directory_path: str, filter_function)\
        -> Optional[tuple[list[Path], list[str], list[int], Dict[int, str]]]:
    """
    Process directories and return lists and dictionaries based on section number.

    :param directory_path: Path to the directory to process.
    :param filter_function: Function to filter and sort the directories.
    :return: Lists and dictionaries of directories, names, numbers, and dicts based on section number.
    """

    root = Path(directory_path)
    if not root.is_dir():
        return None

    paths = filter_function(root)
    if not paths:
        logging.warning(f"No subdirs in {root}")
        return None

    dirs = [Path(p) for p in paths]
    names = [d.name for d in dirs]
    nums = [get_section_num(d) for d in dirs]
    dirs_dict = {num: str(p) for num, p in zip(nums, dirs)}

    return dirs, names, nums, dirs_dict


def get_section_num(section_path: UniPath) -> Optional[int]:
    try:
        num = int(Path(section_path).name.split('_')[0].strip('s'))
        return num
    except (ValueError, IndexError):
        return None


def filter_and_sort_sections(sections_dir: str) -> Optional[list[str]]:
    """
    Filter and sort section directories within a parent directory.

    Only section names in form 's0xxxx_gy' where x and y are numeric will be returned.
    Sorting according to the section number from smallest to largest.
    :param sections_dir: Path to the parent directory containing section directories.
    :return: List of sorted and filtered section directory names.
    """

    # Define a regex pattern to filter section directory names
    pattern = r's\d+_g\d+'
    regex_pattern = compile(pattern)

    # Use glob to filter the section directory names
    dirs = glob(str(Path(sections_dir) / "*"))

    # Filter and sort the matching section directory names
    sorted_dirs = sorted([dir_name for dir_name in dirs
                          if os.path.isdir(dir_name) and regex_pattern.match(Path(dir_name).name)],
                         key=lambda p: get_section_num(p))

    return sorted_dirs if sorted_dirs else None


def process_dirs_unix(directory_path: str) -> Optional[tuple[list[Path], list[str], list[int], dict[int, str]]]:
    """Process directories using Unix commands and return lists and dictionaries based on section number."""

    if not Path(directory_path).exists():
        logging.warning(f"process_dirs_unix found no specified path: {directory_path}")
        return None

    command = f"find {directory_path} -maxdepth 1 -type d -name 's*_g*'"
    try:
        output = subprocess.check_output(command, shell=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return None

    dirs = output.strip().split("\n")
    if not dirs:
        print(f'process_dir_unix: No directories were loaded!')
        return None

    dirs = [Path(d) for d in dirs]
    pattern = compile(r's\d+_g\d+(\.zarr)?$')
    sections_with_paths = [(get_section_num(d.name), d) for d in dirs
                           if pattern.search(d.name)]

    sorted_sections = sorted(sections_with_paths, key=lambda x: x[0])
    nums, sorted_dirs = zip(*sorted_sections)
    names = [d.name for d in sorted_dirs]
    dirs_dict = {num: str(d) for num, d in zip(nums, sorted_dirs)}

    return list(sorted_dirs), names, list(nums), dirs_dict


def get_tile_ids_from_yaml(path: UniPath) -> Optional[list[int]]:
    section_yaml = Path(path) / "section.yaml"
    try:
        with open(section_yaml, 'r') as file:
            contents = yaml.safe_load(file)
            if contents:
                return [int(s["tile_id"]) for s in contents["tiles"]]
            else:
                return None
    except FileNotFoundError as e:
        print(f"{e} \n {section_yaml} does not exists!")
        return None


def read_tile_id_map(dir_section: UniPath) -> Optional[np.ndarray]:
    """
    Return contents of a tile_id_map.json within specified directory path
    :param dir_section: Path to directory containing tile_id_map.json
    :return: tile id map as a numpy array
    """
    fp_json = Path(dir_section) / 'tile_id_map.json'
    if not fp_json.exists():
        print(f'tile_id_map file is missing: {fp_json}')
        return None
    else:
        return get_tile_id_map(fp_json)


def get_tile_id_map(path_tid_map: UniPath) -> np.ndarray:
    """
    Load a JSON file containing a tile ID map and return it as a NumPy array.

    Args:
        path_tid_map (UniPath): Path to the JSON file.

    Returns:
        np.ndarray: Tile ID map as a NumPy array.
    """
    try:
        with open(path_tid_map, "r") as file:
            mp = np.array(json.load(file)).astype(np.int16)
        return mp
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ValueError(f"Error loading tile ID map from {path_tid_map}: {str(e)}")


def aggregate_parallel(
        section_dirs: List[Path],
        target_filename: str,
        processing_func: Callable[[Path], Any],
        progress_cb: Optional[Callable[[int, int], None]] = None,
        max_workers: int = 8
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Aggregates data from multiple directories in parallel using a provided processing function.

    This engine walks through a list of directory paths, looks for a specific target file,
    and applies an injected 'processing_func' to each file found. It handles I/O
    concurrency via multi-threading and provides progress updates via an optional callback.

    Args:
        section_dirs (List[Path]): A list of Path objects pointing to the directories
            to be processed (e.g., individual section folders).
        target_filename (str): The name of the file to look for within each directory
            (e.g., 'cx_cy.json').
        processing_func (Callable[[Path], Any]): A function that takes a Path to the
            target file and returns the processed data object (e.g., a NumPy array).
        progress_cb (Optional[Callable[[int, int], None]]): A callback function
            used for UI progress updates. Receives (current_count, total_count).
        max_workers (int): The maximum number of threads to use for parallel I/O.
            Defaults to 8.

    Returns:
        Tuple[Dict[str, Any], List[str]]: A tuple containing:
            - A dictionary mapping section identifiers (strings) to their processed data.
            - A list of error strings or paths for files that were missing or failed
              to process.
    """
    results: Dict[str, Any] = {}
    failed_paths: List[str] = []
    total: int = len(section_dirs)

    def _worker(p: Path) -> Tuple[Optional[str], Optional[Any], Optional[str]]:
        try:
            sec_num_str: str = str(get_section_num(p))
            fp: Path = p / target_filename

            if not fp.exists():
                return sec_num_str, None, f"s{sec_num_str} (missing {target_filename})"

            data: Any = processing_func(fp)
            return sec_num_str, data, None

        except Exception as e:
            return None, None, f"Error at {p.name}: {str(e)}"

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        mapper = executor.map(_worker, section_dirs)

        for i, (sec_num, data, error) in enumerate(mapper, 1):
            if data is not None and sec_num is not None:
                results[sec_num] = data

            if error:
                failed_paths.append(error)

            if progress_cb and (i % 10 == 0 or i == total):
                progress_cb(i, total)

    return results, failed_paths


def process_offsets(path: Path) -> np.ndarray:
    """
    Now simplified because the JsonReader handles
    dimensionality reduction internally.
    """
    data: CoarseData = read_coarse_mat(path)
    return np.stack([data.cx, data.cy]).astype(np.float32)


def process_tile_maps(path: Path) -> np.ndarray:
    """Logic specific to tile_id_map.json."""
    with open(path, 'r') as f:
        return np.array(json.load(f), dtype=np.int32)


def locate_inf_vals(
        path_cxyz: Union[str, Path],
        dir_out: Union[str, Path],
        store: bool
) -> Optional[list[tuple[int]]]:
    """
    Find all Inf values in a backed-up coarse shift tensor.

    :param path_cxyz: Path to the backed-up coarse shift .npz file
    :param dir_out: Directory where to store results
    :param store: Activates storing the results to a text file
    :return: List containing tuples of section numbers, all Inf
            coordinates and corresponding tile IDs
    """

    try:
        cxyz = np.load(str(path_cxyz), allow_pickle=True)
    except FileNotFoundError as _:
        print('Error reading coarse tensor file.')
        return None

    try:
        path_tid_maps = Path(path_cxyz).parent / 'all_tile_id_maps.npz'
        tid_maps = np.load(str(path_tid_maps), allow_pickle=True)
    except FileNotFoundError as _:
        tid_maps = None
        logging.warning('Error reading all_tile_id_maps.npz')

    all_coords = []
    all_tids = []
    tids_list = ()

    for section_num in cxyz:
        inf_coords = np.where(np.isinf(cxyz[section_num]))
        coords_list = list(zip(*inf_coords))

        # Get TileIDs of a corrupted tile-pair
        if tid_maps is not None:
            tile_id_map = tid_maps[section_num]
            tids_list = []
            for crd in coords_list:
                tile_id_a = tile_id_from_coord(crd, tile_id_map)

                # Determine the direction of the tile neighbor
                dx = 1 if crd[0] == 0 else 0
                dy = 1 if crd[0] != 0 else 0

                # Compute the neighbor's coordinates
                nn_dxdy = np.zeros_like(crd)
                nn_dxdy[-2:] = (dy, dx)  # Assign dy and dx directly
                nn_crd = crd + nn_dxdy

                # Get the tile ID of the neighboring coordinate
                tile_id_b = tile_id_from_coord(nn_crd, tile_id_map)

                tids_list.append((tile_id_a, tile_id_b))

        if len(tids_list) > 0:
            coords_w_key = [(int(section_num),) + c + tids
                            for c, tids in zip(coords_list, tids_list)]
        else:
            coords_w_key = [(int(section_num),) + c for c in coords_list]

        all_coords.extend(coords_w_key)
        all_tids.append(tids_list)

    if store:
        path_out = str(Path(dir_out) / 'inf_vals.txt')
        logging.info(f"Storing Inf values to: {path_out}")
        np.savetxt(fname=path_out, X=all_coords, fmt='%s', delimiter='\t',
                   header=f'Slice\tC\tZ\tY\tX\tTileID\tTileID_nn')

    return all_coords

def tile_id_from_coord(coord: TileCoord, tile_id_map: np.ndarray) -> Optional[int]:
    """Determines tile ID from tile coordinates.

    Args:
        coord (TileCoord): Tile coordinates, either (c, z, y, x) or (y, x).
        tile_id_map (np.ndarray): Array containing tile IDs.
    Returns:
        Optional[int]: The tile ID if found, None otherwise.
    """
    if len(coord) in (2, 4):
        # Unpack the last two elements of the tuple as y, x
        y, x = coord[-2:]
    else:
        return None

    try:
        return int(tile_id_map[int(y), int(x)])
    except (ValueError, IndexError):
        return None


def get_tile_ids_set(path_all_tid_maps: str) -> set[int]:
    try:
        path_tid_maps = Path(path_all_tid_maps).parent / 'all_tile_id_maps.npz'
        tid_maps = np.load(str(path_tid_maps), allow_pickle=True)
    except FileNotFoundError as _:
        tid_maps = None
        logging.warning('Error reading all_tile_id_maps.npz')

    tile_ids = set()
    for tid in tid_maps.values():
        tile_ids |= set(tid.flatten())

    tile_ids.remove(-1)

    return tile_ids


def plot_trace_from_backup(
        path_cxyz: str,
        path_id_maps: str,
        path_plot: str,
        tile_id: int,
        sec_range: tuple[Optional[int], Optional[int]],
        show_plot: bool,
):
    """Plots traces from input cxyz tensor

    Args:
        path_cxyz: str -  path to aggregated file containing all coarse offsets
        path_id_map: str - path to aggregated file containing all tile_id_maps
        path_plot: str - path where to store resulting graph
        tile_id: int - ID of the tile trace to be plotted
        sec_range: Optional[tuple(int, int)] - range of section numbers to be plotted

    :return:
    """

    def plot_traces(x_axis: np.ndarray, traces: np.ndarray, _path_plot: str,
                    _tile_id: int, _vert_nn_tile_id: Optional[int], _show_plot: bool) -> None:

        """Plots array of both coarse offset vectors' values """

        fig, ax = plt.subplots(figsize=(15, 9))
        labels = ('c0x', 'c0y', 'c1x', 'c1y')
        for j in range(traces.shape[0]):
            ax.plot(x_axis, traces[j, :], '-', label=f'{labels[j]}')

        # Add labels, title, and legend
        ax.set_xlabel('Section number')
        ax.set_ylabel('Shift [pix]')
        nn_tile_id = '' if _vert_nn_tile_id is None else f" ({str(_vert_nn_tile_id)})"
        ax.set_title(f'Coarse Offsets for Tile ID {_tile_id} {nn_tile_id}')
        ax.legend(loc='upper right')
        ax.grid(True)

        # Adjust x-axis and y-axis ticks density
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=30))
        ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=20))

        plt.savefig(_path_plot)
        if _show_plot:
            plt.show()

        plt.close(fig)
        return

    path_cxyz = Path(cross_platform_path(path_cxyz))
    path_id_maps = Path(cross_platform_path(path_id_maps))
    path_plot = cross_platform_path(path_plot)

    if not path_cxyz.exists() or not path_id_maps.exists():
        print(f'Input files are missing. Check path_cxyz: {path_cxyz}')
        return

    # Load coarse offsets
    cxyz_obj = np.load(path_cxyz)
    cxyz_keys = list(cxyz_obj.files)
    sec_nums = set(map(int, cxyz_keys))

    # Load tile_id_maps
    tile_id_maps = np.load(path_id_maps)
    tile_id_maps_keys = list(tile_id_maps.files)
    sec_nums_id_maps = set(map(int, tile_id_maps_keys))

    # Compatible section numbers
    sec_nums = sec_nums.intersection(sec_nums_id_maps)

    if len(sec_nums) == 0:
        # Not possible to map tile_id_map files to the coarse offset files
        print(f'Available offsets maps and tile_id_maps do not match.')
        return

    # Select range of sections to be processed
    first, last = sec_range
    if first is None:
        first = min(sec_nums)

    if last is None:
        last = max(sec_nums)

    if first > last:
        logging.warning('Plot traces: wrong section range definition.')
        return

    sec_nums_plot = set(np.arange(first, last, step=1))
    sec_nums_plot = sec_nums.intersection(sec_nums_plot)
    logging.info(f'Trace plotting: {len(sec_nums_plot)} sections will be processed.')

    if len(sec_nums_plot) <= 1:
        print(f'Nothing to plot. Sections {first} : {last} not in available'
              f'range: [{min(sec_nums)} : {max(sec_nums)}].')
        return

    arr = np.full(shape=(4, last - first), fill_value=np.nan)
    x_axis_sec_nums = np.arange(first, last)
    vert_nn_tile_id = None

    for i, num in enumerate(x_axis_sec_nums):
        if num in sec_nums_plot:
            tile_id_map = tile_id_maps[str(num)]
            if vert_nn_tile_id is None:
                vert_nn_tile_id = get_vert_tile_id(tile_id_map, tile_id)
            coord = get_tid_idx(tile_id_map, tile_id)
            if coord is not None:
                y, x = coord
                try:
                    shifts = cxyz_obj[str(num)][:, :, y, x]
                    arr[:, i] = shifts.flatten().transpose()
                except IndexError as _:
                    logging.warning(f'Trace plotting: unable to determine shifts of s{num} t{tile_id}')
                except ValueError as _:
                    logging.warning(f"Trace plotting failed for s{num} t{tile_id}")
            else:
                continue

    if not np.all(np.isnan(arr)):
        plot_traces(x_axis_sec_nums, arr, path_plot, tile_id, vert_nn_tile_id, show_plot)


def get_vert_tile_id(tile_id_map: np.ndarray, tile_id: int) -> Optional[int]:
    """
    Retrieves the tile ID located directly below the specified tile ID in the given tile ID map.

    Example:
        tile_id_map = np.array([[1, 2, 3],
                                [4, 5, 6],
                                [7, 8, 9]])
        get_vert_tile_id(tile_id_map, 5) returns: 8
        get_vert_tile_id(tile_id_map, 9) returns: None
    """
    tile_id = int(tile_id)
    if not isinstance(tile_id, int):
        raise ValueError(f"Invalid tile_id '{tile_id}' specification: must be an integer.")

    if tile_id < 0:
        logging.warning(f"Invalid tile_id specification (must be non-negative)!")
        return None

    if tile_id not in tile_id_map:
        logging.warning(f"Invalid tile_id specification ({tile_id} not in tile_id_map)!")
        return None

    y, x = np.where(tile_id == tile_id_map)
    y, x = y[0], x[0]
    try:
        return int(tile_id_map[y + 1][x])
    except IndexError as _:
        logging.warning(f"tile_id {tile_id} not found in tile_id_map.")
        return None


def get_tid_idx(tile_id_map: np.ndarray, tile_id: int) -> Optional[tuple[int, int]]:
    """Finds the first occurrence of tile_id in a 2D array."""
    if tile_id == -1:
        return None

    coords = np.argwhere(tile_id_map == tile_id)
    if coords.size == 0:
        return None

    return tuple(coords[0])


def compute_tile_id_map(
        grid_shape: tuple[int, int],
        tile_ids: Sequence[int]
) -> np.ndarray[int]:
    """
    Build a 2D grid of shape `grid_shape` where each cell contains its linear tile index
    if that index is in `tile_ids`, or -1 otherwise. Finally, trim any full-(-1) border
    rows/columns.

    Parameters
    ----------
    grid_shape : tuple of (rows, cols)
        The shape of the full grid of tile indices [0 ... rows*cols-1].
    tile_ids : sequence of int
        Linear indices to keep in the grid; all other positions become -1.

    Returns
    -------
    np.ndarray
        A cropped 2D array containing only the minimal bounding box of non-(-1) tiles.

    Raises
    ------
    ValueError
        If `tile_ids` is empty.
    """
    if not tile_ids:
        raise ValueError("`tile_ids` must not be empty")

    rows, cols = grid_shape
    full_indices = np.arange(rows * cols).reshape(rows, cols)

    # mask-in only the requested tile_ids, fill others with -1
    mask = np.isin(full_indices, tile_ids)
    grid = np.where(mask, full_indices, -1)

    # find rows/cols that have any non-(-1) entries
    non_empty_rows = np.any(grid != -1, axis=1)
    non_empty_cols = np.any(grid != -1, axis=0)

    # slice out the minimal bounding box
    return grid[non_empty_rows][:, non_empty_cols]


def get_tile_dicts(path: UniPath) -> Optional[Dict[int, str]]:
    section_yaml = Path(path) / "section.yaml"
    try:
        with open(section_yaml, 'r') as file:
            contents = yaml.safe_load(file)
            if contents:
                return {int(s["tile_id"]): str(cross_platform_path(s["path"]))
                        for s in contents["tiles"]}
            else:
                return None
    except FileNotFoundError as e:
        print(f"{e} \n {section_yaml} does not exists!")
        return None


def save_img(path: str, data: np.ndarray):

    if not isinstance(data, np.ndarray):
        logging.warning(f'Image {Path(path).stem} could not be resized.')
        return

    print(f'saving mini to: {path}')
    # cv2.imwrite(path, cv2.convertScaleAbs(data))
    skimage.io.imsave(path, data)
    return


def downscale_image(img: np.ndarray, fct: float) -> np.ndarray:
    """
    Downscale an image using OpenCV.

    Args:
        img (np.ndarray): The input image.
        fct (float): The scaling factor.

    Returns:
        np.ndarray: The downscaled image.
    """
    return cv2.resize(img, None, fx=fct, fy=fct, interpolation=cv2.INTER_AREA)


def read_zarr_volume(path_volume: Union[Path, str]) -> zarr.Group | None:
    path_str = cross_platform_path(str(path_volume))
    try:
        vol = zarr.open_group(store=path_str, mode='r')  # ← fails if it's actually an array
        logging.debug(str(vol.info))

        if not list(vol.keys()):
            logging.error("Zarr group is empty")
            return None

        arrays = list_arrays(vol)  # your fixed recursive function
        if not arrays:
            logging.warning("No arrays found in group")

        return vol
    except Exception as e:
        logging.error(f"Failed to open Zarr group at {path_str}: {e}")
        return None


def list_arrays(group: zarr.Group, prefix: str = '') -> list[str]:
    keys = []
    for key in group.keys():
        item = group[key]
        # In zarr 3.x: item is Array or Group
        if isinstance(item, zarr.Array):
            keys.append(prefix + key)
        elif isinstance(item, zarr.Group):
            keys.extend(list_arrays(item, prefix=prefix + key + '/'))
    return keys


def get_tile_shape(fp_yaml: UniPath) -> Optional[TileXY]:
    try:
        # Load the YAML data
        with open(fp_yaml, "r") as yaml_file:
            data = yaml.safe_load(yaml_file)
            h = data['tile_height']
            w = data['tile_width']
        return h, w
    except Exception as e:
        print(f"Error in get_tile_shape occurred: {e}")
        return None


def load_mapped_npz(fp: str) -> Optional[MaskMap]:
    file_path = Path(fp)
    if not file_path.exists():
        logging.info(f"File '{file_path}' not found.")
        return None

    fmt_data = {}
    try:
        data = np.load(fp, allow_pickle=True)
        for key in data.keys():
            fmt_data[eval(key)] = data[key]
        return fmt_data

    except BadZipFile:
        logging.warning(f"File '{file_path}' is not a valid zip file.")
        return None

    except Exception as e:
        logging.warning(f"An unknown error occurred while loading '{file_path}': {e}")
        return None



def pair_is_vertical(
        tile_id_map: np.ndarray,
        tile_id_a: int,
        tile_id_b: int
) -> Optional[bool]:

    assert isinstance(tile_id_map, np.ndarray), f"Incorrect tile_id_map type {type(tile_id_map)}. Check if it was loaded correctly."

    if tile_id_a < 0 or tile_id_b < 0:
        logging.warning('f(pair_is_vertical): tile_id must be greater than -1!')
        return None

    if tile_id_a == tile_id_b:
        logging.warning('f(pair_is_vertical): tile_ids must differ!')
        return None

    if tile_id_a not in tile_id_map:
        # logging.warning(f'Tile ID {tile_id_a} not present in TileID map')
        return None
    elif tile_id_b not in tile_id_map:
        # logging.warning(f'Tile ID {tile_id_b} not present in TileID map')
        return None
    else:
        y, x = np.where(tile_id_a == tile_id_map)
        y, x = y[0], x[0]
        try:
            tile_id_up = tile_id_map[y - 1, x]
            if tile_id_b == tile_id_up:
                return True
        except IndexError as _:
            pass
            # logging.warning(f"{tile_id_a} doesn't have a vertical neighbor.")

        try:
            tile_id_down = tile_id_map[y + 1, x]
            if tile_id_b == tile_id_down:
                return True
        except IndexError as _:
            pass
            # logging.warning(f"{tile_id_a} doesn't have a vertical neighbor.")

        if tile_id_b in tile_id_map:
            return False
        else:
            return None


def apply_clahe(image, clip_limit=2., grid_size=(8, 8)):
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=grid_size)
    return clahe.apply(image)



def get_shift(cx_cy: np.ndarray[float],
              tile_id_map: np.ndarray,
              tile_id: int,
              axis: int
              ) -> Optional[Vector]:
    """Returns a shift vector to tile 'tile_id' in 'tile_id_map'.

    Params:
        cx_cy: coarse shift matrix
        tile_id_map: numpy array containing tile IDs
        tile_id: tile number for which to extract shift vector
        axis: 0 for horizontal pair, 1 for vertical pair
    Returns:
        Vector or None if Inf
    """

    coord = np.where(tile_id_map == tile_id)
    y, x = coord[0][0], coord[1][0]
    try:
        vec = cx_cy[axis, :, y, x]
        if np.inf in vec:
            # logging.warning(f"t{tile_id} nothing to plot: shift vector contains Inf value")  # TODO plot?
            return None
        else:
            vec = cx_cy[axis, :, y, x].astype(np.int64)
            return tuple(vec)

    except TypeError as _:
        logging.warning(f"t{tile_id} nothing to plot: shift vector not defined")
        return None


def create_directory(dir_path: UniPath):
    dir_path = Path(cross_platform_path(str(dir_path)))
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        print(f"Directory '{dir_path}' already exists.")
    except PermissionError:
        print(f"Permission denied. Unable to create directory '{dir_path}'.")
    except OSError as e:
        print(f"Error creating directory '{dir_path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")




def plot_thin_image(
        img_pair: np.ndarray,
        is_vertical: bool,
        path_plot: Optional[str],
        show_plot: bool,
        blur: float,
        rotate_vert=False,
        return_array: bool = False
) -> np.ndarray:
    """Plot a thin section of an image and save or show the result.

        Args:
            img_pair (np.ndarray): Input image pair.
            is_vertical (bool): Flag to determine if the image is vertical.
            path_plot (Optional[str]): Path to save the plot image.
            show_plot (bool): Flag to show the plot.
            blur (float): Gaussian blur sigma value.
            rotate_vert (bool): Flag to rotate the image vertically.
            return_array (bool): Return image array only, do not use matplotlib
                                (switch for InteractiveProcessor)

        Returns:
            np.ndarray: The processed image.
        """
    # Define region of interest dimensions
    dy, dx = 250, 250
    h, w = img_pair.shape
    h_mid, w_mid = h // 2, w // 2

    # output_img = output_img[h_mid - dy:h_mid + dy, w_mid-dx:w_mid+dx]
    if is_vertical:
        img = img_pair[h_mid - dy:h_mid + dy, : w_mid + dx]
    else:
        img = img_pair[:h_mid + dy, w_mid - dx:w_mid + dx]

    # Apply Gaussian blur if specified
    if blur > 1.0:
        img = skimage.filters.gaussian(img, sigma=blur)

    # Return image immediately
    if return_array:
        final_img = np.rot90(img, k=-1) if (rotate_vert and not is_vertical) else img
        return final_img

    # Normalize image to 8-bit depth
    image_8bit = norm_img(img)  # Ensure `norm_img` is defined elsewhere

    # Create a figure and axes
    h, w = img.shape
    fig, ax = plt.subplots(figsize=(w / 100, h / 100))

    # Plot the image with minimal empty space
    ax.imshow(
        image_8bit, cmap='gray', aspect='equal', extent=(0, w, h, 0), vmin=0, vmax=255)
    ax.axis('off')

    # Save the plot and show if needed
    if path_plot is not None:
        image_8bit = np.rot90(image_8bit, k=-1) if (rotate_vert and not is_vertical) else image_8bit
        logging.info(path_plot)
        skimage.io.imsave(path_plot, image_8bit)
        logging.info(f'storing ov thin image to: {path_plot}')

    if show_plot:
        plt.show()

    plt.close(fig)  # Ensure you close the specific figure created
    return img


def norm_img(data) -> np.ndarray:
    norm_gray = (data - np.min(data)) / (np.max(data) - np.min(data))
    return (norm_gray * 255).astype(np.uint8)


def get_tile_num(section_path: UniPath) -> Optional[int]:
    try:
        num = int(Path(section_path).name.split('_')[-2].strip('t'))
        return num
    except (ValueError, IndexError):
        return None


def insert_image(canvas, image, x, y, alpha_on=False):
    """Inserts image data into a canvas at specific coordinates.

    Args:
        canvas: numpy array representing the canvas (2D array)
        image: numpy array representing the greyscale image to be inserted
        x, y: coordinates to place the top-left corner of the image on the canvas
        alpha_on: set to True to visualize the images in transparent mode

    Returns:
        Updated canvas with the inserted greyscale image.
    """

    x = int(round(float(x)))
    y = int(round(float(y)))
    h, w = image.shape[:2]
    h, w = int(h), int(w)
    cnv_h, cnv_w = canvas.shape[:2]

    # Bounds check using the now-safe integers
    if x < 0 or y < 0 or x + w > cnv_w or y + h > cnv_h:
        logging.info(f"Invalid insertion: x={x}, y={y} exceeds canvas {cnv_w}x{cnv_h}")
        return canvas  # Better to return original canvas than None to avoid cascading crashes

    if alpha_on:
        alpha = 0.5
        canvas[y:y + h, x:x + w] = (
                alpha * image[:, :] + (1 - alpha) * canvas[y:y + h, x:x + w]
        )
    else:
        canvas[y:y + h, x:x + w] = image[:, :]

    return canvas


def insert_image_orig(canvas, image, x, y, alpha_on=False):
    """Inserts image data into a canvas at specific coordinates.

    Args:
        canvas: numpy array representing the canvas (2D array)
        image: numpy array representing the greyscale image to be inserted
        x, y: coordinates to place the top-left corner of the image on the canvas
        alpha_on: set to True to visualize the images in transparent mode

    Returns:
        Updated canvas with the inserted greyscale image.
    """

    cnv_h, cnv_w = canvas.shape
    print(cnv_h, cnv_w)
    h, w = image.shape
    print(f'hw:{h, w}')
    print(f'x, y: {x, y}')
    print(f'x+w, y+h: {x+w, y+h}')


    if x < 0 or y < 0 or x + w > cnv_w or y + h > cnv_h:
        logging.info("Invalid insertion coordinates. Image exceeds canvas boundaries.")
        return None

    if alpha_on:
        alpha = 0.5
        canvas[y:y + h, x:x + w] = (alpha * image[:, :] +
                                    (1 - alpha) * canvas[y:y + h, x:x + w])
    else:
        canvas[y:y + h, x:x + w] = image[:, :]

    return canvas


def plot_tile_pair(
        tile_map: TileMap,
        shift_vec: Vector,
        show_plot: bool,
        path_plot: Optional[str] = None,
        reverse_render: bool = True,
        scaling_factor: Optional[float] = None,
        alpha_on=False,
        blur=2.0,
        img_only: bool = False
) -> Optional[np.ndarray]:
    """Plots two images of a vertical tile-pair
    Args:
        tile_map: mapping of two images into a dictionary with keys
                  being 2D-map indices
        shift_vec: coarse shift between the tiles
        path_plot: graph storage location
        show_plot: visualize plot (disable when running on cluster)
        reverse_render: True for rendering upper image on top of the lower image
                        True for rendering left image on top of the image on the right
        scaling_factor (optional): plot downscaled version of the canvas
        alpha_on: if non-zero, plots the overlap in transparent mode
            coordinates of the map
        blur: perform Gaussian blurring on plotted images
        img_only: if True, return only blended image-pair

    Returns: Rendered canvas

    """

    try:
        any_tile = next(iter(tile_map.values()))
    except StopIteration as _:
        logging.warning(f'Plot_tile_pair: Nothing to plot. Check input "tile_map" parameter.')
        return None

    if isinstance(any_tile, np.ndarray):
        h, w = any_tile.shape
    else:
        logging.warning(f'Plot_tile_pair: Input tile_map object contains wrong data.')
        return None

    pad = 1000  # Black border around the image pair  TODO parameter into f-def?
    canvas = np.zeros((h * 2 + pad, w * 2 + pad))

    # Define order in which the images will be rendered
    or_a = (0, 0)
    or_b = tuple(x + y for x, y in zip(or_a, shift_vec))
    origins = [or_a, or_b]
    if reverse_render:
        tile_map = OrderedDict(reversed(tile_map.items()))
        origins = origins[::-1]

    # Insert image data into canvas
    for i, (coord, img) in enumerate(tile_map.items()):

        # Get image offset coordinates (with respect to the canvas top-left corner)
        dx, dy = origins[i]
        x0 = int(int(pad / 2) + dx + coord[0] * w)
        y0 = int(int(pad / 2) + dy + coord[1] * h)

        if blur > 1:
            img = skimage.filters.gaussian(img, sigma=blur)

        logging.debug(f"Inserting img at location {x0, y0}")
        canvas = insert_image(canvas, img, x0, y0, alpha_on)

        if canvas is None:
            return None

    # Render canvas
    img_out = canvas
    if scaling_factor is not None:
        img_out = skimage.transform.rescale(canvas, scaling_factor, anti_aliasing=True)

    # Plot canvas
    if not img_only:
        plt.imshow(img_out, cmap='grey')
        fig = plt.gcf()

        if show_plot:
            fig.canvas.manager.full_screen_toggle()
            plt.show()

        if path_plot is not None:
            logging.info(f'storing plot to: {path_plot}')
            plt.savefig(path_plot, dpi=600)

        plt.close(fig)

    return img_out


def build_tiles_coords(
        tile_id_map: np.ndarray
) -> Optional[tuple[TileXY]]:
    """Builds tile coordinates map from the given tile ID map.

    Args:
        tile_id_map (np.ndarray): The tile ID map.

    Returns:
        Optional[Tuple[TileXY]]: A tuple of tile coordinates (x, y).
    """
    if not isinstance(tile_id_map, np.ndarray):
        return None

    rows, cols = np.where(tile_id_map != -1)
    return tuple(zip(cols, rows))


def get_ov_tid_pairs(directory: UniPath) -> list[tuple[int, int]]:
    """
    Extracts pairs of tile IDs from folder names in the specified directory.

    Folders should follow the format 'tXXXX_tYYYY', where 'XXXX' and 'YYYY' are integers.

    Parameters:
    - directory (UniPath): The path to the directory containing folders.

    Returns:
    - List[Tuple[int, int]]: A list of tuples, each containing a pair of tile IDs.
    """
    pattern = compile(r'^t(\d{4})_t(\d{4})$')  # Exact match for 'tXXXX_tYYYY'
    matches: list[tuple[int, int]] = []

    dir_path = Path(directory)

    if not dir_path.is_dir():
        raise ValueError(f"The provided path '{directory}' is not a valid directory.")

    for entry in dir_path.iterdir():
        if entry.is_dir():
            match = pattern.match(entry.name)
            if match:
                num1 = int(match.group(1))
                num2 = int(match.group(2))
                matches.append((num1, num2))

    return sorted(matches)


def get_ov_sec_nums(directory: UniPath) -> list[int]:
    # Regular expression pattern to match "s0510_t0754_t0786_ov.jpg"
    pattern = compile(r's(\d+)_t\d+_t\d+_ov\.jpg')
    numbers = []

    # Create a Path object for the directory
    dir_path = Path(cross_platform_path(str(directory)))
    if not dir_path.exists():
        return numbers

    # Iterate over all entries in the directory
    for entry in dir_path.iterdir():
        if entry.is_file():  # Check if it's a file
            match = pattern.match(entry.name)
            if match:
                s_number = int(match.group(1))  # Integer following 's'
                numbers.append(s_number)

    return sorted(numbers)



def save_coarse_mat(
        cxy_mat: np.ndarray,
        dir_path: UniPath,
        file_format: str = 'json',
) -> None:
    """
    Save coarse offsets array to a file in the specified format ('json' or 'npz').
    :param cxy_mat: cxy array to save
    :param dir_path: directory path where to store the coarse-shift array
    :param file_format: format for saving ('json' or 'npz')
    :return: None
    """
    dir_path = Path(dir_path)

    if not dir_path.is_dir():
        logging.error(f'save_coarse_mat: directory {dir_path} does not exist.')
        return

    try:
        if file_format == 'json':
            cx_0, cx_1 = cxy_mat[0][0], cxy_mat[0][1]
            cy_0, cy_1 = cxy_mat[1][0], cxy_mat[1][1]
            cx = [cx_0.tolist()], [cx_1.tolist()]
            cy = [cy_0.tolist()], [cy_1.tolist()]
            data = {
                "cx": list(cx),
                "cy": list(cy)
            }
            with open(dir_path / 'cx_cy.json', 'w') as json_file:
                json.dump(data, json_file, indent=4)
                logging.info(f'storing coarse mat: {dir_path}')
        elif file_format == 'npz':
            fn_fix = dir_path / 'coarse_fixed.npz'
            np.savez(fn_fix, cxy_mat)
        else:
            logging.error(f'Error: Unsupported file format "{file_format}". Supported formats are "json" and "npz".')

    except Exception as e:
        logging.error(f'Error during save_coarse_mat: {e}')


def get_pyramid(
        levels=3,
        max_ext=50,
        stride=10
) -> list[tuple[int, int]]:
    # Define pyramid of search parameters
    params = [(max_ext // N, stride // N) for N in range(1, levels + 1)]
    params = [tup for tup in params if 0 not in tup]
    return params



def get_shift_grid(
        max_ext: int,
        stride: int,
        shift_vec: Vector,
        is_vert: bool
) -> tuple[list[tuple[int, int]], np.ndarray, np.ndarray]:
    """
    Generate a grid of 2D shift vectors with specific stride and maximum extent.

    The function creates a meshgrid of x and y displacements and combines them into a list
    of shift vectors. Each shift vector represents a 2D displacement.

    Parameters:
    - max_ext (int): Maximum extent in pixels for both x and y displacements.
    - stride (int): Stride for mesh points, determining the spacing between displacements.

    Returns:
    - List[Tuple[int, int]]: A list of tuples where each tuple represents a 2D shift vector.
    """

    if not is_vert:
        x_lim = min(-6, max_ext + shift_vec[0])
        x_disp, y_disp = np.meshgrid(
            np.arange(-max_ext + shift_vec[0], x_lim, stride),
            np.arange(-max_ext + shift_vec[1], max_ext + shift_vec[1] + 1, stride), indexing='ij')
    else:
        y_lim = min(-6, max_ext + shift_vec[1])
        x_disp, y_disp = np.meshgrid(
            np.arange(-max_ext + shift_vec[0], max_ext + shift_vec[0], stride),
            np.arange(-max_ext + shift_vec[1], y_lim, stride), indexing='ij')

    shifts = list(zip(x_disp.flatten().astype(int), y_disp.flatten().astype(int)))

    return shifts, x_disp, y_disp



def interp_coarse_grid(
        coarse_grid_xy: tuple[np.ndarray, np.ndarray],
        coarse_grid_z: list[float],
) -> tuple[Vector, tuple[GridXY, GridXY]]:

    cgx, cgy = coarse_grid_xy
    cgz = np.array(coarse_grid_z)
    cgx, cgy, cgz = [a.flatten() for a in (cgx, cgy, cgz)]

    # Fine coarse offset grid
    fgx, fgy = np.meshgrid(
        np.linspace(min(cgx), max(cgx), 100),
        np.linspace(min(cgy), max(cgy), 100)
    )

    # Create CloughTocher2DInterpolator instance
    interp = CloughTocher2DInterpolator((cgx, cgy), cgz)

    # Perform interpolation on the finer grid
    fgz = interp(fgx, fgy)

    # Find the index of the smallest value in fine grid data
    min_index = np.argmin(fgz)

    # Convert the index to 2D coordinates
    min_index_2d = np.unravel_index(min_index, fgz.shape)
    min_coord = (int(np.round(fgx[min_index_2d])),
                 int(np.round(fgy[min_index_2d])))

    # For plotting purposes
    coarse_grid_xyz = (cgx, cgy, cgz)
    fine_grid_xyz = (fgx, fgy, fgz)
    refined_data = coarse_grid_xyz, fine_grid_xyz

    logging.info(f'estimated offset: {min_coord}')
    return min_coord, refined_data



def plot_refined_grid(
        interp_data: tuple[GridXY, GridXY],
        path_plot: Optional[str],
        show_plot=False
):

    # Plot the filled contour plot
    (x, y, z), (gx, gy, gz) = interp_data

    plt.contourf(gx, gy, gz, cmap='viridis')
    plt.colorbar(label='Inaccuracy [fct. of SSIM]')
    plt.scatter(x, y, c=z, cmap='viridis', edgecolors='k', linewidth=0.5)
    plt.xlabel('Coarse offset X [pix]')
    plt.ylabel('Coarse offset Y [pix]')
    plt.title('Seam inaccuracy in coarse offset space')

    if show_plot:
        plt.show()

    if path_plot is not None:
        if Path(path_plot).parent.exists():
            plt.savefig(path_plot)

    plt.close()
    return


def crop_nan(img: np.ndarray[float]) -> np.ndarray:
    """Remove all columns in the input image that contain nan values"""
    nans = np.argwhere(np.isnan(img))
    nan_col_indices = set(nans[:, 1])
    mask = np.ones(img.shape[1], dtype=bool)
    mask[list(nan_col_indices)] = False

    # Crop out columns based on the mask
    cropped_arr = img[:, mask]
    return cropped_arr


def get_neighbour_pairs(tid_map: np.ndarray) -> list[tuple[int, int]]:
    """
    Generates pairs of neighboring elements in a 2D numpy array
     where each element is not equal to -1.

    Usually used to get tile-neighbors from tile_id_map.
    Args:
        tid_map (np.ndarray): A 2D numpy array.

    Returns:
        list: A list of tuples containing pairs of neighboring elements.
    """
    pairs = []
    for i in range(tid_map.shape[0]):
        for j in range(tid_map.shape[1]):
            if tid_map[i, j] != -1:
                if i + 1 < tid_map.shape[0] and tid_map[i + 1, j] != -1:
                    pairs.append((tid_map[i, j], tid_map[i + 1, j]))
                if j + 1 < tid_map.shape[1] and tid_map[i, j + 1] != -1:
                    pairs.append((tid_map[i, j], tid_map[i, j + 1]))
    return pairs


def validate_section_numbers(start: int, end: int, sec_nums: Sequence[int]) -> list[int]:
    requested_set = set(sec_nums)
    if not requested_set:  # empty input
        return []

    available = range(start, end + 1)
    available_set = set(available)
    if requested_set.issubset(available_set):
        return sorted(requested_set)

    valid_nums = [n for n in requested_set if start <= n <= end]
    if not valid_nums:
        raise ValueError(
            f"None of the requested sections {sorted(requested_set)} exist "
            f"in range [{start} – {end}]"
        )

    discarded = requested_set - set(valid_nums)
    if discarded:
        logging.warning(
            f"Ignored {len(discarded)} non-existing section(s): {sorted(discarded)}"
        )

    return sorted(valid_nums)


def list_stitched(dir_stitched: str) -> list[str]:
    """Returns sorted list of full paths to all *.zarr files in the input folder."""
    pattern = os.path.join(dir_stitched, "*.zarr")
    return sorted(glob(pattern))


def find_outliers(
        vector_trace: Dict[int, float],
        n_before: int = 10,
        n_after: int = 10,
        n_sigmas: float = 5.,
) -> list[int]:

    min_win_len = 10
    max_win_len = min_win_len + 20

    data = np.array(list(vector_trace.values()))
    sec_nums = list(vector_trace.keys())

    # Calculate preliminary rolling mean and standard deviation
    preliminary_rm, preliminary_rs = rolling_mean_std_refactored(
        data, n_before, n_after, min_win_len, max_win_len, n_sigmas
    )

    # Mask outliers based on the preliminary rolling mean and std
    outlier_mask = np.abs(data - preliminary_rm) > n_sigmas * preliminary_rs
    cleaned_data = np.ma.masked_array(data, mask=outlier_mask)

    # Compute rolling mean and std on cleaned data
    rm, rs = rolling_mean_std_refactored(
        cleaned_data, n_before, n_after, min_win_len, max_win_len, n_sigmas
    )

    # Check for NaNs in rm and rs
    if np.isnan(rm).all() or np.isnan(rs).all():
        print("Warning: Mean or standard deviation contains NaN values.")
        return []  # Return an empty list or handle as needed

    # Find the final outlier indices based on the cleaned data
    outlier_indices = np.where(np.abs(data - rm) > n_sigmas * rs)[0]
    return sorted(list(sec_nums[i] for i in outlier_indices))


def find_outliers_new(
        trace: dict[int, float],
        n_before: int,
        n_after: int,
        n_sigmas: float
) -> list[int]:
    """
    Identifies outliers in a trace using a rolling median absolute deviation (MAD).
    Handles missing sections (NaNs) by ignoring them in the window calculation.
    """
    if not trace:
        return []

    # 1. Convert dict to a sorted Series to handle gaps naturally
    s = pd.Series(trace).sort_index()

    # 2. Define the window
    # center=True with (n_before + n_after + 1) captures the neighborhood
    window_size = n_before + n_after + 1

    # 3. Robust Statistics: Rolling Median and MAD
    # We use Median because it is more resistant to outliers than Mean
    rolling_median = s.rolling(window=window_size, center=True, min_periods=1).median()

    # Calculate Deviation from Median
    dev = (s - rolling_median).abs()

    # Calculate Rolling MAD (Median Absolute Deviation)
    rolling_mad = dev.rolling(window=window_size, center=True, min_periods=1).median()

    # 4. Outlier Criteria
    # Using 1.4826 converts MAD to a scale consistent with Standard Deviation
    # We add a small epsilon (1e-6) to prevent division by zero in flat regions
    is_outlier = dev > (n_sigmas * (rolling_mad * 1.4826 + 1e-6))

    # Return section numbers where is_outlier is True
    outlier_sections = s.index[is_outlier].tolist()

    return outlier_sections


def rolling_mean_std_refactored(
    data: np.ndarray,
    n_before: int,
    n_after: int,
    min_win_length: int,
    max_win_length: int,
    n_sigmas: float = 4.0,          # new parameter - typically 3.0–5.0
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute rolling mean and standard deviation using an asymmetric window.

    For each position i:
    - Looks at up to n_before points before and n_after points after i
    - Excludes the value at i itself initially
    - Expands symmetrically if too few valid points
    - NEW: If the current value is outside [mean ± n_sigmas × std] of its neighbors,
      it is treated as an outlier and **excluded from all future windows**
      (i.e. masked for positions > i)

    Parameters
    ----------
    data : np.ndarray
        Input 1D array
    n_before : int
        Desired points before current index
    n_after : int
        Desired points after current index
    min_win_length : int
        Minimum number of valid points needed to compute stats
    max_win_length : int
        Maximum total points allowed in window (excluding center)
    n_sigmas : float, default 4.0
        Outlier threshold multiplier (e.g. 4.0 → outside ±4 sigma)

    Returns
    -------
    mean_out, std_out : tuple of np.ndarray
        Rolling mean and std (NaN where not enough valid points or input is inf)
    """
    data = np.asarray(data, dtype=float)
    n = len(data)

    if n == 0:
        return np.array([]), np.array([])

    mean_out = np.full(n, np.nan)
    std_out  = np.full(n, np.nan)

    # Global mask: which points are still considered valid for future windows
    # Initially all finite values are valid
    is_valid = np.isfinite(data).copy()

    for i in range(n):
        if not is_valid[i]:
            continue

        # ───── Initial window ─────
        left  = max(0, i - n_before)
        right = min(n, i + n_after + 1)

        # Only use currently valid points
        masked = np.ma.masked_where(~is_valid[left:right], data[left:right])

        # Exclude current point (even if valid)
        center_idx = i - left
        if 0 <= center_idx < len(masked):
            masked[center_idx] = np.ma.masked

        valid_count = masked.count()

        # ───── Expand symmetrically if needed ─────
        expand_l = n_before
        expand_r = n_after

        while valid_count < min_win_length:
            if (expand_l + expand_r + 1) >= max_win_length:
                break

            expand_l += 1
            expand_r += 0

            left  = max(0, i - expand_l)
            right = min(n, i + expand_r + 1)

            masked = np.ma.masked_where(~is_valid[left:right], data[left:right])

            center_idx = i - left
            if 0 <= center_idx < len(masked):
                masked[center_idx] = np.ma.masked

            valid_count = masked.count()

            if left == 0 and right == n:
                break

        # ───── Compute preliminary statistics ─────
        if valid_count < min_win_length:
            continue

        prelim_mean = masked.mean()
        prelim_std  = masked.std(ddof=0)   # or ddof=1

        mean_out[i] = prelim_mean
        std_out[i]  = prelim_std

        # ───── Outlier check ─────
        if n_sigmas > 0 and prelim_std > 0:
            deviation = abs(data[i] - prelim_mean)
            if deviation > n_sigmas * prelim_std:
                # Mark current point as invalid for all **future** windows
                is_valid[i] = False

    return mean_out, std_out


def load_outliers(path_outliers: UniPath) -> Dict[int, list[tuple[int, int]]]:
    """
    Load outliers data from a text file.

    :param path_outliers: Path to the file containing outliers data
    :return: A dictionary where keys are slice numbers and values are
    lists of tuples, each containing two integers (TileID, TileID_nn).
    """
    path = Path(path_outliers)

    if not path.is_file():
        logging.warning(f"Outliers file not found: {path}")
        return {}

    outliers_data = {}
    try:
        with open(path, 'r') as f:
            # Skip header
            header = next(f, None)
            if header is None:
                raise ValueError("File is empty")

            # Read data line by line
            for line in f:
                parts = line.strip().split('\t')
                slice_num = int(parts[0])
                tile_id = int(parts[-2])
                tile_id_nn = int(parts[-1])

                # Check if the key already exists in the dictionary
                if slice_num in outliers_data:
                    # If the key exists, append the new outlier data to the existing list
                    outliers_data[slice_num].append((tile_id, tile_id_nn))
                else:
                    # If the key does not exist, create a new list with the outlier data
                    outliers_data[slice_num] = [(tile_id, tile_id_nn)]

    except Exception as e:
        logging.error(f"Failed to read outliers file {path}: {e}")
        raise

    # Check if outliers_data is empty
    if not outliers_data:
        raise ValueError(f"No valid outlier entries found in file: {path}")

    return outliers_data


def process_single_section(path_to_check: Path, sec_num_str: str):
    """Worker function to read and process a single JSON file."""
    try:
        if not path_to_check.exists():
            return sec_num_str, None, f"s{sec_num_str}\n"

        # Assume read_coarse_mat is your custom JSON reader
        coarse_data = read_coarse_mat(path_to_check)
        cx, cy = coarse_data.cx, coarse_data.cy

        # Efficiently handle dimensionality reduction
        # Using slice(0, 1) or indexing to avoid multiple ndim checks if consistent
        while cx.ndim > 2:
            cx = cx[:, 0, ...]
            cy = cy[:, 0, ...]

        cxy = np.asarray((cx, cy), dtype=np.float32)  # float32 saves 50% space vs float64
        return sec_num_str, cxy, None
    except Exception as e:
        logging.error(f"Error processing section {sec_num_str}: {e}")
        return sec_num_str, None, f"s{sec_num_str} (error)\n"


def parse_section_range(input_str: str) -> list[int]:
    """
    Parses strings like '1000:1005, 1010, 1020-1022' into [1000, 1001, 1002, 1003, 1004, 1005, 1010, 1020, 1021, 1022].
    """
    if not input_str or not str(input_str).strip():
        return []

    sections = set()
    parts = re.split(r'[,\s]+', str(input_str).strip())

    for part in parts:
        if not part: continue

        # Handle ranges indicated by : or -
        if ':' in part or '-' in part:
            try:
                start_str, end_str = re.split(r'[:-]', part)
                start, end = int(start_str), int(end_str)
                sections.update(range(start, end + 1))
            except ValueError:
                logging.warning(f"Could not parse range part: {part}")
        else:
            try:
                sections.add(int(part))
            except ValueError:
                logging.warning(f"Could not parse single section part: {part}")

    return sorted(list(sections))


# Convert dict → hashable tuple before calling
def make_hashable_params(params: dict | None) -> tuple[tuple[str, any], ...] | None:
    return tuple(sorted(params.items())) if params else None



if __name__ == "__main__":
    pass