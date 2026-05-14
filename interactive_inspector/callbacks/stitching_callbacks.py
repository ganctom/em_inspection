import threading
from dash import Input, Output, State, callback, no_update
from dash.exceptions import PreventUpdate

from constants import UI, MSG
from data_service import service, orchestrator
from inspection_refactored import init_specific_section_dirs
from parameter_config import RegistrationConfig


@callback(
    [Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "value", allow_duplicate=True),
     Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled", allow_duplicate=True)],
    Input(UI.ID_STITCH_PPLN_RUN, "n_clicks"),
    [State(UI.ID_STITCH_PPLN_PARALLEL_TOGGLE, "value"),
     State(UI.ID_STITCH_PPLN_INP, "value"),
     State(UI.ID_STITCH_PPLN_STEPS, "value"),
     State(UI.ID_STITCH_CONFIG_PATH, "value"),
     State(UI.ID_RESCALE_FCT, "value"),
     State(UI.ID_GLOBAL_SETTINGS_STORE, 'data')
     ],
    prevent_initial_call=True
)
def start_stitching_pipeline(
        n_clicks,
        parallel_value,
        range_str,
        selected_steps,
        config_path,
        scl_fct,
        settings_data
):
    if not n_clicks:
        raise PreventUpdate

    if not selected_steps:
        return [UI.log_row(MSG.NO_STEPS_ERROR, type="error")], 0, True

    # Resolve parallel state
    is_par = bool(parallel_value) if not isinstance(parallel_value, list) else 'parallel' in parallel_value

    # Validation & Config Prep
    ui_config = RegistrationConfig(**settings_data)
    # print(f'fetching patch size: {ui_config.patch_size}')
    # print(ui_config)
    try:
        sec_nums, final_config = orchestrator.validate_and_prepare(
            range_str,
            config_path,
            ui_params_raw = {
                UI.ID_RESCALE_FCT: scl_fct,
                UI.ID_CONF_PATCH: tuple(ui_config.patch_size)
            }
        )
    except Exception as e:
        return [UI.log_row(MSG.SETUP_ERROR.format(error=e), type="error")], 0, True

    # Initialize sections data
    init_specific_section_dirs(service.inspection, sec_nums)

    # Thread Dispatch
    target_method = (orchestrator.run_parallel_pipeline if is_par
                     else orchestrator.run_sequential_pipeline)

    threading.Thread(
        target=target_method,
        args=(sec_nums, selected_steps, final_config),
        daemon=True
    ).start()

    # Generate Log using MSG Constants
    mode_str = MSG.MODE_PARALLEL if is_par else MSG.MODE_SEQUENTIAL
    tsk_lbl = MSG.format_tasks(selected_steps)

    init_log = [
        UI.log_row(MSG.PPLN_START.format(mode=mode_str), type="info"),
        UI.log_row(MSG.PPLN_TASKS.format(tasks=tsk_lbl)),
        UI.log_row(MSG.PPLN_SCOPE.format(
            count=len(sec_nums),
            first=sec_nums[0],
            last=sec_nums[-1]
        )),
    ]

    if is_par:
        init_log.append(UI.log_row(MSG.PARALLEL_WARN, type="warning"))

    init_log.append(UI.log_row(MSG.PPLN_DIVIDER))

    return init_log, 2, False


# --- CALLBACK B: SYNC PROGRESS ---
@callback(
    [Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "value", allow_duplicate=True),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "animated"),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "striped"),
     Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled", allow_duplicate=True),
     Output("pipeline-status-bar", "children")],
    Input(UI.ID_STITCH_PPLN_PROGRESS_INT, "n_intervals"),
    State(UI.ID_STITCH_PPLN_CONSOLE, "children"),
    prevent_initial_call=True
)
def sync_pipeline_progress(n, current_logs):
    status = service.stitch_status

    # 1. Fetch new logs and clear the buffer
    new_logs = status.get("pending_messages", [])
    status["pending_messages"] = []  # Clear the bridge

    updated_logs = current_logs + new_logs
    progress = status.get("progress", 0)
    msg = status.get("message", "Processing...")
    is_active = status.get("active", False)

    # 2. Logic for Finished State
    if not is_active and progress >= 100:
        # Stop animation, stop the interval, show final success msg
        return (
            updated_logs,
            100,  # Progress
            False,  # Animated
            False,  # Striped
            True,  # Disable Interval (Stops the loop)
            f"✅ {msg}"
        )

    # 3. Logic for Aborted/Error State
    if not is_active and status.get("error"):
        return updated_logs, progress, False, False, True, f"❌ Error: {status['error']}"

    # 4. Standard Running State
    return updated_logs, progress, True, True, False, f"⏳ {msg}"


@callback(
    Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
    Input(UI.ID_STITCH_UTILS_MISSING, "n_clicks"),
    State(UI.ID_STITCH_CONFIG_PATH, "value"),
    prevent_initial_call=True
)
def handle_find_missing(n_clicks, config_path):
    if not n_clicks:
        return no_update

    # Logic: Scan output directory for missing .zarr or .tif indices
    missing_indices = service.get_missing_stitched_sections()

    if not missing_indices:
        return [UI.log_row("✨ No missing sections found. Dataset is complete.", type="success")]

    msg = f"Found {len(missing_indices)} missing sections: {missing_indices[:10]}..."
    return [UI.log_row(msg, type="warning")]