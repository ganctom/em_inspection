import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import logging
from typing import Optional, Tuple

import experiment_configs as cfg
from inspection_refactored import Inspection, Section
import plotly.express as px
import numpy as np

from inspection_utils_refactor import get_vert_tile_id
from inspection_refactored import _prepare_sections, Vector

class DataService:
    def __init__(self):
        configs = cfg.get_experiment_configurations()
        self.exp_config = configs[cfg.ExperimentName.ROLI_F1]

        self.inspection = Inspection(self.exp_config)
        self.processor = self.inspection.co_processor
        self.tile_ids = self.processor.get_largest_tile_id_map()
        self._section_cache = {}  # {sec_path: SectionObject}


    def get_trace(self, tid: str):
        return self.processor.get_full_trace(tid)


    def get_overlap_figure(self, tid_a: str, z: int, overlap_type: str) -> Optional[px.imshow]:
        """
        High-level orchestrator for overlap visualization.
        Logic is split into: Context -> Resources -> Execution -> Presentation.
        """
        z_str = str(z)
        tid_a_int = int(tid_a)
        ov_type = overlap_type.upper()

        # Phase 1: Context Resolution (Coordinates and Neighbors)
        context = self._resolve_overlap_context(z_str, tid_a_int, ov_type)
        if not context:
            return None
        y, x, tid_b, axis = context

        # Phase 2: Resource Acquisition (Section Loading/Injection)
        section = self._get_initialized_section(z)
        if not section:
            return None

        # Phase 3: Data Preparation (Retype Vector)
        raw_vec = self.processor.get_shift_vec(z, axis, y, x)
        shift_vec = tuple(np.round(raw_vec).astype(int))

        # Phase 4: Compute Image Array
        try:
            img_array = section.plot_ov(
                tid_a=tid_a_int,
                tid_b=tid_b,
                shift_vec=shift_vec,
                blur=1.2,
                clahe=True,
                rotate_vert=True,
                return_img=True,
                show_plot=False,
            )
        except Exception as e:
            logging.error(f"Failed to plot overlap for Z:{z} T:{tid_a_int}: {e}")
            return None

        if img_array is None:
            return None

        # img_array = np.random.rand(256, 1024) * 255
        return self._build_plotly_figure(img_array, tid_a, tid_b, ov_type, z)

    def _resolve_overlap_context(self, z_str: str, tid_a: int, ov_type: str) -> Optional[Tuple[int, int, int, int]]:
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


    @staticmethod
    def _build_plotly_figure(img: np.ndarray, t1: str, t2: int, ov: str, z: int):
        fig = px.imshow(img, binary_string=True, origin='upper')

        fig.update_layout(
            title=dict(
                text=f"<b>OVERLAP {ov}</b> | {t1} ↔ {t2} | Z={z}",
                x=0.5, y=0.98, xanchor='center',
                font=dict(family="Monospace", size=14, color="#00FFCC")
            ),
            margin=dict(l=0, r=0, b=0, t=40),
            # Ensure axes are enabled for interaction even if invisible
            xaxis=dict(visible=False, fixedrange=False),
            yaxis=dict(visible=False, fixedrange=False),

            paper_bgcolor='black',
            plot_bgcolor='black',
            dragmode='pan',
            # This helps the image fill the container
            autosize=True
        )

        return fig

# Initialize single instance
service = DataService()