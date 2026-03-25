from typing import Dict, Any

from dash import html
import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from interactive_inspector.constants import UIConstants


def create_grid_navigator(
        tile_ids: np.ndarray,
        active_tid: str = None,
        dirty_tids: set = None,
        available_tids: set = None
) -> go.Figure:

    # Single lookup for all valid tile coordinates
    valid_coords = np.where(tile_ids != -1)
    valid_y, valid_x = valid_coords
    dirty_tids = dirty_tids or set()

    # 1. BASE HEATMAP
    fig = go.Figure(data=go.Heatmap(
        z=np.where(tile_ids != -1, 1, np.nan),
        hoverinfo='skip',
        colorscale=[[0, UIConstants.CLR_GRID_BASE_HTMP],
                    [1, UIConstants.CLR_GRID_BASE_HTMP]],
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
            text_colors.append(UIConstants.GRID_DARK)
            if section_filter_active:
                marker_colors.append(UIConstants.CLR_DIM)
                line_colors.append(UIConstants.CLR_BASE)
                line_widths.append(2)
            else:
                marker_colors.append(UIConstants.CLR_BASE)
                line_colors.append(UIConstants.CLR_BASE)
                line_widths.append(0)
        else:
            text_colors.append(UIConstants.GRID_DARK)
            marker_colors.append(UIConstants.CLR_BASE)
            line_colors.append(UIConstants.CLR_BASE)
            line_widths.append(0)

    fig.add_trace(go.Scatter(
        x=valid_x, y=valid_y,
        mode='markers+text',
        text=text_list,
        textposition="middle center",
        textfont=dict(family="Arial", size=UIConstants.SIZE_TEXT_GRID_TILE_ID, color=text_colors),
        marker=dict(
            symbol='square', size=UIConstants.SIZE_MARKER_GRID_TILE_ACTIVE,
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
        height=280, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(autorange='reversed', scaleanchor="x", visible=False, fixedrange=True),
        plot_bgcolor=UIConstants.CLR_BASE,
        paper_bgcolor=UIConstants.CLR_BASE,
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

# def selection_card_orig(index: int, item: dict) -> html.Div:
#     """A condensed, row-style card to maximize sidebar space."""
#     return html.Div([
#         # Metadata Group
#         html.Div([
#             html.Span(f"T{item['tid']}", className="fw-bold me-2", style={'fontSize': '12px'}),
#             html.Span(f"Z{item['z']}", className="text-muted me-2", style={'fontSize': '11px'}),
#             dbc.Badge(
#                 item['overlap'],
#                 color="secondary",
#                 style={'fontSize': '8px', 'padding': '2px 4px'}
#             )
#         ], className="d-flex align-items-center flex-grow-1"),
#
#         # Action Group
#         dbc.ButtonGroup([
#             dbc.Button("OV", id={'type': 'plot-ov-btn', 'index': index},
#                        size="sm", color="secondary", outline=True,
#                        style={'padding': '1px 5px', 'fontSize': '10px'}),
#             dbc.Button("Calc", id={'type': 'compute-single-btn', 'index': index},
#                        size="sm", color="primary", outline=True,
#                        style={'padding': '1px 5px', 'fontSize': '10px'}),
#             dbc.Button("×", id={'type': 'remove-btn', 'index': index},
#                        size="sm", color="danger", outline=True,
#                        style={'padding': '1px 5px', 'fontSize': '10px'})
#         ], className="ms-1")
#     ], className="d-flex align-items-center p-1 px-2 border-bottom bg-white hover-shadow-sm",
#        style={'minHeight': '32px'})

# def selection_card(i, item):
#     """
#     Aligns buttons immediately to the right of the label.
#     This prevents scrollbar overlap by keeping everything on the left.
#     """
#     tid = item.get('tid', '??')
#     z = item.get('z', '??')
#     entry_type = item.get('type', 'MANUAL')
#
#     label = f"T{tid} | Z{z}"
#     is_inf = (entry_type == 'INF_ERROR')
#     label_class = "text-danger fw-bold" if is_inf else "text-dark"
#
#     return html.Div([
#         # 1. The Label (Left-aligned)
#         html.Span(label, className=f"small font-monospace {label_class} me-3",
#                   style={"minWidth": "90px"}),
#
#         # 2. The Buttons (Immediately following the label)
#         html.Div([
#             dbc.Button(
#                 "OV", id={'type': 'plot-ov-btn', 'index': i},
#                 size="sm", color="info", outline=True,
#                 className="py-0 px-1", style={"fontSize": "10px"}
#             ),
#             dbc.Button(
#                 "Calc", id={'type': 'compute-single-btn', 'index': i},
#                 size="sm", color="warning", outline=True,
#                 className="py-0 px-1", style={"fontSize": "10px"}
#             ),
#             dbc.Button(
#                 "X", id={'type': 'remove-btn', 'index': i},
#                 size="sm", color="danger",
#                 className="py-0 px-1", style={"fontSize": "10px"}
#             ),
#         ], className="d-flex gap-2")  # Use 'gap-2' for consistent spacing between buttons
#
#     ], className="d-flex align-items-center p-1 border-bottom bg-white")
