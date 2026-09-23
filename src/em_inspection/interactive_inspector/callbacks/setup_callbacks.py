import logging
import threading
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, ctx, no_update, ALL
from data_service import service
from experiment_configs import (
    get_experiment_configurations,
    ExpConfig,
    ExperimentRegistryError,
)
from constants import UI
from os.path import isdir
from pydantic import ValidationError
from assets.dash_helpers import parse_form, create_alert
from layouts.components_layouts import to_details_card, create_progress_view


# ==============================================================================
# --- LOAD EXISTING EXPERIMENT ---
# ==============================================================================
@callback(
    [
        Output("setup-feedback", "children", allow_duplicate=True),
        Output(UI.ID_GLOBAL_SETTINGS_STORE, "data", allow_duplicate=True),
    ],
    [Input(UI.ID_BTN_INIT, "n_clicks")],
    [State(UI.ID_SEL_EXPERIMENT, "value")],
    prevent_initial_call=True,
)
def handle_load_experiment(n_clicks, sel_name):
    if not n_clicks or not ctx.triggered_id:
        return no_update, no_update

    try:
        configs = get_experiment_configurations()
        cfg = configs.get(sel_name)

        if not cfg:
            title = "Invalid Selection"
            msg = "The chosen experiment could not be found."
            return create_alert(title, msg), no_update

        # Load into core data service memory state
        service.load_experiment(cfg)

        # 1. Primary Success Alert
        feedback_components = [
            create_alert(
                "Success!",
                f"Experiment '{cfg.name}' loaded successfully.",
                color="success",
            )
        ]

        # 2. Defensive I/O check against the infrastructure volume
        acq_dir_path = service.exp_config.acq_dir

        # Verify both path existence and that it's actually a directory
        if not acq_dir_path or not isdir(acq_dir_path):
            warning_alert = dbc.Alert(
                [
                    html.H5(
                        "⚠️ Infrastructure Warning",
                        className="alert-heading font-weight-bold",
                    ),
                    html.P(
                        [
                            f"The processing directory does not exist or is inaccessible: ",
                            html.Code(
                                str(acq_dir_path),
                                className="bg-light p-1 rounded small text-break",
                            ),
                        ],
                        className="mb-0",
                    ),
                    html.Hr(),
                    html.P(
                        "Downstream actions will fail until this volume is mounted or created.",
                        className="small mb-0 text-muted",
                    ),
                ],
                color="warning",
                className="mt-2 shadow-sm",
            )

            feedback_components.append(warning_alert)

        # Wrap multiple components in a standard HTML container div
        return (html.Div(feedback_components), service.stitch_config.model_dump())

    except Exception as e:
        logging.error("Error loading experiment: %s", e, exc_info=True)
        return create_alert(
            "Initialization Error", color="danger", exception=e
        ), no_update


# ==============================================================================
# --- CREATE NEW EXPERIMENT ---
# ==============================================================================
@callback(
    [
        Output("setup-feedback", "children", allow_duplicate=True),
        Output(UI.ID_GLOBAL_SETTINGS_STORE, "data", allow_duplicate=True),
    ],
    [Input(UI.ID_BTN_ADD_EXP, "n_clicks")],
    [State({"type": UI.TYPE_EXP_FIELD, "index": ALL}, "value")],
    prevent_initial_call=True,
)
@parse_form(type_tag=UI.TYPE_EXP_FIELD, target_model=ExpConfig, param_name="exp_config")
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
            service.stitch_config.model_dump(),
        )

    except (ValueError, ExperimentRegistryError) as e:
        return create_alert("Infrastructure Setup Failed", exception=e), no_update

    except Exception as e:
        logging.error(
            f"Unexpected error during experiment creation: {e}", exc_info=True
        )
        return create_alert(
            "Action Failed",
            "An unexpected internal server error occurred.",
            exception=e,
        ), no_update


