from dataclasses import dataclass
import logging
from functools import lru_cache
from typing import Optional, Tuple, Any
import plotly.express as px
import numpy as np

from inspection_refactored import Inspection, Section, _prepare_sections, Vector, utils, store_cxyz_to_offset_files
from Tile_refactored import Tile
import experiment_configs as cfg

import logging

### Set up logging
# logging.basicConfig(level=logging.DEBUG)
# logging.basicConfig(level=logging.INFO)
logging.basicConfig(level=logging.WARNING)

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
        configs = cfg.get_experiment_configurations()
        self.exp_config = configs[cfg.ExperimentName.ROLI_F1]
        self.inspection = Inspection(self.exp_config)
        self.processor = self.inspection.co_processor
        self.tile_ids = self.processor.get_largest_tile_id_map()
        self._section_cache = {}  # {sec_path: SectionObject}


    def get_trace(self, tid: str):
        return self.processor.get_full_trace(tid)


    def _get_overlap_context(self, tid_a: str, z: int, overlap_type: str) -> Optional[OverlapContext]:
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


# Initialize single instance
service = DataService()