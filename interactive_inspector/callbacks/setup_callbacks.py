import threading
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, ctx
from data_service import service
from experiment_configs import get_experiment_configurations
from constants import UI


@callback(
    Output("setup-feedback", "children"),
    [Input(UI.BTN_INIT['id'], "n_clicks"),
     Input(UI.BTN_ADD_EXP['id'], "n_clicks")],
    [State(UI.ID_SEL_EXPERIMENT, "value"),
     State(UI.ID_INP_NAME, "value"),
     State(UI.ID_INP_ACQ, "value"),
     State(UI.ID_INP_PROC, "value"),
     State(UI.ID_INP_GRID_NUM, "value"),
     State(UI.ID_INP_GS_X, "value"),
     State(UI.ID_INP_GS_Y, "value"),
     State(UI.ID_INP_FIRST_SEC, "value"),
     State(UI.ID_INP_LAST_SEC, "value"),
     State(UI.ID_INP_PX_SIZE, "value"),
     State(UI.ID_INP_CT, "value")],
    prevent_initial_call=True
)
def handle_project_initialization(n_load, n_add, sel_name, n_name, n_acq,
                                  n_proc, n_grid_num, n_sx, n_sy, n_f, n_l, px, ct):
    trigger = ctx.triggered_id

    try:
        if trigger == UI.ID_BTN_INIT:
            configs = get_experiment_configurations()
            cfg = configs.get(sel_name)
            service.load_experiment(cfg)
            return dbc.Alert([
                html.H5("Success!", className="alert-heading"),
                html.P(f"Experiment '{cfg.name}' loaded successfully."),
            ], color="success", className="mt-3")

        elif trigger == UI.ID_BTN_ADD_EXP:
            if not all([n_name, n_acq, n_proc, n_sx, n_sy]):
                return dbc.Alert("Please fill in all required fields.", color="warning")

            grid_shape = tuple([n_sx, n_sy])
            service.create_and_save_new_experiment(
                n_name, n_proc, n_grid_num, grid_shape, n_f, n_l, n_acq, px, ct
            )

            return dbc.Alert([
                html.H5("Success!", className="alert-heading"),
                html.P(f"Experiment '{n_name}' created. Continue with 'Parse Section Data'."),
            ], color="success", className="mt-3")

    except Exception as e:
        return dbc.Alert(
            f"Initialization Error: {str(e)}", color="danger", className="mt-3")


@callback(
    [Output("experiment-details-card", "children"),
     Output(UI.ID_BTN_INIT, "disabled")],
    Input("experiment-select", "value")
)
def update_details(exp_name):
    if not exp_name:
        return "", True

    configs = get_experiment_configurations()
    cfg = configs.get(exp_name)
    if not cfg:
        return dbc.Alert("Configuration not found", color="danger"), True

    card = dbc.Card([
        dbc.CardHeader(html.Strong(cfg.name)),
        dbc.CardBody([
            html.P([html.B("Path: "), html.Span(cfg.proc_dir, className="text-break small")]),
            html.P([html.B("Sections: "), f"{cfg.first_sec} - {cfg.last_sec}"], className="mb-1"),
            html.P([html.B("Grid: "), f"#{cfg.grid_num} ({cfg.grid_shape[0]}x{cfg.grid_shape[1]})"], className="mb-1"),
        ])
    ], className="mt-3 shadow-sm")

    return card, False


# --- TRIGGER CALLBACK ---
@callback(
    [Output("progress-interval", "disabled"),
     Output("progress-collapse", "is_open"),
     Output("parsing-progress-bar", "animated", allow_duplicate=True),
     Output("parsing-progress-bar", "striped", allow_duplicate=True),
     Output("parsing-progress-bar", "color", allow_duplicate=True),
     Output("parsing-progress-bar", "value", allow_duplicate=True),
     Output("setup-feedback", "children", allow_duplicate=True)],
    Input(UI.ID_BTN_PARSE, "n_clicks"),
    State(UI.ID_INP_NAME, "value"),
    prevent_initial_call=True
)
def trigger_parsing(n, exp_name):
    if not exp_name:
        return True, False, dash.no_update, dash.no_update, dash.no_update, 0, dash.no_update

    thread = threading.Thread(
        target=service.parse_experiment,
        args=(exp_name,),
        daemon=True
    )
    thread.start()

    return False, True, True, True, "primary", 0, ""


@callback(
    [Output(UI.ID_BTN_PARSE, "disabled"),
     Output(UI.ID_TTP_PARSE, "children")],
    [Input(UI.ID_INP_NAME, "value"),
     Input("setup-feedback", "children"),
     Input(UI.ID_BTN_INIT, "n_clicks")],
    prevent_initial_call=False
)
def toggle_parse_button(exp_name, feedback, n_init):
    # 1. Check the Backend: Does the service have an active config?
    has_config = service.exp_config is not None

    # 2. Check the Frontend: Is there a name present?
    current_name = exp_name if exp_name else (service.exp_config.name if has_config else None)
    has_name = bool(current_name and current_name.strip())

    # 3. Validation: Did the last action result in an error?
    is_error = False
    if isinstance(feedback, dict) and 'props' in feedback:
        is_error = feedback.get('props', {}).get('color') == 'danger'

    # The "Green Light" condition
    is_ready = has_config and has_name and not is_error

    # Return state
    button_disabled = not is_ready
    tooltip_msg = UI.MSG_PARSE_READY if is_ready else UI.MSG_PARSE_DISABLED

    return button_disabled, tooltip_msg


# --- POLLER CALLBACK ---
@callback(
    [Output("parsing-progress-bar", "value"),
     Output("parsing-progress-bar", "label"),
     Output("parsing-status-text", "children"),
     Output("progress-interval", "disabled", allow_duplicate=True),
     Output("setup-feedback", "children", allow_duplicate=True),
     Output("parsing-progress-bar", "animated"),
     Output("parsing-progress-bar", "striped"),
     Output("parsing-progress-bar", "color")],
    Input("progress-interval", "n_intervals"),
    prevent_initial_call=True
)
def update_ui_from_service(n):
    service.update_percentage_only()
    status = service.parsing_status
    finished = not status["active"] and status["progress"] >= 100

    final_alert = dash.no_update
    if finished:
        missing = status.get("missing_count", 0)
        invalid = status.get("invalid_maps_count", 0)

        # Determine alert color based on findings
        alert_color = "success" if (missing == 0 and invalid == 0) else "warning"

        final_alert = dbc.Alert([
            html.H5("Processing Complete", className="alert-heading"),
            html.P("Parsing and Validation finished."),
            html.Ul([
                html.Li(f"Missing Section Folders: {missing}"),
                html.Li(f"Invalid Tile-ID Maps: {invalid}"),
            ], className="mb-0")
        ], color=alert_color, className="mt-3")

    # Visual state
    is_animated = not finished
    is_striped = not finished
    bar_color = "success" if finished else "primary"
    if finished and (status.get("missing_count", 0) > 0 or status.get("invalid_maps_count", 0) > 0):
        bar_color = "warning"  # Visually flag that it's done but with issues

    return (
        status["progress"],
        f"{status['progress']}%",
        status["message"],
        finished,
        final_alert,
        is_animated,
        is_striped,
        bar_color
    )
