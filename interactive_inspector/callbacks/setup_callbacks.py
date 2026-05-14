import logging
import threading
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, ctx, no_update
from data_service import service
from experiment_configs import get_experiment_configurations, ExpConfig, ExperimentRegistryError
from constants import UI


# --- 1. INITIALIZATION CALLBACK ---
@callback(
    [
        Output("setup-feedback", "children", allow_duplicate=True),
        Output(UI.ID_GLOBAL_SETTINGS_STORE, 'data', allow_duplicate=True)
    ],
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
def handle_project_initialization(
        n_load, n_add, sel_name, n_name, n_acq,
        n_proc, n_grid_num, n_sx, n_sy, n_f, n_l, px, ct
):

    # 1. Immediate Guard: Exit if no actual button was clicked
    if not ctx.triggered_id or (not n_load and not n_add):
        return no_update, no_update

    trigger = ctx.triggered_id

    # 2. Initialize store_data at function scope to prevent UnboundLocalError
    store_data = no_update

    try:
        # --- CASE A: LOAD EXISTING ---
        if trigger == UI.ID_BTN_INIT:
            configs = get_experiment_configurations()
            cfg = configs.get(sel_name)

            if not cfg:
                return dbc.Alert("Invalid experiment selection.", color="danger"), no_update

            service.load_experiment(cfg)

            if service.reg_config:
                store_data = service.reg_config.to_dict()

            alert = dbc.Alert([
                html.H5("Success!", className="alert-heading"),
                html.P(f"Experiment '{cfg.name}' loaded successfully."),
            ], color="success", className="mt-3")

            return alert, store_data

        # --- CASE B: CREATE NEW ---
        elif trigger == UI.ID_BTN_ADD_EXP:
            if not all([n_name, n_acq, n_proc, n_sx, n_sy]):
                return dbc.Alert("Missing required fields.", color="warning"), no_update

            exp_config = ExpConfig(
                name=n_name,
                acq_dir=n_acq,
                proc_dir=n_proc,
                grid_num= n_grid_num,
                grid_shape= (int(n_sx), int(n_sy)),
                first_sec=n_f,
                last_sec=n_l,
                pixel_size=px,
                cut_thickness=ct,
            )

            try:
                exp_config = exp_config.validate_range()
                service.create_and_save_new_experiment(exp_config)

                alert = dbc.Alert([
                    html.H5("Success!", className="alert-heading"),
                    html.P(f"Experiment '{n_name}' created."),
                ], color="success", className="mt-3")

                return alert, no_update

            except (ValueError, ExperimentRegistryError) as e:
                return dbc.Alert([
                    html.H5("Action Failed", className="alert-heading"),
                    html.P(str(e)),
                ], color="danger", className="mt-3"), no_update

            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                return dbc.Alert("An internal server error occurred.", color="danger"), no_update

    except Exception as e:
        return dbc.Alert(f"Initialization Error: {str(e)}", color="danger", className="mt-3"), store_data

    return no_update, no_update

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
    # 1. Check the Backend: Does the ppln_service have an active stitch_config?
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
def master_ui_poller(n):
    """Handles ONLY Parsing background process for the Setup Page."""

    # --- PARSING IS ACTIVE ---
    if service.parsing_status["active"] or service.parsing_status["progress"] > 0:
        service.update_percentage_only()
        status = service.parsing_status
        finished = not status["active"] and status["progress"] >= 100

        final_alert = dash.no_update
        if finished:
            service.parsing_status["progress"] = 0  # Reset for next run
            alert_color = "success" if (status.get("missing_count", 0) == 0) else "warning"
            final_alert = dbc.Alert([
                html.H5("Processing Complete", className="alert-heading"),
                html.Ul([
                    html.Li(f"Missing Folders: {status.get('missing_count', 0)}"),
                    html.Li(f"Invalid Maps: {status.get('invalid_maps_count', 0)}"),
                ], className="mb-0")
            ], color=alert_color, className="mt-3")

        # Return state: value, label, status_text, interval_disabled, feedback, animated, striped, color
        return (
            status["progress"],
            f"{status['progress']}%",
            status["message"],
            finished,
            final_alert,
            not finished,
            not finished,
            "success" if finished else "primary"
        )

    # --- NOTHING ACTIVE ---
    # Shut down the interval to save resources
    return (
        dash.no_update, dash.no_update, dash.no_update,
        True,  # Disable interval
        dash.no_update, dash.no_update, dash.no_update, dash.no_update
    )
#
# @callback(
#     Output(UI.ID_GLOBAL_SETTINGS_STORE, 'data'),
#     Input(UI.ID_BTN_INIT, 'n_clicks'),  # Triggered when project is initialized
#     State(UI.ID_SEL_EXPERIMENT, 'value'),
#     prevent_initial_call=True
# )
# def sync_config_to_store(n_clicks, selected_exp):
#     if not n_clicks or not selected_exp:
#         return no_update
#
#     # At this point, service.load_experiment() has been called
#     # (likely in another callback or as part of the init process)
#     if service.stitch_config:
#         cfg = service.stitch_config.registration_config
#
#         # Flatten the object into a dictionary for JSON serialization in dcc.Store
#         config_dict = {
#             "min_peak_ratio": cfg.min_peak_ratio,
#             "min_peak_sharpness": cfg.min_peak_sharpness,
#             "max_deviation": cfg.max_deviation,
#             "max_magnitude": cfg.max_magnitude,
#             "min_patch_size": cfg.min_patch_size,
#             "max_gradient": cfg.max_gradient,
#             "reconcile_flow_max_deviation": cfg.reconcile_flow_max_deviation
#         }
#         return config_dict
#
#     return no_update