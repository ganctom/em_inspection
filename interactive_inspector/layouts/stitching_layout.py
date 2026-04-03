from dash import html, dcc
import dash_bootstrap_components as dbc
from constants import UI
import parameter_config as pcfg

# Reusing your standard configs
default_mesh = pcfg.MeshIntegrationConfig()
default_warp = pcfg.WarpConfigStitching()


def layout(active_service=None):

    return dbc.Container([
        # 1. CONFIGURATION SECTION (COLLAPSIBLE)
        dbc.Row([
            dbc.Col([
                dbc.Accordion([
                    dbc.AccordionItem(
                        item_id="stitch_config-manager",
                        title=html.Div([
                            html.I(className="bi bi-sliders2 me-2"),
                            "Stitching Configuration Manager",
                            dbc.Badge("Ready", color="success", className="ms-2", id="sync-badge"),
                            html.Small(id="header-path-summary", className="ms-3 text-muted",
                                       style={"fontSize": "11px", "fontWeight": "normal"})
                        ]),
                        children=[
                            # Path Selection
                            UI.PATH_SELECTOR_STITCH(active_service),

                            # 1. CONFIGURATION SECTION (Final Tabs Assembly)
                            dbc.Tabs([
                                UI.TAB_ACQUISITION(active_service)
                            ], id="stitch_config-tabs", active_tab="tab-acq")
                        ]
                    )
                ], active_item="stitch_config-manager", className="shadow-sm mt-4")
            ], width=12)
        ]),

        # 2. PIPELINE EXECUTION SECTION
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    UI.STITCH_PPLN_HEADER,
                    dbc.CardBody([
                        dbc.Row([
                            UI.COL_STITCH_TARGETS,
                            UI.COL_STITCH_STEPS,

                            # COLUMN C: Actions
                            dbc.Col([
                                dbc.Button(**UI.BTN_STITCH_PPLN_RUN),
                                dbc.Button(**UI.BTN_STITCH_PPLN_ABORT),

                                dcc.RadioItems(
                                    id=UI.ID_STITCH_PPLN_PARALLEL_TOGGLE,
                                    options=[
                                        {'label': ' Sequential', 'value': False},
                                        {'label': ' Parallel', 'value': True}
                                    ],
                                    value=False,  # Default to Sequential
                                    labelStyle={'display': 'inline-block', 'marginRight': '15px'}
                                )

                            ], width=3, className="d-flex flex-column justify-content-center"),
                        ]),
                    ]),
                ], className="shadow-sm mt-4 border-danger")
            ], width=12)
        ]),

        # 3. CONSOLE & PROGRESS (Refined)
        dbc.Row([
            dbc.Col([
                # Status Bar (Dynamic Text)
                html.Div(id="pipeline-status-bar", className="mt-3 fw-bold small text-secondary"),
                UI.STITCH_PPLN_CONSOLE,  # The Main Console Output
                UI.STITCH_PPLN_PROGRESS_BAR   # The Progress Indicator
            ], width=12)
        ], className="px-3"),



        dcc.Interval(id=UI.ID_STITCH_PPLN_PROGRESS_INT, interval=1000, disabled=True),
        dcc.Store(id="scroll-trigger-dummy")
    ], fluid=True)