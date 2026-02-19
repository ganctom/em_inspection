# from dash import html, Input, Output, State, callback, ctx, no_update, ALL
# from interactive_inspector.data_service import service
#
# """
# This file handles the buttons that actually do something with your data.
# By separating this from the navigation, you can easily add heavy-duty backend
# tasks (like starting a Celery worker or a subprocess) without cluttering your plotting code.
# """
#
#
# # @callback(
# #     [Output('registration-log', 'children'),
# #      Output('integrated-overlap-graph', 'figure'),
# #      Output('integrated-ov-status', 'children')],
# #     [Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
# #      Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
# #      Input('open-sofima', 'n_clicks')],
# #     [State('selection-store', 'data')],
# #     prevent_initial_call=True
# # )
# # def handle_actions(ov_clicks, calc_clicks, sofima_n, data):
# #     trig = ctx.triggered_id
# #     if not trig or not ctx.triggered:
# #         return no_update, no_update, no_update
# #
# #     triggered_val = ctx.triggered[0]['value']
# #     if triggered_val is None or triggered_val == 0:
# #         return no_update, no_update, no_update
# #
# #     # 1. Handle Integrated Overlap Plotting
# #     if isinstance(trig, dict) and trig.get('type') == 'plot-ov-btn':
# #         idx = trig.get('index')
# #         if idx >= len(data): return no_update, no_update, no_update
# #         item = data[idx]
# #         fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
# #         status_msg = f"Tile {item['tid']} | Z={item['z']} | Type: {item['overlap']}"
# #         log_msg = f"Loaded Overlap: {status_msg}"
# #         return log_msg, fig, status_msg
# #
# #     # 2. Handle Global SOFIMA
# #     if trig == 'open-sofima':
# #         return f"Running SOFIMA on {len(data)} items...", no_update, "Processing batch..."
# #
# #     # 3. Handle Single Calculation
# #     if isinstance(trig, dict) and trig.get('type') == 'compute-single-btn':
# #         idx = trig.get('index')
# #         if idx >= len(data): return no_update, no_update, no_update
# #
# #         item = data[idx]
# #         tid, z, ov_type = item['tid'], item['z'], item['overlap']
# #
# #         # Perform computation
# #         print(f'computing shift: {tid, z, ov_type}')
# #         new_vec = service.compute_coarse_shift(tid, z, ov_type)
# #
# #         # Generate the updated figure with the new vector applied
# #         fig = service.get_overlap_figure(tid, z, ov_type)
# #
# #         status_msg = f"Re-calculated T{tid} | New Vector: {new_vec}"
# #         log_msg = f"{status_msg}"
# #
# #         return log_msg, fig, status_msg
# #
# #
# #     return no_update, no_update, no_update
#
#
# @callback(
#     [Output('registration-log', 'children'),
#      Output('integrated-overlap-graph', 'figure'),
#      Output('integrated-ov-status', 'children')],
#     [Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
#      Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
#      Input('manual-nudge-store', 'data')],  # Now responds to nudges!
#     [State('selection-store', 'data'),
#      State('manual-nudge-store', 'data')],
#     prevent_initial_call=True
# )
# def handle_actions(ov_clicks, calc_clicks, nudge_input, data, nudge_state):
#     trig = ctx.triggered_id
#     if not trig: return no_update, no_update, no_update
#
#     # Determine which item we are talking about
#     # Usually we track the "active" item in a Store, but for now we'll use the last clicked index
#     idx = trig.get('index') if isinstance(trig, dict) else 0
#     item = data[idx]
#
#     # Current nudge values from the store
#     nudge = (nudge_state['dx'], nudge_state['dy'])
#
#     # CASE A: User clicked "OV" or moved the "Nudge" buttons
#     if (isinstance(trig, dict) and trig.get('type') == 'plot-ov-btn') or trig == 'manual-nudge-store':
#         fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'], manual_nudge=nudge)
#         status = f"T{item['tid']} | Nudge: {nudge}"
#         return no_update, fig, status
#
#     # CASE B: User clicked "Calc"
#     if isinstance(trig, dict) and trig.get('type') == 'compute-single-btn':
#         result = service.compute_coarse_shift(item['tid'], item['z'], item['overlap'], initial_nudge=nudge)
#
#         if isinstance(result, str):  # Error message
#             return html.Div(result, className="text-danger"), no_update, "Error"
#
#         # Success: Show the journey from DB -> Nudge -> Final
#         log_msg = html.Div([
#             html.P("Refinement Successful", className="text-success fw-bold"),
#             html.Small(f"DB Vector: {result['initial']}"), html.Br(),
#             html.Small(f"User Nudge Start: {result['nudged_start']}", className="text-info"), html.Br(),
#             html.P(f"FINAL: {result['refined']}", className="text-white fw-bold")
#         ])
#
#         # Refresh figure with final refined vector (nudge reset to 0 internally now)
#         fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
#         return log_msg, fig, "Refinement Complete"
#
#     return no_update, no_update, no_update
#


