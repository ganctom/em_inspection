import logging
import threading
import yaml
import dash
from dash import Input, Output, State, callback, no_update, clientside_callback
from constants import UI
from data_service import service
import parameter_config as pcfg
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params

#
# @callback(
#     # Outputs for every single UI element defined in the layout
#     [
#         Output(UI.ID_STITCH_CONFIG_PATH, "value"),
#         Output("conf-output-dir", "value"),
#         Output("conf-start", "value"),
#         Output("conf-end", "value"),
#         # Registration
#         Output(UI.ID_CONF_OVERLAPS_X, "value"),
#         Output(UI.ID_CONF_OVERLAPS_Y, "value"),
#         Output(UI.ID_CONF_MIN_OVERLAP, "value"),
#         Output(UI.ID_CONF_MIN_RANGE, "value"),
#         Output(UI.ID_CONF_FILTER_SIZE, "value"),
#         # Status
#         Output("config-load-status", "children"),
#         Output("header-path-summary", "children")
#     ],
#     Input(UI.ID_STITCH_LOAD_YAML, "n_clicks"),
#     State(UI.ID_STITCH_CONFIG_PATH, "value"),
#     prevent_initial_call=True
# )
# def handle_config_load(n_clicks, file_path):
#     if not file_path:
#         return [no_update] * 20 + ["Please enter a path", ""]
#
#     try:
#         with open(file_path, 'r') as f:
#             data = yaml.safe_load(f)
#
#         cfg = pcfg.StitchingConfig(**data)
#         reg = cfg.registration_config
#
#         return [
#             file_path,
#             cfg.output_dir,
#             cfg.start_section,
#             cfg.end_section,
#             ", ".join(map(str, reg.overlaps_x)),
#             ", ".join(map(str, reg.overlaps_y)),
#             reg.min_overlap,
#             ", ".join(map(str, reg.min_range)),
#             reg.filter_size,
#             "Config loaded successfully",
#             f"Active: {file_path.split('/')[-1]}"
#         ]
#     except Exception as e:
#         return [no_update] * 20 + [f"Error: {str(e)}", "Error"]

@callback(
    [
        Output(UI.ID_STITCH_CONFIG_PATH, "value"),
        Output("conf-output-dir", "value"),
        Output("conf-start", "value"),
        Output("conf-end", "value"),
        # Registration
        Output(UI.ID_CONF_OVERLAPS_X, "value"),
        Output(UI.ID_CONF_OVERLAPS_Y, "value"),
        Output(UI.ID_CONF_MIN_OVERLAP, "value"),
        Output(UI.ID_CONF_MIN_RANGE, "value"),
        Output(UI.ID_CONF_FILTER_SIZE, "value"),
        # Status
        Output("config-load-status", "children"),
        Output("header-path-summary", "children")
    ],
    Input(UI.ID_STITCH_LOAD_YAML, "n_clicks"),
    State(UI.ID_STITCH_CONFIG_PATH, "value"),
    prevent_initial_call=True
)
def handle_config_load(n_clicks, file_path):
    # Total outputs = 11. We must return exactly 11 items.
    if not file_path:
        return [no_update] * 9 + ["Please enter a path", ""]

    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        # Validate with Pydantic
        cfg = pcfg.StitchingConfig(**data)
        reg = cfg.registration_config

        return [
            file_path,                               # ID_STITCH_CONFIG_PATH
            cfg.output_dir,                          # conf-output-dir
            cfg.start_section,                       # conf-start
            cfg.end_section,                         # conf-end
            ", ".join(map(str, reg.overlaps_x)),     # ID_CONF_OVERLAPS_X
            ", ".join(map(str, reg.overlaps_y)),     # ID_CONF_OVERLAPS_Y
            reg.min_overlap,                         # ID_CONF_MIN_OVERLAP
            ", ".join(map(str, reg.min_range)),      # ID_CONF_MIN_RANGE
            reg.filter_size,                         # ID_CONF_FILTER_SIZE
            "Config loaded successfully",            # config-load-status
            f"Active: {file_path.split('/')[-1]}"    # header-path-summary
        ]
    except Exception as e:
        # Return 9 no_updates followed by the error message and status
        return [no_update] * 9 + [f"Error: {str(e)}", "Error"]


