import functools
import io
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional, Tuple, Any

import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import numpy.typing as npt
import gc
import threading
import yaml

import parameter_config
import parse_sbem_dataset

from Section_refactored import CoarseStitchConfig
from coarse_offset_processor import SectionIndex
from experiment_configs import ExperimentRegistry, ExpConfig
from parameter_config import (AcquisitionConfig, StitchingConfig, RegistrationConfig, MeshIntegrationConfig,
                              MaskingConfig, WarpConfig)
from Tile_refactored import Tile
from constants import DataConstants as DC
from constants import UIConstants as UI
from presenters.flow_presenter import FlowPresenter
from presenters.overlap_presenter import OverlapPresenter
from schema import InspectionSchema as IS
from inspection_utils_refactor import get_missing_stitched_sections
from pipeline_actions import PipelineOrchestrator
from inspection_refactored import (
    Inspection, Section, _prepare_sections, Vector, utils, cached_read_image, init_specific_section_dirs,
)
from Section_refactored import SectionInfrastructureError
from dynamic_range_masks import RangeAnalysisConfig, create_range_mask_plot


class DataServiceError(Exception):
    """Base exception for the entire experiment registry errors"""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class OverlapContext:
    section: Section
    tid_a: int
    tid_b: int
    axis: int
    y: int
    x: int
    shift_vec: Vector

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(f"OverlapContext has no attribute '{key}'")

    def keys(self):
        return self.__annotations__.keys()


