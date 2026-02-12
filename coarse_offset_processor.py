from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Optional, Sequence, Any

import matplotlib.pyplot as plt
import numpy as np

import inspection_utils_refactor as utils
import experiment_configs as cfg

Vector = tuple[float, float] | tuple[Any, ...]
import numpy.typing as npt

# logging.basicConfig(level=logging.DEBUG)

@dataclass
class CoarseOffsetTrace:
    tile_id: str
    shift_vectors: npt.NDArray[np.float64]
    section_numbers: list[int] = field(default_factory=list)


class CoarseOffsetProcessor:
    def __init__(self, config: cfg.ExpConfig):
        self.config = config
        self.root = Path(config.path)
        self.cxyz_obj: Optional[Any] = None
        self.tile_id_maps_obj: Optional[Any] = None
        self.dir_inspect = self.root / '_inspect'
        self.path_cxyz = Path(self.dir_inspect / 'all_offsets.npz')
        self.path_id_maps = Path(self.dir_inspect / 'all_tile_id_maps.npz')
        self.path_co_outliers = Path(self.dir_inspect / f"coarse_offset_outliers.txt")
        self.co_outliers: dict = {}
        self.co_traces: dict[str, Optional[CoarseOffsetTrace]]
        self._coord_cache = {}  # {sec_key: {tile_id: (y, x)}}
        self._all_unique_ids = None


    def load_all_offsets_and_tile_id_maps_from_npz(self):
        if not self.path_cxyz.exists():
            raise FileNotFoundError(f"Missing cxyz file: {self.path_cxyz}")
        if not self.path_id_maps.exists():
            raise FileNotFoundError(f"Missing tile id maps: {self.path_id_maps}")

        self.cxyz_obj = np.load(self.path_cxyz, allow_pickle=False)
        self.tile_id_maps_obj = np.load(self.path_id_maps, allow_pickle=False)

    def process_tile_id(
            self,
            tile_id: int,
            n_before: int,
            n_after: int,
            n_sigmas: float
    ):

        mapped_outliers = {}
        for axis in range(2):
            trace_dict = self.get_trace(tile_id, axis)
            logging.debug(f"trace_dict len: {len(trace_dict)}")
            if trace_dict is None:
                continue

            for vec_component in range(2):
                trace = {sec_num: v[0][vec_component] for sec_num, v in trace_dict.items()}
                out_sec_nums = utils.find_outliers(trace, n_before, n_after, n_sigmas)
                logging.info(
                    f"Nr. of detected outliers (tile {tile_id}, axis={axis}, "
                    f"comp={vec_component}): {len(out_sec_nums)}"
                )

                for num in sorted(out_sec_nums):
                    y, x = trace_dict[num][1]
                    tid_map = self.tile_id_maps_obj[str(num)]
                    tid_a = int(tid_map[y][x])
                    tid_b = utils.get_vert_tile_id(tid_map, tid_a) if axis == 1 else int(tid_map[y][x + 1])
                    mapped_outliers[num] = (axis, vec_component, y, x, tid_a, tid_b)

        self.co_outliers.update(mapped_outliers)
        return


    def store_outliers(self) -> None:
        # Get filename
        fn_out = self.path_co_outliers
        logging.info(f"Storing outliers to: {fn_out}")
        fmt_outs = [np.array((k,) + v) for k, v in self.co_outliers.items()]

        file_exists = fn_out.exists()
        with open(fn_out, 'a') as f:
            if not file_exists:
                f.write('# Slice\tC\tZ\tY\tX\tTileID\tTileID_nn\n')
            np.savetxt(f, fmt_outs, fmt='%s', delimiter='\t')
        return

    def process_all_tile_ids(self, n_before, n_after, n_sigmas):
        unique_tile_ids = self.get_unique_tile_ids()
        for tile_id in unique_tile_ids:
            self.process_tile_id(tile_id, n_before, n_after, n_sigmas)

    def get_largest_tile_id_map(self) -> np.ndarray:
        """
        Computes tile-id map with the largest extent in all tile-grid directions.
        Uses cached unique IDs to avoid redundant disk or memory scans.
        """
        # 1. Get IDs from cache (O(1) if already called, or O(N) once)
        unique_ids = self.get_unique_tile_ids()

        if not unique_ids:
            logging.warning("No unique tile IDs found. Returning empty grid.")
            # Return an empty grid of the configured shape if no data exists
            return np.zeros(self.config.grid_shape, dtype=int)

        # 2. Sort for deterministic map generation
        sorted_ids = sorted(unique_ids)

        # 3. Delegate to utility
        # We assume utils.compute_tile_id_map handles the spatial placement
        return utils.compute_tile_id_map(
            self.config.grid_shape,
            sorted_ids
        )

    def _build_index_for_section(self, sec_key: str):
        """Indexes a section map and updates the global unique ID set."""
        tile_map = self.tile_id_maps_obj[sec_key]
        y_idxs, x_idxs = np.where(tile_map > 0)

        # Build local section map
        section_lookup = {
            int(tile_map[y, x]): (int(y), int(x))
            for y, x in zip(y_idxs, x_idxs)
        }

        self._coord_cache[sec_key] = section_lookup
        return section_lookup

    def get_unique_tile_ids(self) -> set[int]:
        """Returns a set of all tile IDs present across all sections."""
        if self._all_unique_ids is None:
            unique_ids = set()
            for sec_key in self.tile_id_maps_obj.keys():
                lookup = self._get_section_lookup(sec_key)
                unique_ids.update(lookup.keys())
            self._all_unique_ids = unique_ids
        return self._all_unique_ids

    def _get_section_lookup(self, sec_key: str) -> dict[int, tuple[int, int]]:
        """Helper to get or build the coordinate cache for a section."""
        if sec_key not in self._coord_cache:
            return self._build_index_for_section(sec_key)
        return self._coord_cache[sec_key]

    def get_trace(self, tile_id: int, axis: int) -> Optional[dict[int, tuple[tuple, tuple[int, int]]]]:
        """
        Retrieves shift vectors for a specific axis across all sections where the tile exists.
        Leverages the coordinate cache to avoid expensive array searches.
        """
        trace_dict = {}
        if tile_id not in self.get_unique_tile_ids():
            return None

        for sec_key in self.tile_id_maps_obj.keys():
            lookup = self._get_section_lookup(sec_key)
            coord = lookup.get(tile_id)
            if coord is None:
                continue
            try:
                y, x = coord
                vec = self.cxyz_obj[sec_key][axis, :, y, x]
                trace_dict[int(sec_key)] = (tuple(vec), (y, x))

            except (IndexError, KeyError) as e:
                logging.warning(f"Failed to extract axis {axis} for s{sec_key} t{tile_id}: {e}")
                continue

        return trace_dict if trace_dict else None

    def get_full_trace(self, tile_id: str) -> Optional[CoarseOffsetTrace]:
        if not (self.cxyz_obj and self.tile_id_maps_obj):
            logging.error("Data objects not initialized.")
            return None

        sec_keys = sorted(self.tile_id_maps_obj.keys(), key=int)
        sec_nums_all = [int(k) for k in sec_keys]
        t_id_int = int(tile_id)

        # Create a continuous range of section numbers for the X-axis
        first, last = sec_nums_all[0], sec_nums_all[-1]
        full_range_x = list(range(first, last + 1))

        num_sections = len(full_range_x)
        traces = np.full((4, num_sections), np.nan)

        trace_obj = CoarseOffsetTrace(
            tile_id=tile_id,
            section_numbers=full_range_x,  # Full range ensures X aligns with array
            shift_vectors=traces,
        )

        if t_id_int not in self.get_unique_tile_ids():
            return trace_obj

        for str_num in sec_keys:
            lookup = self._get_section_lookup(str_num)
            coord = lookup.get(t_id_int)
            if coord:
                y, x = coord
                # Calculate the correct index relative to 'first'
                idx = int(str_num) - first
                try:
                    traces[:, idx] = self.cxyz_obj[str_num][:, :, y, x].ravel()
                except (IndexError, ValueError) as e:
                    logging.warning(f"Failed extraction at s{str_num} t{tile_id}: {e}")

        return trace_obj

    def _get_cached_coord(self, sec_key: str, tile_id: int) -> Optional[tuple[int, int]]:
        """
        Private helper to manage a coordinate lookup cache.
        Reduces complexity from O(N) array scans to O(1) hash lookups.
        """
        # Initialize cache on the instance if it doesn't exist
        if not hasattr(self, "_coord_cache"):
            self._coord_cache = {}

        # Build the dictionary for this section if not already cached
        if sec_key not in self._coord_cache:
            tile_map = self.tile_id_maps_obj[sec_key]

            # Find indices of all non-background tiles in one pass
            y_idxs, x_idxs = np.where(tile_map > 0)

            # Map {tile_id: (y, x)}
            self._coord_cache[sec_key] = {
                int(tile_map[y, x]): (int(y), int(x))
                for y, x in zip(y_idxs, x_idxs)
            }

        return self._coord_cache[sec_key].get(tile_id)

