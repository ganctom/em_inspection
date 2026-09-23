import logging

import numpy as np
import numpy.typing as npt
from dash import no_update, html
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from interactive_inspector.constants import UIConstants, OverlapType, UI, KeyboardShortcuts
from layouts.components_layouts import selection_card, create_grid_navigator
from parameter_config import RegistrationConfig

from data_service import service


class InspectionWorkflowManager:
    """
    Orchestration layer separating Dash UI state evaluation from
    scientific domain execution.
    """

    @staticmethod
    def safe_extract_pattern_index(
            triggered_id: any,
            selection_data: list
    ) -> dict | None:
        """
        Validates pattern-matched triggers and enforces safe index bounds
        against selection state.
        """
        if not triggered_id or not selection_data:
            return None

        clicked_idx = triggered_id.get('index') if isinstance(triggered_id, dict) else None
        if clicked_idx is None or clicked_idx >= len(selection_data):
            logging.warning(f"Workflow: Extraction aborted. Index pointer out of bounds: {clicked_idx}")
            return None

        return selection_data[clicked_idx]


    @classmethod
    def handle_flow_visualization(
            cls,
            triggered_id: any,
            triggered_events: list,
            selection_data: list,
            settings_data: dict
    ):
        """
        Orchestrates calculation gating and execution for flow fields.
        """
        # 1. Structural Lifecycle Guards
        trig_val = triggered_events[0]['value'] if triggered_events else None
        if not trig_val or trig_val == 0:
            return no_update, no_update, no_update

        # 2. Domain Data Verification
        item = cls.safe_extract_pattern_index(triggered_id, selection_data)
        if not item:
            return no_update, "Index out of bounds.", no_update

        item_tid, item_z = item['tid'], item['z']
        trig_type = triggered_id.get('type') if isinstance(triggered_id, dict) else triggered_id

        # 3. Parameter Evaluation Logic
        do_clean_flow = False
        ui_config = None
        if trig_type == UIConstants.ID_BTN_CLEAN_FLOW:
            ui_config = RegistrationConfig(**settings_data['registration_config'])  # TODO
            do_clean_flow = True

        # 4. Backend Processing Ingestion
        fig = service.get_flow_fig(item_z, item_tid, ui_config, do_clean_flow)
        if fig is None:
            error_msg = service.message_queue.pop() if service.message_queue else "Unknown Error"
            return no_update, "Flow Error", html.Div(error_msg, className="text-danger")

        fig.update_layout(autosize=True, uirevision=True)
        return fig, f"Inspecting flow: t{item_tid} | z{item_z}", no_update


    @classmethod
    def handle_range_masks_visualization(
            cls,
            triggered_id: any,
            triggered_events: list,
            selection_data: list
    ):
        """
        Orchestrates range mask figure execution.
        """
        trig_val = triggered_events[0]['value'] if triggered_events else None
        if not trig_val or trig_val == 0:
            return no_update, no_update, no_update

        item = cls.safe_extract_pattern_index(triggered_id, selection_data)
        if not item:
            return no_update, "Index out of bounds.", no_update

        item_tid, item_z = item['tid'], item['z']

        fig = service.get_range_masks_fig(section_num=int(item_z), tile_id_num=int(item_tid))
        if fig is None:
            error_msg = service.message_queue.pop() if service.message_queue else "Unknown Error"
            return no_update, "Dynamic Range Masks Visualization Error", html.Div(error_msg, className="text-danger")

        fig.update_layout(autosize=True, uirevision=True)
        return fig, f"Inspecting range masks: t{item_tid} | z{item_z}", no_update


    @classmethod
    def handle_raw_tile_visualization(
            cls,
            triggered_id: any,
            triggered_events: list,
            selection_data: list
    ):
        """
        Orchestrates raw tile image acquisition and layout protection.
        """
        trig_val = triggered_events[0]['value'] if triggered_events else None
        if not trig_val or trig_val == 0:
            return no_update, no_update, no_update

        item = cls.safe_extract_pattern_index(triggered_id, selection_data)
        if not item:
            return no_update, "Index out of bounds.", no_update

        item_tid, item_z = item.get('tid'), item.get('z')

        try:
            fig = service.get_tile_image_fig(section_num=int(item_z), tile_id_num=int(item_tid))
            if fig is None:
                error_msg = service.message_queue.pop() if getattr(service, 'message_queue', None) else "Unknown Error"
                return no_update, "Tile Image Load Error", html.Div(error_msg, className="text-danger")

            fig.update_layout(autosize=True, uirevision=True)
            return fig, f"Inspecting raw tile image: t{item_tid} | z{item_z}", no_update

        except Exception as e:
            return no_update, f"Visualizer Crash: {str(e)}", html.Div(str(e), className="text-danger")


    @classmethod
    def handle_tile_overlap_replot(cls, active_idx: int, nudge_trigger: any, selection_data: list):
        """Orchestrates overlap figure generation and safely tracks vector nudges."""
        if not selection_data or active_idx is None or active_idx >= len(selection_data):
            return no_update, "Waiting for selection..."

        nudge_dict = nudge_trigger if isinstance(nudge_trigger, dict) else {}
        nudge = (nudge_dict.get('dx', 0), nudge_dict.get('dy', 0))

        item = selection_data[active_idx]
        tile_id = item.get('tid')
        sec_num = item.get('z')
        ov_type = item.get('overlap')

        try:
            fig = service.get_overlap_figure(tile_id, sec_num, ov_type, nudge)
            if fig is not None:
                fig.update_layout(autosize=True, uirevision=True)

            status = f"Inspecting overlap: t{tile_id} | s{sec_num} | Nudge: {nudge}"
            return fig, status

        except Exception as e:
            return no_update, html.Div(f"Rendering Error: {str(e)}", className="text-danger")


    @classmethod
    def handle_single_calculation(cls, triggered_id: any, triggered_events: list, selection_data: list,
                                  active_idx: int, nudge_trigger: any, search_rad: float):
        """Calculates specific vector shift profiles and returns the updated validation view."""
        trig_val = triggered_events[0]['value'] if triggered_events else None
        if not trig_val or trig_val == 0:
            return no_update, no_update, no_update

        btn_idx = triggered_id.get('index') if isinstance(triggered_id, dict) else None
        if btn_idx is None or btn_idx >= len(selection_data):
            return no_update, no_update, no_update

        calc_item = selection_data[btn_idx]
        item_tid, item_z, item_ov = calc_item['tid'], calc_item['z'], calc_item['overlap']

        safe_nudge = nudge_trigger if isinstance(nudge_trigger, dict) else {'dx': 0, 'dy': 0}
        nudge = (safe_nudge.get('dx', 0), safe_nudge.get('dy', 0))
        current_nudge = nudge if btn_idx == active_idx else (0, 0)

        result = service.compute_coarse_shift(
            item_tid, item_z, item_ov, initial_nudge=current_nudge, max_ext=search_rad
        )

        if isinstance(result, str):
            return html.Div(result, className="text-danger"), no_update, "Refinement Failed"

        item = selection_data[active_idx]
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])

        return (
            html.P(f"T{calc_item['tid']} Refined: {result['refined']}", className="text-success small"),
            fig,
            "Refinement Applied"
        )

    @classmethod
    def handle_selection_state_mutation(
            cls, triggered_id: any, sel_data: dict, clear_n: int,
            import_n: int, remove_n: list, current_store: list, grid_click: dict
    ):
        """Manages coordination profiles inside the active vector shopping basket."""
        if service.processor is None:
            return no_update

        # 1. Handle Clear All
        if triggered_id == 'clear-selection':
            service.clear_cache()
            return []

        # 2. Handle Individual Removal
        if isinstance(triggered_id, dict) and triggered_id.get('type') == 'remove-btn':
            return [item for i, item in enumerate(current_store) if i != triggered_id.get('index')]

        active_tid = grid_click['points'][0]['text'] if grid_click else None
        if not active_tid:
            return current_store

        new_store = list(current_store)

        # 3. Import of INF offsets
        if triggered_id == UI.ID_BTN_IMPORT_INF:
            inf_failures = service.processor.find_inf_offsets_for_tile(str(active_tid))
            for err in inf_failures:
                entry = {'tid': active_tid, 'z': err['z'], 'overlap': err['overlap'], 'type': 'INF_ERROR'}
                if entry not in new_store:
                    new_store.append(entry)
            return new_store

        # 4. Handle Graphical Selection (Lasso/Box/Click)
        if triggered_id == 'quad-plot' and sel_data and 'points' in sel_data:
            for p in sel_data['points']:
                if 'customdata' not in p or not p['customdata']:
                    continue

                overlap, entry_type = p['customdata']
                entry = {'tid': active_tid, 'z': p['x'], 'overlap': overlap, 'type': entry_type}
                if entry not in new_store:
                    new_store.append(entry)
            return new_store

        return no_update

    @staticmethod
    def sync_basket_ui_container(data: list):
        """Renders components dynamically based on basket storage states."""
        if not data:
            return html.Div("No vectors selected.", className="text-muted small italic p-2")
        return [selection_card(i, item) for i, item in enumerate(data)]

    @classmethod
    def handle_main_quad_visualization(cls, grid_click: dict, selection_store: list, dark_mode: list):
        """Generates continuous data traces with highlight elements."""
        if service.processor is None:
            return no_update

        raw_tid = grid_click['points'][0]['text'] if grid_click else None
        if not raw_tid:
            return go.Figure()

        trace_data = service.get_trace(str(raw_tid))
        if not trace_data or trace_data.shift_vectors is None:
            return go.Figure()

        sec_nums = trace_data.section_numbers
        shifts = trace_data.shift_vectors

        range_h, range_v = service.compute_auto_zoom_ranges(shifts, sec_nums)
        inf_failures = service.processor.find_inf_offsets_for_tile(str(raw_tid))

        fig = make_subplots(
            rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=UI.QUAD_PLOT_TITLES
        )

        configs = [(1, 1, 0, "H-dx"), (2, 1, 1, "H-dy"), (1, 2, 2, "V-dx"), (2, 2, 3, "V-dy")]

        # --- SECTION A: Plotting continuous data paths ---
        for r, c, idx, label in configs:
            ov_type = OverlapType.HORIZONTAL if c == 1 else OverlapType.VERTICAL
            c_data = [[ov_type, "MANUAL"]] * len(sec_nums)

            fig.add_trace(go.Scatter(
                x=sec_nums, y=shifts[idx, :], mode='lines+markers', name=label, customdata=c_data,
                marker=dict(size=4, color=UIConstants.TRACE_COLOR), line=dict(width=1), hoverinfo='x+y'
            ), row=r, col=c)

        # --- SECTION B: Overlay failure entries ---
        for ov_type, col in [(OverlapType.HORIZONTAL, 1), (OverlapType.VERTICAL, 2)]:
            axis_errors = [e for e in inf_failures if e['overlap'] == ov_type]
            if not axis_errors:
                continue

            inf_x = [e['z'] for e in axis_errors]
            inf_c_data = [[ov_type, "INF_ERROR"]] * len(inf_x)

            for row_pos, comp_idx in ([(1, 0), (2, 1)] if col == 1 else [(1, 2), (2, 3)]):
                y_ceil = service.get_inf_y_ceiling(shifts[comp_idx, :])

                fig.add_trace(go.Scatter(
                    x=inf_x, y=[y_ceil] * len(inf_x), mode='markers',
                    marker=dict(color='red', symbol='x', size=10), name=f"INF-{ov_type}",
                    customdata=inf_c_data, hovertext=f"Solver Fail: {ov_type}"
                ), row=row_pos, col=col)

        # --- SECTION C: Highlight active target parameters ---
        current_tid_selections = [s for s in selection_store if str(s['tid']) == str(raw_tid)]
        for pt in current_tid_selections:
            try:
                z_val = int(pt['z'])
                if z_val not in sec_nums:
                    continue

                data_idx = list(sec_nums).index(z_val)
                pt_ov = pt.get('overlap')
                is_h = (pt_ov == OverlapType.HORIZONTAL or str(pt_ov).endswith('HORIZONTAL'))

                col = 1 if is_h else 2
                idx_x, idx_y = (0, 1) if is_h else (2, 3)

                is_inf = pt.get('type') == 'INF_ERROR'
                h_color = "#FF851B" if is_inf else UIConstants.HIGHLIGHT_COLOR
                marker_style = dict(size=14, color=h_color, symbol='circle-open', line=dict(width=2))

                for row_num, shift_idx in [(1, idx_x), (2, idx_y)]:
                    y_val = shifts[shift_idx, data_idx]
                    if np.isinf(y_val):
                        y_val = service.get_inf_y_ceiling(shifts[shift_idx, :])

                    fig.add_trace(go.Scatter(
                        x=[z_val], y=[y_val], mode='markers', marker=marker_style, hoverinfo='skip'
                    ), row=row_num, col=col)
            except (ValueError, IndexError, KeyError):
                continue

        apply_padded_y_ranges(fig, shifts, UI.QUAD_PLOT_PAD_FCT)

        is_dark = len(dark_mode) > 0
        fig.update_layout(
            template="plotly_dark" if is_dark else "plotly_white",
            paper_bgcolor='rgba(0,0,0,0)' if is_dark else 'white',
            plot_bgcolor='rgba(0,0,0,0)' if is_dark else 'white',
            hovermode='x unified',
            xaxis=dict(range=range_h, autorange=False), xaxis3=dict(range=range_h, autorange=False),
            xaxis2=dict(range=range_v, autorange=False), xaxis4=dict(range=range_v, autorange=False),
            margin=dict(l=40, r=10, t=50, b=30), showlegend=False, uirevision=str(raw_tid)
        )

        return fig


    @classmethod
    def handle_batch_calculation(
            cls,
            n_clicks: int,
            selection_data: list,
            active_idx: int,
            nudge_trigger: any,
            guess_mode: str,
            m_dx: float, m_dy:
            float, search_rad: float
    ):
        """Orchestrates iterative batch refinement calculations over the entire selection basket."""
        if not n_clicks or not selection_data or active_idx is None or active_idx >= len(selection_data):
            return "Waiting for selection...", no_update, no_update

        safe_nudge = nudge_trigger if isinstance(nudge_trigger, dict) else {'dx': 0, 'dy': 0}
        nudge = (safe_nudge.get('dx', 0), safe_nudge.get('dy', 0))
        manual_ref = (m_dx or 0, m_dy or 0)
        is_manual = (guess_mode == "manual")

        results = []
        for s_item in selection_data:
            res = service.compute_coarse_shift(
                s_item['tid'], s_item['z'], s_item['overlap'],
                initial_nudge=nudge if not is_manual else (0, 0),
                override_vector=manual_ref if is_manual else None,
                max_ext=search_rad,
            )
            results.append((s_item, res))

        log_entries = [
            html.Div(f"T{s[0]['tid']}: {s[1]['refined']}" if isinstance(s[1], dict) else f"T{s[0]['tid']}: FAILED",
                     className="text-success small" if isinstance(s[1], dict) else "text-danger small")
            for s in results
        ]

        item = selection_data[active_idx]
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])

        return html.Div(log_entries), fig, "Batch Complete"

    @classmethod
    def handle_grid_navigation(cls, triggered_id: any, slider_val: int, click_data: dict,
                               manual_z: int, basket_data: list):
        """
        Orchestrates continuous section sequence indexing and cross-filters spatial tracking
        matrices using an optimized coordinate lookup interface.
        """
        if not triggered_id:
            return slider_val, no_update, no_update

        z_keys = getattr(service.processor, 'section_sequence', [])
        if not z_keys:
            logging.warning("Grid Navigator Workflow: Action aborted. Section sequence empty.")
            return no_update, no_update, no_update

        z_min, z_max = min(z_keys), max(z_keys)

        # Coordinate transformation tracking (SBFI EM depth-inversion mapping rule)
        if triggered_id == 'manual-z-input' and manual_z is not None:
            current_z = max(z_min, min(z_max, int(manual_z)))
            slider_val = (z_max + z_min) - current_z
        elif triggered_id == 'section-filter-slider' and slider_val is not None:
            current_z = (z_max + z_min) - slider_val
        else:
            current_z = (z_max + z_min) - slider_val if slider_val is not None else z_min

        active_tid = click_data['points'][0]['text'] if click_data else None
        registry = getattr(service.processor, '_inf_registry', {})
        dirty_tids = set(registry.keys())

        try:
            z_str = str(int(current_z))
            lookup = service.processor.get_section_lookup(z_str)
            available_tids = set(lookup.tile_to_coords.keys())
        except Exception as e:
            logging.warning(f"Workflow Map Refinement Failure on slice {current_z}: {e}")
            available_tids = set()

        fig = create_grid_navigator(
            tile_ids=service.tile_ids,
            active_tid=active_tid,
            dirty_tids=dirty_tids,
            available_tids=available_tids
        )

        return slider_val, fig, int(current_z)

    @classmethod
    def handle_keyboard_slice_navigation(cls, n_events: int, event: dict, current_slider_val: int):
        """Tracks keystroke events and maps them to vertical section incremental offsets."""
        if service.processor is None or not event or current_slider_val is None:
            return no_update

        z_keys = getattr(service.processor, 'section_sequence', [])
        if not z_keys:
            return no_update

        key = event.get("key", "").lower()

        if key == KeyboardShortcuts.KEY_GRID_NAV_SLIDER_PLUS:
            return min(current_slider_val + 1, max(z_keys))
        elif key == KeyboardShortcuts.KEY_GRID_NAV_SLIDER_MINUS:
            return max(current_slider_val - 1, min(z_keys))

        return no_update

    @classmethod
    def handle_nudge_and_basket_navigation(cls, triggered_id: any, key_event: dict, step_list: list,
                                           current_nudge: dict, current_active: int, selection_store: list):
        """
        Manages fine vector shifting delta updates and state machine index manipulation
        for active selections.
        """
        if service.processor is None:
            return no_update, no_update

        step = step_list[0] if step_list else 10

        if isinstance(triggered_id, dict):
            btn_type = triggered_id.get('type')
            btn_index = triggered_id.get('index')

            # --- A. Nudge Vector Logic ---
            if btn_type == 'nudge-btn':
                if current_active is None:
                    return no_update, no_update
                dx, dy = current_nudge.get('dx', 0), current_nudge.get('dy', 0)

                if btn_index == 'left':  dx -= step
                if btn_index == 'right': dx += step
                if btn_index == 'up':    dy -= step
                if btn_index == 'down':  dy += step
                return {'dx': dx, 'dy': dy}, no_update

            # --- B. Shopping Basket Navigation Logic ---
            if btn_type == 'nav-btn':
                if not selection_store:
                    return {'dx': 0, 'dy': 0}, None
                list_len = len(selection_store)
                idx = current_active if current_active is not None else 0

                if btn_index == 'first':
                    idx = 0
                elif btn_index == 'last':
                    idx = list_len - 1
                elif btn_index == 'prev':
                    idx = (idx - 1) % list_len
                elif btn_index == 'next':
                    idx = (idx + 1) % list_len
                return {'dx': 0, 'dy': 0}, idx

            # --- C. Target Toggle Logic ---
            if btn_type == UI.ID_BTN_PLOT_OV:
                return {'dx': 0, 'dy': 0}, btn_index

        # --- D. Keyboard Event Fallback Routing ---
        if triggered_id == 'keyboard-listener' and key_event and current_active is not None:
            dx, dy = current_nudge.get('dx', 0), current_nudge.get('dy', 0)
            key = key_event.get('key')

            if key == "ArrowLeft":
                dx -= step
            elif key == "ArrowRight":
                dx += step
            elif key == "ArrowUp":
                dy -= step
            elif key == "ArrowDown":
                dy += step
            else:
                return no_update, no_update

            return {'dx': dx, 'dy': dy}, no_update

        return no_update, no_update


