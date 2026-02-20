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
     Input('active-item-index', 'data')],
    [State('selection-store', 'data'),
     State('manual-nudge-store', 'data')],
    prevent_initial_call=True
)
def handle_actions(nudge_trigger, calc_clicks, active_idx, selection_data, nudge_state):
    # 1. Gatekeeper: If no index is active or basket is empty, abort.
    if active_idx is None or not selection_data or active_idx >= len(selection_data):
        return no_update, no_update, "No tile selected"

    trig = ctx.triggered_id
    item = selection_data[active_idx]
    nudge = (nudge_state['dx'], nudge_state['dy'])

    # 2. Identify specifically what happened
    # Check if a 'compute-single-btn' was clicked
    is_compute_trigger = isinstance(trig, dict) and trig.get('type') == 'compute-single-btn'

    # We verify that at least one button in the ALL list has actually been clicked
    # This prevents the callback from running 'Calculate' logic on page load/selection
    btn_clicked = any(click is not None for click in calc_clicks)

    # LOGIC: Calculate (Only if the button was the trigger)
    if is_compute_trigger and btn_clicked:
        btn_idx = trig.get('index')
        calc_item = selection_data[btn_idx]
        current_nudge = nudge if btn_idx == active_idx else (0, 0)

        result = service.compute_coarse_shift(
            calc_item['tid'], calc_item['z'], calc_item['overlap'], initial_nudge=current_nudge
        )

        if isinstance(result, str):
            return html.Div(result, className="text-danger"), no_update, "Refinement Failed"

        log_msg = html.Div([
            html.P(f"Refinement Successful (T{item['tid']})", className="text-success mb-0"),
            html.Small(f"Final Vector: {result['refined']}", className="text-white-50")
        ])

        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
        return log_msg, fig, "Refinement Applied"

    # LOGIC: Re-Plot (Nudge or Active Item changed)
    # We use an 'elif' to ensure we don't try to plot while calculating
    elif trig == 'manual-nudge-store' or trig == 'active-item-index':
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'], manual_nudge=nudge)
        if fig is None:
            return no_update, no_update, "Failed to load overlap image"

        status = f"INSPECTING: T{item['tid']} | Z{item['z']} | Nudge: {nudge}"
        return no_update, fig, status

    return no_update, no_update, no_update