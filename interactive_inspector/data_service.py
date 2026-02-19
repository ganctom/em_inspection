import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from dataclasses import dataclass, fields
import logging
from typing import Optional, Tuple, Any, Dict
import plotly.express as px
import numpy as np

from inspection_refactored import Inspection, Section, _prepare_sections, Vector, utils
from Tile_refactored import Tile
import experiment_configs as cfg

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

        context = self._resolve_overlap_context(z_str, tid_a_int, ov_type)
        if not context:
            return None
        y, x, tid_b, axis = context

        section = self._get_initialized_section(z)
        if not section:
            return None

        raw_vec = self.processor.get_shift_vec(z, axis, y, x)
        print(f'raw_vec: {raw_vec}')
        shift_vec: Vector = tuple(np.round(raw_vec).astype(int))

        return OverlapContext(
            section=section,
            tid_a=tid_a_int,
            tid_b=tid_b,
            axis=axis,
            y=y,
            x=x,
            shift_vec=shift_vec
        )


    def get_overlap_figure_(self, tid_a: str, z: int, overlap_type: str) -> Optional[px.imshow]:
        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx:
            return None

        print(f'plotting ov with shift vec.: {ctx.shift_vec}')

        try:
            img_array = ctx.section.plot_ov(
                tid_a=ctx.tid_a,
                tid_b=ctx.tid_b,
                shift_vec=ctx.shift_vec,
                blur=1.2,
                clahe=True,
                rotate_vert=True,
                return_img=True,
                show_plot=False,
            )
        except Exception as e:
            logging.error(f"Failed to plot overlap for Z:{z} T:{tid_a}: {e}")
            return None

        if img_array is None:
            return None

        return self._build_plotly_figure(img_array, tid_a, ctx['tid_b'], overlap_type.upper(), z)

    def get_overlap_figure(
            self,
            tid_a: str,
            z: int,
            overlap_type: str,
            manual_nudge: Tuple[int, int] = (0, 0)
    ) -> Optional[px.imshow]:

        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx: return None

        # Apply the nudge to the loaded shift vector
        nudged_vec = (
            ctx.shift_vec[0] + manual_nudge[0],
            ctx.shift_vec[1] + manual_nudge[1]
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


    def compute_coarse_shift_(self, tid_a: str, z: int, overlap_type: str):
        """
        Calculates a new shift vector using the backend processor.
        """
        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx:
            return "Context Error"

        # Run refining using pyramidal search
        levels: int = 4
        max_ext: int = 250
        stride: int = 60

        section: Section = ctx.section
        orig_shift: Vector = ctx.shift_vec
        print(f'old vec: {orig_shift}')
        tid_a: int = ctx.tid_a
        tid_b: int = ctx.tid_b
        is_vert: bool = bool(ctx.axis)

        try:
            current_shift = orig_shift
            t1 = Tile(section.tile_dicts[tid_a])
            t2 = Tile(section.tile_dicts[tid_b])

            for i, (max_ext, stride) in enumerate(utils.get_pyramid(
                    levels, max_ext, stride)
            ):
                try:
                    current_shift, _ = section.refine_coarse_offset_eval_ov(
                        offset=current_shift,
                        tile_pair=(t1, t2),
                        is_vert=is_vert,
                        max_ext=max_ext,
                        stride=stride
                    )
                except TypeError as e:
                    current_shift = (np.nan, np.nan)  # Refining offset failed for some reason
                    logging.error(f"Calculation failed: {e}")
                    continue

            # Optionally update the internal processor state so get_overlap_figure
            # picks up the new vector immediately on the next call
            print(f'new_vec: {current_shift}')

            if np.nan in current_shift:
                logging.error(f"Calculation failed: {current_shift}")
                return f"Error: {current_shift}"

            self.processor.update_shift_vec(z, ctx.axis, ctx.y, ctx.x, current_shift)
            return current_shift

        except Exception as e:
            logging.error(f"Calculation failed: {e}")
            return f"Error: {e}"

    def compute_coarse_shift(self, tid_a: str, z: int, overlap_type: str, initial_nudge: Tuple[int, int] = (0, 0)):
        """
        Calculates a new shift vector using a manual nudge as the starting point.
        """
        ctx = self._get_overlap_context(tid_a, z, overlap_type)
        if not ctx:
            return "Context Error"

        # Pyramidal parameters - can be tuned
        levels: int = 1
        max_ext: int = 30
        stride: int = 5

        section: Section = ctx.section
        start_offset: Vector = (
            ctx.shift_vec[0] + initial_nudge[0],
            ctx.shift_vec[1] + initial_nudge[1]
        )

        tid_a_int: int = ctx.tid_a
        tid_b: int = ctx.tid_b
        is_vert: bool = bool(ctx.axis)

        try:
            current_shift = start_offset
            t1 = Tile(section.tile_dicts[tid_a_int])
            t2 = Tile(section.tile_dicts[tid_b])

            for max_ext, stride in utils.get_pyramid(levels, max_ext, stride):
                try:
                    current_shift, _ = section.refine_coarse_offset_eval_ov(
                        offset=current_shift,
                        tile_pair=(t1, t2),
                        is_vert=is_vert,
                        max_ext=max_ext,
                        stride=stride
                    )
                except TypeError:
                    current_shift = (np.nan, np.nan)
                    continue

            if np.isnan(current_shift).any():
                return "Refinement failed to converge."

            # Update the processor so the change persists in the session
            self.processor.update_shift_vec(z, ctx.axis, ctx.y, ctx.x, current_shift)

            return {
                "initial": ctx.shift_vec,  # The very first one from DB
                "nudged_start": start_offset,  # Where the user moved it to
                "refined": current_shift  # The final result
            }

        except Exception as e:
            logging.error(f"Calculation failed: {e}")
            return str(e)


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