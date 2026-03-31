import logging
import threading
import yaml
import dash
from dash import Input, Output, State, callback, no_update, clientside_callback
from constants import UI
from data_service import service
import parameter_config as pcfg
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params


# --- 1. UNIFIED LOAD CALLBACK ---
@callback(
    [
        Output(UI.ID_STITCH_CONFIG_PATH, "value"),
        Output("conf-output-dir", "value"),
        Output("conf-start", "value"),
        Output("conf-end", "value"),
        # Registration (9 outputs)
        Output(UI.ID_CONF_OVERLAPS_X, "value"),
        Output(UI.ID_CONF_OVERLAPS_Y, "value"),
        Output(UI.ID_CONF_MIN_OVERLAP, "value"),
        Output(UI.ID_CONF_MIN_RANGE, "value"),
        Output(UI.ID_CONF_FILTER_SIZE, "value"),
        Output(UI.ID_CONF_PATCH, "value"),
        Output(UI.ID_CONF_BATCH, "value"),
        Output(UI.ID_CONF_MIN_PKR, "value"),
        Output(UI.ID_CONF_MIN_PKS, "value"),
        # Extra Reg (5 outputs)
        Output(UI.ID_CONF_MAX_DEV, "value"),
        Output(UI.ID_CONF_MAX_MAG, "value"),
        Output(UI.ID_CONF_MIN_PATCH, "value"),
        Output(UI.ID_CONF_MAX_GRAD, "value"),
        Output(UI.ID_CONF_REC_FLOW_MAX_GRAD, "value"),
        # Mesh (13 outputs)
        Output(UI.ID_CONF_MESH_DT, "value"),
        Output(UI.ID_CONF_MESH_GAMMA, "value"),
        Output(UI.ID_CONF_MESH_K0, "value"),
        Output(UI.ID_CONF_MESH_K, "value"),
        Output(UI.ID_CONF_MESH_STRIDE, "value"),
        Output(UI.ID_CONF_MESH_NUM_ITERS, "value"),
        Output(UI.ID_CONF_MESH_MAX_ITERS, "value"),
        Output(UI.ID_CONF_MESH_STOP_V, "value"),
        Output(UI.ID_CONF_MESH_DT_MAX, "value"),
        Output(UI.ID_CONF_MESH_START_CAP, "value"),
        Output(UI.ID_CONF_MESH_FINAL_CAP, "value"),
        Output(UI.ID_CONF_MESH_ORIG_ORDER, "value"),
        Output(UI.ID_CONF_MESH_REMOVE_DRIFT, "value"),
        # Warp (6 outputs)
        Output(UI.ID_CONF_WARP_MARGIN, "value"),
        Output(UI.ID_CONF_WARP_PARALLEL, "value"),
        Output(UI.ID_CONF_WARP_KERNEL, "value"),
        Output(UI.ID_CONF_WARP_CLIP, "value"),
        Output(UI.ID_CONF_WARP_NBINS, "value"),
        Output(UI.ID_CONF_WARP_CLAHE, "value"),
        # Status
        Output("config-load-status", "children"),
        Output("header-path-summary", "children")
    ],
    Input(UI.ID_STITCH_LOAD_YAML, "n_clicks"),
    State(UI.ID_STITCH_CONFIG_PATH, "value"),
    prevent_initial_call=True
)
def handle_config_load(n_clicks, file_path):
    # Total outputs = 39. We must return exactly 39 items.
    total_outputs = 39
    if not file_path:
        return [no_update] * (total_outputs - 2) + ["Please enter a path", ""]

    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        cfg = pcfg.StitchingConfig(**data)
        reg, mesh, warp = cfg.registration_config, cfg.mesh_integration_config, cfg.warp_config

        to_csv = lambda x: ", ".join(map(str, x)) if x else ""

        return [
            file_path, cfg.output_dir, cfg.start_section, cfg.end_section,
            # Registration
            to_csv(reg.overlaps_x), to_csv(reg.overlaps_y), reg.min_overlap,
            to_csv(reg.min_range), reg.filter_size, to_csv(reg.patch_size),
            reg.batch_size, reg.min_peak_ratio, reg.min_peak_sharpness,
            reg.max_deviation, reg.max_magnitude, reg.min_patch_size,
            reg.max_gradient, reg.reconcile_flow_max_deviation,
            # Mesh
            mesh.dt, mesh.gamma, mesh.k0, mesh.k, mesh.stride,
            mesh.num_iters, mesh.max_iters, mesh.stop_v_max, mesh.dt_max,
            mesh.start_cap, mesh.final_cap,
            [True] if mesh.prefer_orig_order else [],
            [True] if mesh.remove_drift else [],
            # Warp
            warp.margin, warp.warp_parallelism, warp.kernel_size,
            warp.clip_limit, warp.nbins,
            [True] if warp.use_clahe else [],
            # Status
            "Config loaded successfully", f"Active: {file_path.split('/')[-1]}"
        ]
    except Exception as e:
        return [no_update] * (total_outputs - 2) + [f"Error: {str(e)}", "Error"]


