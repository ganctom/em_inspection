import logging
import threading
from dash import Input, Output, State, callback

from constants import UI
from data_service import service, orchestrator
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params


@callback(
    [Output(UI.ID_STITCH_PPLN_CONSOLE, "children"),
     Output(UI.ID_STITCH_PPLN_PROGRESS, "value"),
     Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled")],
    Input(UI.ID_STITCH_PPLN_RUN, "n_clicks"),
    [State(UI.ID_STITCH_PPLN_INP, "value"),
     State(UI.ID_STITCH_PPLN_STEPS, "value"),
     State(UI.ID_STITCH_CONFIG_PATH, "value")
     ],
    prevent_initial_call=True
)
def start_stitching_pipeline(n_clicks, range_str, selected_steps, config_path):
    if not selected_steps:
        return [UI.log_row("Error: No steps selected.", type="error")], 0, True

    if not service.exp_config:
        return [UI.log_row("Error: Experiment not initialized.", type="error")], 0, True

    # 1. Section Validation (Delegated to Orchestrator or Utility)
    try:
        first, last = service.exp_config.first_sec, service.exp_config.last_sec
        if str(range_str).lower() == 'all':
            sec_nums_valid = list(range(first, last + 1))
        else:
            sec_nums_req = parse_section_range(range_str)
            sec_nums_valid = validate_section_numbers(first, last, sec_nums_req)
    except Exception as e:
        return [UI.log_row(f"Validation Error: {e}", type="error")], 0, True

    # 2. Prepare the StitchingConfig Object
    try:
        final_config = service.prepare_stitching_params(config_path, ui_params=None)
    except Exception as e:
        return [UI.log_row(f"Configuration Error: {e}", type="error")], 0, True

    # 3. Launch Thread via Orchestrator
    # We use orchestrator.run_sequential_pipeline as the target
    init_log = [
        UI.log_row(f"🚀 Initializing Pipeline: {len(selected_steps)} steps", type="info"),
        UI.log_row(f"Sections: {sec_nums_valid[0]} to {sec_nums_valid[-1]}"),
        UI.log_row("-" * 40)
    ]

    logging.info(f'sec nums valid: {sec_nums_valid}')
    logging.info(f'selected steps: {selected_steps}')
    logging.info(f'final config: {final_config}')

    thread = threading.Thread(
        target=orchestrator.run_sequential_pipeline,
        args=(sec_nums_valid, selected_steps, final_config),
        daemon=True
    )
    thread.start()

    return init_log, 5, False
