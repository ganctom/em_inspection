import numpy as np
from dash import Input, Output, State, callback, ctx, no_update, ALL, html
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from interactive_inspector.constants import UIConstants, OverlapType, KeyboardShortcuts
from interactive_inspector.data_service import service
from interactive_inspector.layouts.components import selection_card, create_grid_navigator


@callback(
    Output('selection-store', 'data'),
    [Input('quad-plot', 'selectedData'),
     Input('clear-selection', 'n_clicks'),
     Input('import-inf-btn', 'n_clicks'),
     Input({'type': 'remove-btn', 'index': ALL}, 'n_clicks')],
    [State('selection-store', 'data'), State('master-grid', 'clickData')],
    prevent_initial_call=True
)
def handle_selection_state(sel_data, clear_n, import_n, remove_n, current_store, grid_click):
    trigger = ctx.triggered_id

    # 1. Handle Clear All
    if trigger == 'clear-selection':
        service.clear_cache()
        return []

    # 2. Handle Individual Removal
    if isinstance(trigger, dict) and trigger.get('type') == 'remove-btn':
        return [item for i, item in enumerate(current_store) if i != trigger.get('index')]

    # Ensure we know which tile we are working with
    active_tid = grid_click['points'][0]['text'] if grid_click else None
    if not active_tid:
        return current_store

    new_store = list(current_store)

    # 3. Import of INF offsets
    if trigger == 'import-inf-btn':
        inf_failures = service.processor.find_inf_offsets_for_tile(str(active_tid))
        for err in inf_failures:
            entry = {
                'tid': active_tid,
                'z': err['z'],
                'overlap': err['overlap'],
                'type': 'INF_ERROR'
            }
            if entry not in new_store:
                new_store.append(entry)
        return new_store

    # 4. Handle Graphical Selection (Lasso/Box/Click)
    if trigger == 'quad-plot' and sel_data and 'points' in sel_data:
        for p in sel_data['points']:
            if 'customdata' not in p or not p['customdata']:
                continue

            overlap, entry_type = p['customdata']
            entry = {
                'tid': active_tid,
                'z': p['x'],
                'overlap': overlap,
                'type': entry_type
            }

            if entry not in new_store:
                new_store.append(entry)
        return new_store

    return no_update


@callback(
    Output('selection-list-container', 'children'),
    Input('selection-store', 'data')
)
def sync_selection_ui(data):
    """Updates the 'Basket' UI whenever the store changes."""
    if not data:
        return html.Div("No vectors selected.", className="text-muted small italic p-2")
    return [selection_card(i, item) for i, item in enumerate(data)]


