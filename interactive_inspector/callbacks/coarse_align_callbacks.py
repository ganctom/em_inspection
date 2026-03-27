import logging
import threading
import yaml
from dash import Input, Output, State, callback, no_update, clientside_callback

from constants import UI
from data_service import service
import parameter_config as pcfg
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params


@callback(
    # Outputs for every single UI element defined in the layout
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
        Output(UI.ID_CONF_PATCH, "value"),
        Output(UI.ID_CONF_BATCH, "value"),
        # Mesh
        Output(UI.ID_CONF_MESH_DT, "value"),
        Output(UI.ID_CONF_MESH_GAMMA, "value"),
        Output(UI.ID_CONF_MESH_K0, "value"),
        Output(UI.ID_CONF_MESH_K, "value"),
        Output(UI.ID_CONF_MESH_NUM_ITERS, "value"),
        Output(UI.ID_CONF_MESH_MAX_ITERS, "value"),
        Output(UI.ID_CONF_MESH_STOP_V, "value"),
        # Warp
        Output(UI.ID_CONF_WARP_MARGIN, "value"),
        Output(UI.ID_CONF_WARP_PARALLEL, "value"),
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
    if not file_path:
        return [no_update] * 20 + ["Please enter a path", ""]

    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        # Validate with Pydantic
        cfg = pcfg.StitchingConfig(**data)

        reg = cfg.registration_config
        mesh = cfg.mesh_integration_config
        warp = cfg.warp_config

        return [
            file_path,
            cfg.output_dir,
            cfg.start_section,
            cfg.end_section,
            # Registration (Join lists to CSV strings for the UI)
            ", ".join(map(str, reg.overlaps_x)),
            ", ".join(map(str, reg.overlaps_y)),
            reg.min_overlap,
            ", ".join(map(str, reg.min_range)),
            reg.filter_size,
            ", ".join(map(str, reg.patch_size)),
            reg.batch_size,
            # Mesh
            mesh.dt,
            mesh.gamma,
            mesh.k0,
            mesh.k,
            mesh.num_iters,
            mesh.max_iters,
            mesh.stop_v_max,
            # Warp
            warp.margin,
            warp.warp_parallelism,
            [True] if warp.use_clahe else [],
            "Config loaded successfully",
            f"Active: {file_path.split('/')[-1]}"
        ]
    except Exception as e:
        return [no_update] * 20 + [f"Error: {str(e)}", "Error"]


@callback(
    Output(UI.ID_STITCH_CONSOLE, "children", allow_duplicate=True),
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
        State(UI.ID_CONF_PATCH, "value"),
        State(UI.ID_CONF_FILTER_SIZE, "value"),
        State(UI.ID_CONF_BATCH, "value"),
        State(UI.ID_CONF_MIN_PKR, "value"),
        State(UI.ID_CONF_MIN_PKS, "value"),
        State(UI.ID_CONF_MAX_DEV, "value"),
        State(UI.ID_CONF_MAX_MAG, "value"),
        State(UI.ID_CONF_MIN_PATCH, "value"),
        State(UI.ID_CONF_MAX_GRAD, "value"),
        State(UI.ID_CONF_REC_FLOW_MAX_GRAD, "value"),
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
         ox, oy, m_ov, m_rng, fs, patch, batch, pkr, pks, max_dev, max_mag, min_p, max_g, rec_g,
         m_dt, m_gamma, m_k0, m_k, m_stride, m_iters, m_max_i, m_stop, m_dt_m, m_scap, m_fcap, m_orig, m_drift,
         w_margin, w_parallel, w_kernel, w_clip, w_nbins, w_clahe) = args

        reg_data = clean_dict({
            "overlaps_x": parse_csv(ox),
            "overlaps_y": parse_csv(oy),
            "min_overlap": m_ov,
            "min_range": parse_csv(m_rng),
            "filter_size": fs,
            "patch_size": parse_csv(patch),
            "batch_size": batch,
            "min_peak_ratio": pkr,
            "min_peak_sharpness": pks,
            "max_deviation": max_dev,
            "max_magnitude": max_mag,
            "min_patch_size": min_p,
            "max_gradient": max_g,
            "reconcile_flow_max_deviation": rec_g
        })

        mesh_data = clean_dict({
            "dt": m_dt, "gamma": m_gamma, "k0": m_k0, "k": m_k,
            "stride": m_stride, "num_iters": m_iters, "max_iters": m_max_i,
            "stop_v_max": m_stop, "dt_max": m_dt_m, "start_cap": m_scap,
            "final_cap": m_fcap,
            "prefer_orig_order": bool(m_orig), "remove_drift": bool(m_drift)
        })

        warp_data = clean_dict({
            "margin": w_margin, "warp_parallelism": w_parallel,
            "kernel_size": w_kernel, "clip_limit": w_clip,
            "nbins": w_nbins, "use_clahe": bool(w_clahe)
        })

        # Final Assembly
        main_data = clean_dict({
            "output_dir": out_dir,
            "start_section": start,
            "end_section": end,
            "registration_config": pcfg.RegistrationConfig(**reg_data),
            "mesh_integration_config": pcfg.MeshIntegrationConfig(**mesh_data),
            "warp_config": pcfg.WarpConfigStitching(**warp_data)
        })

        new_cfg = pcfg.StitchingConfig(**main_data)
        new_cfg.acquisition_config = service.acq_config
        pcfg.save_to_disk(new_cfg, path)

        return f"Successfully saved to {path}. Defaults applied for empty fields."

    except Exception as e:
        return f"Save failed: {str(e)}"


@callback(
    [Output(UI.ID_STITCH_CONSOLE, "children", allow_duplicate=True),
     Output("stitch-progress-interval", "disabled", allow_duplicate=True),
     Output("stitch-progress-bar", "style", allow_duplicate=True)],
    Input(UI.ID_STITCH_RUN_BTN, "n_clicks"),
    [State(UI.ID_STITCH_SECTION_INP, "value"),
     State(UI.ID_STITCH_CONFIG_PATH, "value"),
     State(UI.ID_CONF_OVERLAPS_X, "value"),
     State(UI.ID_CONF_OVERLAPS_Y, "value"),
     State(UI.ID_CONF_MIN_RANGE, "value"),
     State(UI.ID_CONF_MIN_OVERLAP, "value"),
     State(UI.ID_CONF_FILTER_SIZE, "value")],
    prevent_initial_call=True
)
def run_stitching_estimation(n_clicks, range_str, config_path, ox, oy, m_range, m_overlap, fs):
    # 1. Initial experiment check
    if not service.exp_config:
        msg = UI.log_row("Error: No active experiment found. Please initialize in Step 1.", type="error")
        return [msg], True, {"display": "none"}

    if not range_str:
        msg = UI.log_row("Error: Please specify sections for estimation.", type="error")
        return [msg], True, {"display": "none"}

    # 2. Section Validation Logic
    first_sec = service.exp_config.first_sec
    last_sec = service.exp_config.last_sec
    valid_sec_nums = list(range(first_sec, last_sec + 1))

    if str(range_str).lower() != 'all':
        try:
            all_requested = parse_section_range(range_str)
            valid_sec_nums = validate_section_numbers(first_sec, last_sec, all_requested)
        except ValueError as e:
            logging.warning(f"Validation failed: {e}")
            return [UI.log_row(f"Error: {e}", type="error")], True, {"display": "none"}

    if not valid_sec_nums:
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
        UI.log_row(f"Sections: {len(valid_sec_nums)} requested ({valid_sec_nums[0]}-{valid_sec_nums[-1]})"),
        UI.log_row(f"Using Overlaps: {final_stitch_params['overlaps_xy']}"),
        UI.log_row("-" * 50),
        UI.log_row("▶ Thread started. Monitoring progress...", type="success")
    ]

    # 5. Launch the Thread
    thread = threading.Thread(
        target=service.run_stitching_thread,
        args=(valid_sec_nums, final_stitch_params),
        daemon=True
    )
    thread.start()

    # 6. Returns: [Console Children], Interval Disabled=False, Progress Style=Visible
    return start_log, False, {"display": "block"}


