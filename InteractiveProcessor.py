from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import numpy as np

from dash import Dash, dcc, html, Input, Output, State, callback, ctx, no_update, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import experiment_configs as cfg
from coarse_offset_processor import CoarseOffsetProcessor


# --- 1. DOMAIN MODELS & CONSTANTS ---

@dataclass(frozen=True)
class OverlapType:
    HORIZONTAL = "H"
    VERTICAL = "V"


class UIConstants:
    """Centralized UI configuration and styling."""
    THEME = dbc.themes.BOOTSTRAP
    PRIMARY_COLOR = "#007bff"
    TRACE_COLOR = "#2c3e50"
    HIGHLIGHT_COLOR = "red"

    # Mapping CurveNumber -> OverlapType
    # This is the 'Source of Truth' for event handling
    SELECTION_MAP = {
        0: OverlapType.HORIZONTAL, 1: OverlapType.HORIZONTAL,
        2: OverlapType.VERTICAL, 3: OverlapType.VERTICAL
    }


# --- 2. DATA PROVIDER (Singleton Pattern) ---

class DataService:
    """Handles data fetching and business logic processing."""

    def __init__(self):
        configs = cfg.get_experiment_configurations()
        self.exp_config = configs[cfg.ExperimentName.ROLI_F1]
        self.processor = CoarseOffsetProcessor(self.exp_config)
        self.processor.load_all_offsets_and_tile_id_maps_from_npz()
        self.tile_ids = self.processor.get_largest_tile_id_map()

    def get_trace(self, tid: str):
        return self.processor.get_full_trace(tid)


data_service = DataService()


# --- 3. UI FACTORIES ---

class LayoutFactory:
    """Static methods to generate complex UI components."""

    @staticmethod
    def create_grid_navigator(tile_ids: np.ndarray) -> go.Figure:
        rows, cols = tile_ids.shape
        mask = (tile_ids != -1)

        fig = go.Figure(data=go.Heatmap(
            z=np.where(mask, np.random.rand(rows, cols), np.nan),
            text=np.where(mask, tile_ids.astype(str), ""),
            texttemplate="%{text}",
            colorscale=[[0, '#e9ecef'], [1, '#e9ecef']],
            showscale=False, xgap=2, ygap=2, hoverinfo='text'
        ))

        fig.update_layout(
            height=280, margin=dict(l=0, r=0, t=0, b=0),
            xaxis=dict(visible=False, fixedrange=True),
            yaxis=dict(autorange='reversed', scaleanchor="x", visible=False, fixedrange=True),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
        )
        return fig

    @staticmethod
    def selection_card(index: int, item: Dict[str, Any]) -> html.Div:
        """Generates a professional-looking list item for the basket."""
        label_style = {'color': '#6c757d', 'fontSize': '9px'}

        return html.Div([
            html.Div([
                html.Small("TILE", style=label_style),
                html.B(f" {item['tid']}", className="me-2"),
                html.Small("Z", style=label_style),
                html.B(f" {item['z']}", className="me-2"),
                dbc.Badge(item['overlap'], color="secondary", style={'fontSize': '9px'})
            ], className="d-flex align-items-center flex-grow-1"),

            dbc.ButtonGroup([
                # Item Action: View Overlap
                dbc.Button("OV", id={'type': 'plot-ov-btn', 'index': index},
                           size="sm", outline=True, color="secondary", title="Plot Overlap"),
                # Item Action: Re-calculate this specific vector
                dbc.Button("Calc", id={'type': 'compute-single-btn', 'index': index},
                           size="sm", outline=True, color="primary", title="Compute Single Shift"),
                # Item Action: Remove
                dbc.Button("×", id={'type': 'remove-btn', 'index': index},
                           size="sm", outline=True, color="danger")
            ], className="ms-2")
        ], className="p-2 mb-1 border rounded bg-white d-flex align-items-center shadow-sm")


# --- 4. APPLICATION SETUP ---

app = Dash(__name__, external_stylesheets=[UIConstants.THEME])

app.layout = dbc.Container([
    dcc.Store(id='selection-store', data=[]),

    dbc.Row([
        # Sidebar Column
        dbc.Col([
            html.H6("Navigation", className="mt-3 text-uppercase text-muted"),
            dcc.Graph(
                id='master-grid',
                figure=LayoutFactory.create_grid_navigator(data_service.tile_ids),
                config={'displayModeBar': False}
            ),

            html.Div([
                html.Div([
                    html.H6("Selection Basket", className="mb-0"),
                    dbc.Button("Clear All", id='clear-selection', color="link", size="sm")
                ], className="d-flex justify-content-between align-items-center mb-2"),

                html.Div(id='selection-list-container', style={'maxHeight': '400px', 'overflowY': 'auto'})
            ], className="p-3 bg-light border rounded mt-3"),

            # Inside your App Layout or Sidebar component:
            html.Div([
                html.H6("Global Operations", className="mt-4 text-uppercase text-muted", style={'fontSize': '11px'}),
                dbc.ButtonGroup([
                    dbc.Button([html.I(className="bi bi-play-fill me-2"), "Run SOFIMA"],
                               id='open-sofima', color="primary", className="mb-2 w-100"),
                    dbc.Button([html.I(className="bi bi-cpu me-2"), "Run SSIM Batch"],
                               id='open-ssim', color="info", outline=True, className="w-100"),
                ], vertical=True, className="w-100"),

                # Status Log for feedback
                html.Div(id='registration-log',
                         className="mt-3 p-2 small border rounded bg-dark text-success font-monospace",
                         style={'minHeight': '60px', 'fontSize': '10px'})
            ], className="mt-auto")

        ], width=3, className="border-end"),

        # Main Display Column
        dbc.Col([
            dbc.NavbarSimple(brand="Coarse Offset Trace Explorer", brand_href="#", color="white", dark=False,
                             className="mb-2 shadow-none"),
            dcc.Graph(id='quad-plot', config={'modeBarButtonsToAdd': ['drawrect', 'select2d'], 'scrollZoom': True})
        ], width=9)
    ], className="g-0")
], fluid=True)


