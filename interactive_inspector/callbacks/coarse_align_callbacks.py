import logging
import threading
import yaml
import dash
from dash import Input, Output, State, callback, no_update, clientside_callback

from constants import UI
from data_service import service, orchestrator
import parameter_config as pcfg



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
        Output(UI.ID_CONF_RECON_FLOW_MAX_DEV, "value"),
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
        # Mask (2 outputs)
        Output(UI.ID_CONF_MASK_MARGIN, "value"),
        Output(UI.ID_CONF_MASK_RIM_SIZE, "value"),
        # Status
        Output("stitch_config-load-status", "children"),
        Output("header-path-summary", "children")
    ],
    Input(UI.ID_STITCH_LOAD_YAML, "n_clicks"),
    State(UI.ID_STITCH_CONFIG_PATH, "value"),
    prevent_initial_call=True
)
def handle_config_load(n_clicks, file_path):

    total_outputs = 41
    if not file_path:
        return [no_update] * (total_outputs - 2) + ["Please enter a path", ""]

    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        cfg = pcfg.StitchingConfig(**data)

        reg, mesh, warp, mask = (cfg.registration_config, cfg.mesh_integration_config, cfg.warp_config, cfg.mask_config)

        service.stitch_config = cfg
        service.reg_config = reg

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
            # Masking
            mask.mask_margin, mask.rim_size,
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
        State(UI.ID_CONF_MAX_GRAD, "value"), State(UI.ID_CONF_RECON_FLOW_MAX_DEV, "value"),
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
        # Masking states
        State(UI.ID_CONF_MASK_MARGIN, "value"), State(UI.ID_CONF_MASK_RIM_SIZE, "value"),
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
         ox, oy, m_ov, m_rng, fs, patch, batch, pkr, pks, max_dev, max_mag, min_p, max_g, rec_dev,
         m_dt, m_gamma, m_k0, m_k, m_stride, m_iters, m_max_i, m_stop, m_dt_m, m_scap, m_fcap, m_orig, m_drift,
         w_margin, w_parallel, w_kernel, w_clip, w_nbins, w_clahe,
         mask_margin, mask_rim_size
         ) = args

        reg_cfg = pcfg.RegistrationConfig(**clean_dict({
            "overlaps_x": parse_csv(ox), "overlaps_y": parse_csv(oy), "min_overlap": m_ov,
            "min_range": parse_csv(m_rng), "filter_size": fs, "patch_size": parse_csv(patch),
            "batch_size": batch, "min_peak_ratio": pkr, "min_peak_sharpness": pks,
            "max_deviation": max_dev, "max_magnitude": max_mag, "min_patch_size": min_p,
            "max_gradient": max_g, "reconcile_flow_max_deviation": rec_dev
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

        mask_cfg = pcfg.MaskingConfig(**clean_dict({
            "mask_margin": mask_margin,
            "rim_size": mask_rim_size
        }))

        new_cfg = pcfg.StitchingConfig(
            output_dir=out_dir,
            start_section=start,
            end_section=end,
            registration_config=reg_cfg,
            mesh_integration_config=mesh_cfg,
            warp_config=warp_cfg,
            mask_config=mask_cfg,
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
def run_coarse_alignment(n_clicks, range_str, config_path, *ui_vals):
    # 1. Map raw UI values to keys
    ui_keys = ["overlaps_x", "overlaps_y", "min_range", "min_overlap", "filter_size"]
    ui_params_raw = dict(zip(ui_keys, ui_vals))

    try:
        # 2. Delegate logic to Orchestrator
        sec_nums, stitching_cfg = orchestrator.validate_and_prepare(
            range_str, config_path, ui_params_raw
        )
        reg_cfg = stitching_cfg.registration_config
        orchestrator.start_coarse_align(sec_nums, reg_cfg)

        # 3. Return UI feedback
        start_log = [
            UI.log_row("▶ Coarse Alignment Initialized", type="info"),
            UI.log_row(f"Sections: {sec_nums[0]}-{sec_nums[-1]} ({len(sec_nums)} total)"),
            UI.log_row(f"Overlaps X: {reg_cfg.overlaps_x}"),
            UI.log_row(f"Overlaps Y: {reg_cfg.overlaps_y}"),
            UI.log_row("-" * 50),
            UI.log_row("▶ Thread active. Monitoring...", type="success")
        ]
        return start_log, False, {"display": "block"}

    except Exception as e:
        return [UI.log_row(f"Initialization Failed: {e}", type="error")], True, {"display": "none"}


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

    # Re-load coarse offsets database and largest tile-id map
    service.processor.load_all_offsets_and_tile_id_maps_from_npz()
    service.tile_ids = service.processor.get_largest_tile_id_map()

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
    # 1. Determine which process is currently active in the ppln_service
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


def assemble_stitching_config_from_ui(*args):
    """
    Shared logic to parse UI States into a StitchingConfig Pydantic model.
    """
    def clean_dict(d):
        return {k: v for k, v in d.items() if v is not None and v != ""}

    def parse_csv(val):
        if not val or not str(val).strip(): return None
        return [int(x.strip()) for x in str(val).split(",")]

    (out_dir, start, end,
     ox, oy, m_ov, m_rng, fs, patch, batch, pkr, pks,
     max_dev, max_mag, min_p, max_g, rec_dev,
     m_dt, m_gamma, m_k0, m_k, m_stride, m_iters, m_max_i, m_stop, m_dt_m, m_scap, m_fcap, m_orig, m_drift,
     w_margin, w_parallel, w_kernel, w_clip, w_nbins, w_clahe,
     mask_margin, mask_rim_size
    ) = args

    reg_cfg = pcfg.RegistrationConfig(**clean_dict({
        "overlaps_x": parse_csv(ox), "overlaps_y": parse_csv(oy), "min_overlap": m_ov,
        "min_range": parse_csv(m_rng), "filter_size": fs, "patch_size": parse_csv(patch),
        "batch_size": batch, "min_peak_ratio": pkr, "min_peak_sharpness": pks,
        "max_deviation": max_dev, "max_magnitude": max_mag, "min_patch_size": min_p,
        "max_gradient": max_g, "reconcile_flow_max_deviation": rec_dev
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

    mask_cfg = pcfg.MaskingConfig(**clean_dict({
        "mask_margin": mask_margin,
        "rim_size": mask_rim_size
    }))

    new_cfg = pcfg.StitchingConfig(
        output_dir=out_dir,
        start_section=start,
        end_section=end,
        registration_config=reg_cfg,
        mesh_integration_config=mesh_cfg,
        warp_config=warp_cfg,
        mask_config=mask_cfg,
    )

    return new_cfg


@callback(
    Output(UI.ID_GLOBAL_SETTINGS_STORE, 'data'),
    Input(UI.ID_BTN_FETCH_GLOBAL, "n_clicks"),
    [
        State("conf-output-dir", "value"),
        State("conf-start", "value"),
        State("conf-end", "value"),
        # Registration (9 outputs)
        State(UI.ID_CONF_OVERLAPS_X, "value"),
        State(UI.ID_CONF_OVERLAPS_Y, "value"),
        State(UI.ID_CONF_MIN_OVERLAP, "value"),
        State(UI.ID_CONF_MIN_RANGE, "value"),
        State(UI.ID_CONF_FILTER_SIZE, "value"),
        State(UI.ID_CONF_PATCH, "value"),
        State(UI.ID_CONF_BATCH, "value"),
        State(UI.ID_CONF_MIN_PKR, "value"),
        State(UI.ID_CONF_MIN_PKS, "value"),
        # Extra Reg (5 outputs)
        State(UI.ID_CONF_MAX_DEV, "value"),
        State(UI.ID_CONF_MAX_MAG, "value"),
        State(UI.ID_CONF_MIN_PATCH, "value"),
        State(UI.ID_CONF_MAX_GRAD, "value"),
        State(UI.ID_CONF_RECON_FLOW_MAX_DEV, "value"),
        # Mesh (13 outputs)
        State(UI.ID_CONF_MESH_DT, "value"),
        State(UI.ID_CONF_MESH_GAMMA, "value"),
        State(UI.ID_CONF_MESH_K0, "value"),
        State(UI.ID_CONF_MESH_K, "value"),
        State(UI.ID_CONF_MESH_STRIDE, "value"),
        State(UI.ID_CONF_MESH_NUM_ITERS, "value"),
        State(UI.ID_CONF_MESH_MAX_ITERS, "value"),
        State(UI.ID_CONF_MESH_STOP_V, "value"),
        State(UI.ID_CONF_MESH_DT_MAX, "value"),
        State(UI.ID_CONF_MESH_START_CAP, "value"),
        State(UI.ID_CONF_MESH_FINAL_CAP, "value"),
        State(UI.ID_CONF_MESH_ORIG_ORDER, "value"),
        State(UI.ID_CONF_MESH_REMOVE_DRIFT, "value"),
        # Warp (6 outputs)
        State(UI.ID_CONF_WARP_MARGIN, "value"),
        State(UI.ID_CONF_WARP_PARALLEL, "value"),
        State(UI.ID_CONF_WARP_KERNEL, "value"),
        State(UI.ID_CONF_WARP_CLIP, "value"),
        State(UI.ID_CONF_WARP_NBINS, "value"),
        State(UI.ID_CONF_WARP_CLAHE, "value"),
        # Mask (2 outputs)
        State(UI.ID_CONF_MASK_MARGIN, "value"),
        State(UI.ID_CONF_MASK_RIM_SIZE, "value"),
    ],
    prevent_initial_call=True
)
def fetch_to_global_store(n_clicks, *args):
    if not n_clicks:
        return no_update

    try:
        config_model = assemble_stitching_config_from_ui(*args)
        return config_model.model_dump()  # Sync to dcc.Store
    except Exception as e:
        logging.error(f"Fetch to global store failed: {e}")
        return no_update
