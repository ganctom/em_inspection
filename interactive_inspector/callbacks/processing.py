from dash import html, Input, Output, State, ctx, no_update, ALL
from app import app
from data_service import service


# --- CALLBACK 1: MANAGE THE NUDGE STATE ---
# processing.py - Update handle_nudging callback

from dash import Input, Output, State, ctx, no_update, ALL


@app.callback(
    [Output('manual-nudge-store', 'data'),
     Output('active-item-index', 'data')],
    [Input({'type': 'nudge-btn', 'index': ALL}, 'n_clicks'),
     Input({'type': 'nav-btn', 'index': ALL}, 'n_clicks'),
     Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
     Input('keyboard-listener', 'n_events')],
    [State('keyboard-listener', 'event'),
     State({'type': 'nudge-config', 'index': ALL}, 'value'), # Changed to ALL
     State('manual-nudge-store', 'data'),
     State('active-item-index', 'data'),
     State('selection-store', 'data')],
    prevent_initial_call=True
)
def handle_nudging(nudge_clicks, nav_clicks, ov_clicks, n_events,
                   key_event, step_list, current_nudge, current_active, selection_store):
    # 1. Boilerplate Safety
    if service.processor is None or not ctx.triggered:
        return no_update, no_update

    trig = ctx.triggered_id

    # 2. Handle Pattern Matched Buttons (Nudge & Nav)
    # Extract the step value safely from the list
    step = step_list[0] if step_list else 10

    if isinstance(trig, dict):
        btn_type = trig.get('type')
        btn_index = trig.get('index')

        # --- A. NUDGE LOGIC ---
        if btn_type == 'nudge-btn':
            if current_active is None: return no_update, no_update
            dx, dy = current_nudge.get('dx', 0), current_nudge.get('dy', 0)
            s = step

            if btn_index == 'left':  dx -= s
            if btn_index == 'right': dx += s
            if btn_index == 'up':    dy -= s
            if btn_index == 'down':  dy += s
            return {'dx': dx, 'dy': dy}, no_update

        # --- B. NAVIGATION LOGIC ---
        if btn_type == 'nav-btn':
            if not selection_store: return {'dx': 0, 'dy': 0}, None
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

        # --- C. OVERLAP PLOT BUTTONS (Already pattern matched) ---
        if btn_type == 'plot-ov-btn':
            return {'dx': 0, 'dy': 0}, btn_index

    # 3. Handle Keyboard Nudging
    if trig == 'keyboard-listener' and key_event and current_active is not None:
        dx, dy = current_nudge.get('dx', 0), current_nudge.get('dy', 0)
        s = step if step else 10
        key = key_event.get('key')

        if key == "ArrowLeft":
            dx -= s
        elif key == "ArrowRight":
            dx += s
        elif key == "ArrowUp":
            dy -= s
        elif key == "ArrowDown":
            dy += s
        else:
            return no_update, no_update

        return {'dx': dx, 'dy': dy}, no_update

    return no_update, no_update


@app.callback(
    [Output('registration-log', 'children'),
     Output('integrated-overlap-graph', 'figure'),
     Output('integrated-ov-status', 'children')],
    [Input('manual-nudge-store', 'data'),
     Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
     Input('run-batch-btn', 'n_clicks'),
     Input('active-item-index', 'data')],
    [State('selection-store', 'data'),
     State('guess-mode-select', 'value'),
     State('manual-dx', 'value'),
     State('manual-dy', 'value')],
    prevent_initial_call=True
)
def handle_actions(nudge_trigger, single_clicks, batch_clicks, active_idx,
                   selection_data, guess_mode, m_dx, m_dy):
    # 1. Boilerplate Safety
    if not selection_data or active_idx is None or active_idx >= len(selection_data):
        return no_update, no_update, "Waiting for selection..."

    trig = ctx.triggered_id
    trig_val = ctx.triggered[0]['value'] if ctx.triggered else None

    # Standardize Nudge
    safe_nudge = nudge_trigger if isinstance(nudge_trigger, dict) else {'dx': 0, 'dy': 0}
    nudge = (safe_nudge.get('dx', 0), safe_nudge.get('dy', 0))
    manual_ref = (m_dx or 0, m_dy or 0)
    item = selection_data[active_idx]

    # --- CASE A: BATCH (THE LOOPED VERSION) ---
    if trig == 'run-batch-btn' and (trig_val or 0) > 0:
        results = []
        is_manual = (guess_mode == "manual")

        for s_item in selection_data:
            res = service.compute_coarse_shift(
                s_item['tid'],
                s_item['z'],
                s_item['overlap'],
                initial_nudge=nudge if not is_manual else (0, 0),
                override_vector=manual_ref if is_manual else None
            )
            results.append((s_item, res))

        # Format Log
        log_entries = []
        for s_item, res in results:
            if isinstance(res, dict):
                log_entries.append(html.Div(f"T{s_item['tid']}: {res['refined']}", className="text-success small"))
            else:
                log_entries.append(html.Div(f"T{s_item['tid']}: FAILED", className="text-danger small"))

        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
        return html.Div(log_entries), fig, "Batch Complete"

    # --- CASE B: SINGLE CALCULATION ---
    elif isinstance(trig, dict) and trig.get('type') == 'compute-single-btn' and (trig_val or 0) > 0:
        btn_idx = trig.get('index')
        calc_item = selection_data[btn_idx]

        # Use nudge only if it's the item we're looking at
        current_nudge = nudge if btn_idx == active_idx else (0, 0)

        result = service.compute_coarse_shift(
            calc_item['tid'], calc_item['z'], calc_item['overlap'], initial_nudge=current_nudge
        )

        if isinstance(result, str):
            return html.Div(result, className="text-danger"), no_update, "Refinement Failed"

        log_msg = html.Div([
            html.P(f"Refinement Successful (T{calc_item['tid']})", className="text-success mb-0"),
            html.Small(f"Final Vector: {result['refined']}", className="text-white-50")
        ])
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
        return log_msg, fig, "Refinement Applied"

    # --- CASE C: RE-PLOT ---
    if active_idx is not None:
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'], manual_nudge=nudge)
        status = f"INSPECTING: T{item['tid']} | Z{item['z']} | Nudge: {nudge}"
        return no_update, fig, status

    return no_update, no_update, no_update


@app.callback(
    Output('selection-list-container', 'aria-busy'),
    Input('selection-store', 'data'),
    prevent_initial_call=True
)
def handle_background_preload(selection_data):
    if selection_data and len(selection_data) > 0:
        service.preload_source_images(selection_data)
        return "true"
    return "false"

# --- CALLBACK: CLEAR BASKET & CACHE ---
@app.callback(
    [Output('selection-store', 'data', allow_duplicate=True),
     Output('active-item-index', 'data', allow_duplicate=True)],
    Input('clear-selection', 'n_clicks'),
    prevent_initial_call=True
)
def handle_clear_basket(n):
    if n:
        service.clear_cache() # Clear RAM
        return [], None
    return no_update, no_update