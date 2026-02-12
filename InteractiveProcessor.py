from typing import Sequence, Any

from dash import Dash, dcc, html, Input, Output, State, callback, ctx, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from tensorflow.lite.python.schema_py_generated import SequenceRNNOptionsT

import experiment_configs as cfg
from coarse_offset_processor import CoarseOffsetTrace, CoarseOffsetProcessor, Vector


app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])


# --- CONFIGURATION ---

# Get project config
configs = cfg.get_experiment_configurations()
exp_config = configs[cfg.ExperimentName.ROLI_F1]

# Initialize CoarseOffsetProcessor and read coarse offsets
co_processor = CoarseOffsetProcessor(exp_config)
co_processor.load_all_offsets_and_tile_id_maps_from_npz()
tile_ids = co_processor.get_largest_tile_id_map()

# Pre-process tile-ids for the grid navigator
ROWS, COLS = np.shape(tile_ids)

# Preprocess tileIDs for the grid navigator
mask = (tile_ids != -1)
display_text = tile_ids.astype(str)
display_text[tile_ids == -1] = ""
z_data = np.random.rand(ROWS, COLS)
z_data[~mask] = np.nan


master_grid_fig = go.Figure(data=go.Heatmap(
    z=z_data,
    text=display_text,
    texttemplate="%{text}",
    colorscale=[[0, '#e9ecef'], [1, '#e9ecef']], # Soft gray
    showscale=False,
    xgap=2, ygap=2,
    hoverinfo='text',
))

master_grid_fig.update_layout(
    height=300, margin=dict(l=5, r=5, t=5, b=5),
    xaxis=dict(visible=False, fixedrange=True),
    yaxis=dict(autorange='reversed', scaleanchor="x", scaleratio=1, visible=False, fixedrange=True),
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)',
)