def apply_padded_y_ranges(
        fig: go.Figure,
        shifts: npt.NDArray[np.float64],
        padding_factor: float
) -> None:
    """
    Calculates the finite bounding boxes for each row in the shifts matrix
    and applies a fractional headroom/footroom padding to the figure's y-axes.

    Mutates the layout of the provided fig object in place.
    """
    # Map layout (row, col) coordinates to raw 'shifts' matrix indices
    subplot_matrix_mapping: dict[tuple[int, int], int] = {
        (1, 1): 0,  # H-dx
        (2, 1): 1,  # H-dy
        (1, 2): 2,  # V-dx
        (2, 2): 3,  # V-dy
    }

    grid_ref = getattr(fig, "_grid_ref", None)

    for (r, c), matrix_idx in subplot_matrix_mapping.items():
        data_row = shifts[matrix_idx, :]
        finite_data = data_row[np.isfinite(data_row)]

        if finite_data.size == 0:
            continue

        y_min = finite_data.min()
        y_max = finite_data.max()
        y_range = y_max - y_min

        # Prevent arithmetic collapse on invariant/flatline inputs
        if y_range == 0.0:
            y_range = 1.0

        y_lower = y_min - (y_range * padding_factor)
        y_upper = y_max + (y_range * padding_factor)

        if grid_ref is not None:
            try:
                subplot_refs = grid_ref[r - 1][c - 1]
                if subplot_refs:
                    ref = subplot_refs[0]

                    if hasattr(ref, 'layout_keys') and len(ref.layout_keys) >= 2:
                        y_axis_key = ref.layout_keys[1]
                    else:
                        axis_id = ref.id.replace('x', '')
                        y_axis_key = f"yaxis{axis_id.replace('y', '')}" if axis_id != 'y' else 'yaxis'

                    fig.layout[y_axis_key].update(range=[y_lower, y_upper])
                else:
                    raise KeyError("Empty subplot reference list.")

            except (IndexError, AttributeError, KeyError) as e:
                logging.debug(f"Grid reference extraction failed, falling back to update. Error: {e}")
                fig.update_yaxes(range=[y_lower, y_upper], row=r, col=c)
        else:
            fig.update_yaxes(range=[y_lower, y_upper], row=r, col=c)
