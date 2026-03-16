import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, ctx
from data_service import service
from experiment_configs import get_experiment_configurations, ExpConfig


@callback(
    [Output("experiment-details-card", "children"),
     Output("load-config-btn", "disabled")],
    Input("experiment-select", "value")
)
def update_details(exp_name):
    if not exp_name:
        return "", True

    configs = get_experiment_configurations()
    cfg = configs.get(exp_name)

    if not cfg:
        return dbc.Alert("Configuration not found", color="danger"), True

    # Show the user what they are about to load
    card = dbc.Card([
        dbc.CardHeader(html.Strong(cfg.name)),
        dbc.CardBody([
            html.P([html.B("Path: "), html.Span(cfg.proc_dir, className="text-break small")]),
            html.P([html.B("Sections: "), f"{cfg.first_sec} - {cfg.last_sec}"], className="mb-1"),
            html.P([html.B("Grid: "), f"#{cfg.grid_num} ({cfg.grid_shape[0]}x{cfg.grid_shape[1]})"], className="mb-1"),
        ])
    ], className="mt-3 shadow-sm")

    return card, False


@callback(
    Output("setup-feedback", "children"),
    [Input("load-config-btn", "n_clicks"),
     Input("add-new-exp-btn", "n_clicks")],
    [State("experiment-select", "value"),
     State("new-exp-name", "value"),
     State("new-exp-acq", "value"),
     State("new-exp-proc", "value"),
     State("new-exp-grid", "value"),
     State("new-exp-shape-x", "value"),
     State("new-exp-shape-y", "value"),
     State("new-exp-first", "value"),
     State("new-exp-last", "value")],
    prevent_initial_call=True
)
def handle_project_initialization(n_load, n_add, sel_name, n_name, n_acq,
                                  n_proc, n_grid_num, n_sx, n_sy, n_f, n_l):
    trigger = ctx.triggered_id

    try:
        if trigger == "load-config-btn":
            configs = get_experiment_configurations()
            cfg = configs.get(sel_name)

        elif trigger == "add-new-exp-btn":
            # Validation for new experiment
            if not all([n_name, n_acq, n_proc, n_sx, n_sy]):
                return dbc.Alert(
                    "Please fill in all required fields (Name, Path, Shape).", color="warning")

            # Initialize the DataService with this config
            grid_shape = [n_sx, n_sy]
            service.initialize_experiment(
                n_name, n_proc, n_grid_num, n_f, n_l, grid_shape, n_acq
            )

            # Parse dataset and create section directories
            service.parse_experiment()

            return dbc.Alert([
                html.H5("Success!", className="alert-heading"),
                html.P(f"Experiment '{n_name}' created and sections were parsed successfully."),
            ], color="success", className="mt-3")

        # Initialize the DataService with this config
        service.load_experiment(cfg)
        return dbc.Alert([
            html.H5("Success!", className="alert-heading"),
            html.P(f"Experiment '{cfg.name}' loaded successfully."),
            html.Hr(),
            html.P("You can now navigate to 'Coarse Proc' or 'Inspection'.", className="mb-0 small"),
        ], color="success", className="mt-3")

    except Exception as e:
        return dbc.Alert(f"Initialization Error: {str(e)}", color="danger", className="mt-3")