# ==============================================================================
# --- 3. EXPERIMENT SELECTION DETAILS DISPLAY ---
# ==============================================================================
@callback(
    [Output("experiment-details-card", "children"), Output(UI.ID_BTN_INIT, "disabled")],
    Input("experiment-select", "value"),
)
def update_details(exp_name):
    if not exp_name:
        return "", True

    cfg = get_experiment_configurations().get(exp_name)
    if not cfg:
        return create_alert("Error", "Configuration not found."), True

    return to_details_card(cfg), False


# ==============================================================================
# --- 4. TOGGLE PARSE GATEWAY BUTTON ---
# ==============================================================================
@callback(
    [Output(UI.ID_BTN_PARSE, "disabled"), Output(UI.ID_TTP_PARSE, "children")],
    [
        Input({"type": UI.TYPE_EXP_FIELD, "index": UI.ID_INP_NAME}, "value"),
        Input(UI.ID_GLOBAL_SETTINGS_STORE, "data"),
    ],
    prevent_initial_call=False,
)
def toggle_parse_button(exp_name, settings_data):
    has_config = service.exp_config is not None
    name_matches = False
    if has_config and exp_name:
        name_matches = exp_name.strip() == service.exp_config.name

    is_ready = has_config and name_matches
    button_disabled = not is_ready
    tooltip_msg = UI.MSG_PARSE_READY if is_ready else UI.MSG_PARSE_DISABLED

    return button_disabled, tooltip_msg


# ==============================================================================
# --- 5. TRIGGER PARSING  ---
# ==============================================================================
@callback(
    [
        Output(UI.ID_PARSE_PROGRESS_BAR, "children"),
        Output("progress-interval", "disabled"),
        Output("progress-collapse", "is_open"),
        # Add this line here to target the alert slot
        Output("setup-feedback", "children", allow_duplicate=True),
    ],
    Input(UI.ID_BTN_PARSE, "n_clicks"),
    State({"type": UI.TYPE_EXP_FIELD, "index": UI.ID_INP_NAME}, "value"),
    prevent_initial_call=True,
)
def trigger_parsing(n_clicks, exp_name):
    if not n_clicks:
        return no_update, no_update, no_update, no_update

    if not exp_name:
        return no_update, True, False, no_update

    # Start backend compilation worker thread
    threading.Thread(
        target=service.parse_experiment, args=(exp_name,), daemon=True
    ).start()

    # Generate layout view at 0% to populate the wrapper container instantly
    initial_loader = create_progress_view(
        progress=0, message="Initializing process...", active=True
    )

    return initial_loader, False, True, ""


# ==============================================================================
# --- 6. MASTER UI POLLER (Watches background interval loops) ---
# ==============================================================================
@callback(
    [
        Output(UI.ID_PARSE_PROGRESS_BAR, "children", allow_duplicate=True),
        Output("progress-interval", "disabled", allow_duplicate=True),
        Output("setup-feedback", "children", allow_duplicate=True),
    ],
    Input("progress-interval", "n_intervals"),
    prevent_initial_call=True,
)
def master_ui_poller(n):
    """Interval ticker tracking backend threading completion state updates."""
    status = service.parsing_status

    # --- Case A: Background thread processing is actively moving ---
    if status["active"] or status["progress"] > 0:
        service.update_percentage_only()
        is_finished = not status["active"] and status["progress"] >= 100

        final_alert = no_update
        if is_finished:
            status["progress"] = 0  # Reset token map registry boundary

            has_issues = (
                status.get("missing_count", 0) > 0
                or status.get("invalid_maps_count", 0) > 0
            )
            alert_color = "warning" if has_issues else "success"

            final_alert = create_alert(
                title="Processing Complete"
                if not has_issues
                else "Processing Finished with Warnings",
                color=alert_color,
                bullet_points=[
                    f"Missing Folders: {status.get('missing_count', 0)}",
                    f"Invalid Maps: {status.get('invalid_maps_count', 0)}",
                ],
            )

        progress_view = create_progress_view(
            progress=status["progress"],
            message=status["message"],
            active=not is_finished,
        )

        return progress_view, is_finished, final_alert

    # --- Case B: Process completely went cold/idle ---
    return no_update, True, no_update
