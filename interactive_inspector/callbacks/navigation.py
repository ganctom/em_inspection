from dash import Input, Output, State, callback, ctx, no_update, ALL, html
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from interactive_inspector.constants import UIConstants, OverlapType
from interactive_inspector.data_service import service
from interactive_inspector.layouts.components import selection_card, create_grid_navigator


@callback(
    Output('selection-store', 'data'),
    [Input('quad-plot', 'selectedData'),
     Input('clear-selection', 'n_clicks'),
     Input({'type': 'remove-btn', 'index': ALL}, 'n_clicks')],
    [State('selection-store', 'data'), State('master-grid', 'clickData')],
    prevent_initial_call=True
)
def handle_selection_state(sel_data, clear_n, remove_n, current_store, grid_click):
    trigger = ctx.triggered_id

    # 1. Clear All
    if trigger == 'clear-selection':
        return []

    # 2. Remove Specific Item (Pattern Matching)
    if isinstance(trigger, dict) and trigger.get('type') == 'remove-btn':
        return [item for i, item in enumerate(current_store) if i != trigger.get('index')]

    # 3. Add New Selections from Graph
    if sel_data and 'points' in sel_data:
        tid = grid_click['points'][0]['text'] if grid_click else "N/A"
        new_store = list(current_store)

        for p in sel_data['points']:
            overlap = UIConstants.SELECTION_MAP.get(p.get('curveNumber'))
            if not overlap:
                continue

            entry = {'tid': tid, 'z': p['x'], 'overlap': overlap}
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
    """Renders the 4-panel trace view with current selections highlighted."""
    raw_tid = grid_click['points'][0]['text'] if grid_click else None
    if not raw_tid:
        return go.Figure()

    trace_data = service.get_trace(str(raw_tid))
    if not trace_data or trace_data.shift_vectors is None:
        return go.Figure()

    sec_nums = trace_data.section_numbers
    shifts = trace_data.shift_vectors

    fig = make_subplots(
        rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("H-Overlap: Δx", "V-Overlap: Δx", "H-Overlap: Δy", "V-Overlap: Δy")
    )

    # Standardized trace configurations (Row, Col, Index in shift_vectors, Label)
    configs = [
        (1, 1, 0, "H-dx"), (2, 1, 1, "H-dy"),
        (1, 2, 2, "V-dx"), (2, 2, 3, "V-dy")
    ]

    for r, c, idx, label in configs:
        fig.add_trace(go.Scatter(
            x=sec_nums, y=shifts[idx, :],
            mode='lines+markers', name=label,
            marker=dict(size=4, color=UIConstants.TRACE_COLOR),
            line=dict(width=1), hoverinfo='x+y'
        ), row=r, col=c)

    # Dynamic Highlights for the selected Tile
    current_tid_selections = [s for s in selection_store if str(s['tid']) == str(raw_tid)]
    for pt in current_tid_selections:
        try:
            z_val = int(pt['z'])
            data_idx = list(sec_nums).index(z_val)
            is_h = (pt['overlap'] == OverlapType.HORIZONTAL)

            col, idx_x, idx_y = (1, 0, 1) if is_h else (2, 2, 3)
            marker_style = dict(
                size=12, color=UIConstants.HIGHLIGHT_COLOR,
                symbol='circle-open', line=dict(width=2)
            )

            # Highlight on both X and Y drift plots for that overlap
            fig.add_trace(go.Scatter(x=[z_val], y=[shifts[idx_x, data_idx]],
                                     mode='markers', marker=marker_style, hoverinfo='skip'),
                          row=1, col=col)
            fig.add_trace(go.Scatter(x=[z_val], y=[shifts[idx_y, data_idx]],
                                     mode='markers', marker=marker_style, hoverinfo='skip'),
                          row=2, col=col)
        except (ValueError, IndexError):
            continue

    # Determine theme
    is_dark = len(dark_mode) > 0
    theme = "plotly_dark" if is_dark else "plotly_white"

    fig.update_layout(
        title={
            'text': "Trace Explorer",
            'y': 0.98,
            'x': 0.02,
            'xanchor': 'left',
            'yanchor': 'top',
            'font': {'size': 14, 'color': 'gray'}  # Clean, muted grey to match "Navigation" header
        },
        template=theme,
        paper_bgcolor='rgba(0,0,0,0)' if is_dark else 'white',
        plot_bgcolor='rgba(0,0,0,0)' if is_dark else 'white',
        autosize=True,
        modebar=dict(
            orientation='h',
            bgcolor='rgba(0,0,0,0)',
            color='#7f7f7f',
            activecolor='#1f77b4'
        ),
        margin=dict(l=40, r=10, t=50, b=30),
        showlegend=False,
        uirevision=str(raw_tid)
    )
    return fig


@callback(
    Output('master-grid', 'figure'),
    Input('master-grid', 'clickData'),
    prevent_initial_call=False  # Run on startup to draw the initial grid
)
def update_grid_highlight(click_data):
    # Extract TID from click
    active_tid = click_data['points'][0]['text'] if click_data else None

    # Generate the grid with the highlight
    return create_grid_navigator(service.tile_ids, active_tid=active_tid)


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