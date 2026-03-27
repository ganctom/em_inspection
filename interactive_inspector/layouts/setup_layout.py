import dash_bootstrap_components as dbc
from dash import html, dcc
from constants import UI

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

                    dbc.Label(UI.NAME_INP_NAME, **UI.LBL_CFG),
                    dbc.Input(**UI.INP_NAME),

                    dbc.Label(UI.NAME_INP_ACQ, **UI.LBL_CFG),
                    dbc.Input(**UI.INP_ACQ),

                    dbc.Label(UI.NAME_INP_PROC, **UI.LBL_CFG),
                    dbc.Input(**UI.INP_PROC),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label(UI.NAME_INP_GRID_NUM, **UI.LBL_CFG),
                            dbc.Input(**UI.INP_GRID_NUM),
                        ], width=4),
                        dbc.Col([
                            dbc.Label(UI.NAME_INP_GRID_SIZE, **UI.LBL_CFG),
                            dbc.InputGroup([
                                dbc.Input(**UI.INP_GS_X),
                                dbc.Input(**UI.INP_GS_Y),
                            ], size="sm"),
                        ], width=8),
                    ], className="mb-2"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label(UI.NAME_INP_SEC_RANGE, **UI.LBL_CFG),
                            dbc.InputGroup([
                                dbc.Input(**UI.INP_FIRST_SEC),
                                dbc.Input(**UI.INP_LAST_SEC),
                            ], size="sm"),
                        ], width=12),
                    ], className="mb-3"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label(UI.NAME_INP_PX_SIZE, **UI.LBL_CFG),
                            dbc.Input(**UI.INP_PX_SIZE),
                        ], width=6),
                        dbc.Col([
                            dbc.Label(UI.NAME_INP_CT, **UI.LBL_CFG),
                            dbc.Input(**UI.INP_CT),
                        ], width=6),
                    ], className="mb-3"),

                    html.Div([
                        dbc.Button(**UI.BTN_ADD_EXP),
                        html.Span(dbc.Button(**UI.BTN_PARSE),
                                  id=UI.ID_BTN_PARSE_WRAPPER,
                                  className="d-grid"),
                        dbc.Tooltip(**UI.TTP_PARSE),

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
                    # --- HEADER ---
                    html.H4("Existing Experiments", className="mb-3"),
                    html.P("Select a pre-configured experiment to begin inspection.",
                           className="text-muted small"),

                    # Selection dropdown
                    dbc.Select(**UI.SEL_EXPERIMENT, options=options, value=initial_exp),

                    # Placeholder for dynamic experiment info
                    html.Div(id="experiment-details-card"),

                    # --- BUTTON GROUP ---
                    html.Div([
                        # 1. Initialize Project Button
                        dbc.Button(**UI.BTN_INIT),

                        # 2. Store Offsets & Maps Button with Tooltip Wrapper
                        html.Span([
                            dbc.Button(**UI.BTN_BCKP_CO)
                        ], id=UI.ID_BTN_BCKP_WRAPPER, className="d-grid"),

                        dbc.Tooltip(
                            id=UI.ID_TTP_BCKP,
                            target=UI.ID_BTN_BCKP_WRAPPER,
                            placement="bottom",
                            trigger="hover",
                        )
                    ], className="d-grid gap-2 mt-3")  # mt-3 separates buttons from the details card

                ], className="p-4 bg-light border rounded h-100")
            ], width=5),
        ], className="mt-5 g-4"),

        # Feedback Toast/Alert
        html.Div(id="setup-feedback", className="mt-4")
    ], fluid=True)