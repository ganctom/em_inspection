import logging
import threading
from dash import Input, Output, State, callback
from dash.exceptions import PreventUpdate

from constants import UI
from data_service import service, orchestrator
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params



@callback(
    [Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "value", allow_duplicate=True),
     Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled", allow_duplicate=True)],
    Input(UI.ID_STITCH_PPLN_RUN, "n_clicks"),
    [State(UI.ID_STITCH_PPLN_PARALLEL_TOGGLE, "value"),
     State(UI.ID_STITCH_PPLN_INP, "value"),
     State(UI.ID_STITCH_PPLN_STEPS, "value"),
     State(UI.ID_STITCH_CONFIG_PATH, "value")],
    prevent_initial_call=True
)
def start_stitching_pipeline(n_clicks, use_parallel, range_str, selected_steps, config_path):
    if not n_clicks or not selected_steps:
        raise PreventUpdate

    # 1. Validation & Config Prep (Logic remains the same)
    try:
        sec_nums, final_config = orchestrator.validate_and_prepare(
            range_str, config_path, ui_params_raw=None
        )
    except Exception as e:
        return [UI.log_row(f"❌ Setup Error: {e}", type="error")], 0, True

    # 2. Launching the Parallel Orchestrator
    # We launch a single MASTER THREAD that manages the PROCESS POOL.
    # This prevents the Dash server from hanging while waiting for the pool.

    # Check if 'parallel' was checked in the list
    target_method = (orchestrator.run_parallel_pipeline if use_parallel
                     else orchestrator.run_sequential_pipeline)

    thread = threading.Thread(
        target=target_method,
        args=(sec_nums, selected_steps, final_config),
        daemon=True
    )
    thread.start()

    init_log = [
        UI.log_row(f"🚀 Parallel Pipeline Started: {len(selected_steps)} tasks", type="info"),
        UI.log_row(f"Targeting {len(sec_nums)} sections across multiple cores."),
        UI.log_row("-" * 40)
    ]
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