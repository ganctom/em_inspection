from dash import html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import numpy as np

def create_grid_navigator(tile_ids: np.ndarray, active_tid: str = None) -> go.Figure:
    rows, cols = tile_ids.shape
    mask = (tile_ids != -1)

    fig = go.Figure(data=go.Heatmap(
        z=np.where(mask, np.random.rand(rows, cols), np.nan),
        text=np.where(mask, tile_ids.astype(str), ""),
        texttemplate="%{text}",
        colorscale=[[0, '#e9ecef'], [1, '#e9ecef']],
        showscale=False, xgap=2, ygap=2, hoverinfo='text'
    ))

    if active_tid and active_tid != "N/A":
        coords = np.argwhere(tile_ids.astype(str) == str(active_tid))
        if coords.size > 0:
            r, c = coords[0]
            fig.add_shape(
                type="rect", x0=c-0.5, y0=r-0.5, x1=c+0.5, y1=r+0.5,
                line=dict(color="#00d2d3", width=2),
                fillcolor="rgba(0, 210, 211, 0.15)",
                layer="above" # Ensure highlight is on top of the grid
            )

    fig.update_layout(
        height=280, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(autorange='reversed', scaleanchor="x", visible=False, fixedrange=True),
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig


def selection_card(index: int, item: dict) -> html.Div:
    """A condensed, row-style card to maximize sidebar space."""
    return html.Div([
        # Metadata Group
        html.Div([
            html.Span(f"T{item['tid']}", className="fw-bold me-2", style={'fontSize': '12px'}),
            html.Span(f"Z{item['z']}", className="text-muted me-2", style={'fontSize': '11px'}),
            dbc.Badge(
                item['overlap'],
                color="secondary",
                style={'fontSize': '8px', 'padding': '2px 4px'}
            )
        ], className="d-flex align-items-center flex-grow-1"),

        # Action Group
        dbc.ButtonGroup([
            dbc.Button("OV", id={'type': 'plot-ov-btn', 'index': index},
                       size="sm", color="secondary", outline=True,
                       style={'padding': '1px 5px', 'fontSize': '10px'}),
            dbc.Button("Calc", id={'type': 'compute-single-btn', 'index': index},
                       size="sm", color="primary", outline=True,
                       style={'padding': '1px 5px', 'fontSize': '10px'}),
            dbc.Button("×", id={'type': 'remove-btn', 'index': index},
                       size="sm", color="danger", outline=True,
                       style={'padding': '1px 5px', 'fontSize': '10px'})
        ], className="ms-1")
    ], className="d-flex align-items-center p-1 px-2 border-bottom bg-white hover-shadow-sm",
       style={'minHeight': '32px'})

