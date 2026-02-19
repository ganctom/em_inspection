from dash import Input, Output, State, callback, ctx, no_update, ALL
from interactive_inspector.data_service import service

"""
This file handles the buttons that actually do something with your data. 
By separating this from the navigation, you can easily add heavy-duty backend 
tasks (like starting a Celery worker or a subprocess) without cluttering your plotting code.
"""


@callback(
    [Output('registration-log', 'children'),
     Output('integrated-overlap-graph', 'figure'),
     Output('integrated-ov-status', 'children')],
    [Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
     Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
     Input('open-sofima', 'n_clicks')],
    [State('selection-store', 'data')],
    prevent_initial_call=True
)
def handle_actions(ov_clicks, calc_clicks, sofima_n, data):
    trig = ctx.triggered_id
    if not trig or not ctx.triggered:
        return no_update, no_update, no_update

    triggered_val = ctx.triggered[0]['value']
    if triggered_val is None or triggered_val == 0:
        return no_update, no_update, no_update

    # 1. Handle Integrated Overlap Plotting
    if isinstance(trig, dict) and trig.get('type') == 'plot-ov-btn':
        idx = trig.get('index')
        if idx >= len(data): return no_update, no_update, no_update
        item = data[idx]
        fig = service.get_overlap_figure(item['tid'], item['z'], item['overlap'])
        status_msg = f"Tile {item['tid']} | Z={item['z']} | Type: {item['overlap']}"
        log_msg = f"Loaded Overlap: {status_msg}"
        return log_msg, fig, status_msg

    # 2. Handle Global SOFIMA
    if trig == 'open-sofima':
        return f"Running SOFIMA on {len(data)} items...", no_update, "Processing batch..."

    # 3. Handle Single Calculation
    if isinstance(trig, dict) and trig.get('type') == 'compute-single-btn':
        idx = trig.get('index')
        item = data[idx]
        return f"Re-calculating {item['tid']}...", no_update, no_update

    return no_update, no_update, no_update
