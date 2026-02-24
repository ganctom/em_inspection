from dash import html, dcc
import dash_bootstrap_components as dbc
from interactive_inspector.data_service import service
from interactive_inspector.layouts.components import create_grid_navigator
from dash_extensions import EventListener


def create_layout():
    return dbc.Container([
        # --- KEYBOARD LISTENER ---
        EventListener(
            id="keyboard-listener",
            events=[{"event": "keydown", "props": ["key", "n_events"], "preventDefault": True}],
            logging=False
        ),

        dcc.Store(id='selection-store', data=[]),
        dcc.Store(id='active-item-index', data=None),
        dcc.Store(id='manual-nudge-store', data={'dx': 0, 'dy': 0}),

        # Dark mode switch
        html.Div([
            dbc.Checklist(
                options=[{"label": " Dark Mode", "value": 1}],
                value=[], id="theme-switch", switch=True,
                className="mb-3 text-muted small"
            ),
        ], className="px-3"),

        dbc.Row([
            # --- SIDEBAR COLUMN ---
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

                    # B. Selection Basket
                    html.Div([
                        html.Div([
                            html.H6("Basket", className="mb-0"),
                            html.Div([
                                dbc.Button("Store", id='save-cxyz-btn', color="warning", size="sm", className="me-1"),
                                dbc.Button("Clear", id='clear-selection', color="link", size="sm")
                            ])
                        ], className="d-flex justify-content-between align-items-center mb-2"),
                        html.Div(
                            id='selection-list-container',
                            style={'maxHeight': '20vh', 'overflowY': 'auto', 'border': '1px solid #dee2e6',
                                   'borderRadius': '4px'}
                        )
                    ], className="mt-3 flex-shrink-0"),

                    # C. Run Button (Moved just below Basket)
                    html.Div([
                        dbc.ButtonGroup([
                            dbc.Button("Run batch registration", id='run-batch-btn', color="primary", className="flex-grow-1"),
                            dbc.Button("⚙️", id="batch-settings-target", color="primary", outline=True),
                        ], className="w-100 mt-2"),

                        # THE POPOVER MUST BE AT THE SAME LEVEL AS THE TARGET
                        dbc.Popover([
                            dbc.PopoverHeader("Settings"),
                            dbc.PopoverBody([
                                dbc.Label("Guess Mode:", className="small"),
                                dbc.Select(
                                    id="guess-mode-select",  # THIS ID MUST BE REGISTERED
                                    options=[
                                        {"label": "Nudge (View)", "value": "nudge"},
                                        {"label": "Manual", "value": "manual"},
                                    ],
                                    value="nudge", size="sm"
                                ),
                                html.Div([
                                    dbc.Row([
                                        dbc.Col(dbc.Input(id="manual-dx", type="number", value=0, size="sm"), width=6),
                                        dbc.Col(dbc.Input(id="manual-dy", type="number", value=0, size="sm"), width=6),
                                    ], className="g-1 mt-2")
                                ], id="manual-input-container", style={"display": "none"})
                            ])
                        ], target="batch-settings-target", trigger="click", placement="right"),
                    ], className="flex-shrink-0"),

                    # D. Expanded Logger
                    html.Div([
                        html.H6("Process Log", className="mt-3 text-uppercase text-muted small"),
                        html.Div(id='registration-log',
                                 className="p-2 border rounded bg-dark text-success font-monospace flex-grow-1",
                                 style={'fontSize': '10px', 'overflowY': 'auto', 'marginBottom': '10px'})
                    ], className="d-flex flex-column flex-grow-1", style={'minHeight': '0'})

                ], style={'height': '100vh', 'display': 'flex', 'flexDirection': 'column', 'padding': '0 15px'})
            ], width=3, className="border-end bg-light"),

            # --- MAIN DISPLAY COLUMN ---
            dbc.Col([
                dbc.NavbarSimple(
                    brand="Coarse Offset Trace Explorer",
                    brand_style={"fontSize": "1.1rem", "fontWeight": "bold"},
                    color="white", className="mb-0 py-0 shadow-none border-bottom",
                    style={'height': '3.5vh', 'minHeight': '35px'}
                ),

                # 1. Main Trace Plot
                html.Div([
                    dcc.Graph(
                        id='quad-plot',
                        style={'height': '100%', 'width': '100%'},
                        config={'modeBarButtonsToAdd': ['drawrect', 'select2d'], 'scrollZoom': True,
                                'displaylogo': False}
                    )
                ], style={'height': '56.5vh', 'padding': '0'}),

                # 2. Integrated Overlap Viewer
                html.Div([
                    html.Div([
                        html.Span("Overlap Inspection: ", className="fw-bold small"),
                        html.Span(id="integrated-ov-status", children="Select a trace", className="text-muted small")
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

                    dcc.Graph(
                        id="integrated-overlap-graph",
                        style={'flex': '1'},
                        config={'scrollZoom': True, 'displaylogo': False}
                    ),
                ],
                    className="border-top mt-auto",
                    style={'backgroundColor': 'black', 'height': '38vh', 'display': 'flex', 'flexDirection': 'column'})
            ], width=9, style={'height': '100vh', 'display': 'flex', 'flexDirection': 'column'})
        ], className="g-0")
    ], fluid=True, style={'height': '98vh', 'overflow': 'hidden'})