# --- 2. UNIFIED SAVE CALLBACK (Synchronized with Loader) ---
@callback(
    Output(UI.ID_RUN_ESTIM_CONSOLE, "children", allow_duplicate=True),
    Input(UI.ID_STITCH_SAVE_YAML, "n_clicks"),
    [
        State(UI.ID_STITCH_CONFIG_PATH, "value"),
        State("conf-output-dir", "value"),
        State("conf-start", "value"),
        State("conf-end", "value"),
        # Reg States
        State(UI.ID_CONF_OVERLAPS_X, "value"), State(UI.ID_CONF_OVERLAPS_Y, "value"),
        State(UI.ID_CONF_MIN_OVERLAP, "value"), State(UI.ID_CONF_MIN_RANGE, "value"),
        State(UI.ID_CONF_FILTER_SIZE, "value"), State(UI.ID_CONF_PATCH, "value"),
        State(UI.ID_CONF_BATCH, "value"), State(UI.ID_CONF_MIN_PKR, "value"),
        State(UI.ID_CONF_MIN_PKS, "value"), State(UI.ID_CONF_MAX_DEV, "value"),
        State(UI.ID_CONF_MAX_MAG, "value"), State(UI.ID_CONF_MIN_PATCH, "value"),
        State(UI.ID_CONF_MAX_GRAD, "value"), State(UI.ID_CONF_REC_FLOW_MAX_GRAD, "value"),
        # Mesh States
        State(UI.ID_CONF_MESH_DT, "value"), State(UI.ID_CONF_MESH_GAMMA, "value"),
        State(UI.ID_CONF_MESH_K0, "value"), State(UI.ID_CONF_MESH_K, "value"),
        State(UI.ID_CONF_MESH_STRIDE, "value"), State(UI.ID_CONF_MESH_NUM_ITERS, "value"),
        State(UI.ID_CONF_MESH_MAX_ITERS, "value"), State(UI.ID_CONF_MESH_STOP_V, "value"),
        State(UI.ID_CONF_MESH_DT_MAX, "value"), State(UI.ID_CONF_MESH_START_CAP, "value"),
        State(UI.ID_CONF_MESH_FINAL_CAP, "value"), State(UI.ID_CONF_MESH_ORIG_ORDER, "value"),
        State(UI.ID_CONF_MESH_REMOVE_DRIFT, "value"),
        # Warp States
        State(UI.ID_CONF_WARP_MARGIN, "value"), State(UI.ID_CONF_WARP_PARALLEL, "value"),
        State(UI.ID_CONF_WARP_KERNEL, "value"), State(UI.ID_CONF_WARP_CLIP, "value"),
        State(UI.ID_CONF_WARP_NBINS, "value"), State(UI.ID_CONF_WARP_CLAHE, "value"),
    ],
    prevent_initial_call=True
)
def handle_config_save(n_clicks, path, *args):
    if not path: return "Error: No path specified."

    def clean_dict(d):
        return {k: v for k, v in d.items() if v is not None and v != ""}

    def parse_csv(val):
        if not val or not str(val).strip(): return None
        return [int(x.strip()) for x in str(val).split(",")]

    try:
        # Unpack exactly as listed in the States above
        (out_dir, start, end,
         ox, oy, m_ov, m_rng, fs, patch, batch, pkr, pks, max_dev, max_mag, min_p, max_g, rec_g,
         m_dt, m_gamma, m_k0, m_k, m_stride, m_iters, m_max_i, m_stop, m_dt_m, m_scap, m_fcap, m_orig, m_drift,
         w_margin, w_parallel, w_kernel, w_clip, w_nbins, w_clahe) = args

        reg_cfg = pcfg.RegistrationConfig(**clean_dict({
            "overlaps_x": parse_csv(ox), "overlaps_y": parse_csv(oy), "min_overlap": m_ov,
            "min_range": parse_csv(m_rng), "filter_size": fs, "patch_size": parse_csv(patch),
            "batch_size": batch, "min_peak_ratio": pkr, "min_peak_sharpness": pks,
            "max_deviation": max_dev, "max_magnitude": max_mag, "min_patch_size": min_p,
            "max_gradient": max_g, "reconcile_flow_max_deviation": rec_g
        }))

        mesh_cfg = pcfg.MeshIntegrationConfig(**clean_dict({
            "dt": m_dt, "gamma": m_gamma, "k0": m_k0, "k": m_k, "stride": m_stride,
            "num_iters": m_iters, "max_iters": m_max_i, "stop_v_max": m_stop,
            "dt_max": m_dt_m, "start_cap": m_scap, "final_cap": m_fcap,
            "prefer_orig_order": bool(m_orig), "remove_drift": bool(m_drift)
        }))

        warp_cfg = pcfg.WarpConfigStitching(**clean_dict({
            "margin": w_margin, "warp_parallelism": w_parallel, "kernel_size": w_kernel,
            "clip_limit": w_clip, "nbins": w_nbins, "use_clahe": bool(w_clahe)
        }))

        new_cfg = pcfg.StitchingConfig(
            output_dir=out_dir, start_section=start, end_section=end,
            registration_config=reg_cfg, mesh_integration_config=mesh_cfg, warp_config=warp_cfg
        )

        pcfg.save_to_disk(new_cfg, path)
        return f"Successfully saved to {path}."

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

