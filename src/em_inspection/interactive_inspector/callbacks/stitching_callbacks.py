from dash import Input, Output, State, callback

from constants import UI
from workflows.stitching_workflow import StitchingWorkflowManager


@callback(
    [
        Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
        Output(UI.ID_STITCH_PPLN_PROGRESS, "value", allow_duplicate=True),
        Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled", allow_duplicate=True),
    ],
    Input(UI.ID_STITCH_PPLN_RUN, "n_clicks"),
    [
        State(UI.ID_STITCH_PPLN_PARALLEL_TOGGLE, "value"),
        State(UI.ID_STITCH_PPLN_INP, "value"),
        State(UI.ID_STITCH_PPLN_STEPS, "value"),
        State(UI.ID_STITCH_CONFIG_PATH, "value"),
        State(UI.ID_RESCALE_FCT, "value"),
        State(UI.ID_GLOBAL_SETTINGS_STORE, "data"),
    ],
    prevent_initial_call=True,
)
def start_stitching_pipeline(
    n_clicks,
    parallel_value,
    range_str,
    selected_steps,
    config_path,
    scl_fct,
    settings_data,
):
    return StitchingWorkflowManager.run_pipeline(
        n_clicks=n_clicks,
        parallel_value=parallel_value,
        range_str=range_str,
        selected_steps=selected_steps,
        config_path=config_path,
        scl_fct=scl_fct,
        settings_data=settings_data,
    )


@callback(
    [
        Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
        Output(UI.ID_STITCH_PPLN_PROGRESS, "value", allow_duplicate=True),
        Output(UI.ID_STITCH_PPLN_PROGRESS, "animated"),
        Output(UI.ID_STITCH_PPLN_PROGRESS, "striped"),
        Output(UI.ID_STITCH_PPLN_PROGRESS_INT, "disabled", allow_duplicate=True),
        Output("pipeline-status-bar", "children"),
    ],
    Input(UI.ID_STITCH_PPLN_PROGRESS_INT, "n_intervals"),
    State(UI.ID_STITCH_PPLN_CONSOLE, "children"),
    prevent_initial_call=True,
)
def sync_pipeline_progress(n, current_logs):
    return StitchingWorkflowManager.sync_progress(
        n_intervals=n, current_logs=current_logs
    )


@callback(
    Output(UI.ID_STITCH_PPLN_CONSOLE, "children", allow_duplicate=True),
    Input(UI.ID_STITCH_UTILS_MISSING, "n_clicks"),
    prevent_initial_call=True,
)
def handle_find_missing(n_clicks):
    return StitchingWorkflowManager.locate_missing_indices(n_clicks=n_clicks)
