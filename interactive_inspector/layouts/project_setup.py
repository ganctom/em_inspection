import dash_bootstrap_components as dbc
from dash import html, dcc
from constants import UIConstants

from experiment_configs import get_experiment_configurations
from data_service import service


def layout():
    configs = get_experiment_configurations()
    options = [{"label": name, "value": name} for name, cfg in configs.items()]


    # Determine the "Initial Value" based on the currently active experiment
    initial_exp = service.exp_config.name if service.exp_config else None

    return dbc.Container([

        # 1. ADD THE MISSING INTERVAL HERE
        dcc.Interval(
            id="progress-interval",
            interval=1000,  # poll every 1 second
            n_intervals=0,
            disabled=True  # starts disabled
        ),

        dbc.Row([
            # --- LEFT COLUMN: ADD NEW ---
            dbc.Col([
                html.Div([
                    html.H4("Add New Experiment", className="mb-3"),

                    dbc.Label("Experiment Name", className="small mb-0"),
                    dbc.Input(id="new-exp-name", persistence=True, placeholder="e.g. FISH_ID_1", size="sm",
                              className="mb-2"),
                    dbc.Label("Acquisition Directory (Absolute Path)", className="small mb-0"),
                    dbc.Input(id="new-exp-acq", persistence=True, placeholder="/Volumes/.../sbem_acq-dir", size="sm",
                              className="mb-2"),

                    dbc.Label("Processing Directory (Absolute Path)", className="small mb-0"),
                    dbc.Input(id="new-exp-proc", persistence=True, placeholder="/Volumes/.../run-01", size="sm",
                              className="mb-2"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Grid Num", className="small mb-0"),
                            dbc.Input(id="new-exp-grid", type="number", value=0, size="sm"),
                        ], width=4),
                        dbc.Col([
                            dbc.Label("Shape (X, Y)", className="small mb-0"),
                            dbc.InputGroup([
                                dbc.Input(id="new-exp-shape-x", type="number", placeholder="X", size="sm"),
                                dbc.Input(id="new-exp-shape-y", type="number", placeholder="Y", size="sm"),
                            ], size="sm"),
                        ], width=8),
                    ], className="mb-2"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label("First Section", className="small mb-0"),
                            dbc.Input(id="new-exp-first", type="number", size="sm"),
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Last Section", className="small mb-0"),
                            dbc.Input(id="new-exp-last", type="number", size="sm"),
                        ], width=6),
                    ], className="mb-3"),

                    html.Div([
                        dbc.Button(**UIConstants.BTN_ADD_EXP_CFG),
                        dbc.Button(**UIConstants.BTN_PARSE_CFG),
                    ], className="d-grid gap-2"),

                    # THE PROGRESS UI
                    dbc.Collapse(
                        id="progress-collapse",
                        is_open=False,
                        children=[
                            html.Div([
                                html.Div(id="parsing-status-text", className="small fw-bold mb-1 mt-3"),
                                dbc.Progress(
                                    id="parsing-progress-bar",
                                    value=0,
                                    label="0%",
                                    striped=True,
                                    animated=True,
                                    style={"height": "25px"}
                                ),
                            ])
                        ]
                    )
                ], className="p-4 border rounded h-100")
            ], width=7),

            # --- RIGHT COLUMN: LOAD EXISTING ---
            dbc.Col([
                html.Div([
                    html.H4("Existing Experiments", className="mb-3"),
                    html.P("Select a pre-configured experiment to begin inspection.",
                           className="text-muted small"),

                    dbc.Select(
                        id="experiment-select",
                        options=options,
                        value=initial_exp,
                        placeholder="Choose an experiment...",
                        className="mb-3"
                    ),

                    html.Div(id="experiment-details-card"),
                    dbc.Button(**UIConstants.BTN_INIT_CFG),
                ], className="p-4 bg-light border rounded h-100")
            ], width=5),
        ], className="mt-5 g-4"),

        # Feedback Toast/Alert
        html.Div(id="setup-feedback", className="mt-4")
    ], fluid=True)