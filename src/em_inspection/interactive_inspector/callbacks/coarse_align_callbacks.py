from os.path import basename
from dash import (
    Input,
    Output,
    State,
    callback,
    no_update,
    clientside_callback,
    ctx,
    ALL,
)
from pydantic import ValidationError

from assets.dash_helpers import parse_stitch_configuration, create_alert
from constants import UI
from parameter_config import StitchingConfig
from workflows.coarse_align_workflow import CoarseAlignManager


@callback(
    [
        Output(
            {"type": UI.TYPE_ACQ_CFG_FIELD, "index": ALL}, "value", allow_duplicate=True
        ),
        Output(
            {"type": UI.TYPE_REG_CFG_FIELD, "index": ALL}, "value", allow_duplicate=True
        ),
        Output(
            {"type": UI.TYPE_MESH_CFG_FIELD, "index": ALL},
            "value",
            allow_duplicate=True,
        ),
        Output(
            {"type": UI.TYPE_WARP_CFG_FIELD, "index": ALL},
            "value",
            allow_duplicate=True,
        ),
        Output(
            {"type": UI.TYPE_MASK_CFG_FIELD, "index": ALL},
            "value",
            allow_duplicate=True,
        ),
        Output("stitch_config-load-status", "children"),
        Output("header-path-summary", "children"),
        Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
    ],
    Input(UI.ID_STITCH_LOAD_YAML, "n_clicks"),
    [
        State(UI.ID_STITCH_CONFIG_PATH, "value"),
        State({"type": UI.TYPE_ACQ_CFG_FIELD, "index": ALL}, "id"),
        State({"type": UI.TYPE_REG_CFG_FIELD, "index": ALL}, "id"),
        State({"type": UI.TYPE_MESH_CFG_FIELD, "index": ALL}, "id"),
        State({"type": UI.TYPE_WARP_CFG_FIELD, "index": ALL}, "id"),
        State({"type": UI.TYPE_MASK_CFG_FIELD, "index": ALL}, "id"),
    ],
    prevent_initial_call=True,
)
def handle_config_load(n_clicks, file_path, *layout_ids_lists):
    no_updates = [[no_update] * len(group) for group in layout_ids_lists]

    if not n_clicks:
        return [*no_updates, no_update, no_update, no_update]

    try:
        layout_payloads = CoarseAlignManager.load_yaml_config(
            file_path, layout_ids_lists
        )
        filename = basename(file_path) if file_path else "Unknown Source"

        success_log = [
            UI.log_row(
                f"Configuration loaded successfully from: {filename}", type="info"
            )
        ]
        return [
            *layout_payloads,
            "Loaded successfully",
            f"Active: {filename}",
            success_log,
        ]

    except ValidationError as err:
        error_messages = []
        for e in err.errors():
            field_path = " -> ".join(str(loc) for loc in e["loc"])
            error_messages.append(f"[{field_path}]: {e['msg']}")

        alert_component = create_alert(
            title="Configuration Load Blocked",
            message=f"File validation failed on: {'; '.join(error_messages)}",
        )
        return [*no_updates, "Load failed", "Error", alert_component]

    except Exception as e:
        alert_component = create_alert(
            title="Configuration Load Failed",
            message=f"Infrastructural failure processing file resource: {str(e)}",
        )
        return [*no_updates, "Load failed", "Error", alert_component]


@callback(
    Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
    Input(UI.ID_STITCH_SAVE_YAML, "n_clicks"),
    [
        State(UI.ID_STITCH_CONFIG_PATH, "value"),
        State({"type": UI.TYPE_ACQ_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_REG_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_MESH_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_WARP_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_MASK_CFG_FIELD, "index": ALL}, "value"),
    ],
    prevent_initial_call=True,
)
@parse_stitch_configuration(param_name="stitch_config")
def handle_config_save(n_clicks, path, *args, stitch_config: StitchingConfig = None):
    if not n_clicks or not ctx.triggered_id:
        return no_update

    if isinstance(stitch_config, ValidationError):
        error_messages = []
        for err in stitch_config.errors():
            field_path = " -> ".join(str(loc) for loc in err["loc"])
            error_messages.append(f"[{field_path}]: {err['msg']}")

        return create_alert(
            title="Configuration Save Blocked",
            message=f"Validation failed on: {'; '.join(error_messages)}",
        )

    return CoarseAlignManager.save_yaml_config(n_clicks, path, stitch_config)