@callback(
    Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
    Input(UI.ID_STITCH_SAVE_YAML, "n_clicks"),
    [
        State(UI.ID_STITCH_CONFIG_PATH, "value"),
        # Acquisition & Range
        State("conf-output-dir", "value"),
        State("conf-start", "value"),
        State("conf-end", "value"),
        # Registration States
        State(UI.ID_CONF_OVERLAPS_X, "value"),
        State(UI.ID_CONF_OVERLAPS_Y, "value"),
        State(UI.ID_CONF_MIN_OVERLAP, "value"),
        State(UI.ID_CONF_MIN_RANGE, "value"),
        State(UI.ID_CONF_FILTER_SIZE, "value"),
    ],
    prevent_initial_call=True
)
def handle_config_save(n_clicks, path, *args):
    if not path:
        return "Error: No config path specified."

    # Helper to only include values that are not None or empty strings
    def clean_dict(d):
        return {k: v for k, v in d.items() if v is not None and v != ""}

    # Helper for CSV parsing
    def parse_csv(val):
        if not val or not str(val).strip(): return None
        return [int(x.strip()) for x in str(val).split(",")]

    try:
        (out_dir, start, end,
         ox, oy, m_ov, m_rng, fs) = args

        reg_data = clean_dict({
            "overlaps_x": parse_csv(ox),
            "overlaps_y": parse_csv(oy),
            "min_overlap": m_ov,
            "min_range": parse_csv(m_rng),
            "filter_size": fs,
        })

        # Final Assembly
        main_data = clean_dict({
            "output_dir": out_dir,
            "start_section": start,
            "end_section": end,
            "registration_config": pcfg.RegistrationConfig(**reg_data),
        })

        new_cfg = pcfg.StitchingConfig(**main_data)
        new_cfg.acquisition_config = service.acq_config
        pcfg.save_to_disk(new_cfg, path)

        return f"Successfully saved to {path}. Defaults applied for empty fields."

    except Exception as e:
        return f"Save failed: {str(e)}"


@callback(
    [Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
     Output("stitch-progress-interval", "disabled", allow_duplicate=True),
     Output("stitch-progress-bar", "style", allow_duplicate=True)],
    Input(UI.ID_RUN_ESTIM_BTN, "n_clicks"),
    [State(UI.ID_RUN_ESTIM_INP, "value"),
     State(UI.ID_STITCH_CONFIG_PATH, "value"),
     State(UI.ID_CONF_OVERLAPS_X, "value"),
     State(UI.ID_CONF_OVERLAPS_Y, "value"),
     State(UI.ID_CONF_MIN_RANGE, "value"),
     State(UI.ID_CONF_MIN_OVERLAP, "value"),
     State(UI.ID_CONF_FILTER_SIZE, "value")],
    prevent_initial_call=True
)
def run_coarse_alignment(n_clicks, range_str, config_path, ox, oy, m_range, m_overlap, fs):
    # 1. Initial experiment check
    if not service.exp_config:
        msg = UI.log_row("Error: No active experiment found. Please initialize in Step 1.", type="error")
        return [msg], True, {"display": "none"}

    if not range_str:
        msg = UI.log_row("Error: Please specify sections for estimation.", type="error")
        return [msg], True, {"display": "none"}

    # 2. Section Validation Logic  # TODO move to some utility module (it is also in stitching_callback)
    first_sec = service.exp_config.first_sec
    last_sec = service.exp_config.last_sec
    sec_nums_valid = list(range(first_sec, last_sec+1))

    if str(range_str).lower() != 'all':
        try:
            sec_nums_req = parse_section_range(range_str)
            sec_nums_valid = validate_section_numbers(first_sec, last_sec, sec_nums_req)
        except ValueError as e:
            logging.warning(f"Validation failed: {e}")
            return [UI.log_row(f"Error: {e}", type="error")], True, {"display": "none"}

    if not sec_nums_valid:
        return [UI.log_row("Error: No valid sections selected.", type="error")], True, {"display": "none"}

    # 3. Parameter Preparation (Consolidated before thread starts)
    ui_params_dict = {
        "overlaps_x": ox,
        "overlaps_y": oy,
        "min_range": m_range,
        "min_overlap": m_overlap,
        "filter_size": fs,
    }

    try:
        final_stitch_params = service.prepare_stitching_params(
            config_path=config_path,
            ui_params=make_hashable_params(ui_params_dict)
        )
    except Exception as e:
        return [UI.log_row(f"Config Error: {e}", type="error")], True, {"display": "none"}

    # 4. Construct Initial Console UI (List of Components)
    start_log = [
        UI.log_row("▶ Starting Coarse Offset Estimation...", type="info"),
        UI.log_row(f"Experiment location: {service.exp_config.proc_dir}"),
        UI.log_row(f"Sections: {len(sec_nums_valid)} requested ({sec_nums_valid[0]}-{sec_nums_valid[-1]})"),
        UI.log_row(f"Using Overlaps: {final_stitch_params['overlaps_xy']}"),
        UI.log_row("-" * 50),
        UI.log_row("▶ Thread started. Monitoring progress...", type="success")
    ]

    # 5. Launch the Thread
    thread = threading.Thread(
        target=service.run_coarse_align_thread,
        args=(sec_nums_valid, final_stitch_params),
        daemon=True
    )
    thread.start()

    # 6. Returns: [Console Children], Interval Disabled=False, Progress Style=Visible
    return start_log, False, {"display": "block"}


