from dash import html, Input, Output, State, callback, ctx, no_update, ALL
from interactive_inspector.data_service import service


# --- CALLBACK 1: MANAGE THE NUDGE STATE ---
@callback(
    [Output('manual-nudge-store', 'data'),
     Output('active-item-index', 'data')],
    [Input('nudge-left', 'n_clicks'),
     Input('nudge-right', 'n_clicks'),
     Input('nudge-up', 'n_clicks'),
     Input('nudge-down', 'n_clicks'),
     Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
     Input('keyboard-listener', 'n_events')],  # Trigger on the count, not just the key name
    [State('keyboard-listener', 'event'),  # Get the actual key from State instead
     State('nudge-step', 'value'),
     State('manual-nudge-store', 'data'),
     State('active-item-index', 'data')],
    prevent_initial_call=True
)
def handle_nudging(l, r, u, d, ov_clicks, n_events, key_event, step, current_nudge, current_active):
    trig = ctx.triggered_id

    # 1. Handle Selection Reset
    if isinstance(trig, dict) and trig.get('type') == 'plot-ov-btn':
        return {'dx': 0, 'dy': 0}, trig.get('index')

    if current_active is None:
        return no_update, no_update

    dx, dy = current_nudge.get('dx', 0), current_nudge.get('dy', 0)
    step = step if step else 10

    # 2. Logic for Keyboard (triggered by n_events)
    if trig == 'keyboard-listener' and key_event:
        key = key_event.get('key')
        if key == "ArrowLeft":
            dx -= step
        elif key == "ArrowRight":
            dx += step
        elif key == "ArrowUp":
            dy -= step
        elif key == "ArrowDown":
            dy += step

    # 3. Logic for Buttons
    else:
        if trig == 'nudge-left':  dx -= step
        if trig == 'nudge-right': dx += step
        if trig == 'nudge-up':    dy -= step
        if trig == 'nudge-down':  dy += step

    return {'dx': dx, 'dy': dy}, no_update


@callback(
    [Output('registration-log', 'children'),
     Output('integrated-overlap-graph', 'figure'),
     Output('integrated-ov-status', 'children')],
    [Input('manual-nudge-store', 'data'),
     Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
     Input('run-sofima-btn', 'n_clicks'),
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
    if trig == 'run-sofima-btn' and (trig_val or 0) > 0:
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
    fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'], manual_nudge=nudge)
    status = f"INSPECTING: T{item['tid']} | Z{item['z']} | Nudge: {nudge}"
    return no_update, fig, status