@callback(
    [
        Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
        Output("stitch-progress-interval", "disabled", allow_duplicate=True),
        Output("stitch-progress-bar", "style", allow_duplicate=True),
    ],
    Input(UI.ID_RUN_ESTIM_BTN, "n_clicks"),
    [
        State(UI.ID_RUN_ESTIM_INP, "value"),
        State(UI.ID_STITCH_CONFIG_PATH, "value"),
        State({"type": UI.TYPE_ACQ_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_REG_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_MESH_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_WARP_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_MASK_CFG_FIELD, "index": ALL}, "value"),
    ],
    prevent_initial_call=True,
)
@parse_stitch_configuration(param_name="stitch_config")
def run_coarse_alignment(n_clicks, range_str, config_path, *args, stitch_config=None):
    if not n_clicks:
        return no_update, no_update, no_update

    if isinstance(stitch_config, ValidationError):
        err_details = "; ".join(
            [
                f"['{'->'.join(map(str, e['loc']))}']: {e['msg']}"
                for e in stitch_config.errors()
            ]
        )
        log_err = UI.log_row(
            f"Initialization Failed: Schema validation failed -> {err_details}",
            type="error",
        )
        return [log_err], True, {"display": "none"}

    try:
        sec_nums, cp = CoarseAlignManager.run_coarse_alignment_workflow(
            range_str, config_path, stitch_config
        )

        start_log = [
            UI.log_row("▶ Coarse Alignment Initialized", type="info"),
            UI.log_row(
                f"Sections: {sec_nums[0]}-{sec_nums[-1]} ({len(sec_nums)} total)"
            ),
            UI.log_row(f"Overlaps X: {cp.overlaps_x}"),
            UI.log_row(f"Overlaps Y: {cp.overlaps_y}"),
            UI.log_row(f"Min. Range: {cp.min_range}"),
            UI.log_row(f"Min. Overlap: {cp.min_overlap}"),
            UI.log_row(f"Filter Size: {cp.filter_size}"),
            UI.log_row(f"CLAHE: {cp.clahe}"),
            UI.log_row(f"CLAHE clip limit : {cp.clip_limit}"),
            UI.log_row(f"CLAHE kernel size: {cp.kernel_size}"),
            UI.log_row("-" * 50),
            UI.log_row("▶ Thread active. Monitoring...", type="success"),
        ]
        return start_log, False, {"display": "block"}

    except Exception as e:
        log_fail = UI.log_row(f"Initialization Failed: {str(e)}", type="error")
        return [log_fail], True, {"display": "none"}


@callback(
    [
        Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
        Output("stitch-progress-interval", "disabled", allow_duplicate=True),
        Output("stitch-progress-bar", "style", allow_duplicate=True),
    ],
    Input(UI.ID_BTN_BCKP_CO, "n_clicks"),
    prevent_initial_call=True,
)
def handle_coarse_offset_backup(n_clicks):
    if not n_clicks:
        return no_update, no_update, no_update

    try:
        CoarseAlignManager.execute_offset_backup()
        init_log = [
            UI.log_row("💾 Initializing Coarse Offset Backup...", type="info"),
            UI.log_row("Exporting all cx_cy.json files to a .db container."),
        ]
        return init_log, False, {"display": "block", "height": "10px"}

    except Exception as e:
        log_fail = UI.log_row(f"Backup Failed: {str(e)}", type="error")
        return [log_fail], True, {"display": "none"}


@callback(
    [
        Output("stitch-progress-bar", "value"),
        Output("stitch-progress-text", "children"),
        Output("stitch-progress-interval", "disabled", allow_duplicate=True),
        Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
    ],
    Input("stitch-progress-interval", "n_intervals"),
    State(UI.ID_RUN_ESTIM_CONSOLE, "children"),
    prevent_initial_call=True,
)
def unified_progress_poller(n, current_log_components):
    raw_text_history = []
    current_components = (
        current_log_components if isinstance(current_log_components, list) else []
    )

    for comp in current_components:
        try:
            text_val = comp["props"]["children"][1]["props"]["children"]
            raw_text_history.append(text_val)
        except (KeyError, TypeError, IndexError):
            continue

    prog, msg, disable_poller, updated_text_history = (
        CoarseAlignManager.poll_unified_progress(raw_text_history)
    )

    ui_log_rows = []
    for txt in updated_text_history:
        if "ERROR" in txt:
            row_type = "error"
        elif any(token in txt for token in ("Complete", "Done", "Finished")):
            row_type = "success"
        else:
            row_type = "info"

        ui_log_rows.append(UI.log_row(txt, type=row_type))

    return prog, msg, disable_poller, ui_log_rows


@callback(
    Output(UI.ID_GLOBAL_SETTINGS_STORE, "data"),
    Input(UI.ID_BTN_FETCH_GLOBAL, "n_clicks"),
    [
        State({"type": UI.TYPE_ACQ_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_REG_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_MESH_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_WARP_CFG_FIELD, "index": ALL}, "value"),
        State({"type": UI.TYPE_MASK_CFG_FIELD, "index": ALL}, "value"),
    ],
    prevent_initial_call=True,
)
@parse_stitch_configuration(param_name="stitch_config")
def fetch_to_global_store(n_clicks, *args, stitch_config: StitchingConfig = None):

    if (
        not n_clicks
        or isinstance(stitch_config, ValidationError)
        or stitch_config is None
    ):
        return no_update

    return CoarseAlignManager.build_and_serialize_global_store(stitch_config)


@callback(
    [Output(UI.ID_BTN_BCKP_CO, "disabled"), Output(UI.ID_TTP_BCKP, "children")],
    [Input(UI.ID_BTN_BCKP_CO, "n_clicks")],
    State(UI.ID_TTP_BCKP, "children"),
    prevent_initial_call=False,
)
def toggle_backup_button(n_clicks, current_ttp_text):
    ready = CoarseAlignManager.is_backup_ready()
    disabled_state = not ready
    target_msg = UI.MSG_BCKP_CO_READY if ready else UI.MSG_BCKP_CO_DISABLED
    tooltip_output = target_msg if target_msg != current_ttp_text else no_update
    return disabled_state, tooltip_output


clientside_callback(
    """
    function(children) {
        const consoleLog = document.getElementById('stitching-results-console');
        if (!consoleLog) return window.dash_clientside.no_update;
        setTimeout(() => {
            consoleLog.scrollTo({ top: consoleLog.scrollHeight, behavior: 'smooth' });
        }, 100);
        return window.dash_clientside.no_update;
    }
    """,
    Output("scroll-trigger-dummy", "data"),
    Input(UI.ID_RUN_ESTIM_CONSOLE, "children"),
    prevent_initial_call=True,
)
