from dataclasses import dataclass, field
import logging
from typing import Optional, Any, Dict, Tuple
import matplotlib.pyplot as plt
import numpy as np
import numpy.typing as npt

import inspection_utils_refactor as utils
import experiment_configs as cfg

TileXY = tuple[int, int]

# logging.basicConfig(level=logging.DEBUG)

@dataclass
class CoarseOffsetTrace:
    tile_id: str
    shift_vectors: npt.NDArray[np.float64]
    section_numbers: list[int] = field(default_factory=list)

@dataclass(slots=True)  # Minimizes memory overhead for 10k+ instances
class SectionIndex:
    """Represents a spatial index for a single EM section."""
    section_id: str
    tile_to_coords: Dict[int, TileXY] = field(default_factory=dict)

    def __contains__(self, tile_id: int) -> bool:
        """Allows usage: if tile_id in section_index_obj"""
        return tile_id in self.tile_to_coords

    def __getitem__(self, tile_id: int) -> TileXY:
        """Allows usage: y, x = lookup[tile_id]"""
        return self.tile_to_coords[tile_id]

    def get_coords(self, tile_id: int) -> Optional[TileXY]:
        """Safely retrieves (y, x) coordinates for a given tile."""
        return self.tile_to_coords.get(tile_id)


    @property
    def unique_ids(self) -> set[int]:
        """Returns all tile IDs present in this section."""
        return set(self.tile_to_coords.keys())

