from dash import html
import dash_bootstrap_components as dbc
import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
from interactive_inspector.constants import UIConstants as UI
from parameter_config import ExpConfig


def create_grid_navigator(
        tile_ids: npt.NDArray[np.int_],
        active_tid: str = None,
        dirty_tids: set = None,
        available_tids: set = None
) -> go.Figure:

    # Single lookup for all valid tile coordinates
    valid_coords = np.where(tile_ids != -1)
    valid_y, valid_x = valid_coords
    dirty_tids = dirty_tids or set()

    # 1. BASE HEATMAP
    z = np.where(tile_ids != -1, 1, np.nan)
    fig = go.Figure(data=go.Heatmap(
        z=z,
        hoverinfo='skip',
        colorscale=[[0, UI.CLR_GRID_BASE_HTMP],
                    [1, UI.CLR_GRID_BASE_HTMP]],
        showscale=False, xgap=2, ygap=2
    ))

    # 2. TILE NUMBERS & ACTIVE HIGHLIGHTS
    text_list, text_colors = [], []
    marker_colors, line_colors, line_widths = [], [], []
    section_filter_active = available_tids is not None

    for r, c in zip(valid_y, valid_x):
        tid_int = int(tile_ids[r, c])
        text_list.append(str(tid_int))

        is_active = not section_filter_active or tid_int in available_tids
        if is_active:
            text_colors.append(UI.GRID_DARK)
            if section_filter_active:
                marker_colors.append(UI.CLR_DIM)
                line_colors.append(UI.CLR_BASE)
                line_widths.append(2)
            else:
                marker_colors.append(UI.CLR_BASE)
                line_colors.append(UI.CLR_BASE)
                line_widths.append(0)
        else:
            text_colors.append(UI.GRID_DARK)
            marker_colors.append(UI.CLR_BASE)
            line_colors.append(UI.CLR_BASE)
            line_widths.append(0)

    fig.add_trace(go.Scatter(
        x=valid_x, y=valid_y,
        mode='markers+text',
        text=text_list,
        textposition="middle center",
        textfont=dict(family="Arial", size=UI.SIZE_TEXT_GRID_TILE_ID, color=text_colors),
        marker=dict(
            symbol='square',
            size=UI.SIZE_NAVIGATOR/UI.SIZE_MARKER_GRID_FCT/np.shape(z)[0],
            color=marker_colors,
            line=dict(color=line_colors, width=line_widths)
        ),
        hoverinfo='text',
        hovertext=[f"Tile {t}" for t in text_list]
    ))

    # 3. INF FAILURES (Red Square in top-right)
    err_y, err_x = [], []
    for r, c in zip(valid_y, valid_x):
        if str(int(tile_ids[r, c])) in dirty_tids:
            err_y.append(r - 0.3)
            err_x.append(c + 0.3)

    if err_y:
        fig.add_trace(go.Scatter(
            x=err_x, y=err_y,
            mode='markers',
            marker=dict(symbol='square', color='#ef5350', size=6),
            hoverinfo='skip'
        ))

    # 4. USER FOCUS (Selection Highlight)
    if active_tid and active_tid != "N/A":
        try:
            coords = np.argwhere(tile_ids == int(active_tid))
            if coords.size > 0:
                r, c = coords[0]
                fig.add_shape(
                    type="rect", x0=c - 0.5, y0=r - 0.5, x1=c + 0.5, y1=r + 0.5,
                    line=dict(color="#00d2d3", width=3),
                    fillcolor="rgba(0, 210, 211, 0.05)",
                    layer="above"
                )
        except (ValueError, TypeError):
            pass

    fig.update_layout(
        height=UI.SIZE_NAVIGATOR, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(autorange='reversed', scaleanchor="x", visible=False, fixedrange=True),
        plot_bgcolor=UI.CLR_BASE,
        paper_bgcolor=UI.CLR_BASE,
        showlegend=False
    )

    return fig

def selection_card(index: int, item: dict) -> html.Div:
    """Compact selection card – metadata + badge, then buttons on the right with gaps.
       Scrollbar-safe with extra right padding."""

    return html.Div([
        # Metadata + Overlap Badge
        html.Div([
            html.Span(f"T{item['tid']}",
                      className="fw-bold me-2",
                      style={'fontSize': '12px'}),
            html.Span(f"Z{item['z']}",
                      className="text-muted me-2",
                      style={'fontSize': '11px'}),
            dbc.Badge(
                item['overlap'],
                color="secondary",
                style={'fontSize': '8px', 'padding': '2px 4px'}
            ),
        ], className="d-flex align-items-center flex-grow-1 flex-shrink-1"),

        # Action Buttons Group with gaps
        dbc.ButtonGroup([

            dbc.Button("Flow",
                       id={'type': UI.ID_BTN_FLOW, 'index': index},
                       size="sm",
                       color="secondary",
                       outline=True,
                       style={'padding': '1px 6px', 'fontSize': '10px'}),

            dbc.Button("CleanFlow",
                       id={'type': UI.ID_BTN_CLEAN_FLOW, 'index': index},
                       size="sm",
                       color="secondary",
                       outline=True,
                       style={'padding': '1px 6px', 'fontSize': '10px'}),

            dbc.Button("OV",
                       id={'type': 'plot-ov-btn', 'index': index},
                       size="sm",
                       color="secondary",
                       outline=True,
                       style={'padding': '1px 6px', 'fontSize': '10px'}),

            dbc.Button("Calc",
                       id={'type': 'compute-single-btn', 'index': index},
                       size="sm",
                       color="primary",
                       outline=True,
                       style={'padding': '1px 6px', 'fontSize': '10px'}),

            dbc.Button("×",
                       id={'type': 'remove-btn', 'index': index},
                       size="sm",
                       color="danger",
                       outline=True,
                       style={'padding': '2px 7px', 'fontSize': '10px'}),
        ],
        className="flex-shrink-0 gap-1")   # ← This adds nice gap between buttons
    ],
        className="d-flex align-items-center gap-3 p-1 px-3 border-bottom bg-white hover-shadow-sm",
        style={
            'minHeight': '32px',
            'paddingRight': '20px'   # increased a bit for extra safety with gap
        }
    )

def to_details_card(exp_config: ExpConfig) -> dbc.Card:
    """Generates a standardized Dash card UI component from the model instance."""
    return dbc.Card([
        dbc.CardHeader(html.Strong(exp_config.name)),
        dbc.CardBody([
            html.P([html.B("Path: "), html.Span(exp_config.proc_dir, className="text-break small")]),
            html.P([html.B("Sections: "), f"{exp_config.first_sec} - {exp_config.last_sec}"], className="mb-1"),
            html.P([
                html.B("Grid: "),
                f"#{exp_config.grid_num} ({exp_config.grid_shape[0]}x{exp_config.grid_shape[1]})"], className="mb-1"),
        ])
    ], className="mt-3 shadow-sm")


def create_progress_view(
    progress: int,
    message: str,
    active: bool,
    status_id: str = "parsing-status-text",
    bar_id: str = "parsing-progress-bar"
) -> html.Div:
    """
    Generates a reusable, standardized progress block combining status text
    and a bootstrap progress bar. IDs can be overridden for cross-page reuse.
    """
    return html.Div([
        html.P(message, id=status_id, className="small text-muted mb-1"),
        dbc.Progress(
            value=progress,
            label=f"{progress}%" if progress > 0 else "",
            animated=active,
            striped=active,
            color="primary" if active else "success",
            id=bar_id
        )
    ])