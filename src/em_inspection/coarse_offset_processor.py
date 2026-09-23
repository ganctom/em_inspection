from dataclasses import dataclass, field, asdict
import logging
import shutil
from pathlib import Path
import tempfile
from typing import Optional, Any, Dict, Tuple, List, Set, cast

import duckdb
import numpy as np
import numpy.typing as npt
import pandas as pd
from tqdm import tqdm

import em_inspection.inspection_utils_refactor as utils
import em_inspection.experiment_configs as cfg
from em_inspection.interactive_inspector.constants import OverlapType

TileXY = tuple[int, int]

# logging.basicConfig(level=logging.DEBUG)

@dataclass
class OffsetComponents:
    h_dx: float = 0.0
    h_dy: float = 0.0
    v_dx: float = 0.0
    v_dy: float = 0.0


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


class CoarseOffsetRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    @staticmethod
    def initialize_schema(con: duckdb.DuckDBPyConnection) -> None:
        """Initializes the standard coarse offsets relational database schema layout."""
        con.execute("""
                CREATE TABLE coarse_offsets (
                    tile_id VARCHAR,
                    section_number INTEGER,
                    h_dx REAL,
                    h_dy REAL,
                    v_dx REAL,
                    v_dy REAL
                );
            """)

    @staticmethod
    def create_index(con: duckdb.DuckDBPyConnection) -> None:
        """Builds down-stream query optimization indices on the active connection."""
        con.execute("CREATE INDEX idx_offsets_tile ON coarse_offsets (tile_id);")

    def bulk_insert_rows_atomic(self, rows: list[tuple], suffix: str = "_duckdb_build") -> None:
        """
        Executes full atomic table compilation inside isolated local scratch space
        before executing a cross-device file system move to protect network volumes.
        """
        with tempfile.TemporaryDirectory(suffix=suffix) as tmpdir:
            local_path = Path(tmpdir) / "all_offsets_compiled.db"

            try:
                logging.info(f"Compiling DuckDB engine locally on scratch space: {local_path}")
                con = duckdb.connect(str(local_path))

                self.initialize_schema(con)

                logging.info(f"Streaming {len(rows)} records to local database container...")
                con.executemany("INSERT INTO coarse_offsets VALUES (?, ?, ?, ?, ?, ?)", rows)

                self.create_index(con)
                con.close()

                logging.info(f"Transferring completed database file to target: {self.db_path}")
                if self.db_path.exists():
                    self.db_path.unlink()

                shutil.move(str(local_path), str(self.db_path))
                logging.info(f"Database built successfully at: {self.db_path}")

            except Exception as e:
                logging.error(f"Local database transaction compilation failed: {e}")
                raise

    def fetch_unique_sections(self) -> list[int]:
        """Queries the analytical engine for an ordered sequence of unique section keys."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database missing at target path: {self.db_path}")

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            res = con.execute("""
                SELECT DISTINCT section_number 
                FROM coarse_offsets 
                WHERE section_number IS NOT NULL 
                ORDER BY section_number ASC;
            """).fetchall()
            return [int(row[0]) for row in res]


    def fetch_offset(self, sec_num: int, tile_id: str) -> OffsetComponents | None:
        """Retrieves complete 4-component vector records for a physical tile coordinate."""
        if not self.db_path.exists():
            return None

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            res = con.execute("""
                SELECT h_dx, h_dy, v_dx, v_dy FROM coarse_offsets 
                WHERE section_number = ? AND tile_id = ?
            """, [sec_num, tile_id]).fetchone()

            if not res:
                return None
            return OffsetComponents(
                h_dx=float(res[0]) if res[0] is not None else 0.0,
                h_dy=float(res[1]) if res[1] is not None else 0.0,
                v_dx=float(res[2]) if res[2] is not None else 0.0,
                v_dy=float(res[3]) if res[3] is not None else 0.0
            )


    def fetch_inf_errors(self) -> list[tuple[str, int, bool, bool]]:
        """Scans database files using vectorized SQL constraints to locate infinite limits."""
        if not self.db_path.exists():
            return []

        query = """
            SELECT tile_id, section_number, 
                   isinf(h_dx) OR isinf(h_dy) AS h_inf,
                   isinf(v_dx) OR isinf(v_dy) AS v_inf
            FROM coarse_offsets
            WHERE isinf(h_dx) OR isinf(h_dy) OR isinf(v_dx) OR isinf(v_dy);
        """
        with duckdb.connect(str(self.db_path), read_only=True) as con:
            res = con.execute(query).fetchall()
        return cast(list[tuple[str, int, bool, bool]], res)


    def fetch_trace_dataframe(self, tile_id: str, first_sec: int, last_sec: int) -> pd.DataFrame:
        """Streams sequential query records directly into a native memory Pandas structure."""
        if not self.db_path.exists():
            return pd.DataFrame()

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            return con.execute("""
                SELECT section_number, h_dx, h_dy, v_dx, v_dy 
                FROM coarse_offsets 
                WHERE tile_id = ? 
                  AND section_number BETWEEN ? AND ?
                ORDER BY section_number
            """, [str(tile_id), first_sec, last_sec]).df()


    def fetch_axis_records(
            self,
            tile_id: str,
            axis: int,
            first_sec: int,
            last_sec: int
    ) -> dict[int, tuple[float, float]]:
        """Pulls targeted coordinate rows restricted down to a clean relational sub-axis lookup."""
        if not self.db_path.exists():
            return {}

        x_col, y_col = ("h_dx", "h_dy") if axis == 0 else ("v_dx", "v_dy")

        query = f"""
            SELECT section_number, {x_col}, {y_col} 
            FROM coarse_offsets 
            WHERE tile_id = ? 
              AND section_number BETWEEN ? AND ?
            ORDER BY section_number ASC;
        """

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            raw_rows = con.execute(query, [tile_id, first_sec, last_sec]).fetchall()

        records: dict[int, tuple[float, float]] = {}

        for row in raw_rows:
            raw_sec, raw_dx, raw_dy = row
            # Explicit validation filtering out any database NULL values
            if raw_dx is None or raw_dy is None:
                continue

            # Clear type coercion and assignment
            section_number = int(raw_sec)
            offset_vector = (float(raw_dx), float(raw_dy))
            records[section_number] = offset_vector

        return records


    def save_offset_batch_atomic(self, batch: dict[tuple[int, str], OffsetComponents]) -> None:
        """Executes full atomic block updates inside isolated scratch disks to eliminate network locks."""
        with tempfile.TemporaryDirectory(suffix="_duckdb_patch") as tmpdir:
            local_db_path = Path(tmpdir) / "all_offsets_patched.db"

            if self.db_path.exists():
                shutil.copy(str(self.db_path), str(local_db_path))
            else:
                with duckdb.connect(str(local_db_path)) as con:
                    con.execute("""
                        CREATE TABLE coarse_offsets (
                            tile_id VARCHAR, section_number INTEGER,
                            h_dx REAL, h_dy REAL, v_dx REAL, v_dy REAL
                        );
                        CREATE INDEX idx_offsets_tile ON coarse_offsets (tile_id);
                    """)

            with duckdb.connect(str(local_db_path)) as con:
                for (sec_num, tile_id), components in batch.items():
                    exists = con.execute(
                        "SELECT 1 FROM coarse_offsets WHERE section_number = ? AND tile_id = ?",
                        [int(sec_num), str(tile_id)]
                    ).fetchone()

                    if exists:
                        con.execute("""
                            UPDATE coarse_offsets 
                            SET h_dx = ?, h_dy = ?, v_dx = ?, v_dy = ?
                            WHERE section_number = ? AND tile_id = ?
                        """, [
                            components.h_dx, components.h_dy,
                            components.v_dx, components.v_dy,
                            int(sec_num), str(tile_id)
                        ])
                    else:
                        con.execute("INSERT INTO coarse_offsets VALUES (?, ?, ?, ?, ?, ?)", [
                            str(tile_id), int(sec_num),
                            components.h_dx, components.h_dy,
                            components.v_dx, components.v_dy
                        ])

            if self.db_path.exists():
                self.db_path.unlink()
            shutil.move(str(local_db_path), str(self.db_path))


    def fetch_section_tile_ids(self, sec_num: int) -> list[tuple]:
        """Fetches all distinct tile IDs for a specified section number."""
        if not self.db_path.exists():
            return []
        with duckdb.connect(str(self.db_path), read_only=True) as con:
            return con.execute("""
                SELECT DISTINCT tile_id 
                FROM coarse_offsets 
                WHERE section_number = ? AND tile_id IS NOT NULL;
            """, [sec_num]).fetchall()


    def fetch_shift_vector_component(
            self,
            sec_num: int,
            tile_id: str,
            axis: int
    ) -> tuple[float, float] | None:
        """Retrieves only the [dx, dy] components for a specified axis (0=H, 1=V)."""
        if not self.db_path.exists():
            return None
        cols = "h_dx, h_dy" if axis == 0 else "v_dx, v_dy"
        with duckdb.connect(str(self.db_path), read_only=True) as con:
            res = con.execute(f"""
                SELECT {cols} FROM coarse_offsets 
                WHERE section_number = ? AND tile_id = ?
            """, [sec_num, tile_id]).fetchone()
            if res and res[0] is not None and res[1] is not None:
                return float(res[0]), float(res[1])
            return None


    def fetch_all_unique_tile_ids(self) -> list[tuple]:
        """Queries the analytical database for all distinct tile IDs."""
        if not self.db_path.exists():
            return []

        with duckdb.connect(str(self.db_path), read_only=True) as con:
            return con.execute(
                "SELECT DISTINCT tile_id FROM coarse_offsets WHERE tile_id IS NOT NULL;"
            ).fetchall()


class CoarseOffsetProcessor:
    def __init__(self, config: cfg.ExpConfig, paths: dict):
        self.config = config
        self.dir_inspect = paths['inspect']
        self.path_co_outliers = paths['co_outliers']

        # Data containers
        self.db_path = Path(paths['inspect']) / "all_offsets.db"
        self.cxyz_obj = None
        self.tile_id_maps_obj = None
        self.co_outliers = {}
        self.co_traces: dict[str, Optional[CoarseOffsetTrace]] = {}
        self._coord_cache: Dict[str, SectionIndex | None] = {}
        self._all_unique_ids: Optional[set[int]] = None
        self._inf_registry: Dict[str, List[Dict[str, Any]]] = {}
        self.section_sequence: List[int] = []
        self.repo = CoarseOffsetRepository(self.db_path)
        self.modified_offset_entries: dict[tuple[int, str], OffsetComponents] = {}


    def save_temp_offsets(self) -> None:
        """
        Applies only the session modifications down to the master DuckDB file
        atomically via local scratch directories. Clears dirty state on success.
        """
        if not self.modified_offset_entries:
            logging.info("Save execution skipped: Staging cache is clean.")
            return

        try:
            logging.info(f"Flushing {len(self.modified_offset_entries)} edited vectors to local block engine...")
            self.repo.save_offset_batch_atomic(self.modified_offset_entries)

            # Reset transaction tracking state completely upon successful flush
            self.modified_offset_entries.clear()
            logging.info("Master DuckDB analytical store updated successfully.")
        except Exception as e:
            logging.error(f"Failed to persist staged memory offsets to disk: {e}")
            raise e


    def _resolve_coordinate_to_tile(self, z: int | str, y: int, x: int) -> tuple[int, str, str | None]:
        """
        Extracts unified metadata and resolves spatial layout matrix coordinates to a unique Tile ID.

        Returns:
            tuple: (sec_num, z_key, tile_id) where tile_id is None if resolution fails.
        """
        z_key = str(int(z))
        sec_num = int(z_key)

        lookup = self._get_section_lookup(z_key)
        if lookup is None:
            return sec_num, z_key, None

        tile_id = None
        for tid, coords in lookup.tile_to_coords.items():
            if coords == (y, x):
                tile_id = str(tid)
                break

        return sec_num, z_key, tile_id


    def update_shift_vec(
            self,
            z: int | str,
            axis: int,
            y: int,
            x: int,
            shift_vec: npt.NDArray[np.float64] | tuple[int, int]
    ) -> None:
        """Stages parameter deviations cleanly to the processing transactional node."""
        sec_num, z_key, tile_id = self._resolve_coordinate_to_tile(z, y, x)
        if tile_id is None:
            logging.error(f"update_shift_vec: Position ({y}, {x}) matches no active Tile ID for section {z_key}.")
            return

        new_vec = np.asarray(shift_vec).astype(np.float64)
        cache_key = (sec_num, tile_id)

        # Seed cache record from repository if it's a cold cache hit
        if cache_key not in self.modified_offset_entries:
            components = self.repo.fetch_offset(sec_num, tile_id)
            # Use a fresh default instance if the record does not exist in the DB yet
            self.modified_offset_entries[cache_key] = components or OffsetComponents()

        # Apply updates directly to the dataclass fields based on the axis contract
        record = self.modified_offset_entries[cache_key]
        if axis == 0:
            record.h_dx = float(new_vec[0])
            record.h_dy = float(new_vec[1])
        else:
            record.v_dx = float(new_vec[0])
            record.v_dy = float(new_vec[1])


    def save_offsets_to_disk_db(self) -> None:
        """Pushes current staging transactions over into physical infrastructure engines safely."""
        if not self.modified_offset_entries:
            logging.warning("Save execution skipped: Staging cache is clean.")
            return

        try:
            self.repo.save_offset_batch_atomic(self.modified_offset_entries)
            self.modified_offset_entries.clear()
            logging.info("Master transactional storage synchronized successfully.")
        except Exception as e:
            logging.error(f"Critical data boundary corruption: Serialization aborted: {e}")
            raise e


    def get_shift_vec(self, z: int | str, axis: int, y: int, x: int) -> npt.NDArray[np.float64]:
        """Returns [dx, dy] checking the local dirty cache before hitting DuckDB."""
        sec_num, _, tile_id = self._resolve_coordinate_to_tile(z, y, x)
        if tile_id is None:
            return np.array([0.0, 0.0], dtype=np.float64)

        # Check memory cache first
        cache_key = (sec_num, tile_id)
        if cache_key in self.modified_offset_entries:
            dirty = self.modified_offset_entries[cache_key]
            if axis == 0:
                return np.array([dirty.h_dx, dirty.h_dy], dtype=np.float64)
            else:
                return np.array([dirty.v_dx, dirty.v_dy], dtype=np.float64)

        # Fallback to repository tracking
        try:
            vec = self.repo.fetch_shift_vector_component(sec_num, tile_id, axis)
            if vec:
                return np.array([vec[0], vec[1]], dtype=np.float64)
            return np.array([0.0, 0.0], dtype=np.float64)
        except Exception:
            return np.array([0.0, 0.0], dtype=np.float64)


    def get_full_vector_stack(self, z: int | str, y: int, x: int) -> npt.NDArray[np.float64]:
        """Returns all 4 components (H_dx, H_dy, V_dx, V_dy) checking staging cache first."""
        sec_num, _, tile_id = self._resolve_coordinate_to_tile(z, y, x)
        if tile_id is None:
            return np.zeros(4, dtype=np.float64)

        # Staging Hit Tracker
        cache_key = (sec_num, tile_id)
        if cache_key in self.modified_offset_entries:
            d = self.modified_offset_entries[cache_key]
            return np.array([d.h_dx, d.h_dy, d.v_dx, d.v_dy], dtype=np.float64)

        # Fallback repository parse
        try:
            components = self.repo.fetch_offset(sec_num, tile_id)
            if components:
                return np.array([
                    components.h_dx,
                    components.h_dy,
                    components.v_dx,
                    components.v_dy
                ], dtype=np.float64)
            return np.zeros(4, dtype=np.float64)
        except Exception:
            return np.zeros(4, dtype=np.float64)


    def _build_inf_registry(self) -> None:
        """Re-evaluates registry boundaries without inline context configurations."""
        self._inf_registry = {}
        results = self.repo.fetch_inf_errors()

        for tid, sec_num, h_inf, v_inf in results:
            if tid not in self._inf_registry:
                self._inf_registry[tid] = []
            if h_inf:
                self._inf_registry[tid].append(
                    {'z': sec_num, 'overlap': OverlapType.HORIZONTAL, 'type': 'INF_ERROR'}
                )
            if v_inf:
                self._inf_registry[tid].append(
                    {'z': sec_num, 'overlap': OverlapType.VERTICAL, 'type': 'INF_ERROR'}
                )


    def fetch_section_sequence_from_db(self) -> None:
        """Synchronizes structural core caches through decoupled abstract engines."""
        try:
            self.section_sequence = self.repo.fetch_unique_sections()
            logging.info(f"Processor: Cached {len(self.section_sequence)} valid section coordinates.")
        except Exception as e:
            logging.error(f"Failed to populate section sequence cache: {e}")
            self.section_sequence = []

        self._build_inf_registry()
        return None


    def find_inf_offsets_for_tile(self, tile_id: str) -> List[Dict]:
        return [dict(item, tid=tile_id) for item in self._inf_registry.get(str(tile_id), [])]


    def get_full_trace(self, tile_id: str) -> Optional[CoarseOffsetTrace]:
        """Extracts offset traces for a targeted tile ID directly, merging staging cache layers."""
        try:
            df = self.repo.fetch_trace_dataframe(
                tile_id, int(self.config.first_sec), int(self.config.last_sec)
            )
        except Exception as e:
            logging.error(f"get_full_trace: Repository read failure for tile {tile_id}: {e}")
            return None

        # Vectorized cache filtering: Extract relevant data using a clean dict comprehension
        staged_map = {
            sec_num: (c.h_dx, c.h_dy, c.v_dx, c.v_dy)
            for (sec_num, tid), c in self.modified_offset_entries.items()
            if tid == tile_id
        }

        if df.empty and not staged_map:
            return None

        # Establish index on database entries for vectorized alignment
        df.set_index('section_number', inplace=True)

        # Convert the staging cache directly into a matching structured DataFrame
        if staged_map:
            staged_df = pd.DataFrame.from_dict(
                staged_map,
                orient='index',
                columns=['h_dx', 'h_dy', 'v_dx', 'v_dy']
            )
            staged_df.index.name = 'section_number'

            if df.empty:
                df = staged_df
            else:
                # Atomic vectorized override: Replaces DB records with staged modifications in one step
                df.update(staged_df)
                # Combine missing indexes if staging introduces new sections not currently in DB
                new_indices = staged_df.index.difference(df.index)
                if not new_indices.empty:
                    df = pd.concat([df, staged_df.loc[new_indices]]).sort_index()

        # Matrix construction and relative coordinate indexing using clean Pandas indices
        df.reset_index(inplace=True)
        first, last = int(df['section_number'].min()), int(df['section_number'].max())
        full_range = list(range(first, last + 1))
        traces = np.full((4, len(full_range)), np.nan)
        sec_nums_extracted = df['section_number'].to_numpy(dtype=np.int32)
        relative_indices = sec_nums_extracted - first
        matrix_payload = df[['h_dx', 'h_dy', 'v_dx', 'v_dy']].to_numpy(dtype=np.float64).T
        traces[:, relative_indices] = matrix_payload

        return CoarseOffsetTrace(
            tile_id=tile_id,
            section_numbers=full_range,
            shift_vectors=traces
        )


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


    def get_largest_tile_id_map(self) -> npt.NDArray[np.int_]:
        unique_ids = self.get_unique_tile_ids()

        if not unique_ids:
            return np.zeros(self.config.grid_shape, dtype=np.int_)

        return utils.compute_tile_id_map(self.config.grid_shape, sorted(unique_ids))


    def get_unique_tile_ids(self) -> set[int]:
        """
        Returns a memoized set of all unique integer tile IDs present across all sections.
        """
        if self._all_unique_ids is not None:
            return self._all_unique_ids

        try:
            res = self.repo.fetch_all_unique_tile_ids()
        except Exception as e:
            logging.error(f"Failed to query unique tile IDs via repository: {e}")
            self._all_unique_ids = set()
            return self._all_unique_ids

        logging.debug(f'all unique tile-ids:{res}')

        unique_ids: set[int] = set()
        for row in res:
            raw_val = row[0]
            if isinstance(raw_val, int):
                unique_ids.add(raw_val)
            elif isinstance(raw_val, str) and raw_val.strip().isdigit():
                unique_ids.add(int(raw_val))

        self._all_unique_ids = unique_ids
        return self._all_unique_ids


    def _get_section_lookup(self, sec_key: str) -> Optional[SectionIndex]:
        """Memoized lookup: translates TileID -> (y, x) by lazy-loading structural coordinates via repo."""
        if sec_key in self._coord_cache:
            return self._coord_cache[sec_key]

        try:
            target_sec_num = int(sec_key)
            res = self.repo.fetch_section_tile_ids(target_sec_num)

            if not res:
                self._coord_cache[sec_key] = None
                return None

            section_tids = [int(str(row[0]).strip()) for row in res if str(row[0]).strip().isdigit()]
            if not section_tids:
                self._coord_cache[sec_key] = None
                return None

            z_map = utils.compute_tile_id_map(self.config.grid_shape, sorted(section_tids))
            y_idxs, x_idxs = np.where(z_map != -1)

            mapping = {int(z_map[y, x]): (int(y), int(x)) for y, x in zip(y_idxs, x_idxs)}

            self._coord_cache[sec_key] = SectionIndex(section_id=sec_key, tile_to_coords=mapping)
            return self._coord_cache[sec_key]

        except Exception as e:
            logging.error(f"[CACHE_LOOKUP] Failed to compile lazy section lookup for slice {sec_key}: {e}",
                          exc_info=True)
            self._coord_cache[sec_key] = None
            return None


    def get_section_lookup(self, sec_key: str) -> Optional[SectionIndex]:
        """Public accessor for the section lookup table."""
        return self._get_section_lookup(sec_key)


    def get_trace(self, tile_id: int, axis: int) -> Optional[dict[int, tuple[tuple, tuple[int, int]]]]:
        """Retrieves shift vectors for a specific axis across all sections using cache and repository lookup."""
        trace_dict = {}
        target_tid_str = str(tile_id)

        staged_sections = {sec for (sec, tid) in self.modified_offset_entries.keys() if str(tid) == target_tid_str}

        try:
            db_records = self.repo.fetch_axis_records(
                target_tid_str, axis, int(self.config.first_sec), int(self.config.last_sec)
            )
        except Exception as e:
            logging.error(f"get_trace: Repository read failure for tile {tile_id}: {e}")
            db_records = {}

        all_sections = sorted(staged_sections.union(db_records.keys()))

        for sec_num in all_sections:
            index = self._get_section_lookup(str(sec_num))
            if index is None:
                continue

            coord = index.get_coords(tile_id)
            if coord is None:
                continue

            y, x = coord

            # Check for an active in-memory override first
            cache_key = (sec_num, target_tid_str)
            if cache_key in self.modified_offset_entries:
                dirty = self.modified_offset_entries[cache_key]
                vec = (dirty.h_dx, dirty.h_dy) if axis == 0 else (dirty.v_dx, dirty.v_dy)
            elif sec_num in db_records:
                vec = db_records[sec_num]
            else:
                continue

            trace_dict[sec_num] = (vec, (y, x))

        return trace_dict if trace_dict else None

 
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


    def store_cxyz_to_offset_files(
            self,
            sec_paths_dict: dict[int, str],
            target_sections: list[int]
    ) -> None:
        """
        Reconstructs section-specific formal 4D coarse offset alignment matrices (2, 2, Y, X)
        matching localized spatial constraints, and persists them into individual section cx_cy.json files.
        """

        stats = {"ok": 0, "err": 0}

        con = duckdb.connect(str(self.db_path), read_only=True)
        try:
            for sec_num in tqdm(target_sections, desc="Exporting JSON offsets"):
                sec_key = str(sec_num)
                sec_path = sec_paths_dict.get(sec_num)

                # 1. Resolve spatial positions for this specific section slice
                lookup = self._get_section_lookup(sec_key)
                if lookup is None or not lookup.tile_to_coords:
                    logging.warning(f"Skipping section s{sec_num}: Spatial map index empty or unresolved.")
                    stats["err"] += 1
                    continue

                coords = list(lookup.tile_to_coords.values())
                sec_grid_y = max(c[0] for c in coords) + 1
                sec_grid_x = max(c[1] for c in coords) + 1

                logging.debug(f"Section s{sec_num} dimensional profile localized to: ({sec_grid_y}, {sec_grid_x})")

                # 2. Extract baseline records from database for this section
                res = con.execute("""
                    SELECT tile_id, h_dx, h_dy, v_dx, v_dy 
                    FROM coarse_offsets 
                    WHERE section_number = ? AND tile_id IS NOT NULL;
                """, [sec_num]).fetchall()

                # Initialize 4D array matching exactly the localized dimensions
                # Initialize with np.nan to ensure untracked slots output correctly
                coarse_mat = np.full((2, 2, sec_grid_y, sec_grid_x), np.nan, dtype=np.float64)

                db_records = {}
                for row in res:
                    tid_str = str(row[0])
                    db_records[tid_str] = {
                        'h_dx': float(row[1]) if row[1] is not None else np.nan,
                        'h_dy': float(row[2]) if row[2] is not None else np.nan,
                        'v_dx': float(row[3]) if row[3] is not None else np.nan,
                        'v_dy': float(row[4]) if row[4] is not None else np.nan,
                    }

                # 3. Consolidate DB rows with local memory cache modifications
                all_section_tids = set(db_records.keys()).union(
                    {str(tid) for (s, tid) in self.modified_offset_entries.keys() if s == sec_num}
                )

                # 4. Fill matrix coordinates sequentially using spatial coordinate index lookups
                for tid_str in all_section_tids:
                    tid_int = int(tid_str) if tid_str.isdigit() else None
                    if tid_int not in lookup.tile_to_coords:
                        continue

                    y, x = lookup.tile_to_coords[tid_int]

                    # Default values from DB record
                    vals = db_records.get(
                        tid_str, {'h_dx': np.nan, 'h_dy': np.nan, 'v_dx': np.nan, 'v_dy': np.nan}
                    )

                    # Apply volatile in-memory overrides if present
                    cache_key = (sec_num, tid_str)
                    if cache_key in self.modified_offset_entries:
                        dirty_vals = self.modified_offset_entries[cache_key]

                        # Direct attribute lookup avoids dictionary serialization overhead
                        for field_item in ['h_dx', 'h_dy', 'v_dx', 'v_dy']:
                            v = getattr(dirty_vals, field_item)
                            if v is not None and not np.isnan(v):
                                vals[field_item] = v

                    # Assign vector components to specific localized matrix locations
                    coarse_mat[0, 0, y, x] = vals['h_dx']  # Horizontal dx
                    coarse_mat[0, 1, y, x] = vals['h_dy']  # Horizontal dy
                    coarse_mat[1, 0, y, x] = vals['v_dx']  # Vertical dx
                    coarse_mat[1, 1, y, x] = vals['v_dy']  # Vertical dy

                # 5. Export finalized matrix data to filesystem endpoint
                p = utils.cross_platform_path(str(sec_path))

                try:
                    utils.save_coarse_mat(coarse_mat, p, file_format='json')
                    stats["ok"] += 1
                except (IOError, OSError) as e:
                    logging.error(f"Failed writing json target coordinates for s{sec_key}: {e}")
                    stats["err"] += 1

            print(f"\nJSON Sync Complete: {stats['ok']} files updated | {stats['err']} errors encountered.")

        except Exception as e:
            logging.critical(f"Critical execution error during json export sequence: {e}", exc_info=True)
        finally:
            con.close()


    def flatten_and_save_coarse_offsets(
            self,
            offsets: dict[str, np.ndarray],
            tile_id_maps_dict: dict[str, np.ndarray]
    ) -> None:
        """
        Translates multi-dimensional alignment arrays and tile layouts into
        flat relational rows, then persists them to the underlying repository.
        """
        logging.info("Processor: Flattening coordinate matrices into relational row layouts...")
        all_rows = []

        for sec_num_str, array_stack in offsets.items():
            sec_num = int(sec_num_str)
            tile_map = tile_id_maps_dict[sec_num_str]

            # Resolve physical coordinate indices where real tile IDs exist
            y_indices, x_indices = np.where(tile_map > 0)

            for y, x in zip(y_indices, x_indices):
                tid = str(int(tile_map[y, x]))

                # Encapsulate the 4D matrix indexing rule safely within the processor
                h_dx = float(array_stack[0, 0, y, x])
                h_dy = float(array_stack[0, 1, y, x])
                v_dx = float(array_stack[1, 0, y, x])
                v_dy = float(array_stack[1, 1, y, x])

                all_rows.append((tid, sec_num, h_dx, h_dy, v_dx, v_dy))

        if not all_rows:
            logging.warning("Processor: No relational entries generated from coordinates stack lookup.")
            return

        # Atomically stream the processed rows to storage via the repository engine
        self.repo.bulk_insert_rows_atomic(all_rows, suffix="_duckdb_build")


if __name__ == "__main__":
    # test_get_largest_tile_id_map()
    # tst_get_full_trace()
    pass