class CoarseOffsetProcessor:
    def __init__(self, config: cfg.ExpConfig, paths: dict):
        self.config = config
        self.dir_inspect = paths['inspect']
        self.path_cxyz = paths['cxyz']
        self.path_id_maps = paths['tid_maps']
        self.path_co_outliers = paths['co_outliers']

        # Data containers
        self.cxyz_obj = None
        self.tile_id_maps_obj = None
        self.co_outliers = {}
        self.co_traces: dict[str, Optional[CoarseOffsetTrace]]
        self._coord_cache: Dict[str, SectionIndex] = {}
        self._all_unique_ids: Optional[set[int]] = None

    def get_section_lookup(self, sec_key: str):
        """Public accessor for the section lookup table."""
        return self._get_section_lookup(sec_key)

    def update_shift_vec(
            self,
            z: int | str,
            axis: int,
            y: int,
            x: int,
            shift_vec: npt.NDArray[np.float64] | Tuple[int, int]
    ) -> None:
        z_key = str(z)
        new_vec = np.asarray(shift_vec).astype(np.float64)
        self.cxyz_obj[z_key][axis, :, y, x] = new_vec
        return None

    def get_shift_vec(self, z: int | str, axis: int, y: int, x: int) -> npt.NDArray[np.float64]:
        """Returns [dx, dy] for a specific section, axis (H/V), and grid coord."""
        z_key = str(z)  # Or f"{int(z):04d}" if your files use padding
        return self.cxyz_obj[z_key][axis, :, y, x]

    def get_full_vector_stack(self, z: int | str, y: int, x: int) -> npt.NDArray[np.float64]:
        """Returns all 4 components (H_dx, H_dy, V_dx, V_dy) for a grid coord."""
        z_key = str(z)
        return self.cxyz_obj[z_key][:, :, y, x].ravel()

    def load_all_offsets_and_tile_id_maps_from_npz(self):
        """Standardized loading method. Loads data into mutable memory."""
        if not self.path_cxyz.exists() or not self.path_id_maps.exists():
            raise FileNotFoundError("Offset or ID map files missing in _inspect folder.")

        # Load NpzFile objects
        with np.load(self.path_cxyz, allow_pickle=False) as data:
            self.cxyz_obj = {key: data[key].copy() for key in data.files}

        with np.load(self.path_id_maps, allow_pickle=False) as data:
            self.tile_id_maps_obj = {key: data[key].copy() for key in data.files}

        logging.info("CoarseOffsetProcessor: Data loaded into mutable memory.")


    def save_offsets_to_disk(self):
        """Persists in-memory modifications back to the .npz file."""
        if self.cxyz_obj is not None:
            np.savez(self.path_cxyz, **self.cxyz_obj)
            logging.info(f"Saved updated offsets to {self.path_cxyz}")


    def process_tile_id_outliers(
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
        if not self.co_outliers:
            logging.info("No outliers to store.")
            return

        fn_out = self.path_co_outliers
        fmt_outs = [np.array((k,) + v) for k, v in self.co_outliers.items()]

        file_exists = fn_out.exists()
        with open(fn_out, 'a') as f:
            if not file_exists:
                f.write('# Slice\tAxis\tComp\tY\tX\tTileA\tTileB\n')
            np.savetxt(str(f), fmt_outs, fmt='%s', delimiter='\t')


    def process_all_tile_ids_outliers(self, n_before, n_after, n_sigmas):
        unique_tile_ids = self.get_unique_tile_ids()
        for tile_id in unique_tile_ids:
            self.process_tile_id_outliers(tile_id, n_before, n_after, n_sigmas)


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


    def get_unique_tile_ids(self) -> set[int]:
        """Returns a set of all tile IDs present across all sections."""
        if self._all_unique_ids is None:
            unique_ids = set()
            for sec_key in self.tile_id_maps_obj.keys():
                index = self._get_section_lookup(sec_key)
                unique_ids.update(index.unique_ids)
            self._all_unique_ids = unique_ids
        return self._all_unique_ids


    def _get_section_lookup(self, sec_key: str) -> SectionIndex:
        """Memoized lookup: translates TileID -> (y, x) using slotted objects."""
        if sec_key not in self._coord_cache:
            tile_map = self.tile_id_maps_obj[sec_key]

            # Vectorized finding of active tiles
            y_idxs, x_idxs = np.where(tile_map > 0)

            mapping = {
                int(tile_map[y, x]): (int(y), int(x))
                for y, x in zip(y_idxs, x_idxs)
            }

            # Store the lean slotted object
            self._coord_cache[sec_key] = SectionIndex(
                section_id=sec_key,
                tile_to_coords=mapping
            )

        return self._coord_cache[sec_key]


    def get_trace(self, tile_id: int, axis: int) -> Optional[dict[int, tuple[tuple, tuple[int, int]]]]:
        """
        Retrieves shift vectors for a specific axis across all sections where the tile exists.
        Leverages the coordinate cache to avoid expensive array searches.
        """
        trace_dict = {}
        for sec_key in self.tile_id_maps_obj.keys():
            index = self._get_section_lookup(sec_key)
            coord = index.get_coords(tile_id)

            if coord is not None:
                try:
                    y, x = coord
                    vec = self.cxyz_obj[sec_key][axis, :, y, x]
                    trace_dict[int(sec_key)] = (tuple(vec), (y, x))
                except (IndexError, KeyError) as e:
                    logging.warning(f"Axis {axis} s{sec_key} t{tile_id}: {e}")
                    continue

        return trace_dict if trace_dict else None

    # def get_full_trace(self, tile_id: str) -> Optional[CoarseOffsetTrace]:
    #     if not (self.cxyz_obj and self.tile_id_maps_obj):
    #         logging.error("Data objects not initialized.")
    #         return None
    #
    #     sec_keys = sorted(self.tile_id_maps_obj.keys(), key=int)
    #     sec_nums_all = [int(k) for k in sec_keys]
    #     t_id_int = int(tile_id)
    #
    #     # Create a continuous range of section numbers for the X-axis
    #     first, last = sec_nums_all[0], sec_nums_all[-1]
    #     full_range_x = list(range(first, last + 1))
    #
    #     num_sections = len(full_range_x)
    #     traces = np.full((4, num_sections), np.nan)
    #
    #     trace_obj = CoarseOffsetTrace(
    #         tile_id=tile_id,
    #         section_numbers=full_range_x,  # Full range ensures X aligns with array
    #         shift_vectors=traces,
    #     )
    #
    #     if t_id_int not in self.get_unique_tile_ids():
    #         return trace_obj
    #
    #     for str_num in sec_keys:
    #         lookup = self._get_section_lookup(str_num)
    #         coord = lookup.get(t_id_int)
    #         if coord:
    #             y, x = coord
    #             # Calculate the correct index relative to 'first'
    #             idx = int(str_num) - first
    #             try:
    #                 traces[:, idx] = self.cxyz_obj[str_num][:, :, y, x].ravel()
    #             except (IndexError, ValueError) as e:
    #                 logging.warning(f"Failed extraction at s{str_num} t{tile_id}: {e}")
    #
    #     return trace_obj
    #
    # def get_full_trace(self, tile_id: int | str) -> CoarseOffsetTrace:
    #     """Builds a trace across all sections for a given Tile ID."""
    #     t_id_int = int(tile_id)
    #     sec_keys = sorted(self.tile_id_maps_obj.keys(), key=int)
    #
    #     # Establish consistent X-axis range
    #     first, last = int(sec_keys[0]), int(sec_keys[-1])
    #     full_range = list(range(first, last + 1))
    #
    #     # Initialize empty results with NaNs (Shape: 4 components x N sections)
    #     traces = np.full((4, len(full_range)), np.nan)
    #
    #     for z_str in sec_keys:
    #         lookup = self._get_section_lookup(z_str)
    #         if t_id_int in lookup:
    #             y, x = lookup[t_id_int]
    #             idx = int(z_str) - first
    #             traces[:, idx] = self.get_full_vector_stack(z_str, y, x)
    #
    #     return CoarseOffsetTrace(
    #         tile_id=str(tile_id),
    #         shift_vectors=traces,
    #         section_numbers=full_range
    #     )

    def get_full_trace(self, tile_id: str) -> Optional[CoarseOffsetTrace]:
        """
        Extracts the 4-component shift vector trace for a given tile ID.
        Uses the slotted SectionIndex cache for O(1) coordinate lookups.
        """
        if not (self.cxyz_obj and self.tile_id_maps_obj):
            logging.error("Data objects not initialized. Call load_all_offsets first.")
            return None

        # 1. Prepare the global section range
        sec_keys = sorted(self.tile_id_maps_obj.keys(), key=int)
        if not sec_keys:
            return None

        first, last = int(sec_keys[0]), int(sec_keys[-1])
        full_range_x = list(range(first, last + 1))
        num_sections = len(full_range_x)

        # 2. Initialize the empty traces matrix (4 components x Total Sections)
        # Using NaN ensures Plotly shows 'gaps' in the line chart
        traces = np.full((4, num_sections), np.nan)

        t_id_int = int(tile_id)

        # 3. Iterate and Extract
        # We only iterate over sec_keys that actually exist in the .npz
        for str_num in sec_keys:
            index = self._get_section_lookup(str_num)
            coord = index.get_coords(t_id_int)

            if coord:
                y, x = coord
                # Calculate column index in our matrix relative to the first section
                col_idx = int(str_num) - first

                try:
                    # Extract Axis (2) x Component (2) and flatten to 4
                    # Order: [H-dx, H-dy, V-dx, V-dy]
                    traces[:, col_idx] = self.cxyz_obj[str_num][:, :, y, x].ravel()
                except (IndexError, ValueError) as e:
                    logging.warning(f"Data mismatch at section {str_num} for tile {tile_id}: {e}")

        return CoarseOffsetTrace(
            tile_id=tile_id,
            section_numbers=full_range_x,
            shift_vectors=traces
        )


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



if __name__ == "__main__":
    # test_get_largest_tile_id_map()
    tst_get_full_trace()