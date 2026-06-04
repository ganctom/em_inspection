import logging
import threading
import yaml
import dash
from dash import Input, Output, State, callback, no_update, clientside_callback

from constants import UI
from data_service import service, orchestrator
import parameter_config as pcfg
from parameter_config import StitchingConfig


# --- 1. UNIFIED LOAD CALLBACK ---
@callback(
    [
        Output(UI.ID_STITCH_CONFIG_PATH, "value"),
        Output("conf-output-dir", "value"),
        Output("conf-start", "value"),
        Output("conf-end", "value"),
        # Registration (12 outputs)
        Output(UI.ID_CONF_OVERLAPS_X, "value"),
        Output(UI.ID_CONF_OVERLAPS_Y, "value"),
        Output(UI.ID_CONF_MIN_OVERLAP, "value"),
        Output(UI.ID_CONF_MIN_RANGE, "value"),
        Output(UI.ID_CONF_FILTER_SIZE, "value"),
        Output(UI.ID_REG_CLAHE, "value"),
        Output(UI.ID_REG_CLAHE_CLIP, "value"),
        Output(UI.ID_REG_CLAHE_KERNEL, "value"),
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

    def fmt_bool(val: bool) -> list[bool]:
        return [True] if val else []

    total_outputs = 41
    if not file_path:
        return [no_update] * (total_outputs - 2) + ["Please enter a path", ""]

    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        cfg = pcfg.StitchingConfig(**data)

        acq, reg, mesh, warp, mask = (
            cfg.acquisition_config,
            cfg.registration_config,
            cfg.mesh_integration_config,
            cfg.warp_config,
            cfg.mask_config
        )

        service.stitch_config = cfg
        service.reg_config = reg

        to_csv = lambda x: ", ".join(map(str, x)) if x else ""

        return [
            file_path,
            cfg.output_dir,
            cfg.start_section,
            cfg.end_section,

            # Registration
            to_csv(reg.overlaps_x),
            to_csv(reg.overlaps_y),
            reg.min_overlap,
            to_csv(reg.min_range),
            reg.filter_size,
            reg.clahe,
            reg.clip_limit,
            reg.kernel_size,
            to_csv(reg.patch_size),
            reg.batch_size, reg.min_peak_ratio, reg.min_peak_sharpness,
            reg.max_deviation, reg.max_magnitude, reg.min_patch_size,
            reg.max_gradient, reg.reconcile_flow_max_deviation,

            # Mesh
            mesh.dt, mesh.gamma, mesh.k0, mesh.k, mesh.stride,
            mesh.num_iters, mesh.max_iters, mesh.stop_v_max, mesh.dt_max,
            mesh.start_cap, mesh.final_cap,
            fmt_bool(mesh.prefer_orig_order),
            fmt_bool(mesh.remove_drift),

            # Warp
            warp.margin,
            warp.warp_parallelism,
            warp.kernel_size,
            warp.clip_limit,
            warp.nbins,
            fmt_bool(warp.use_clahe),

            # Masking
            mask.mask_margin,
            mask.rim_size,
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
        State(UI.ID_CONF_OVERLAPS_X, "value"),
        State(UI.ID_CONF_OVERLAPS_Y, "value"),
        State(UI.ID_CONF_MIN_OVERLAP, "value"),
        State(UI.ID_CONF_MIN_RANGE, "value"),
        State(UI.ID_CONF_FILTER_SIZE, "value"),
        State(UI.ID_REG_CLAHE, "value"),
        State(UI.ID_REG_CLAHE_CLIP, "value"),
        State(UI.ID_REG_CLAHE_KERNEL, "value"),
        State(UI.ID_CONF_PATCH, "value"),
        State(UI.ID_CONF_BATCH, "value"),
        State(UI.ID_CONF_MIN_PKR, "value"),
        State(UI.ID_CONF_MIN_PKS, "value"),
        State(UI.ID_CONF_MAX_DEV, "value"),
        State(UI.ID_CONF_MAX_MAG, "value"),
        State(UI.ID_CONF_MIN_PATCH, "value"),
        State(UI.ID_CONF_MAX_GRAD, "value"),
        State(UI.ID_CONF_RECON_FLOW_MAX_DEV, "value"),

        # Mesh States
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

        # Warp States
        State(UI.ID_CONF_WARP_MARGIN, "value"),
        State(UI.ID_CONF_WARP_PARALLEL, "value"),
        State(UI.ID_CONF_WARP_KERNEL, "value"),
        State(UI.ID_CONF_WARP_CLIP, "value"),
        State(UI.ID_CONF_WARP_NBINS, "value"),
        State(UI.ID_CONF_WARP_CLAHE, "value"),

        # Masking states
        State(UI.ID_CONF_MASK_MARGIN, "value"),
        State(UI.ID_CONF_MASK_RIM_SIZE, "value"),
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
         ox, oy, m_ov, m_rng, fs,
         clahe, clahe_clip, clahe_kernel,
         patch, batch, pkr, pks, max_dev, max_mag, min_p, max_g, rec_dev,
         m_dt, m_gamma, m_k0, m_k, m_stride, m_iters, m_max_i, m_stop, m_dt_m,
         m_scap, m_fcap, m_orig, m_drift,
         w_margin, w_parallel, w_kernel, w_clip, w_nbins, w_clahe,
         mask_margin, mask_rim_size
         ) = args

        reg_cfg = pcfg.RegistrationConfig(**clean_dict({
            "overlaps_x": parse_csv(ox),
            "overlaps_y": parse_csv(oy),
            "min_overlap": m_ov,
            "min_range": parse_csv(m_rng),
            "filter_size": fs,
            "clahe": bool(clahe),
            "clip_limit": clahe_clip,
            "kernel_size": clahe_kernel,
            "patch_size": parse_csv(patch),
            "batch_size": batch,
            "min_peak_ratio": pkr,
            "min_peak_sharpness": pks,
            "max_deviation": max_dev,
            "max_magnitude": max_mag,
            "min_patch_size": min_p,
            "max_gradient": max_g,
            "reconcile_flow_max_deviation": rec_dev
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
            acquisition_config=service.acq_config,
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
     State(UI.ID_CONF_FILTER_SIZE, "value"),
     State(UI.ID_REG_CLAHE, "value"),
     State(UI.ID_REG_CLAHE_CLIP, "value"),
     State(UI.ID_REG_CLAHE_KERNEL, "value"),
     ],
    prevent_initial_call=True
)
def run_coarse_alignment(n_clicks, range_str, config_path, *ui_vals):
    # 1. Map raw UI values to keys
    ui_keys = [
        "overlaps_x",
        "overlaps_y",
        "min_range",
        "min_overlap",
        "filter_size",
        "clahe",
        "clip_limit",
        "kernel_size",
    ]
    ui_params_raw = dict(zip(ui_keys, ui_vals))

    ui_params_raw['clahe'] = bool(ui_params_raw['clahe'])

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
            UI.log_row(f"Min. Range: {reg_cfg.min_range}"),
            UI.log_row(f"Min. Overlap: {reg_cfg.min_overlap}"),
            UI.log_row(f"Filter Size: {reg_cfg.filter_size}"),
            UI.log_row(f"CLAHE: {reg_cfg.clahe}"),
            UI.log_row(f"CLAHE clip limit : {reg_cfg.clip_limit}"),
            UI.log_row(f"CLAHE kernel size: {reg_cfg.kernel_size}"),
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

    thread = threading.Thread(
        target=service.run_offsets_backup_thread(overwrite=True),
        daemon=True
    )
    thread.start()

    init_log = [
        UI.log_row("💾 Initializing Coarse Offset Backup...", type="info"),
        UI.log_row("Exporting all cx_cy.json files to a .db container.")
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
    # 1. Determine which process is currently active in the ppln_service
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


def assemble_stitching_config_from_ui(ui_states: dict) -> StitchingConfig:
    """
    Shared logic to parse UI keyword states into a StitchingConfig Pydantic model.
    """
    def clean_dict(d):
        return {k: v for k, v in d.items() if v is not None and v != ""}

    def parse_csv(val):
        if not val or not str(val).strip():
            return None
        return [int(x.strip()) for x in str(val).split(",")]

    reg_cfg = pcfg.RegistrationConfig(**clean_dict({
        "overlaps_x": parse_csv(ui_states.get("overlaps_x")),
        "overlaps_y": parse_csv(ui_states.get("overlaps_y")),
        "min_overlap": ui_states.get("min_overlap"),
        "min_range": parse_csv(ui_states.get("min_range")),
        "clahe": bool(ui_states.get("clahe")),
        "filter_size": ui_states.get("filter_size"),
        "clip_limit": ui_states.get("clip_limit"),
        "kernel_size": ui_states.get("kernel_size"),
        "patch_size": parse_csv(ui_states.get("patch")),
        "batch_size": ui_states.get("batch"),
        "min_peak_ratio": ui_states.get("min_pkr"),
        "min_peak_sharpness": ui_states.get("min_pks"),
        "max_deviation": ui_states.get("max_dev"),
        "max_magnitude": ui_states.get("max_mag"),
        "min_patch_size": ui_states.get("min_patch"),
        "max_gradient": ui_states.get("max_grad"),
        "reconcile_flow_max_deviation": ui_states.get("recon_flow_max_dev")
    }))

    mesh_cfg = pcfg.MeshIntegrationConfig(**clean_dict({
        "dt": ui_states.get("mesh_dt"),
        "gamma": ui_states.get("mesh_gamma"),
        "k0": ui_states.get("mesh_k0"),
        "k": ui_states.get("mesh_k"),
        "stride": ui_states.get("mesh_stride"),
        "num_iters": ui_states.get("mesh_num_iters"),
        "max_iters": ui_states.get("mesh_max_iters"),
        "stop_v_max": ui_states.get("mesh_stop_v"),
        "dt_max": ui_states.get("mesh_dt_max"),
        "start_cap": ui_states.get("mesh_start_cap"),
        "final_cap": ui_states.get("mesh_final_cap"),
        "prefer_orig_order": bool(ui_states.get("mesh_orig_order")),
        "remove_drift": bool(ui_states.get("mesh_remove_drift"))
    }))

    warp_cfg = pcfg.WarpConfigStitching(**clean_dict({
        "margin": ui_states.get("warp_margin"),
        "warp_parallelism": ui_states.get("warp_parallel"),
        "kernel_size": ui_states.get("warp_kernel"),
        "clip_limit": ui_states.get("warp_clip"),
        "nbins": ui_states.get("warp_nbins"),
        "use_clahe": bool(ui_states.get("warp_clahe"))
    }))

    mask_cfg = pcfg.MaskingConfig(**clean_dict({
        "mask_margin": ui_states.get("mask_margin"),
        "rim_size": ui_states.get("mask_rim_size")
    }))

    # Create a deep copy of the configuration while simultaneously updating specific fields
    new_cfg = service.stitch_config.model_copy(
        update={
            "registration_config": reg_cfg,
            "mesh_integration_config": mesh_cfg,
            "warp_config": warp_cfg,
            "mask_config": mask_cfg,
        },
        deep=True  # Performs a deep copy of all un-mutated sub-structures
    )

    return new_cfg


@callback(
    Output(UI.ID_GLOBAL_SETTINGS_STORE, 'data'),
    # Use the 'inputs' keyword argument to group the triggering Input and all context States
    inputs=dict(
        n_clicks=Input(UI.ID_BTN_FETCH_GLOBAL, "n_clicks"),
        # General Scope
        output_dir=State("conf-output-dir", "value"),
        start_sec=State("conf-start", "value"),
        end_sec=State("conf-end", "value"),
        # Registration Parameters
        overlaps_x=State(UI.ID_CONF_OVERLAPS_X, "value"),
        overlaps_y=State(UI.ID_CONF_OVERLAPS_Y, "value"),
        min_overlap=State(UI.ID_CONF_MIN_OVERLAP, "value"),
        min_range=State(UI.ID_CONF_MIN_RANGE, "value"),
        filter_size=State(UI.ID_CONF_FILTER_SIZE, "value"),
        clahe=State(UI.ID_REG_CLAHE, "value"),
        clip_limit=State(UI.ID_REG_CLAHE_CLIP, "value"),
        kernel_size=State(UI.ID_REG_CLAHE_KERNEL, "value"),
        patch=State(UI.ID_CONF_PATCH, "value"),
        batch=State(UI.ID_CONF_BATCH, "value"),
        min_pkr=State(UI.ID_CONF_MIN_PKR, "value"),
        min_pks=State(UI.ID_CONF_MIN_PKS, "value"),
        # Extra Reg Parameters
        max_dev=State(UI.ID_CONF_MAX_DEV, "value"),
        max_mag=State(UI.ID_CONF_MAX_MAG, "value"),
        min_patch=State(UI.ID_CONF_MIN_PATCH, "value"),
        max_grad=State(UI.ID_CONF_MAX_GRAD, "value"),
        recon_flow_max_dev=State(UI.ID_CONF_RECON_FLOW_MAX_DEV, "value"),
        # Mesh Solver Parameters
        mesh_dt=State(UI.ID_CONF_MESH_DT, "value"),
        mesh_gamma=State(UI.ID_CONF_MESH_GAMMA, "value"),
        mesh_k0=State(UI.ID_CONF_MESH_K0, "value"),
        mesh_k=State(UI.ID_CONF_MESH_K, "value"),
        mesh_stride=State(UI.ID_CONF_MESH_STRIDE, "value"),
        mesh_num_iters=State(UI.ID_CONF_MESH_NUM_ITERS, "value"),
        mesh_max_iters=State(UI.ID_CONF_MESH_MAX_ITERS, "value"),
        mesh_stop_v=State(UI.ID_CONF_MESH_STOP_V, "value"),
        mesh_dt_max=State(UI.ID_CONF_MESH_DT_MAX, "value"),
        mesh_start_cap=State(UI.ID_CONF_MESH_START_CAP, "value"),
        mesh_final_cap=State(UI.ID_CONF_MESH_FINAL_CAP, "value"),
        mesh_orig_order=State(UI.ID_CONF_MESH_ORIG_ORDER, "value"),
        mesh_remove_drift=State(UI.ID_CONF_MESH_REMOVE_DRIFT, "value"),
        # Warp Parameters
        warp_margin=State(UI.ID_CONF_WARP_MARGIN, "value"),
        warp_parallel=State(UI.ID_CONF_WARP_PARALLEL, "value"),
        warp_kernel=State(UI.ID_CONF_WARP_KERNEL, "value"),
        warp_clip=State(UI.ID_CONF_WARP_CLIP, "value"),
        warp_nbins=State(UI.ID_CONF_WARP_NBINS, "value"),
        warp_clahe=State(UI.ID_CONF_WARP_CLAHE, "value"),
        # Mask Parameters
        mask_margin=State(UI.ID_CONF_MASK_MARGIN, "value"),
        mask_rim_size=State(UI.ID_CONF_MASK_RIM_SIZE, "value"),
    ),
    prevent_initial_call=True
)
def fetch_to_global_store(**ui_states):
    n_clicks = ui_states.get("n_clicks")
    if not n_clicks:
        return no_update

    try:
        config_model = assemble_stitching_config_from_ui(ui_states)

        stitch_config = StitchingConfig(**config_model.model_dump())
        service.stitch_config = stitch_config

        return config_model.model_dump()

    except Exception as e:
        logging.error(f"Fetch to global store execution failed: {e}", exc_info=True)
        return no_update