@callback(
    [Output("stitch-progress-bar", "value"),
     Output("stitch-progress-text", "children"),
     Output("stitch-progress-interval", "disabled", allow_duplicate=True),
     Output(UI.ID_STITCH_CONSOLE, "children", allow_duplicate=True)],
    Input("stitch-progress-interval", "n_intervals"),
    State(UI.ID_STITCH_CONSOLE, "children"),
    prevent_initial_call=True
)
def update_stitch_progress(n, current_log):
    status = service.stitch_status

    # 1. Ensure log_history is ALWAYS a list of components
    if not isinstance(current_log, list):
        log_history = []
    else:
        log_history = current_log

    # 2. Handle Errors (Append a row and stop)
    if status.get("error"):
        new_row = UI.log_row(f"ERROR: {status['error']}", type="error")
        return 0, "Failed", True, log_history + [new_row]

    prog = status.get("progress", 0)
    msg = status.get("message", "")

    # 3. Defensive check: Peek at the last message to avoid duplicates
    last_msg = ""
    try:
        if log_history:
            # Safely navigate the Dash component dictionary structure
            # Row -> Children List -> Second Span (index 1) -> Its Children (the text)
            last_row = log_history[-1]
            if isinstance(last_row, dict) and 'props' in last_row:
                last_msg = last_row['props']['children'][1]['props']['children']
    except (KeyError, IndexError, TypeError):
        # If the structure is weird, just assume it's a new message
        last_msg = ""

    # 4. Add New Row only if it's fresh information
    if msg and msg != last_msg:
        log_history.append(UI.log_row(msg, type="info"))

    # 5. Handle Completion
    if not status.get("active") and prog >= 100:
        log_history.append(UI.log_row("Alignment Task Completed.", type="success"))
        return 100, "Done", True, log_history

    return prog, msg, False, log_history


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
    Input(UI.ID_STITCH_CONSOLE, "children"),
    prevent_initial_call=True
)