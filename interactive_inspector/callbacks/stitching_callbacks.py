import logging
import threading
from dash import Input, Output, State, callback

from constants import UI
from data_service import service
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params


@callback(
    [Output(UI.ID_STITCH_PPLN_CONSOLE, "children"),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "value"),
     Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled")], # Use the NEW unique ID
    Input(UI.ID_STITCH_PPLN_BTN, "n_clicks"),
    [State(UI.ID_STITCH_PPLN_INP, "value"),
     State(UI.ID_STITCH_PPLN_STEPS, "value"),
     State(UI.ID_STITCH_CONFIG_PATH, "value")],
    prevent_initial_call=True
)
def start_stitching_pipeline(n_clicks, range_str, selected_steps, config_path):

    if not selected_steps:
        return [UI.log_row("Error: No steps selected.", type="error")], 0, True

    # Check for service initialization
    if not service.exp_config:
        return [UI.log_row("Error: Experiment not initialized in Step 1.", type="error")], 0, True

    # 1. Section Validation
    first, last = service.exp_config.first_sec, service.exp_config.last_sec

    try:
        if str(range_str).lower() == 'all':
            sec_nums_valid = list(range(first, last + 1))
        else:
            sec_nums_req = parse_section_range(range_str)
            sec_nums_valid = validate_section_numbers(first, last, sec_nums_req)
    except Exception as e:
        return [UI.log_row(f"Error: {e}", type="error")], 0, True

    if not sec_nums_valid:
        return [UI.log_row("Error: No valid sections.", type="error")], 0, True

    # 2. Logic & Threading
    ordered_tasks = [step for step in UI.PPLN_MASTER_ORDER if step in selected_steps]

    init_log = [
        UI.log_row(f"🚀 Initializing Pipeline: {len(ordered_tasks)} steps", type="info"),
        UI.log_row(f"Targeting {len(sec_nums_valid)} sections."),
        UI.log_row("-" * 40)
    ]

    thread = threading.Thread(
        target=service.run_pipeline_thread,
        args=(sec_nums_valid, ordered_tasks, config_path),
        daemon=True
    )
    thread.start()

    return init_log, 5, False  # Correctly returns to 3 Outputs