@callback(
    Output('quad-plot', 'figure'),
    [Input('master-grid', 'clickData'),
     Input('selection-store', 'data'),
     Input('theme-switch', 'value')]
)
def render_main_visuals(grid_click, selection_store, dark_mode):
    # 1. Exit early if no tile selected
    raw_tid = grid_click['points'][0]['text'] if grid_click else None
    if not raw_tid:
        return go.Figure()

    trace_data = service.get_trace(str(raw_tid))
    if not trace_data or trace_data.shift_vectors is None:
        return go.Figure()

    sec_nums = trace_data.section_numbers
    shifts = trace_data.shift_vectors

    # 2. Determine Column-Specific Auto-Zoom Ranges
    def get_range_for_indices(indices):
        sub_shifts = shifts[indices, :]
        mask = ~np.isnan(sub_shifts).all(axis=0)
        if np.any(mask):
            valid_idx = np.where(mask)[0]
            return [int(sec_nums[valid_idx[0]]) - 2, int(sec_nums[valid_idx[-1]]) + 2]
        return [int(min(sec_nums)), int(max(sec_nums))]

    range_h = get_range_for_indices([0, 1])
    range_v = get_range_for_indices([2, 3])

    # 3. Create Subplots
    fig = make_subplots(
        rows=2, cols=2,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("H-Overlap: Δx", "V-Overlap: Δx", "H-Overlap: Δy", "V-Overlap: Δy")
    )

    configs = [
        (1, 1, 0, "H-dx"), (2, 1, 1, "H-dy"),
        (1, 2, 2, "V-dx"), (2, 2, 3, "V-dy")
    ]

    def get_inf_y_positions(data_row):
        finite_data = data_row[np.isfinite(data_row)]
        return np.max(finite_data) if len(finite_data) > 0 else 0

    # Pull pre-indexed Inf offsets from the Registry
    inf_failures = service.processor.find_inf_offsets_for_tile(str(raw_tid))

    # --- SECTION 3: Main Data Plotting (Refactored) ---
    for r, c, idx, label in configs:
        # Determine overlap enum for this specific subplot config
        ov_type = OverlapType.HORIZONTAL if c == 1 else OverlapType.VERTICAL

        # We store [OverlapType, EntryType] in each point
        c_data = [[ov_type, "MANUAL"]] * len(sec_nums)

        fig.add_trace(go.Scatter(
            x=sec_nums, y=shifts[idx, :],
            mode='lines+markers', name=label,
            customdata=c_data,  # <--- Metadata attached here
            marker=dict(size=4, color=UIConstants.TRACE_COLOR),
            line=dict(width=1), hoverinfo='x+y'
        ), row=r, col=c)

    # --- SECTION 4: Integrated INF Failures (Grouped & CustomData) ---
    for ov_type, col in [(OverlapType.HORIZONTAL, 1), (OverlapType.VERTICAL, 2)]:
        axis_errors = [e for e in inf_failures if e['overlap'] == ov_type]
        if not axis_errors: continue

        inf_x = [e['z'] for e in axis_errors]
        # Metadata for INF points
        inf_c_data = [[ov_type, "INF_ERROR"]] * len(inf_x)

        for row_pos, comp_idx in ([(1, 0), (2, 1)] if col == 1 else [(1, 2), (2, 3)]):
            y_ceil = get_inf_y_positions(shifts[comp_idx, :])

            fig.add_trace(go.Scatter(
                x=inf_x, y=[y_ceil] * len(inf_x),
                mode='markers',
                marker=dict(color='red', symbol='x', size=10),
                name=f"INF-{ov_type}",
                customdata=inf_c_data,  # <--- Metadata attached here
                hovertext=f"Solver Fail: {ov_type}"
            ), row=row_pos, col=col)

    # 5. Dynamic Highlights (Manual + Failures in Basket)
    current_tid_selections = [s for s in selection_store if str(s['tid']) == str(raw_tid)]
    for pt in current_tid_selections:
        try:
            z_val = int(pt['z'])
            if z_val not in sec_nums:
                continue

            # Map Z-value to matrix index
            data_idx = list(sec_nums).index(z_val)

            # Robust Enum Check
            pt_ov = pt.get('overlap')
            is_h = (pt_ov == OverlapType.HORIZONTAL or str(pt_ov).endswith('HORIZONTAL'))

            col = 1 if is_h else 2
            idx_x, idx_y = (0, 1) if is_h else (2, 3)

            # Style: Orange for INF failures, Cyan/Theme for manual
            is_inf = pt.get('type') == 'INF_ERROR'
            h_color = "#FF851B" if is_inf else UIConstants.HIGHLIGHT_COLOR

            marker_style = dict(
                size=14, color=h_color,
                symbol='circle-open', line=dict(width=2)
            )

            # Define Row 1 (dx) and Row 2 (dy) plotting logic
            for row_num, shift_idx in [(1, idx_x), (2, idx_y)]:
                y_val = shifts[shift_idx, data_idx]

                # If we are highlighting an INF point, don't let the circle float to infinity
                if np.isinf(y_val):
                    y_val = get_inf_y_positions(shifts[shift_idx, :])

                fig.add_trace(go.Scatter(
                    x=[z_val], y=[y_val],
                    mode='markers', marker=marker_style, hoverinfo='skip'
                ), row=row_num, col=col)

        except (ValueError, IndexError, KeyError):
            continue

    # 6. Final Layout
    is_dark = len(dark_mode) > 0
    fig.update_layout(
        template="plotly_dark" if is_dark else "plotly_white",
        paper_bgcolor='rgba(0,0,0,0)' if is_dark else 'white',
        plot_bgcolor='rgba(0,0,0,0)' if is_dark else 'white',
        hovermode='x unified',
        xaxis=dict(range=range_h, autorange=False),
        xaxis3=dict(range=range_h, autorange=False),
        xaxis2=dict(range=range_v, autorange=False),
        xaxis4=dict(range=range_v, autorange=False),
        margin=dict(l=40, r=10, t=50, b=30),
        showlegend=False,
        uirevision=str(raw_tid)
    )

    return fig




@callback(
    Output('registration-log', 'children', allow_duplicate=True),
    Input('save-cxyz-btn', 'n_clicks'),
    prevent_initial_call=True
)
def handle_persist_to_disk(n_clicks):
    if not n_clicks:
        return no_update
    try:
        service.processor.save_offsets_to_disk()
        return html.Div([
            html.P("💾 CXYZ File Updated", className="text-warning mb-0 fw-bold"),
            html.Small("Modifications persisted to disk.", className="text-white-50")
        ])
    except Exception as e:
        return html.Div(f"Save Failed: {str(e)}", className="text-danger")



