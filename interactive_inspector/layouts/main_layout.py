from dash import html, dcc
import dash_bootstrap_components as dbc
from interactive_inspector.data_service import service
from interactive_inspector.layouts.components import create_grid_navigator


# In layouts/main_layout.py

def create_layout():
    return dbc.Container([
        dcc.Store(id='selection-store', data=[]),
        dcc.Store(id='active-item-index', data=None),  # Tracks which basket item is on screen

        # Dark mode switch
        html.Div([
            dbc.Checklist(
                options=[{"label": " Dark Mode", "value": 1}],
                value=[],
                id="theme-switch",
                switch=True,
                className="mb-3 text-muted small"
            ),
        ], className="px-3"),

        dbc.Row([
            # --- SIDEBAR COLUMN (Width 3) ---
            dbc.Col([
                html.Div([
                    # A. Navigation Grid
                    html.Div([
                        html.H6("Navigation", className="mt-3 text-uppercase text-muted"),
                        dcc.Graph(
                            id='master-grid',
                            figure=create_grid_navigator(service.tile_ids),
                            config={'displayModeBar': False}
                        ),
                    ], className="flex-shrink-0"),

                    # B. Selection Basket (The Scroll Area)
                    html.Div([
                        html.Div([
                            html.H6("Selection Basket", className="mb-0"),
                            dbc.Button("Clear All", id='clear-selection', color="link", size="sm")
                        ], className="d-flex justify-content-between align-items-center mb-2 flex-shrink-0"),

                        html.Div(
                            id='selection-list-container',
                            style={
                                'flex': '1 1 0', 'overflowY': 'auto', 'minHeight': '0',
                                'border': '1px solid #dee2e6', 'borderRadius': '4px',
                                'backgroundColor': '#fff'
                            }
                        )
                    ], className="d-flex flex-column flex-grow-1 mt-3", style={'minHeight': '0'}),

                    # C. Global Operations
                    html.Div([
                        dbc.ButtonGroup([
                            dbc.Button([html.I(className="bi bi-play-fill me-2"), "Run SOFIMA"],
                                       id='open-sofima', color="primary", className="mb-2 w-100"),
                        ], vertical=True, className="w-100"),
                        html.Div(id='registration-log',
                                 className="mt-3 p-2 small border rounded bg-dark text-success font-monospace",
                                 style={'height': '100px', 'fontSize': '10px', 'overflowY': 'auto'})
                    ], className="flex-shrink-0 mt-auto pb-3")

                ], style={'height': '100vh', 'display': 'flex', 'flexDirection': 'column', 'padding': '0 15px'})
            ], width=3, className="border-end bg-light"),

            # --- MAIN DISPLAY COLUMN ---
            dbc.Col([
                dbc.NavbarSimple(
                    brand="Coarse Offset Trace Explorer",
                    color="white",
                    className="mb-1 shadow-none",
                    style={'height': '5vh'}
                ),

                # 1. Main Trace Plot: Reduced from 65vh to 50vh
                dcc.Graph(
                    id='quad-plot',
                    style={'height': '60vh'},
                    config={'modeBarButtonsToAdd': ['drawrect', 'select2d'], 'scrollZoom': True}
                ),

                # 2. Integrated Overlap Viewer & Log: Remaining ~43vh
                html.Div([
                    html.Div([
                        html.Span("Overlap Inspection: ", className="fw-bold small"),
                        html.Span(id="integrated-ov-status",
                                  children="Select a trace",
                                  className="text-muted small")
                    ], className="px-3 py-1 bg-light border-bottom"),

                    # Nudge Controls Row
                    dbc.Row([
                        dbc.Col([
                            dbc.ButtonGroup([
                                dbc.Button("←", id="nudge-left", size="sm", color="secondary", outline=True),
                                dbc.Button("↑", id="nudge-up", size="sm", color="secondary", outline=True),
                                dbc.Button("↓", id="nudge-down", size="sm", color="secondary", outline=True),
                                dbc.Button("→", id="nudge-right", size="sm", color="secondary", outline=True),
                            ]),
                        ], width="auto"),
                        dbc.Col([
                            dbc.Input(id="nudge-step", type="number", value=10, size="sm", style={'width': '70px'})
                        ], width="auto"),
                        dbc.Col(html.Small(id="current-nudge-display", className="text-info"), width="auto")
                    ], className="bg-dark p-1 g-1 align-items-center"),

                    dcc.Store(id='manual-nudge-store', data={'dx': 0, 'dy': 0}),

                    dcc.Graph(
                        id="integrated-overlap-graph",
                        style={'height': '20vh'},
                        config={'scrollZoom': True, 'displaylogo': False}
                    ),

                ], className="border rounded m-2 shadow-sm",
                    style={'backgroundColor': 'black', 'height': '0vh'})

            ], width=9, style={'display': 'flex', 'flexDirection': 'column'})

        ], className="g-0")
    ], fluid=True, style={'height': '98vh', 'overflow': 'hidden'})