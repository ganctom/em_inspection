import io
import re
import sys
from dataclasses import dataclass
import logging
from typing import Optional, Tuple, Any
import plotly.express as px
import numpy as np
import gc
import threading

from experiment_configs import ExperimentRegistry, ExpConfig
from parameter_config import AcquisitionConfig
from Tile_refactored import Tile
from constants import DataConstants as DC
import parse_sbem_dataset as parse

from inspection_refactored import (
    Inspection, Section, _prepare_sections, Vector, utils,
    store_cxyz_to_offset_files, cached_read_image
)


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
        self.exp_config = None
        self.inspection = None
        self.processor = None
        self.tile_ids = []
        self._section_cache = {}
        self._lock = threading.Lock()
        self._worker = None
        self.parsing_status = {"active": False, "progress": 0, "message": "", "logs": ""}
        self._log_buffer = io.StringIO()
        self._log_lock = threading.Lock()

    def create_and_save_new_experiment(
            self, exp_name, proc_dir, grid_num, first_sec, last_sec, grid_shape, acq_dir
    ):
        """Called by the Dash Callback when the user hits 'Add Experiment'"""

        self.registry.add(exp_name, proc_dir, grid_num, first_sec, last_sec, grid_shape, acq_dir)
        new_conf = self.registry.get_all().get(exp_name)
        if new_conf:
            self.exp_config = new_conf
            self.initialize_experiment_from_config(new_conf)
        else:
            logging.warning("Issue with getting exp. configs")


    def initialize_experiment_from_config(self, config: ExpConfig):
        self.exp_config = config
        self.inspection = Inspection(self.exp_config)
        logging.info(f"DataService: Active experiment set to {config.name}")


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
            acq_cfg = self._prepare_acquisition_config(config)

            parse.main(str(self.inspection.dir_sections), acq_cfg,
                       self.inspection.first_sec, self.inspection.last_sec)

            # Validate parsing
            self.parsing_status["message"] = "Validating dataset..."
            results = self.validate_parsed()

            self.parsing_status.update(results)
            self.parsing_status["progress"] = 100
            self.parsing_status["message"] = "Processing Finished"

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
        validator = parse.Validator(
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


    @staticmethod
    def _prepare_acquisition_config(config) -> AcquisitionConfig:
        """Encapsulates the mapping logic."""
        acq_cfg = AcquisitionConfig()
        acq_cfg.sbem_root_dir = config.acq_dir
        acq_cfg.tile_grid = f"g{config.grid_num:04d}"
        acq_cfg.grid_shape = config.grid_shape
        acq_cfg.thickness = config.cut_thickness
        acq_cfg.resolution_xy = config.pixel_size
        return acq_cfg


    def load_experiment(self, config):
        """
        Loads inspector, coarse offsets tensor & UI data using specified config file
        """
        self.exp_config = config
        self.inspection = Inspection(self.exp_config)
        self.inspection.co_processor.load_all_offsets_and_tile_id_maps_from_npz()
        self.processor = self.inspection.co_processor
        self.tile_ids = self.processor.get_largest_tile_id_map()
        self.clear_cache()
        logging.info(f"DataService: Loaded {config.name} successfully.")

    def parse_experiment(self) -> None:

        outdir = str(self.inspection.dir_sections)
        start = self.inspection.first_sec
        end = self.inspection.last_sec

        logging.info(
            f"Parsing SBEM acquisition...\n"
            f"Dataset source dir: {self.inspection.acq_dir}\n"
            f"Section numbers range: [{start}-{end}]\n"
            f"Output dir: {outdir}"
        )

        conf: AcquisitionConfig = AcquisitionConfig()
        conf.sbem_root_dir = self.exp_config.acq_dir
        conf.tile_grid = f"g000{self.exp_config.grid_num}"
        conf.grid_shape = self.exp_config.grid_shape
        conf.thickness = self.exp_config.cut_thickness
        conf.resolution_xy = self.exp_config.pixel_size

        # Parse metadata, create section directories and section.yaml files
        parse.main(outdir, conf, start, end)

        # Check parsed section folders
        validator = parse.Validator(self.inspection.root, start, end)
        validator.validate_parsed_sbem_acquisition()
        validator.validate_tile_id_maps()

        logging.info(f"Parsing of the experiment done...")
        return


    def initialize_experiment(
            self, exp_name, proc_dir, grid_num, first_sec, last_sec, grid_shape, acq_dir
    ):
        """
        The 'Actual' constructor called by the Setup page.
        """
        # 1. Store the config

        self.exp_config = ExpConfig(
            name=exp_name,
            proc_dir=proc_dir,
            grid_num=grid_num,
            first_sec=first_sec,
            last_sec=last_sec,
            grid_shape=(int(grid_shape[0]), int(grid_shape[1])),
            acq_dir=acq_dir
        )

        # 2. Initialize the heavy objects
        self.inspection = Inspection(self.exp_config)
        logging.info(f"DataService: Experiment {self.exp_config.name} successfully.")


    def load_experiment(self, config):
        """
        The 'Actual' constructor called by the Setup page.
        """
        # 1. Store the config
        self.exp_config = config

        # 2. Initialize the heavy objects
        self.inspection = Inspection(self.exp_config)
        self.inspection.co_processor.load_all_offsets_and_tile_id_maps_from_npz()
        self.processor = self.inspection.co_processor

        # 3. Cache UI-essential data
        self.tile_ids = self.processor.get_largest_tile_id_map()

        # 4. Clear any old data if re-initializing
        self.clear_cache()

        logging.info(f"DataService: Loaded {config.name} successfully.")


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

        # Check for INF or NaN to ensure plotting safety
        if not np.isfinite(raw_vec).all():
            logging.info(f"Invalid vector (Inf/NaN) at Z={z}, T={tid_a_int}. Defaulting to (0,0).")
            shift_vec = (0, 0)
        else:
            shift_vec = tuple(map(int, np.round(raw_vec)))

        logging.info(f'Final shift_vec: {shift_vec} | Raw: {raw_vec}')

        return OverlapContext(
            section=section,
            tid_a=tid_a_int,
            tid_b=tid_b,
            axis=axis,
            y=y,
            x=x,
            shift_vec=shift_vec
        )

    def get_overlap_figure(
            self,
            tid_a: str,
            z: int,
            overlap_type: str,
            manual_nudge: Tuple[int, int] = (0, 0)
    ) -> Optional[px.imshow]:

        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx: return None

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
            return self._build_plotly_figure(
                img_array, tid_a, ctx.tid_b, overlap_type.upper(), z
            )
        except Exception as e:
            logging.error(f"Nudge plot failed: {e}")
            return None


    def _resolve_overlap_context(
            self, z_str: str, tid_a: int, ov_type: str
    ) -> Optional[Tuple[int, int, int, int]]:
        """Determines neighbor IDs and grid coordinates."""
        lookup = self.processor.get_section_lookup(z_str)
        if tid_a not in lookup:
            logging.error(f"Tile {tid_a} missing in section {z_str} lookup.")
            return None

        y, x = lookup[tid_a]
        tid_map = self.processor.tile_id_maps_obj[z_str]

        try:
            if ov_type == 'H':
                return y, x, int(tid_map[y, x + 1]), 0
            return y, x, int(tid_map[y + 1, x]), 1
        except IndexError:
            logging.warning(f"Boundary hit: Tile {tid_a} has no {ov_type} neighbor.")
            return None


    def _get_initialized_section(self, z: int) -> Optional[Section]:
        """Manages Section lifecycle and data injection."""

        sec_num_list = _prepare_sections(self.inspection, start=z, end=z)
        if sec_num_list is None:
            logging.warning(f'Section number {z} not in experiment section range!')
            return None

        sec_path = self.inspection.section_dicts.get(z)
        if not sec_path:
            logging.warning(f"Section {z} path not found in configuration.")
            return None

        with self._lock:
            if sec_path not in self._section_cache:
                section = Section(sec_path)
                # Data Injection from Processor Cache
                z_str = str(z)
                if z_str in self.processor.tile_id_maps_obj:
                    section.tile_id_map = self.processor.tile_id_maps_obj[z_str]
                    section._map_loaded = True
                else:
                    section.read_tile_id_map()

                self._section_cache[sec_path] = section
            return self._section_cache[sec_path]

    def compute_coarse_shift(
            self,
            tid_a: str,
            z: int,
            overlap_type: str,
            initial_nudge: Tuple[int, int] = (0, 0),
            override_vector: Optional[Vector] = None
    ):
        """
        Calculates a new shift vector.
        If override_vector is provided, it uses that as the absolute starting point.
        Otherwise, it adds initial_nudge to the existing coarse offset.
        """

        # Pyramidal parameters - can be tuned
        levels: int = 1
        max_ext: int = 30
        stride: int = 5

        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx:
            return "Context Error"

        section: Section = ctx.section
        section.tile_dicts = utils.get_tile_dicts(section.path)  # Optimize

        if overlap_type.upper().startswith('H'):
            aligned_nudge = (initial_nudge[1], -initial_nudge[0])
        else:
            aligned_nudge = initial_nudge

        if override_vector is not None:
            start_offset = override_vector
            print(f"BATCH MODE: Using override vector {start_offset}")
        else:
            start_offset: Vector = (
                ctx.shift_vec[0] + aligned_nudge[0],
                ctx.shift_vec[1] + aligned_nudge[1]
            )
            print(f"NUDGE MODE: {ctx.shift_vec} + {aligned_nudge} = {start_offset}")

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

            # Commit to memory/processor
            self.processor.update_shift_vec(z, ctx.axis, ctx.y, ctx.x, current_shift)
            print(f'REFINED VECTOR: {current_shift}')
            return {
                "initial": ctx.shift_vec,
                "start_used": start_offset,
                "refined": current_shift
            }

        except Exception as e:
            logging.error(f"Calculation failed: {e}")
            return str(e)


    def store_offsets_to_yamls(self):
        """Stores updated coarse shift vectors into respective sections cx_cy.json files"""
        store_cxyz_to_offset_files(self.inspection, self.processor.cxyz_obj)
        return


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
        # Assuming 'self.inspection' is where your CoarseOffsetProcessor lives
        return self.processor.find_inf_offsets_for_tile(tile_id)


    def preload_source_images(self, selection_data: list):
        """
        Public method to be called by Dash.
        Starts a background thread to fetch tile image-data.
        """
        if not selection_data:
            return

        with self._lock:
            # Avoid overlapping thread execution
            if self._worker and self._worker.is_alive():
                return

            targets = selection_data[:DC.CACHED_BASKET_ITEMS]
            self._worker = threading.Thread(
                target=self._preload_loop,
                args=(targets,),
                daemon=True
            )
            self._worker.start()


    def _preload_loop(self, items):
        """Background task for cluster I/O."""
        for item in items:
            try:
                ctx = self._get_overlap_context(item['tid'], item['z'], item['overlap'])
                if not ctx:
                    continue

                # Ensure section dictionary is populated
                sec = ctx.section
                if sec.tile_dicts is None:
                    sec.tile_dicts = utils.get_tile_dicts(sec.path)

                # Trigger reads into LRU cache
                for tid in (ctx.tid_a, ctx.tid_b):
                    path = sec.tile_dicts.get(tid)
                    if path:
                        cached_read_image(str(path))

            except Exception as e:
                logging.debug(f"Preload skipped {item.get('tid')}: {e}")


    def clear_cache(self):
        """Reset all caches and force garbage collection."""
        with self._lock:
            self._section_cache.clear()
            cached_read_image.cache_clear()
            gc.collect()
            logging.debug("Caches cleared and memory freed.")



    def get_slider_metadata(self):
        # Check if processor exists yet
        if self.processor is None:
            return {"min": 0, "max": 100, "marks": {0: "0", 100: "100"}, "initial_value": 0}

        tile_maps = getattr(self.processor, 'tile_id_maps_obj', {})
        z_values = [int(z) for z in tile_maps.keys()] if tile_maps else []

        z_min = min(z_values) if z_values else 0
        z_max = max(z_values) if z_values else 100

        step_size = max(1, (z_max - z_min) // 5)
        slider_marks = {
            int(v): str(int((z_max + z_min) - v))
            for v in range(z_min, z_max + 1, step_size)
        }
        slider_marks[z_max] = str(z_min)
        slider_marks[z_min] = str(z_max)

        return {
            "min": z_min,
            "max": z_max,
            "marks": slider_marks,
            "initial_value": z_max
        }

# Initialize single instance
service = DataService()