@callback(
    Output("manual-input-container", "style"),
    Input("guess-mode-select", "value")
)
def toggle_manual_input(mode):
    return {"display": "block"} if mode == "manual" else {"display": "none"}


@callback(
    Output('registration-log', 'children', allow_duplicate=True),
    Input('export-sections-btn', 'n_clicks'),
    prevent_initial_call=True
)
def handle_export_sections(n_clicks):
    if not n_clicks:
        return no_update

    try:
        service.store_offsets_to_yamls()

        return html.Div([
            html.P("🚀 Storing coarse offsets to section cx_cy files", className="text-info mb-0 fw-bold"),
            html.Small("Coarse offsets have been stored.", className="text-white-50")
        ])
    except Exception as e:
        return html.Div([
            html.P("❌ Export Failed", className="text-danger mb-0 fw-bold"),
            html.Small(str(e), className="text-white small")
        ])


@callback(
    [Output('section-filter-slider', 'value'),
     Output('master-grid', 'figure'),
     Output('manual-z-input', 'value')],
    [Input('section-filter-slider', 'value'),
     Input('master-grid', 'clickData'),
     Input('manual-z-input', 'value')],
    [State('selection-store', 'data')],
    prevent_initial_call=True
)
def grid_navigator_callback(slider_val, click_data, manual_z, basket_data):
    trigger = ctx.triggered_id

    # 1. Setup bounds
    tile_maps = getattr(service.processor, 'tile_id_maps_obj', {})
    z_keys = sorted([int(z) for z in tile_maps.keys()])
    if not z_keys:
        return no_update, no_update, no_update

    z_min, z_max = min(z_keys), max(z_keys)

    # 2. Resolve Current Z logic
    if trigger == 'manual-z-input' and manual_z is not None:
        # User typed a number. Clamp it to valid range.
        current_z = max(z_min, min(z_max, int(manual_z)))
        # Map logical Z back to the slider's visual position
        # (Assuming visual max at top = logical min)
        slider_val = (z_max + z_min) - current_z

    elif trigger == 'section-filter-slider' and slider_val is not None:
        # Slider moved. Map visual position to logical Z.
        current_z = (z_max + z_min) - slider_val

    else:
        # Fallback/Initial state or clickData trigger
        # Calculate current_z from the existing slider_val
        current_z = (z_max + z_min) - slider_val if slider_val is not None else z_min

    # 3. Generate the Grid Figure
    active_tid = click_data['points'][0]['text'] if click_data else None
    registry = getattr(service.processor, '_inf_registry', {})
    dirty_tids = set(registry.keys())

    z_str = str(int(current_z))
    z_map = tile_maps.get(z_str)
    available_tids = set(z_map[z_map != -1].flatten().astype(int)) if z_map is not None else set()

    fig = create_grid_navigator(
        service.tile_ids,
        active_tid=active_tid,
        dirty_tids=dirty_tids,
        available_tids=available_tids
    )

    # 4. Sync the UI
    # We return the new slider_val and the confirmed current_z to the input box
    return slider_val, fig, int(current_z)


@callback(
    Output('section-filter-slider', 'value', allow_duplicate=True),
    Input('keyboard-listener', 'n_events'),
    State('keyboard-listener', 'event'),
    State('section-filter-slider', 'value'),
    prevent_initial_call=True
)
def handle_keyboard_nav(n_events, event, current_slider_val):
    if not event or current_slider_val is None:
        return no_update

    tile_maps = getattr(service.processor, 'tile_id_maps_obj', {})
    z_keys = [int(z) for z in tile_maps.keys()]
    if not z_keys:
        return no_update

    # Normalize key to lowercase to handle 'W' and 'w'
    key = event.get("key", "").lower()

    # Logic:
    # 'w' -> Move slider handle UP (Increase slice number)
    # 's' -> Move slider handle DOWN (Decrease slice number)
    if key == KeyboardShortcuts.KEY_GRID_NAV_SLIDER_PLUS:
        new_val = min(current_slider_val + 1, max(z_keys))
        return new_val
    elif key == KeyboardShortcuts.KEY_GRID_NAV_SLIDER_MINUS:
        new_val = max(current_slider_val - 1, min(z_keys))
        return new_val

    return no_update