app.layout = html.Div([
    # Store now contains a list of unique 'Vector Keys': "TID_Z_Neighbor"
    dcc.Store(id='selection-store', data=[]),

    html.Div([
        # SIDEBAR
        html.Div([
            html.B("Tile grid"),
            dcc.Graph(id='master-grid', figure=master_grid_fig, config={'displayModeBar': False}),

            html.Div([
                html.Div([
                    html.B("Vector Selection Basket"),
                    dbc.Button("Clear", id='clear-selection', color="link", size="sm", className="float-end")
                ], style={'display': 'flex', 'justifyContent': 'space-between'}),

                html.Div(id='selection-list-container',
                         style={'maxHeight': '300px', 'overflowY': 'auto', 'marginTop': '10px'}),

                html.Hr(),
                html.B("Actions"),
                dbc.ButtonGroup([
                    dbc.Button("SOFIMA", id='open-sofima', color="primary", className="mt-2"),
                    dbc.Button("SSIM", id='open-ssim', color="info", className="mt-2"),
                ], vertical=True, style={'width': '100%'}),

                html.Div(id='registration-log',
                         style={'fontSize': '11px', 'fontFamily': 'monospace', 'marginTop': '10px', 'color': '#28a745'})
            ], style={'padding': '15px', 'backgroundColor': '#f8f9fa', 'marginTop': '10px', 'borderRadius': '8px',
                      'border': '1px solid #ddd'})
        ], style={'width': '22%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '10px'}),

        # MAIN AREA
        html.Div([
            html.H4(id='active-tile-id', children="Coarse offset traces", style={'marginTop': '0'}),
            dcc.Graph(id='quad-plot', config={'modeBarButtonsToAdd': ['drawrect', 'select2d']})
        ], style={'width': '75%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '10px'})
    ], style={'display': 'flex'})
])


# --- CALLBACKS ---

@callback(
    Output('selection-store', 'data'),
    [Input('quad-plot', 'selectedData'),
     Input('clear-selection', 'n_clicks'),
     Input({'type': 'remove-btn', 'index': ALL}, 'n_clicks')],
    [State('selection-store', 'data'),
     State('master-grid', 'clickData')],
    prevent_initial_call=True
)
def update_selection(sel_data, clear_n, remove_n, current_store, grid_click):
    trigger = ctx.triggered_id

    if trigger == 'clear-selection':
        return []

    if isinstance(trigger, dict) and trigger.get('type') == 'remove-btn':
        idx_to_remove = trigger.get('index')
        return [item for i, item in enumerate(current_store) if i != idx_to_remove]

    if sel_data and 'points' in sel_data:
        tid = grid_click['points'][0]['text'] if grid_click else "0"
        new_store = list(current_store)

        for p in sel_data['points']:
            cn = p.get('curveNumber')
            if cn in [0, 1]:
                neighbor = "H"
            elif cn in [2, 3]:
                neighbor = "V"
            else:
                continue

            entry = {'tid': tid, 'z': p['x'], 'neighbor': neighbor}
            if entry not in new_store:
                new_store.append(entry)
        return new_store

    return no_update


# 2. Render the Selection List in Sidebar (Triple Button Layout)
@callback(
    Output('selection-list-container', 'children'),
    Input('selection-store', 'data')
)
def render_list(data):
    if not data:
        return html.Small("No vectors selected.", style={'color': '#999'})

    items = []
    for i, item in enumerate(data):
        items.append(
            html.Div([
                # Vector Label - Taking up the top or left depending on space
                html.Div([
                    html.B(f"T:{item['tid']} Z:{item['z']} {item['neighbor']}",
                           style={'fontSize': '10px', 'display': 'block'}),
                ], style={'flex': '1'}),

                # Action Button Group
                html.Div([
                    # Button 1: Plot Overlap
                    dbc.Button("OV",
                               id={'type': 'plot-ov-btn', 'index': i},
                               size="sm", color="secondary", outline=True,
                               title="Plot Overlap",
                               style={'fontSize': '9px', 'padding': '2px 4px', 'marginRight': '3px'}),

                    # Button 2: Compute Shift (Single)
                    dbc.Button("Calc",
                               id={'type': 'compute-single-btn', 'index': i},
                               size="sm", color="primary", outline=True,
                               title="Compute Shift",
                               style={'fontSize': '9px', 'padding': '2px 4px', 'marginRight': '3px'}),

                    # Button 3: Remove
                    dbc.Button("×",
                               id={'type': 'remove-btn', 'index': i},
                               size="sm", color="danger", outline=True,
                               title="Remove from list",
                               style={'fontSize': '10px', 'padding': '0px 5px', 'fontWeight': 'bold'})
                ], style={'display': 'flex', 'alignItems': 'center'}),

            ], style={
                'padding': '5px 8px',
                'marginBottom': '4px',
                'borderRadius': '4px',
                'border': '1px solid #dee2e6',
                'backgroundColor': '#ffffff',
                'display': 'flex',
                'alignItems': 'center',
                'boxShadow': '1px 1px 2px rgba(0,0,0,0.05)'
            })
        )
    return items


# 3. Callback to handle the "Plot OV" and "Single Compute" logic
@callback(
    Output('registration-log', 'children', allow_duplicate=True),
    [Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
     Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks')],
    State('selection-store', 'data'),
    prevent_initial_call=True
)
def handle_item_actions(ov_clicks, calc_clicks, data):
    if not any(ov_clicks) and not any(calc_clicks):
        return no_update

    trig_id = ctx.triggered_id
    action_type = trig_id.get('type')
    idx = trig_id.get('index')
    item = data[idx]

    if action_type == 'plot-ov-btn':
        return [
            html.Span("Action: ", style={'color': '#aaa'}),
            f"Plotting Overlap for Tile {item['tid']} [Z={item['z']}, {item['neighbor']}]"
        ]

    if action_type == 'compute-single-btn':
        # This is where you would call your specific single-vector registration function
        return [
            html.Span("Action: ", style={'color': '#007bff'}),
            f"Recalculating Vector {item['tid']}_{item['z']}_{item['neighbor']}..."
        ]

    return no_update


# @callback(
#     Output('quad-plot', 'figure'),
#     [Input('master-grid', 'clickData'),
#      Input('selection-store', 'data')],
#     State('quad-plot', 'figure')
# )
# def sync_highlights(grid_click, selection_store, current_fig):
#     # 1. Extract Tile ID
#     raw_tid = grid_click['points'][0]['text'] if grid_click else None
#     if not raw_tid:
#         return go.Figure()  # Or return a blank subplots object
#
#     tid_str = str(raw_tid)
#     tid_int = int(raw_tid)
#
#     trace_data = co_processor.get_full_trace(tid_str)
#     if trace_data is None:
#         return go.Figure()
#
#     sec_nums = trace_data.section_numbers
#     shifts = trace_data.shift_vectors
#
#     # 3. Initialize Subplots
#     fig = make_subplots(
#         rows=2, cols=2,
#         shared_xaxes=True,
#         vertical_spacing=0.1,
#         subplot_titles=("H-Neighbor: dx", "V-Neighbor: dx",
#                         "H-Neighbor: dy", "V-Neighbor: dy")
#     )
#
#     # 4. Map the 4 components to the 2x2 grid
#     # Mapping index: 0=H-dx, 1=V-dx, 2=H-dy, 3=V-dy
#     plot_map = [
#         (0, 1, 1),  # index 0 -> Row 1, Col 1
#         (1, 2, 1),  # index 1 -> Row 1, Col 2
#         (2, 1, 2),  # index 2 -> Row 2, Col 1
#         (3, 2, 2)  # index 3 -> Row 2, Col 2
#     ]
#
#     for idx, row, col in plot_map:
#         y_values = shifts[idx, :]
#
#         # Add the main line trace
#         fig.add_trace(go.Scatter(
#             x=sec_nums,
#             y=y_values,
#             mode='lines+markers',
#             name=f"Component {idx}",
#             marker=dict(size=4, color='#2c3e50', opacity=0.7),
#             line=dict(width=1.0, color='#34495e'),
#             connectgaps=False  # This respects the NaNs we added!
#         ), row=row, col=col)
#
#     # 5. Add Vector Highlights from selection_store
#     active_highlights = [p for p in selection_store if str(p['tid']) == tid_str]
#
#     for pt in active_highlights:
#         z_val = pt['z']
#         neighbor = pt['neighbor']
#
#         try:
#             # 1. Match the Z index (ensure int comparison)
#             z_idx_int = int(z_val)
#             if z_idx_int not in sec_nums:
#                 continue
#             data_idx = list(sec_nums).index(z_idx_int)
#
#             # 2. SELECT INDICES BASED ON NEIGHBOR
#             if neighbor == "H":
#                 target_col = 1  # Left column subplots
#                 idx_dx = 0  # H-dx data
#                 idx_dy = 2  # H-dy data
#             else:  # neighbor == "V"
#                 target_col = 2  # Right column subplots
#                 idx_dx = 1  # V-dx data
#                 idx_dy = 3  # V-dy data
#
#             highlight_style = dict(
#                 size=14, color='red', symbol='circle-open', line=dict(width=3)
#             )
#
#             # 3. DRAW TO SUBPLOTS
#             # Top Row (dx)
#             fig.add_trace(go.Scatter(
#                 x=[z_val],
#                 y=[shifts[idx_dx, data_idx]],
#                 mode='markers',
#                 marker=highlight_style,
#                 hoverinfo='skip'
#             ), row=1, col=target_col)
#
#             # Bottom Row (dy)
#             fig.add_trace(go.Scatter(
#                 x=[z_val],
#                 y=[shifts[idx_dy, data_idx]],
#                 mode='markers',
#                 marker=highlight_style,
#                 hoverinfo='skip'
#             ), row=2, col=target_col)
#
#         except (ValueError, IndexError):
#             continue
#
#     fig.update_layout(
#         height=550,
#         margin=dict(l=40, r=40, t=30, b=30),
#         showlegend=False,
#         template="plotly_white",
#         hovermode='closest'
#     )
#
#     return fig


# --- THE TRUTH TABLE (Based on your .ravel() order) ---
# Index 0: H-dx
# Index 1: H-dy
# Index 2: V-dx
# Index 3: V-dy

# UI POSITION TO ARRAY INDEX
# Format: (Row, Col): array_index


@callback(
    Output('quad-plot', 'figure'),
    [Input('master-grid', 'clickData'),
     Input('selection-store', 'data')]
)
def sync_highlights(grid_click, selection_store):
    raw_tid = grid_click['points'][0]['text'] if grid_click else None
    if not raw_tid or raw_tid == "":
        return go.Figure()

    tid_str = str(raw_tid)
    trace_data = co_processor.get_full_trace(tid_str)

    if not trace_data or trace_data.shift_vectors is None:
        return go.Figure()

    sec_nums = trace_data.section_numbers
    shifts = trace_data.shift_vectors

    fig = make_subplots(
        rows=2, cols=2,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("H-Overlap: dx", "V-Overlap: dx", "H-Overlap: dy", "V-Overlap: dy")
    )

    # FIXED ORDERING: This determines the curveNumber
    # Curve 0: (1,1), Curve 1: (2,1) -> Column 1 (Horizontal)
    # Curve 2: (1,2), Curve 3: (2,2) -> Column 2 (Vertical)
    plot_sequence = [
        {'pos': (1, 1), 'data_idx': 0, 'name': 'H-dx'},  # Curve 0
        {'pos': (2, 1), 'data_idx': 1, 'name': 'H-dy'},  # Curve 1
        {'pos': (1, 2), 'data_idx': 2, 'name': 'V-dx'},  # Curve 2
        {'pos': (2, 2), 'data_idx': 3, 'name': 'V-dy'},  # Curve 3
    ]

    for item in plot_sequence:
        r, c = item['pos']
        fig.add_trace(go.Scatter(
            x=sec_nums,
            y=shifts[item['data_idx'], :],
            mode='lines+markers',
            marker=dict(size=4, color='#2c3e50', opacity=0.7),
            line=dict(width=1),
            name=item['name'],
            hoverinfo='x+y'
        ), row=r, col=c)

    # Add Highlights (These will have curveNumbers 4, 5, 6...)
    active_highlights = [p for p in selection_store if str(p['tid']) == tid_str]
    for pt in active_highlights:
        try:
            z_val = int(pt['z'])
            data_idx = list(sec_nums).index(z_val)

            # Determine which column to draw the red circles in
            col_target, idx_dx, idx_dy = (1, 0, 1) if pt['neighbor'] == "H" else (2, 2, 3)

            style = dict(size=14, color='red', symbol='circle-open', line=dict(width=3))

            fig.add_trace(go.Scatter(x=[z_val], y=[shifts[idx_dx, data_idx]],
                                     mode='markers', marker=style, hoverinfo='skip'), row=1, col=col_target)
            fig.add_trace(go.Scatter(x=[z_val], y=[shifts[idx_dy, data_idx]],
                                     mode='markers', marker=style, hoverinfo='skip'), row=2, col=col_target)
        except (ValueError, KeyError, IndexError):
            continue

    fig.update_layout(height=550, margin=dict(l=40, r=40, t=30, b=30), showlegend=False, template="plotly_white")
    return fig

@callback(
    Output('master-grid', 'figure'),
    Input('master-grid', 'clickData'),
    State('master-grid', 'figure')
)
def highlight_tile(clickData, fig_dict):
    if not clickData:
        return no_update

    # Extract coordinates from click
    point = clickData['points'][0]
    x_val = point['x']
    y_val = point['y']

    # Create the highlight shape (a blue border)
    # Heatmap tiles are centered on integers, so we go +/- 0.5
    highlight_shape = {
        'type': 'rect',
        'x0': x_val - 0.5,
        'x1': x_val + 0.5,
        'y0': y_val - 0.5,
        'y1': y_val + 0.5,
        'line': {
            'color': '#007bff',
            'width': 3,
        },
        'fillcolor': 'rgba(0, 123, 255, 0.1)'  # Light blue tint inside
    }

    # Update the figure layout with the new shape
    fig_dict['layout']['shapes'] = [highlight_shape]

    return fig_dict



if __name__ == '__main__':
    app.run(debug=True)
    # print('0')