from dash import html, Input, Output, State, callback, ctx, no_update, ALL
from interactive_inspector.data_service import service


# --- CALLBACK 1: MANAGE THE NUDGE STATE ---
@callback(
    [Output('manual-nudge-store', 'data'),
     Output('active-item-index', 'data')],  # ADD THIS OUTPUT
    [Input('nudge-left', 'n_clicks'),
     Input('nudge-right', 'n_clicks'),
     Input('nudge-up', 'n_clicks'),
     Input('nudge-down', 'n_clicks'),
     Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks')],
    [State('nudge-step', 'value'),
     State('manual-nudge-store', 'data'),
     State('active-item-index', 'data')],
    prevent_initial_call=True
)
def handle_nudging(l, r, u, d, ov_clicks, step, current_nudge, current_active):
    trig = ctx.triggered_id

    # CASE: New Tile Selected
    if isinstance(trig, dict) and trig.get('type') == 'plot-ov-btn':
        new_idx = trig.get('index')
        return {'dx': 0, 'dy': 0}, new_idx  # Reset nudge AND update active index

    # CASE: Nudging existing tile
    if current_active is None:
        return no_update, no_update

    dx, dy = current_nudge.get('dx', 0), current_nudge.get('dy', 0)
    step = step if step else 10

    if trig == 'nudge-left':  dx -= step
    if trig == 'nudge-right': dx += step
    if trig == 'nudge-up':    dy -= step
    if trig == 'nudge-down':  dy += step

    return {'dx': dx, 'dy': dy}, no_update


# --- CALLBACK 2: EXECUTE ACTIONS (PLOTTING & CALC) ---
@callback(
    [Output('registration-log', 'children'),
     Output('integrated-overlap-graph', 'figure'),
     Output('integrated-ov-status', 'children')],
    [Input('manual-nudge-store', 'data'),
     Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
     Input('active-item-index', 'data')], # Trigger refresh when active item changes
    [State('selection-store', 'data'),
     State('manual-nudge-store', 'data'),
     State('active-item-index', 'data')],
    prevent_initial_call=True
)
def handle_actions(nudge_trigger, calc_clicks, active_trigger, selection_data, nudge_state, active_idx):
    # If no item is active, we have nothing to do
    if active_idx is None or active_idx >= len(selection_data):
        return no_update, no_update, "No tile selected"

    item = selection_data[active_idx]
    nudge = (nudge_state['dx'], nudge_state['dy'])

    trig = ctx.triggered_id

    # LOGIC: Re-Plot (Nudge or Active Item changed)
    if trig == 'manual-nudge-store' or trig == 'active-item-index':
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'], manual_nudge=nudge)
        status = f"INSPECTING: T{item['tid']} | Z{item['z']} | Nudge: {nudge}"
        return no_update, fig, status

    # LOGIC: Calculate
    if isinstance(trig, dict) and trig.get('type') == 'compute-single-btn':
        # Ensure we only calculate for the button actually pressed
        # or verify the pressed button matches the active index
        btn_idx = trig.get('index')
        calc_item = selection_data[btn_idx]

        # Use the nudge only if the button clicked is the one currently on screen
        current_nudge = nudge if btn_idx == active_idx else (0, 0)

        result = service.compute_coarse_shift(
            calc_item['tid'], calc_item['z'], calc_item['overlap'],initial_nudge=current_nudge
        )

        if isinstance(result, str):  # Error
            return html.Div(result, className="text-danger"), no_update, "Refinement Failed"

        log_msg = html.Div([
            html.P(f"Refinement Successful (T{item['tid']})", className="text-success mb-0"),
            html.Small(f"Final Vector: {result['refined']}", className="text-white-50")
        ])

        # Plot the final result
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
        return log_msg, fig, "Refinement Applied"

    return no_update, no_update, no_update