class DataService:
    def __init__(self):
        self.registry = ExperimentRegistry()  # Loads existing user_experiments.yaml

        self.acq_config: AcquisitionConfig | None = None
        self.exp_config: ExpConfig | None = None
        self.stitch_config: StitchingConfig |None = None
        self.reg_config: RegistrationConfig | None = None
        self.mesh_config: MeshIntegrationConfig| None = None
        self.mask_config: MaskingConfig | None = None
        self.warp_config: WarpConfig | None = None

        self.inspection = None
        self.processor = None
        self.tile_ids: npt.NDArray[np.int_] = np.array([], dtype=np.int_)
        self._section_cache = {}
        self._lock = threading.Lock()
        self._worker = None
        self.parsing_status = {"active": False, "progress": 0, "message": "", "logs": ""}
        self._log_buffer = io.StringIO()
        self._log_lock = threading.Lock()
        self.backup_status = {"active": False, "progress": 0, "message": "", "error": None}
        self.coarse_align_status = UI.STITCH_STATUS
        self.abort_requested = False
        self.stitch_status = {"active": False, "pending_messages": []}
        self.message_queue = deque()
        self.service_initialized = False


    def handle_new_exp_infra(self, exp_config: ExpConfig) -> None:
        """Performs actions during new experiment initialization """
        # Register new experiment into list of projects
        self.create_and_save_new_experiment(exp_config)
    
        # Create and save default stitching config to allow further steps
        self.stitch_config = self.create_default_stitch_config(exp_config)
    
        # Save tile_stitching_config.yaml
        self.store_stitch_config(self.stitch_config, path_out=None)

        # Initial self and database
        self.load_experiment(exp_config)

        
    def get_missing_stitched_sections(self) -> list[int]:
        dir_stitched = self.inspection.dir_stitched
        sec_nums_to_check = list(range(self.inspection.first_sec, self.inspection.last_sec))
        return get_missing_stitched_sections(dir_stitched, sec_nums_to_check)


    def create_and_save_new_experiment(self, exp_config: ExpConfig) -> None:
        """Called by the Dash Callback when the user hits 'Add Experiment'

        The list of user experiments is located in the application 'app_data' folder
        and used for selection in 'Existing Experiments' in the SETUP page.
        """

        # Register new experiment
        self.registry.add(exp_config)

        # Store new experiment info into 'user_experiments.yaml'
        self.registry.save_user_experiments(self.registry.app_cfg.exp_yaml_path)

        # Initialize experiment
        new_conf = self.registry.get_all().get(exp_config.name, None)
        if new_conf is None:
            logging.warning(f"Failed to retrieve exp.config: {exp_config.name}.")

        self.initialize_experiment_from_config(new_conf)


    @staticmethod
    def create_default_stitch_config(exp_config: ExpConfig) -> StitchingConfig:
        return StitchingConfig().from_experiment(exp_config)


    def store_stitch_config(
            self,
            stitch_config: StitchingConfig,
            path_out: str | None = None
    ) -> None:

        if path_out is None:
            path_out = self.get_stitch_config_path

        parameter_config.save_to_disk(stitch_config, path_out)


    def initialize_experiment_from_config(self, config: ExpConfig):
        self.exp_config = config
        self.acq_config = AcquisitionConfig().from_experiment(config)
        self.inspection = Inspection(config)
        self.processor = self.inspection.co_processor
        self.service_initialized = True
        logging.info(f"DataService: Active experiment set to {config.name}")


    def get_sec_path(self, sec_num: int) -> str:
        sec_dir = Path(self.exp_config.proc_dir, IS.DIR_SECTIONS)
        grid_num = self.exp_config.grid_num
        sec_name = f"s{sec_num}_g{grid_num}"
        return str(sec_dir / sec_name)


    def get_latest_logs(self):
        """Safely read the current buffer."""
        with self._log_lock:
            return self._log_buffer.getvalue()

    def update_status_from_logs(self, log_text):
        """Extracts the latest percentage from tqdm strings."""
        if not log_text:
            return

        # Capture the raw text for the UI window
        self.parsing_status["logs"] = log_text

        # Regex to find percentages (e.g., '10%')
        # We look for the last one in the string as it's the most recent
        matches = re.findall(r'(\d+)%', log_text)
        if matches:
            last_percent = int(matches[-1])
            if last_percent > self.parsing_status["progress"]:
                self.parsing_status["progress"] = last_percent


    def parse_experiment(self, exp_name: str) -> None:
        with self._log_lock:
            self._log_buffer.seek(0)
            self._log_buffer.truncate(0)
            self.parsing_status = {"active": True, "progress": 0, "message": "Parsing..."}

        save_stdout, save_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = self._log_buffer

        try:
            config = self.registry.get_all().get(exp_name)
            if not config:
                return

            self.exp_config = config
            self.acq_config = AcquisitionConfig().from_experiment(config)

            parse_sbem_dataset.main(
                str(self.inspection.dir_sections),
                self.acq_config,
                self.inspection.first_sec,
                self.inspection.last_sec
            )

            # Validate parsing
            self.parsing_status["message"] = "Validating dataset..."
            results = self.validate_parsed()

            self.parsing_status.update(results)
            self.parsing_status["progress"] = 100
            self.parsing_status["message"] = UI.MSG_PARSE_EXP_OK

        except Exception as e:
            self.parsing_status["message"] = f"Error: {str(e)}"
        finally:
            sys.stdout, sys.stderr = save_stdout, save_stderr
            self.parsing_status["active"] = False

    def update_percentage_only(self):
        """Reads the buffer and updates the internal progress integer."""
        with self._log_lock:
            log_text = self._log_buffer.getvalue()

        # Sniper regex for the tqdm percentage
        matches = re.findall(r'(\d+)%', log_text)
        if matches:
            last_val = int(matches[-1])
            if last_val > self.parsing_status["progress"]:
                self.parsing_status["progress"] = last_val


    def validate_parsed(self) -> dict:
        # Check parsed section folders
        validator = parse_sbem_dataset.Validator(
            self.inspection.root,
            self.inspection.first_sec,
            self.inspection.last_sec
        )

        missing_sections = validator.validate_parsed_sbem_acquisition()
        invalid_maps = validator.validate_tile_id_maps()

        return {
            "missing_count": len(missing_sections),
            "invalid_maps_count": len(invalid_maps)
        }

    @property
    def get_stitch_config_path(self):
        if self.exp_config is None:
            raise (ValueError, "Failed to load tile_stitching_config.yaml. Experiment is not initialized.")
        return str(Path(self.exp_config.proc_dir) / UI.FN_CFG_TILE_STITCHING)


    def load_stitching_config(self, config_path: str) -> StitchingConfig:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)

        logging.info(f'loading {config_path}')

        cfg = StitchingConfig(**data)
        self.stitch_config = cfg

        return cfg


    def load_experiment(self, config: ExpConfig) -> None:
        """Loads inspector configuration profiles and loads offsets database."""
        self.initialize_experiment_from_config(config)

        # === Load Configuration Profiles ===
        self.load_stitching_config(self.get_stitch_config_path)
        self.reg_config = self.stitch_config.registration_config
        self.mesh_config = self.stitch_config.mesh_integration_config
        self.warp_config = self.stitch_config.warp_config
        self.mask_config = self.stitch_config.mask_config

        # === Database Lifecycle Handshake ===
        if not self.processor.db_path.exists():
            logging.info(f"DataService: Target database file for {config.name} not found. Spawning ingestion worker...")
            thread = threading.Thread(
                target=self.run_offsets_backup_thread,
                daemon=True
            )
            thread.start()
        else:
            logging.info(f"DataService: Existing database identified for {config.name}. Synchronizing engines...")
            self.initialize_database_context()

        self.clear_cache()
        logging.info(f"DataService: Loaded {config.name} configuration context successfully.")


    def initialize_experiment(
            self, exp_name, proc_dir, grid_num, first_sec, last_sec,
            grid_shape, acq_dir
    ):
        """
        The 'Actual' constructor called by the Setup page.
        """
        self.exp_config = ExpConfig(
            name=exp_name,
            proc_dir=proc_dir,
            grid_num=grid_num,
            first_sec=first_sec,
            last_sec=last_sec,
            grid_shape=(int(grid_shape[0]), int(grid_shape[1])),
            acq_dir=acq_dir
        )

        self.inspection = Inspection(self.exp_config)
        logging.info(f"DataService: Experiment {self.exp_config.name} successfully.")


    def _update_offsets_backup_stats(self, current, total, task_index, total_tasks=2):
        """
        Calculates global progress across multiple sequential tasks.
        task_index: 0 for the first task, 1 for the second, etc.
        """
        # Calculate how much of the total bar this task represents (e.g., 50% each)
        portion_size = 100 / total_tasks
        base_progress = task_index * portion_size

        # Calculate current task progress within its portion
        task_progress = (current / total) * portion_size
        global_progress = int(base_progress + task_progress)

        self.backup_status["progress"] = global_progress
        self.backup_status["message"] = f"Task {task_index + 1}/{total_tasks}: {current}/{total} sections..."


    def initialize_database_context(self, overwrite: bool = False):
        """
        Orchestrates DuckDB lifecycle. Resolves existing database loads,
        otherwise populates real coarse offsets or initializes a structural NaN placeholder.
        """
        db_path = self.processor.db_path

        if db_path.exists() and overwrite:
            logging.info(f"Overwrite flag active. Purging database container at: {db_path}")
            try:
                db_path.unlink()
            except OSError as e:
                logging.error(f"Failed to unlink database file {db_path}: {e}")
                raise

        if not db_path.exists():
            logging.info(f"Database target {db_path} not found. Attempting real record injection...")

            # 1. Direct execution: Attempt to back up real coarse offsets first
            offsets_discovered = self.backup_coarse_offsets_to_duckdb()

            # 2. Fallback execution: If no files existed on disk, compile structural NaN framework
            if not offsets_discovered:
                logging.warning("No coarse offset matrix files discovered. Generating structural NaN placeholder...")
                self.initialize_empty_coarse_offsets_db()
        else:
            logging.info(f"Existing DuckDB container discovered at {db_path}. Skipping compilation.")

        # === Uniform Post-Initialization / Loading Pipeline ===
        logging.info("Syncing processor state engines with database index layout...")
        self.processor.fetch_section_sequence_from_db()
        self.tile_ids = self.processor.get_largest_tile_id_map()


    def initialize_empty_coarse_offsets_db(self, progress_cb=None):
        """
        Creates a structural placeholder database containing all experiment section numbers
        and tile IDs. Fills all vector displacement fields with float NaN values.
        """
        logging.info("Initializing fallback structural database with NaN placeholder matrices...")

        tile_id_maps_dict, _ = utils.aggregate_parallel(
            section_dirs=self.inspection.section_dirs,
            target_filename=self.inspection.fn_tile_id_map,
            processing_func=utils.get_tile_id_map,
            progress_cb=progress_cb,
            max_workers=20
        )

        if not tile_id_maps_dict:
            raise RuntimeError("Database initialization aborted: Zero valid tile_id_maps resolved.")

        all_rows = []
        nan_val = float('nan')

        for sec_num_str, tile_map in tile_id_maps_dict.items():
            sec_num = int(sec_num_str)
            y_indices, x_indices = np.where(tile_map > 0)

            for y, x in zip(y_indices, x_indices):
                tid = str(int(tile_map[y, x]))
                all_rows.append((tid, sec_num, nan_val, nan_val, nan_val, nan_val))

        if not all_rows:
            raise RuntimeError("No valid tile mappings were generated inside matrix dictionaries.")

        self.processor.repo.bulk_insert_rows_atomic(all_rows, suffix="_duckdb_fallback")


    def backup_coarse_offsets_to_duckdb(self, progress_cb=None) -> bool:
        """
        Aggregates raw file data from disk and passes it to the processor layer.
        Returns True if data was found and backed up, False otherwise.
        """
        offsets, _ = utils.aggregate_parallel(
            section_dirs=self.inspection.section_dirs,
            target_filename=self.inspection.fn_coarse_offsets,
            processing_func=utils.process_offsets,
            progress_cb=progress_cb,
            max_workers=20
        )

        if not offsets:
            return False

        tile_id_maps_dict, _ = utils.aggregate_parallel(
            section_dirs=self.inspection.section_dirs,
            target_filename=self.inspection.fn_tile_id_map,
            processing_func=utils.get_tile_id_map,
            progress_cb=progress_cb,
            max_workers=20
        )

        if not tile_id_maps_dict:
            logging.error("Coarse offsets existed, but corresponding tile_id_maps are missing.")
            return False

        self.processor.flatten_and_save_coarse_offsets(offsets, tile_id_maps_dict)
        return True


    def run_offsets_backup_thread(self, overwrite: bool = False):
        """Compiles spatial arrays and saves them directly into DuckDB stores via background worker."""
        self.backup_status = {"active": True, "progress": 1, "message": "Initializing...", "error": None}
        try:
            if not self.inspection:
                raise ValueError("No inspection object loaded in execution context.")

            fs, ls = self.inspection.first_sec, self.inspection.last_sec
            init_specific_section_dirs(self.inspection, list(range(fs, ls + 1)))

            if not self.inspection.section_dirs:
                raise ValueError("No valid section directories resolved on storage.")

            self.backup_status["message"] = "Task 1/1: Processing DuckDB lifecycle transaction..."

            # Execute unified controller
            self.initialize_database_context(overwrite=overwrite)

            self.backup_status["progress"] = 100
            self.backup_status["message"] = "Backup complete: Relational tables indexed and loaded."
            time.sleep(1.0)

        except Exception as e:
            logging.error(f"Database ingestion thread failed: {e}")
            self.backup_status["error"] = str(e)
        finally:
            self.backup_status["active"] = False


    def get_trace(self, tid: str):
        if not self.processor:
            logging.error("Trace requested but no experiment is loaded.")
            return None
        return self.processor.get_full_trace(tid)


    def _get_overlap_context(
            self, tid_a: str, z: int, overlap_type: str
    ) -> Optional[OverlapContext]:

        z_str = str(z)
        tid_a_int = int(tid_a)
        ov_type = overlap_type.upper()

        res = self._resolve_overlap_context(z_str, tid_a_int, ov_type)
        if not res:
            return None
        y, x, tid_b, axis = res

        # 2. Early exit for section initialization
        section = self._get_initialized_section(z)
        if not section:
            return None

        # 3. Handle Vector Logic
        raw_vec = self.processor.get_shift_vec(z, axis, y, x)
        logging.debug(f'get_overlap_context: raw_vec: {raw_vec}')

        # Check for INF or NaN to ensure plotting safety
        if not np.isfinite(raw_vec).all():
            logging.info(f"Invalid vector (Inf/NaN) at Z={z}, T={tid_a_int}. Defaulting to (0,0).")
            shift_vec = (0, 0)
        else:
            shift_vec = tuple(map(int, np.round(raw_vec)))

        logging.debug(f'Final shift_vec: {shift_vec} | Raw: {raw_vec}')

        return OverlapContext(
            section=section,
            tid_a=tid_a_int,
            tid_b=tid_b,
            axis=axis,
            y=y,
            x=x,
            shift_vec=shift_vec
        )


    def ensure_flow_fig_resources(self, section_num: int) -> Section | None:

        # Load section
        section = self._get_initialized_section(section_num)
        if section is None:
            return None

        # Load fine flows
        try:
            section.ensure_fflows()
        except utils.MeshResourceError as e:
            logging.warning(e)
            return None

        return section


    def get_flow_fig(
            self,
            section_num: int,
            tile_id: str,
            reg_config: RegistrationConfig | None = None,
            do_clean_flow: bool = False
    ) -> Optional[go.Figure]:
        """Retrieves scientific flow field data matrices and hands them off to the FlowPresenter.

            This method ensures the necessary resources are loaded, determines the spatial
            coordinates for the tile, and optionally performs flow cleaning and reconciliation.
            The colormap range is locked to the raw data values to ensure visual consistency
            between raw and cleaned states.

           Args:
            section_num: The index of the section to visualize.
            tile_id: The string identifier for the specific tile.
            reg_config: Configuration for cleaning; defaults to self.reg_config if None.
            do_clean_flow: If True, applies cleaning and reconciliation to the flow fields.

        """
        cfg = reg_config or self.reg_config

        try:
            section = self.ensure_flow_fig_resources(section_num)
        except utils.MeshResourceError as e:
            err_msg = f"Flow figure failure t{tile_id} s{section_num}: {e}"
            self.message_queue.append(err_msg)
            logging.warning(err_msg)
            return None

        if section is None:
            err_msg = f"Flow figure failure t{tile_id} s{section_num}"
            self.message_queue.append(err_msg)
            logging.warning(err_msg)
            return None

        try:
            fine_x_raw = section.fflows[0][0]
            fine_y_raw = section.fflows[1][0]

            sec_lookup = self.processor.get_section_lookup(str(section_num))
            tile_row_idx, tile_col_idx = sec_lookup[int(tile_id)]
            xy = (tile_col_idx, tile_row_idx)

            z_lims = None
            if xy in fine_x_raw and xy in fine_y_raw:
                all_vals = np.concatenate([fine_x_raw[xy][:2].flatten(),
                                           fine_y_raw[xy][:2].flatten()])
                z_lims = (np.nanmin(all_vals), np.nanmax(all_vals))

            fine_x, fine_y = fine_x_raw, fine_y_raw

            if do_clean_flow:
                section.clean_and_reconcile_fflows(cfg)
                fine_x, _ = section.fflows_recon[0]
                fine_y, _ = section.fflows_recon[1]

            return FlowPresenter.render_diagnostic_grid(
                fine_x=fine_x, fine_y=fine_y, xy=xy, z_range=z_lims, transpose=False
            )

        except Exception as e:
            err_msg = f"Flow figure failure t{tile_id} s{section_num}: {e}"
            self.message_queue.append(err_msg)
            logging.warning(err_msg)
            return None


    def _resolve_tile(self, section_num: int, tile_id_num: int) -> Optional[Tile]:
        """Internal domain helper to safely fetch and instantiate a Tile entity."""
        section = self._get_initialized_section(section_num)
        if section is None:
            return None

        if tile_id_num not in section.tile_dicts:
            logging.warning(f'Tile t{tile_id_num} not resolved.')
            return None

        return Tile(section.tile_dicts[tile_id_num])


    def get_range_masks_fig(
            self,
            section_num: int,
            tile_id_num: int
    ) -> Optional[go.Figure]:

        t = self._resolve_tile(section_num, tile_id_num)
        if t is None:
            return None

        t.load_image(clahe=False)

        rac = RangeAnalysisConfig()
        rac.min_range = self.stitch_config.registration_config.min_range
        rac.filter_size = self.stitch_config.registration_config.filter_size

        return create_range_mask_plot(t.img_data, rac)


    def get_tile_image_fig(
            self,
            section_num: int,
            tile_id_num: int,
            bin_fct: int = 2,
            gauss_sigma: float = 0.8,
            apply_clahe: bool = True,
    ) -> go.Figure:

        t = self._resolve_tile(section_num, tile_id_num)

        # 1. Start the common core pipeline steps
        pipeline = t.load_image().denoise(gauss_sigma)

        # 2. Conditionally inject the CLAHE transformation
        if apply_clahe:
            pipeline = pipeline.clahe()

        # 3. Downscaling for responsiveness
        display_img = pipeline.bin(bin_fct).processed

        fig = px.imshow(display_img, color_continuous_scale='gray')

        fig.update_layout(
            coloraxis_showscale=False,
            paper_bgcolor='black',
            plot_bgcolor='black',
            margin=dict(l=0, r=0, b=20, t=15),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, ticks='', visible=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, ticks='', visible=False)
        )

        return fig


    def get_overlap_figure(
            self,
            tid_a: str,
            z: int,
            overlap_type: str,
            manual_nudge: Tuple[int, int] = (0, 0)
    ) -> Optional[go.Figure]:
        """Brokers pixel registration arrays to the OverlapPresenter canvas."""
        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx:
            return None

        dx, dy = manual_nudge
        if overlap_type.upper().startswith('H'):
            corrected_nudge = (dy, -dx)
        else:
            corrected_nudge = (dx, dy)

        nudged_vec = (
            ctx.shift_vec[0] + corrected_nudge[0],
            ctx.shift_vec[1] + corrected_nudge[1]
        )

        try:
            img_array = ctx.section.plot_ov(
                tid_a=ctx.tid_a,
                tid_b=ctx.tid_b,
                shift_vec=nudged_vec,
                blur=1.2,
                clahe=True,
                rotate_vert=True,
                return_img=True,
                show_plot=False,
            )

            return OverlapPresenter.render_overlap_view(
                img_array=img_array,
                build_figure_fn=self._build_plotly_figure,
                tid_a=ctx.tid_a,
                tid_b=ctx.tid_b,
                overlap_type=overlap_type.upper(),
                z=z
            )
        except Exception as e:
            logging.error(f"Nudge plot failed: {e}")
            return None


    def _resolve_overlap_context(
            self, z_str: Any, tid_a: int, ov_type: str
    ) -> Optional[Tuple[int, int, int, int]]:

        normalized_z = str(int(z_str)) if z_str is not None else ""
        lookup: SectionIndex = self.processor.get_section_lookup(normalized_z)
        if lookup is None or not hasattr(lookup, 'tile_to_coords'):
            return None

        if tid_a not in lookup.tile_to_coords:
            logging.debug(f'tile_id {tid_a} not found in the lookup coords: {lookup.tile_to_coords}')
            return None

        y, x = lookup.tile_to_coords[tid_a]
        target_y = y + 1 if ov_type == 'V' else y
        target_x = x + 1 if ov_type == 'H' else x
        axis_idx = 1 if ov_type == 'V' else 0

        # Reverse lookup using the lean slotted SectionIndex cache
        for potential_tid, coords in lookup.tile_to_coords.items():
            if coords == (target_y, target_x):
                return y, x, potential_tid, axis_idx

        logging.warning(f"Boundary hit: Tile {tid_a} has no {ov_type} neighbor.")
        return None


    def _get_initialized_section(self, z: int) -> Optional[Section]:
        """Manages section lifecycle structures using DuckDB mapping coordinates."""
        sec_num_list = _prepare_sections(self.inspection, start=z, end=z)
        if sec_num_list is None:
            logging.warning(f'Section number {z} falls outside experiment ranges.')
            return None

        sec_path = self.inspection.section_dicts.get(z)
        if not sec_path:
            logging.warning(f"Section {z} path missing from active parameters.")
            return None

        with self._lock:
            if sec_path not in self._section_cache:
                try:
                    section = Section(sec_path)
                except SectionInfrastructureError as e:
                    logging.warning(e)
                    return None

                # Generate the layout map dynamically using your lean section lookup cache
                lookup = self.processor.get_section_lookup(str(z))

                # Reconstruct a basic coordinate map array for the Section object if required
                # by filling a grid shape with background (-1) and injecting cached IDs
                grid = np.full(self.exp_config.grid_shape, -1, dtype=np.int32)
                for tid, (y, x) in lookup.tile_to_coords.items():
                    grid[y, x] = tid

                section.tile_id_map = grid
                self._section_cache[sec_path] = section

            return self._section_cache[sec_path]


    def compute_coarse_shift(
            self,
            tid_a: str,
            z: int,
            overlap_type: str,
            initial_nudge: Tuple[int, int] = (0, 0),
            override_vector: Optional[Vector] = None,
            max_ext: int = 25,
    ):
        """
        Calculates a new shift vector.
        If override_vector is provided, it uses that as the absolute starting point.
        Otherwise, it adds initial_nudge to the existing coarse offset.
        """

        # Pyramidal parameters - can be tuned
        levels: int = 1
        stride: int = 5

        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx:
            return "Context Error"

        section: Section = ctx.section
        section.tile_dicts = utils.get_tile_dicts(section.path)  # TODO: Optimize

        if overlap_type.upper().startswith('H'):
            aligned_nudge = (initial_nudge[1], -initial_nudge[0])
        else:
            aligned_nudge = initial_nudge

        if override_vector is not None:
            start_offset = override_vector
            logging.info(f"BATCH MODE: Using override vector {start_offset}")
        else:
            start_offset: Vector = (
                ctx.shift_vec[0] + aligned_nudge[0],
                ctx.shift_vec[1] + aligned_nudge[1]
            )
            logging.info(f"NUDGE MODE: {ctx.shift_vec} + {aligned_nudge} = {start_offset}")

        try:
            current_shift = start_offset
            t1 = Tile(section.tile_dicts[ctx.tid_a])
            t2 = Tile(section.tile_dicts[ctx.tid_b])

            for m_ext, s in utils.get_pyramid(levels, max_ext, stride):
                try:
                    current_shift, _ = section.refine_coarse_offset_eval_ov(
                        offset=current_shift,
                        tile_pair=(t1, t2),
                        is_vert=bool(ctx.axis),
                        max_ext=m_ext,
                        stride=s
                    )
                except TypeError:
                    current_shift = (np.nan, np.nan)
                    continue
            if np.isnan(current_shift).any():
                return "Refinement failed to converge."

            self.processor.update_shift_vec(z, ctx.axis, ctx.y, ctx.x, current_shift)

            logging.info(f's{ctx.section.section_num} t{ctx.tid_a}-t{ctx.tid_b} REFINED VECTOR: {current_shift}')

            return {
                "initial": ctx.shift_vec,
                "start_used": start_offset,
                "refined": current_shift
            }
        except Exception as e:
            logging.error(f"Calculation failed: {e}")
            return str(e)

    def store_offsets_to_cx_cy_json_files(self) -> None:
        """Persists memory adjustments back down into individual slice JSON files."""
        if not self.processor.modified_offset_entries:
            return

        modified_sections = sorted(list(
            {int(sec_num) for (sec_num, _) in self.processor.modified_offset_entries.keys()}
        ))

        sec_paths_dict = {sec_num: self.get_sec_path(sec_num) for sec_num in modified_sections}
        self.processor.store_cxyz_to_offset_files(sec_paths_dict, modified_sections)
        return None


    @staticmethod
    def _build_plotly_figure(img: np.ndarray, t1: str, t2: int, ov: str, z: int):
        fig = px.imshow(img, binary_string=True, origin='upper')
        fig.update_layout(
            title=dict(
                text=f"<b>OVERLAP {ov}</b> | {t1} ↔ {t2} | Z={z}",
                x=0.5, y=0.98, xanchor='center',
                font=dict(family="Monospace", size=14, color="#00FFCC")
            ),
            margin=dict(l=0, r=0, b=0, t=10),
            xaxis=dict(visible=False, fixedrange=False),
            yaxis=dict(visible=False, fixedrange=False),
            paper_bgcolor='black',
            plot_bgcolor='black',
            dragmode='pan',
            autosize=True
        )

        return fig


    def find_inf_offsets_for_tile(self, tile_id: str):
        """Pass-through to the processor logic."""
        return self.processor.find_inf_offsets_for_tile(tile_id)


    def preload_source_images(self, selection_data: list):
        """
        Public method to be called by Dash.
        Starts a background thread to fetch tile image-data.
        """
        if not selection_data:
            return

        with self._lock:
            if self._worker and self._worker.is_alive():
                return

            targets = selection_data[:DC.CACHED_BASKET_ITEMS]
            logging.debug(f'targets: {targets}')
            self._worker = threading.Thread(
                target=self._preload_loop,
                args=(targets,),
                daemon=True
            )
            self._worker.start()


    def _preload_loop(self, items):
        """Background task for cluster I/O."""
        for item in items:
            logging.debug(f'_preload_loop item: {item}')
            try:
                # Defensive formatting checks prior to worker extraction
                if not item or 'tid' not in item or 'z' not in item or 'overlap' not in item:
                    continue

                ctx = self._get_overlap_context(item['tid'], item['z'], item['overlap'])

                if not ctx or ctx.section is None:
                    continue

                sec = ctx.section
                if getattr(sec, 'tile_dicts', None) is None:
                    sec.tile_dicts = utils.get_tile_dicts(sec.path)

                if not sec.tile_dicts:
                    continue

                # Trigger reads into LRU cache
                for tid in (ctx.tid_a, ctx.tid_b):
                    path = sec.tile_dicts.get(tid)
                    if path:
                        cached_read_image(str(path))

            except Exception as e:
                logging.debug(f"Preload worker skipped tile {item.get('tid', 'unknown')}: {e}")


    def clear_cache(self):
        """Reset all caches and force garbage collection."""
        with self._lock:
            self._section_cache.clear()
            cached_read_image.cache_clear()
            gc.collect()
            logging.debug("Caches cleared and memory freed.")


    def get_slider_metadata(self):
        """Returns range bounds for UI navigation sliders using the database sequence."""

        z_values = getattr(self.processor, 'section_sequence', [])

        # FALLBACK: If database isn't built yet, populate boundaries from raw experiment configurations
        if not z_values and self.exp_config is not None:
            z_values = list(range(self.exp_config.first_sec, self.exp_config.last_sec + 1))

        if not z_values:
            return {"min": 0, "max": 100, "marks": {0: "0", 100: "100"}, "initial_value": 0}

        z_min, z_max = min(z_values), max(z_values)
        step_size = max(1, (z_max - z_min) // 5)

        slider_marks = {int(v): str(int((z_max + z_min) - v)) for v in range(z_min, z_max + 1, step_size)}
        slider_marks[z_max] = str(z_min)
        slider_marks[z_min] = str(z_max)

        return {"min": z_min, "max": z_max, "marks": slider_marks, "initial_value": z_max}


    @staticmethod
    @functools.lru_cache(maxsize=32)
    def prepare_stitching_params(
            config_path: str | os.PathLike | None = None,
            ui_params: tuple[tuple[str, any], ...] | None = None,
    ) -> StitchingConfig:
        """
        1. Loads YAML (The Base)
        2. Overlays UI Overrides (The specific edits)
        3. Validates via Pydantic (The Type Guard)
        """
        ui_params_dict = dict(ui_params) if ui_params else {}

        # 1. Load the raw dictionary from disk
        raw_dict: dict = {}
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    raw_dict = yaml.safe_load(f) or {}
            except Exception as e:
                logging.error(f"IO Error: {e}")

        # 2. Map UI Overrides to the correct nested structure
        def _apply_overrides(target_dict):
            # Registration Config
            if "registration_config" not in target_dict:
                target_dict["registration_config"] = {}

            reg = target_dict["registration_config"]
            if "overlaps_x" in ui_params_dict:
                reg["overlaps_x"] = [int(x.strip()) for x in str(ui_params_dict["overlaps_x"]).split(",") if x.strip()]
            if "overlaps_y" in ui_params_dict:
                reg["overlaps_y"] = [int(x.strip()) for x in str(ui_params_dict["overlaps_y"]).split(",") if x.strip()]
            if "min_overlap" in ui_params_dict:
                reg["min_overlap"] = int(ui_params_dict["min_overlap"])
            if "min_peak_ratio" in ui_params_dict:
                reg["min_peak_ratio"] = int(ui_params_dict["min_peak_ratio"])
            if "min_peak_sharpness" in ui_params_dict:
                reg["min_peak_sharpness"] = int(ui_params_dict["min_peak_sharpness"])
            if "clahe" in ui_params_dict:
                reg["clahe"] = ui_params_dict["clahe"]
            if "clip_limit" in ui_params_dict:
                reg["clip_limit"] = float(ui_params_dict["clip_limit"])
            if "kernel_size" in ui_params_dict:
                reg["kernel_size"] = int(ui_params_dict["kernel_size"])
            if "max_deviation" in ui_params_dict:
                reg["max_deviation"] = int(ui_params_dict["max_deviation"])
            if "max_magnitude" in ui_params_dict:
                reg["max_magnitude"] = int(ui_params_dict["max_magnitude"])
            if "min_patch_size" in ui_params_dict:
                reg["min_patch_size"] = int(ui_params_dict["min_patch_size"])
            if "max_gradient" in ui_params_dict:
                reg["max_gradient"] = int(ui_params_dict["max_gradient"])
            if "reconcile_flow_max_deviation" in ui_params_dict:
                reg["reconcile_flow_max_deviation"] = int(ui_params_dict["reconcile_flow_max_deviation"])

            # Warp Config
            if "warp_config" not in target_dict:
                target_dict["warp_config"] = {}

            if "use_clahe" in ui_params_dict:
                target_dict["warp_config"]["use_clahe"] = bool(ui_params_dict["use_clahe"])

            # Pipeline Config
            if "pipeline_config" not in target_dict:
                target_dict["pipeline_config"] = {}

            if UI.ID_RESCALE_FCT in ui_params_dict:
                val = ui_params_dict[UI.ID_RESCALE_FCT]
                if val is not None:
                    target_dict["pipeline_config"]["downscale_factor"] = float(val)

            return

        _apply_overrides(raw_dict)

        # 3. Recursive Validation
        try:
            return StitchingConfig.model_validate(raw_dict)
        except Exception as e:
            logging.warning(f"Validation warning: {e}. Returning defaults for missing keys.")
            return StitchingConfig(**raw_dict)  # Brute force attempt


    def run_coarse_align_thread(
            self,
            section_numbers,
            reg_params: CoarseStitchConfig
    ):
        self.abort_requested = False
        self.coarse_align_status = {
            "active": True,
            "progress": 0,
            "message": "Initializing...",
            "pending_messages": [UI.log_row("Coarse Alignment Started", type="info")],
            "error": None
        }

        total = len(section_numbers)
        failed_sections = []
        successful = 0

        try:
            # Initialize sections
            init_specific_section_dirs(self.inspection, section_numbers)

            for i, sec_num in enumerate(section_numbers):
                if self.abort_requested:
                    self.coarse_align_status["pending_messages"].append(
                        UI.log_row("🛑 Abort signal received. Stopping...", type="warning")
                    )
                    break

                msg = f"Processing section {sec_num} ({i + 1}/{total})"
                self.coarse_align_status["message"] = msg
                self.coarse_align_status["pending_messages"].append(UI.log_row(msg, type="info"))

                try:
                    # 1. Component Instantiation
                    section_data = self.inspection.section_dicts.get(sec_num)
                    if not section_data:
                        raise ValueError(f"Section metadata missing for ID {sec_num}")

                    section = Section(section_data)
                    section.read_tile_id_map()
                    section.ensure_tile_dicts()
                    section.load_tile_map(
                        gauss=True,
                        clahe=reg_params.apply_clahe,
                        clahe_params=reg_params.clahe_params,
                        parallel=True,
                        max_workers=8
                    )
                    coarse_offsets = section.compute_coarse_offsets_section(reg_params)
                    utils.save_coarse_mat(coarse_offsets, section.path)

                    successful += 1

                except (ValueError, TypeError) as e:
                    self._handle_section_failure(
                        sec_num, f"Data Error: {e}", failed_sections, level="warning"
                    )

                except (utils.TileLoadingError, FileNotFoundError) as e:
                    self._handle_section_failure(
                        sec_num, f"IO/Logic Error: {e}", failed_sections, level="error"
                    )

                except Exception as e:
                    self._handle_section_failure(
                        sec_num, f"Unexpected Crash: {e}", failed_sections, level="critical"
                    )

                self.coarse_align_status["progress"] = int(((i + 1) / total) * 100)

        except Exception as e:
            # This catches very unexpected errors (e.g. bug in the loop itself)
            logging.error(f"Unexpected error in coarse alignment thread: {e}")
            self.coarse_align_status["pending_messages"].append(
                UI.log_row(f"Critical error: {e}", type="error")
            )

        finally:
            # === Final summary ===
            self.coarse_align_status["active"] = False

            if failed_sections:
                fail_msg = f"Finished with {len(failed_sections)} failed sections: {failed_sections}"
                logging.warning(fail_msg)
                self.coarse_align_status["pending_messages"].append(
                    UI.log_row(f"⚠️ Completed with errors. Failed sections: {failed_sections}", type="warning")
                )
                self.coarse_align_status["error"] = fail_msg
            else:
                self.coarse_align_status["message"] = f"Successfully processed {successful}/{total} sections."
                self.coarse_align_status["progress"] = 100
                self.coarse_align_status["pending_messages"].append(
                    UI.log_row("🏁 Coarse Alignment Complete", type="success")
                )

    # Helper methods to reduce boilerplate
    def _log_status(self, msg, msg_type):
        self.coarse_align_status["pending_messages"].append(UI.log_row(msg, type=msg_type))

    def _handle_section_failure(self, sec_num, error_msg, failed_list, level="error"):
        logging.log(getattr(logging, level.upper()), f"Section {sec_num}: {error_msg}")
        failed_list.append(sec_num)
        self._log_status(f"❌ {sec_num}: {error_msg}", level)

    @staticmethod
    def compute_auto_zoom_ranges(
            shifts: npt.NDArray[np.float64],
            sec_nums: list[int]
    ) -> Tuple[list[int], list[int]]:
        """
        Calculates column-specific horizontal and vertical auto-zoom bounding x-ranges
        based on active finite coordinates in the shifts data.
        """

        def get_range_for_indices(indices: list[int]) -> list[int]:
            sub_shifts = shifts[indices, :]
            mask = ~np.isnan(sub_shifts).all(axis=0)
            if np.any(mask):
                valid_idx = np.where(mask)[0]
                return [int(sec_nums[valid_idx[0]]) - 2, int(sec_nums[valid_idx[-1]]) + 2]
            return [int(min(sec_nums)), int(max(sec_nums))]

        range_h = get_range_for_indices([0, 1])
        range_v = get_range_for_indices([2, 3])

        return range_h, range_v


    @staticmethod
    def get_inf_y_ceiling(data_row: npt.NDArray[np.float64]) -> float:
        """
        Extracts the maximum finite position within a given vector trace component
        to serve as the canvas height ceiling for infinite tracking markers.
        """
        finite_data = data_row[np.isfinite(data_row)]
        return float(np.max(finite_data)) if finite_data.size > 0 else 0.0


# Initialize single instances
service = DataService()
service.prepare_stitching_params()
orchestrator = PipelineOrchestrator(service)