# --- 5. CALLBACK LOGIC ---

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

    if trigger == 'clear-selection': return []

    if isinstance(trigger, dict) and trigger.get('type') == 'remove-btn':
        return [item for i, item in enumerate(current_store) if i != trigger.get('index')]

    if sel_data and 'points' in sel_data:
        tid = grid_click['points'][0]['text'] if grid_click else "N/A"
        new_store = list(current_store)

        for p in sel_data['points']:
            overlap = UIConstants.SELECTION_MAP.get(p.get('curveNumber'))
            if not overlap: continue

            entry = {'tid': tid, 'z': p['x'], 'overlap': overlap}
            if entry not in new_store: new_store.append(entry)

        return new_store
    return no_update


@callback(
    Output('registration-log', 'children'),
    [Input({'type': 'plot-ov-btn', 'index': ALL}, 'n_clicks'),
     Input({'type': 'compute-single-btn', 'index': ALL}, 'n_clicks'),
     Input('open-sofima', 'n_clicks'),
     Input('open-ssim', 'n_clicks')],
    State('selection-store', 'data'),
    prevent_initial_call=True
)
def handle_actions(ov_clicks, calc_clicks, sofima_n, ssim_n, data):
    trig = ctx.triggered_id

    # 1. Handle Global Batch Actions
    if trig == 'open-sofima':
        return f"Initiating SOFIMA registration for {len(data)} vectors..."

    if trig == 'open-ssim':
        return f"Running SSIM analysis on selection basket..."

    # 2. Handle Item-Specific Actions
    if isinstance(trig, dict):
        idx = trig.get('index')
        item = data[idx]
        action = trig.get('type')

        if action == 'plot-ov-btn':
            return f"Loading Overlap View: Tile {item['tid']} @ Z={item['z']}"

        if action == 'compute-single-btn':
            return f"Re-calculating shift for Vector: {item['tid']}_{item['z']}_{item['overlap']}"

    return no_update


@callback(
    Output('selection-list-container', 'children'),
    Input('selection-store', 'data')
)
def sync_selection_ui(data):
    if not data: return html.Div("No vectors selected.", className="text-muted small italic p-2")
    return [LayoutFactory.selection_card(i, item) for i, item in enumerate(data)]


@callback(
    Output('quad-plot', 'figure'),
    [Input('master-grid', 'clickData'), Input('selection-store', 'data')]
)
def render_main_visuals(grid_click, selection_store):
    raw_tid = grid_click['points'][0]['text'] if grid_click else None
    if not raw_tid: return go.Figure()

    trace_data = data_service.get_trace(str(raw_tid))
    if not trace_data or trace_data.shift_vectors is None: return go.Figure()

    sec_nums = trace_data.section_numbers
    shifts = trace_data.shift_vectors

    fig = make_subplots(
        rows=2, cols=2, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("H-Overlap: Δx", "V-Overlap: Δx", "H-Overlap: Δy", "V-Overlap: Δy")
    )

    # Standardized trace configurations
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

    # Dynamic Highlights
    current_tid_selections = [s for s in selection_store if str(s['tid']) == str(raw_tid)]
    for pt in current_tid_selections:
        try:
            z_val = int(pt['z'])
            data_idx = list(sec_nums).index(z_val)
            is_h = (pt['overlap'] == OverlapType.HORIZONTAL)

            col, idx_x, idx_y = (1, 0, 1) if is_h else (2, 2, 3)

            marker_style = dict(size=12, color=UIConstants.HIGHLIGHT_COLOR, symbol='circle-open', line=dict(width=2))

            fig.add_trace(go.Scatter(x=[z_val], y=[shifts[idx_x, data_idx]], mode='markers', marker=marker_style,
                                     hoverinfo='skip'), row=1, col=col)
            fig.add_trace(go.Scatter(x=[z_val], y=[shifts[idx_y, data_idx]], mode='markers', marker=marker_style,
                                     hoverinfo='skip'), row=2, col=col)
        except (ValueError, IndexError):
            continue

    fig.update_layout(height=600, margin=dict(l=50, r=20, t=40, b=50), showlegend=False, template="plotly_white")
    return fig


if __name__ == '__main__':
    app.run(debug=True)