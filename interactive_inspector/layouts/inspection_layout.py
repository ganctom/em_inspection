from dash import html, dcc
import dash_bootstrap_components as dbc
from data_service import service
from .components_layouts import create_grid_navigator


def create_layout():

    # --- DATA PREP  ---
    meta = service.get_slider_metadata()

    return dbc.Container([

        # --- MAIN UI STRUCTURE ---
        dbc.Row([

            # A. SIDEBAR COLUMN (Width: 3)
            dbc.Col([
                html.Div([

                    # Theme Switch
                    html.Div([
                        dbc.Checklist(
                            options=[{"label": " Dark Mode", "value": 1}],
                            value=[], id="theme-switch", switch=True,
                            className="mt-3 mb-2 text-muted small"
                        ),
                    ], className="px-3"),

                    # Navigation Section
                    html.Div([
                        html.H6("Grid Navigator", className="mt-2 text-uppercase text-muted small"),

                        dbc.Row([
                            # Slider & Manual Entry
                            dbc.Col([
                                html.Div([
                                    dbc.Input(
                                        id="manual-z-input",
                                        type="number",
                                        placeholder="Z...",
                                        size="sm",
                                        value=meta["initial_value"],
                                        debounce=True,
                                        style={"width": "85px", "marginBottom": "10px", "marginLeft": "0px"},
                                        persistence=True
                                    ),
                                    dcc.Slider(
                                        id='section-filter-slider',
                                        min=meta["min"],
                                        max=meta["max"],
                                        step=1,
                                        value=meta["max"],
                                        vertical=True,
                                        verticalHeight=230,
                                        marks=meta["marks"],
                                        included=False,  # Removes the purple fill
                                        updatemode='mouseup',
                                    ),
                                ], style={'display': 'flex', 'flexDirection': 'column', 'alignItems': 'top'})
                            ], width=3),

                            # Master Grid Navigator
                            dbc.Col([
                                dcc.Graph(
                                    id='master-grid',
                                    figure=create_grid_navigator(service.tile_ids),
                                    config={'displayModeBar': False,}
                                ),
                            ], width=8),
                        ], className="g-0 align-items-center"),
                    ], className="flex-shrink-0 px-2"),

                    # Selection Basket Section in Sidebar
                    html.Div([
                        html.Div([
                            html.H6("Basket", className="mb-0 small text-uppercase text-muted"),
                            html.Div([
                                dbc.Button("JSON", id='export-sections-btn', color="info", size="sm",
                                           className="me-1 py-0"),
                                dbc.Button("NPZ", id='save-cxyz-btn', color="warning", size="sm",
                                           className="me-1 py-0"),
                                dbc.Button("Clear", id='clear-selection', color="link", size="sm",
                                           className="p-0 small"),
                            ])
                        ], className="d-flex justify-content-between align-items-center mb-2 mt-4"),

                        html.Div(
                            id='selection-list-container',
                            style={
                                'maxHeight': '25vh',
                                'overflowY': 'auto',
                                'border': '1px solid #dee2e6',
                                'borderRadius': '4px',
                                'backgroundColor': '#f8f9fa'  # Light grey background to distinguish the list
                            }
                        )
                    ], className="flex-shrink-0 px-2"),

                    # Batch Processing & Settings
                    html.Div([
                        dbc.ButtonGroup([
                            dbc.Button("Run Batch Registration", id='run-batch-btn', color="primary",
                                       className="flex-grow-1"),
                            dbc.Button("⚙️", id="batch-settings-target", color="primary", outline=True),
                        ], className="w-100 mt-3"),

                        dbc.Popover([
                            dbc.PopoverHeader("Settings"),
                            dbc.PopoverBody([
                                dbc.Label("Guess Mode:", className="small"),
                                dbc.Select(
                                    id="guess-mode-select",
                                    options=[
                                        {"label": "Nudge (View)", "value": "nudge"},
                                        {"label": "Manual", "value": "manual"},
                                    ],
                                    value="nudge", size="sm"
                                ),
                                html.Div([
                                    dbc.Row([
                                        dbc.Col(dbc.Input(id="manual-dx", type="number", value=0, placeholder="dx",
                                                          size="sm"), width=6),
                                        dbc.Col(dbc.Input(id="manual-dy", type="number", value=0, placeholder="dy",
                                                          size="sm"), width=6),
                                    ], className="g-1 mt-2")
                                ], id="manual-input-container", style={"display": "none"})
                            ])
                        ], target="batch-settings-target", trigger="click", placement="right"),
                    ], className="flex-shrink-0 px-2"),

                    # Process Log
                    html.Div([
                        html.Div([
                            html.H6("Log", className="m-0 small text-uppercase text-muted"),
                            dbc.Button("Import INF", id='import-inf-btn', color="danger", size="sm",
                                       className="py-0 px-1", style={"fontSize": "10px"}),
                        ], className="d-flex justify-content-between align-items-center mt-3 mb-1"),
                        html.Div(id='registration-log',
                                 className="p-2 border rounded bg-dark text-success font-monospace flex-grow-1",
                                 style={'fontSize': '10px', 'overflowY': 'auto', 'minHeight': '100px'})
                    ], className="d-flex flex-column flex-grow-1 px-2 pb-3")

                ], style={'height': '100%', 'display': 'flex', 'flexDirection': 'column'})
            ], width=3, className="border-end bg-light"),

            # B. MAIN DISPLAY COLUMN (Width: 9)
            dbc.Col([
                # Navbar
                dbc.NavbarSimple(
                    brand="Coarse Offset Trace Explorer",
                    brand_style={"fontSize": "1rem", "fontWeight": "bold"},
                    color="white", className="mb-0 py-1 shadow-none border-bottom",
                    style={'height': '40px'}
                ),

                # Trace Plot (Quad Plot)
                html.Div([
                    dcc.Graph(
                        id='quad-plot',
                        style={'height': '100%', 'width': '100%'},
                        config={
                            'modeBarButtonsToAdd': ['drawrect', 'select2d'],
                            'scrollZoom': True,
                            'displaylogo': False,
                            'doubleClick': 'reset+autosize'
                        }
                    )
                ], style={'height': '55vh', 'padding': '0'}),

                # Overlap Viewer
                html.Div([
                    # Status Header
                    html.Div([
                        html.Span("Overlap Inspection: ", className="fw-bold small"),
                        html.Span(id="integrated-ov-status", children="Select a trace", className="text-muted small")
                    ], className="px-3 py-1 bg-light border-bottom"),

                    # Control Bar
                    dbc.Row([
                        dbc.Col([
                            # Change the old IDs to this format in your create_layout():
                            dbc.ButtonGroup([
                                dbc.Button("|<", id={'type': 'nav-btn', 'index': 'first'}, size="sm", color="info",
                                           outline=True),
                                dbc.Button("«", id={'type': 'nav-btn', 'index': 'prev'}, size="sm", color="info",
                                           outline=True),
                                dbc.Button("»", id={'type': 'nav-btn', 'index': 'next'}, size="sm", color="info",
                                           outline=True),
                                dbc.Button(">|", id={'type': 'nav-btn', 'index': 'last'}, size="sm", color="info",
                                           outline=True),
                            ], className="me-2"),

                            dbc.ButtonGroup([
                                dbc.Button("←", id={'type': 'nudge-btn', 'index': 'left'}, size="sm", color="secondary",
                                           outline=True),
                                dbc.Button("↑", id={'type': 'nudge-btn', 'index': 'up'}, size="sm", color="secondary",
                                           outline=True),
                                dbc.Button("↓", id={'type': 'nudge-btn', 'index': 'down'}, size="sm", color="secondary",
                                           outline=True),
                                dbc.Button("→", id={'type': 'nudge-btn', 'index': 'right'}, size="sm",
                                           color="secondary", outline=True),
                            ]),
                        ], width="auto"),
                        dbc.Col([
                            # Change the id of the nudge-step input:
                            dbc.Input(
                                id={'type': 'nudge-config', 'index': 'step'},  # Changed from "nudge-step"
                                type="number",
                                value=10,
                                size="sm",
                                style={'width': '65px'}
                            )
                        ], width="auto"),
                        dbc.Col(html.Small(id="current-nudge-display", className="text-info font-monospace"),
                                width="auto")
                    ], className="bg-dark p-1 g-1 align-items-center"),

                    # Main Overlap Graph
                    dcc.Graph(
                        id="integrated-overlap-graph",
                        style={'flex': '1'},
                        config={'scrollZoom': True, 'displaylogo': False}
                    ),
                ],
                    className="border-top mt-auto",
                    style={'backgroundColor': 'black', 'height': '40vh', 'display': 'flex', 'flexDirection': 'column'})

            ], width=9, style={'height': '100%', 'display': 'flex', 'flexDirection': 'column'})
        ], className="g-0")
    ], fluid=True, style={'height': '100%', 'overflow': 'hidden'})