def tst_get_largest_tile_id_map():
    # Get actual config
    configs = cfg.get_experiment_configurations()
    exp_config = configs[cfg.ExperimentName.ROLI_F1]

    # Initialize CoarseOffsetProcessor and read coarse offsets
    co_processor = CoarseOffsetProcessor(exp_config)
    co_processor.load_all_offsets_and_tile_id_maps_from_npz()

    # Test fn
    largest = co_processor.get_largest_tile_id_map()

    assert isinstance(largest, np.ndarray)
    print('\n')
    print(f"{largest}\n")
    print(f"shape: {np.shape(largest)}")

    return


def tst_get_full_trace():
    # Get actual config
    configs = cfg.get_experiment_configurations()
    exp_config = configs[cfg.ExperimentName.ROLI_F1]

    # Initialize CoarseOffsetProcessor and read coarse offsets
    co_processor = CoarseOffsetProcessor(exp_config)
    co_processor.load_all_offsets_and_tile_id_maps_from_npz()

    tile_id = 413
    trace = co_processor.get_full_trace(str(tile_id))

    x = trace.section_numbers
    y = trace.shift_vectors[0][:]

    plt.plot(x, y, '-')
    plt.show()
    return

def tst_unique():
    # Get actual config
    configs = cfg.get_experiment_configurations()
    exp_config = configs[cfg.ExperimentName.ROLI_F1]

    # Initialize CoarseOffsetProcessor and read coarse offsets
    co_processor = CoarseOffsetProcessor(exp_config)
    co_processor.load_all_offsets_and_tile_id_maps_from_npz()

    co_processor.get_unique_tile_ids()
    unique = sorted(co_processor._all_unique_ids)

    tile_id = 489
    trace = co_processor.get_full_trace(str(tile_id))
    print(trace)
    return


def tst_cxyz():
    # Get actual config
    configs = cfg.get_experiment_configurations()
    exp_config = configs[cfg.ExperimentName.ROLI_F1]

    # Initialize CoarseOffsetProcessor and read coarse offsets
    co_processor = CoarseOffsetProcessor(exp_config)
    co_processor.load_all_offsets_and_tile_id_maps_from_npz()

    cxyz = co_processor.cxyz_obj
    print(np.shape(cxyz)[0])
    trace = co_processor.get_full_trace(tile_id='386')
    print('done')
    return

if __name__ == "__main__":
    # test_get_largest_tile_id_map()
    # tst_get_full_trace()
    # tst_unique()
    tst_cxyz()