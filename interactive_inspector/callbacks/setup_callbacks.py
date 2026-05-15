import logging
import threading
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, ctx, no_update, ALL
from data_service import service
from experiment_configs import get_experiment_configurations, ExpConfig, ExperimentRegistryError
from constants import UI
from pydantic import ValidationError
from assets.dash_helpers import parse_form, create_alert


# ==============================================================================
# --- LOAD EXISTING EXPERIMENT ---
# ==============================================================================
@callback(
    [Output("setup-feedback", "children", allow_duplicate=True),
     Output(UI.ID_GLOBAL_SETTINGS_STORE, 'data', allow_duplicate=True)],
    [Input(UI.ID_BTN_INIT, "n_clicks")],
    [State(UI.ID_SEL_EXPERIMENT, "value")],
    prevent_initial_call=True
)
def handle_load_experiment(n_clicks, sel_name):
    if not n_clicks or not ctx.triggered_id:
        return no_update, no_update

    try:
        configs = get_experiment_configurations()
        cfg = configs.get(sel_name)

        if not cfg:
            return create_alert("Invalid Selection", "The chosen experiment could not be found."), no_update

        service.load_experiment(cfg)

        return (
            create_alert("Success!", f"Experiment '{cfg.name}' loaded successfully.", color="success"),
            service.stitch_config.model_dump()
        )

    except Exception as e:
        logging.error(f"Error loading experiment: {e}", exc_info=True)
        return create_alert("Initialization Error", color="danger", exception=e), no_update


# ==============================================================================
# --- CREATE NEW EXPERIMENT ---
# ==============================================================================
@callback(
    [Output("setup-feedback", "children", allow_duplicate=True),
     Output(UI.ID_GLOBAL_SETTINGS_STORE, 'data', allow_duplicate=True)],
    [Input(UI.ID_BTN_ADD_EXP, "n_clicks")],
    [State({'type': UI.TYPE_EXP_FIELD, 'index': ALL}, "value")],
    prevent_initial_call=True
)
@parse_form(
    type_tag=UI.TYPE_EXP_FIELD,
    target_model=ExpConfig,
    param_name="exp_config"
)
def handle_create_experiment(n_clicks, _raw_layout_values, exp_config=None):
    if not n_clicks or not ctx.triggered_id:
        return no_update, no_update

    # 1. Handle Pydantic validation intercept
    if isinstance(exp_config, ValidationError):
        return create_alert("Validation Failed", exception=exp_config), no_update

    # 2. Infrastructure configuration pass
    try:
        service.handle_new_exp_infra(exp_config)

        success_msg = f"Experiment '{exp_config.name}' created. Continue with the 'Parse Experiment' step."
        return (
            create_alert("Success!", success_msg, color="success"),
            service.stitch_config.model_dump()
        )

    except (ValueError, ExperimentRegistryError) as e:
        return create_alert("Infrastructure Setup Failed", exception=e), no_update

    except Exception as e:
        logging.error(f"Unexpected error during experiment creation: {e}", exc_info=True)
        return create_alert("Action Failed", "An unexpected internal server error occurred.", exception=e), no_update


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
    State({'type': UI.TYPE_EXP_FIELD, 'index': UI.ID_INP_NAME}, "value"),
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
    [Input({'type': UI.TYPE_EXP_FIELD, 'index': UI.ID_INP_NAME}, "value"),
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