clientside_callback(
    """
    function(children) {
        // Find the console element
        const consoleLog = document.getElementById('stitching-results-console');

        // Defensive check: if it doesn't exist yet, just exit silently
        if (!consoleLog) {
            return window.dash_clientside.no_update;
        }

        // Use a slight delay to ensure Dash has finished injecting the new <div> rows
        setTimeout(() => {
            consoleLog.scrollTo({
                top: consoleLog.scrollHeight,
                behavior: 'smooth'
            });
        }, 100);

        return window.dash_clientside.no_update;
    }
    """,
    Output("scroll-trigger-dummy", "data"),  # Target the dummy store instead of the Console ID
    Input(UI.ID_RUN_ESTIM_CONSOLE, "children"),
    prevent_initial_call=True
)


# --- 1. TRIGGER BACKUP ---
@callback(
    [Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
     Output("stitch-progress-interval", "disabled", allow_duplicate=True),
     Output("stitch-progress-bar", "style", allow_duplicate=True)],
    Input(UI.ID_BTN_BCKP_CO, "n_clicks"),
    prevent_initial_call=True
)
def handle_coarse_offset_backup(n_clicks):
    if not n_clicks or not service.exp_config:
        return [UI.log_row("Error: No active experiment.", type="error")], True, no_update

    thread = threading.Thread(target=service.run_offsets_backup_thread, daemon=True)
    thread.start()

    init_log = [
        UI.log_row("💾 Initializing Coarse Offset Backup...", type="info"),
        UI.log_row("Exporting all cx_cy.json files to .npz container.")
    ]

    return init_log, False, {"display": "block", "height": "10px"}


# --- 2. UNIFIED POLLER ---
@callback(
    [Output("stitch-progress-bar", "value"),
     Output("stitch-progress-text", "children"),
     Output("stitch-progress-interval", "disabled", allow_duplicate=True),
     Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True)],
    Input("stitch-progress-interval", "n_intervals"),
    State(UI.ID_RUN_ESTIM_CONSOLE, "children"),
    prevent_initial_call=True
)
def unified_progress_poller(n, current_log):
    # 1. Determine which process is currently active in the service
    # We check Backup first, then Coarse Alignment
    if service.backup_status["active"] or service.backup_status["progress"] > 0:
        status = service.backup_status
        is_backup = True
    else:
        status = service.coarse_align_status
        is_backup = False

    log_history = current_log if isinstance(current_log, list) else []

    # 2. Handle Thread Errors
    if status.get("error"):
        log_history.append(UI.log_row(f"🛑 ERROR: {status['error']}", type="error"))
        return 0, "Failed", True, log_history

    prog = status.get("progress", 0)
    msg = status.get("message", "")

    # 3. Deduplication: Only add to console if the message is new
    last_msg = ""
    try:
        if log_history:
            # Reaching into the Dash component structure to find the text string
            last_msg = log_history[-1]['props']['children'][1]['props']['children']
    except:
        pass

    if msg and msg != last_msg:
        log_type = "success" if "Complete" in msg or "Done" in msg else "info"
        log_history.append(UI.log_row(msg, type=log_type))

    # 4. Termination Logic
    # If the thread is no longer active and we hit 100%
    if not status.get("active") and prog >= 100:
        # Reset the progress so the bar doesn't stay full for the next task
        if is_backup:
            service.backup_status["progress"] = 0
        else:
            service.coarse_align_status["progress"] = 0

        return 100, "Operation Finished.", True, log_history

    return prog, msg, False, log_history


# --- 3. DYNAMIC BUTTON STATE ---
@callback(
    [Output(UI.ID_BTN_BCKP_CO, "disabled"),
     Output(UI.ID_TTP_BCKP, "children")],  # Still targeting the 'children' key
    [Input(UI.ID_BTN_BCKP_CO, "n_clicks")],
    State(UI.ID_TTP_BCKP, "children"),
    prevent_initial_call=False
)
def toggle_backup_button(n_clicks, current_ttp_text):
    is_ready = service.exp_config is not None
    button_disabled = not is_ready

    # Use the logic-driven message
    new_msg = UI.MSG_BCKP_CO_READY if is_ready else UI.MSG_BCKP_CO_DISABLED

    tooltip_output = new_msg if new_msg != current_ttp_text else dash.no_update
    return button_disabled, tooltip_output

