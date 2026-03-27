from dash import html, dcc
import dash_bootstrap_components as dbc
from constants import UI
import parameter_config as pcfg

# Reusing your standard configs
default_mesh = pcfg.MeshIntegrationConfig()
default_warp = pcfg.WarpConfigStitching()


def layout(active_service=None):
    # Determine the initial path(s)
    initial_output_dir = UI.get_proj_dir(active_service)
    stitch_yaml_path = UI.get_stitching_config_path(active_service)
    inp_stitch_cfg = UI.INP_STITCH_CFG

    if stitch_yaml_path:
        inp_stitch_cfg["value"] = stitch_yaml_path

    return dbc.Container([
        # 1. CONFIGURATION SECTION (COLLAPSIBLE)
        dbc.Row([
            dbc.Col([
                dbc.Accordion([
                    dbc.AccordionItem(
                        item_id="config-manager",
                        title=html.Div([
                            html.I(className="bi bi-sliders2 me-2"),
                            "Stitching Configuration Manager",
                            dbc.Badge("Ready", color="success", className="ms-2", id="sync-badge"),
                            html.Small(id="header-path-summary", className="ms-3 text-muted",
                                       style={"fontSize": "11px", "fontWeight": "normal"})
                        ]),
                        children=[
                            # Path Selection
                            dbc.Row([
                                dbc.Col([
                                    UI.label_factory(UI.LBL_CFG_PATH_YAML, is_bold=True),
                                    dbc.InputGroup([
                                        dbc.Input(**inp_stitch_cfg),
                                        dbc.Button("Load", id=UI.ID_STITCH_LOAD_YAML, color="primary", size="sm"),
                                        dbc.Button("Save / Export", id=UI.ID_STITCH_SAVE_YAML, color="success",
                                                   size="sm"),
                                    ]),
                                    html.Div(id="config-load-status", className="small mt-1 text-muted")
                                ], width=12, className="mb-3")
                            ]),

                            dbc.Tabs([
                                # ACQUISITION TAB
                                dbc.Tab(label=UI.LBL_ACQ_RNG, tab_id="tab-acq", children=[
                                    html.Div([
                                        UI.label_factory(UI.LBL_OUT_DIR),
                                        dbc.Input(id="conf-output-dir", value=initial_output_dir, size="sm"),
                                        dbc.Row([
                                            dbc.Col([UI.label_factory("Start Section"),
                                                     dbc.Input(id="conf-start", type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("End Section"),
                                                     dbc.Input(id="conf-end", type="number", size="sm")], width=6),
                                        ], className="mt-2"),
                                    ], className="p-3 border-start border-end border-bottom")
                                ]),

                                # REGISTRATION TAB
                                dbc.Tab(label="Registration (SOFIMA)", tab_id="tab-reg", children=[
                                    html.Div([
                                        dbc.Row([
                                            dbc.Col([UI.label_factory("Overlaps X (csv)"),
                                                     dbc.Input(id=UI.ID_CONF_OVERLAPS_X, placeholder="200, 300, 400",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Overlaps Y (csv)"),
                                                     dbc.Input(id=UI.ID_CONF_OVERLAPS_Y, placeholder="200, 300, 400",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Range (csv)"),
                                                     dbc.Input(id=UI.ID_CONF_MIN_RANGE, placeholder="10, 100, 0",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Overlap"),
                                                     dbc.Input(id=UI.ID_CONF_MIN_OVERLAP, placeholder="20",
                                                               type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Filter Size"),
                                                     dbc.Input(id=UI.ID_CONF_FILTER_SIZE, placeholder="10",
                                                               type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Patch Size (csv)"),
                                                     dbc.Input(id=UI.ID_CONF_PATCH, placeholder="120, 120", size="sm")],
                                                    width=6),
                                            dbc.Col([UI.label_factory("Batch Size"),
                                                     dbc.Input(id=UI.ID_CONF_BATCH, placeholder="8000", type="number",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Peak Ratio"),
                                                     dbc.Input(id=UI.ID_CONF_MIN_PKR, placeholder="1.0", size="sm")],
                                                    width=6),
                                            dbc.Col([UI.label_factory("Min Peak Sharpness"),
                                                     dbc.Input(id=UI.ID_CONF_MIN_PKS, placeholder="1.0", size="sm")],
                                                    width=6),
                                            dbc.Col([UI.label_factory("Max Deviation"),
                                                     dbc.Input(id=UI.ID_CONF_MAX_DEV, placeholder="6", type="number",
                                                               size="sm")], width=6),
                                        ]),
                                        dbc.Row([
                                            dbc.Col([UI.label_factory("Max Magnitude"),
                                                     dbc.Input(id=UI.ID_CONF_MAX_MAG, placeholder="0", type="number",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Patch Size"),
                                                     dbc.Input(id=UI.ID_CONF_MIN_PATCH, placeholder="10", type="number",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Max Gradient"),
                                                     dbc.Input(id=UI.ID_CONF_MAX_GRAD, placeholder="12", type="number",
                                                               size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Rec. Flow Max Dev"),
                                                     dbc.Input(id=UI.ID_CONF_REC_FLOW_MAX_GRAD, placeholder="-1",
                                                               type="number", size="sm")], width=6),
                                        ], className="mt-2"),
                                    ], className="p-3 border-start border-end border-bottom")
                                ]),

                                # MESH & WARP TAB
                                dbc.Tab(label="Mesh & Warp", tab_id="tab-mesh", children=[
                                    html.Div([
                                        html.H6("Mesh Integration (Elastic Solver)",
                                                className="small fw-bold mt-2 mb-3 text-primary"),
                                        dbc.Row([
                                            dbc.Col([
                                                UI.label_factory("dt"),
                                                dbc.Input(id=UI.ID_CONF_MESH_DT, type="number", step=0.0001,
                                                          value=default_mesh.dt, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("gamma"),
                                                dbc.Input(id=UI.ID_CONF_MESH_GAMMA, type="number", step=0.01,
                                                          value=default_mesh.gamma, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("k0"),
                                                dbc.Input(id=UI.ID_CONF_MESH_K0, type="number", step=0.001,
                                                          value=default_mesh.k0, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("k"),
                                                dbc.Input(id=UI.ID_CONF_MESH_K, type="number", step=0.1,
                                                          value=default_mesh.k, size="sm")
                                            ], width=3),
                                        ], className="mb-2"),

                                        dbc.Row([
                                            dbc.Col([
                                                UI.label_factory("Stride"),
                                                dbc.Input(id=UI.ID_CONF_MESH_STRIDE, type="number",
                                                          value=default_mesh.stride, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("Num Iters"),
                                                dbc.Input(id=UI.ID_CONF_MESH_NUM_ITERS, type="number",
                                                          value=default_mesh.num_iters, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("Max Iters"),
                                                dbc.Input(id=UI.ID_CONF_MESH_MAX_ITERS, type="number",
                                                          value=default_mesh.max_iters, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("Stop v Max"),
                                                dbc.Input(id=UI.ID_CONF_MESH_STOP_V, type="number", step=0.001,
                                                          value=default_mesh.stop_v_max, size="sm")
                                            ], width=3),
                                        ], className="mb-2"),

                                        dbc.Row([
                                            dbc.Col([
                                                UI.label_factory("dt Max"),
                                                dbc.Input(id=UI.ID_CONF_MESH_DT_MAX, type="number",
                                                          value=default_mesh.dt_max, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("Start Cap"),
                                                dbc.Input(id=UI.ID_CONF_MESH_START_CAP, type="number", step=0.01,
                                                          value=default_mesh.start_cap, size="sm")
                                            ], width=3),
                                            dbc.Col([
                                                UI.label_factory("Final Cap"),
                                                dbc.Input(id=UI.ID_CONF_MESH_FINAL_CAP, type="number",
                                                          value=default_mesh.final_cap, size="sm")
                                            ], width=3),
                                        ], className="mb-3"),

                                        dbc.Row([
                                            dbc.Col([
                                                dbc.Checklist(
                                                    options=[{"label": "Prefer Orig Order", "value": True}],
                                                    id=UI.ID_CONF_MESH_ORIG_ORDER,
                                                    value=[True] if default_mesh.prefer_orig_order else [],
                                                    switch=True, className="small"
                                                )
                                            ], width=4),
                                            dbc.Col([
                                                dbc.Checklist(
                                                    options=[{"label": "Remove Drift", "value": True}],
                                                    id=UI.ID_CONF_MESH_REMOVE_DRIFT,
                                                    value=[True] if default_mesh.remove_drift else [],
                                                    switch=True, className="small"
                                                )
                                            ], width=4),
                                        ], className="mb-4"),

                                        html.Hr(),

                                        html.H6("Warping (Image Rendering)",
                                                className="small fw-bold mt-2 mb-3 text-primary"),
                                        dbc.Row([
                                            dbc.Col([
                                                UI.label_factory("Margin"),
                                                dbc.Input(id=UI.ID_CONF_WARP_MARGIN, type="number",
                                                          value=default_warp.margin, size="sm")
                                            ], width=4),
                                            dbc.Col([
                                                UI.label_factory("Parallelism"),
                                                dbc.Input(id=UI.ID_CONF_WARP_PARALLEL, type="number",
                                                          value=default_warp.warp_parallelism, size="sm")
                                            ], width=4),
                                            dbc.Col([
                                                UI.label_factory("Kernel Size"),
                                                dbc.Input(id=UI.ID_CONF_WARP_KERNEL, type="number",
                                                          value=default_warp.kernel_size, size="sm")
                                            ], width=4),
                                        ], className="mb-2"),

                                        dbc.Row([
                                            dbc.Col([
                                                UI.label_factory("Clip Limit"),
                                                dbc.Input(id=UI.ID_CONF_WARP_CLIP, type="number", step=0.01,
                                                          value=default_warp.clip_limit, size="sm")
                                            ], width=4),
                                            dbc.Col([
                                                UI.label_factory("nbins"),
                                                dbc.Input(id=UI.ID_CONF_WARP_NBINS, type="number",
                                                          value=default_warp.nbins, size="sm")
                                            ], width=4),
                                            dbc.Col([
                                                UI.label_factory("Enhancement"),
                                                dbc.Checklist(
                                                    options=[{"label": "Use CLAHE", "value": True}],
                                                    id=UI.ID_CONF_WARP_CLAHE,
                                                    value=[True] if default_warp.use_clahe else [],
                                                    switch=True, className="small"
                                                )
                                            ], width=4),
                                        ]),
                                    ], className="p-3 border-start border-end border-bottom")
                                ]),
                            ], id="config-tabs", active_tab="tab-acq")
                        ]
                    )
                ], active_item="config-manager", className="shadow-sm mt-4")
            ], width=12)
        ]),

        # 2. PIPELINE EXECUTION SECTION
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.I(className="bi bi-cpu-fill me-2"),
                        "Stitching Pipeline Controller"
                    ], className="fw-bold bg-danger text-white"),

                    dbc.CardBody([
                        dbc.Row([
                            # COLUMN A: Section Selection
                            dbc.Col([
                                UI.label_factory("1. Target Sections", is_bold=True),
                                dbc.Input(id=UI.ID_STITCH_PPLN_INP, placeholder="e.g. 0-100 or 'all'", size="sm"),
                                html.P("Define the range for the operations below.", className="text-muted small mb-0"),
                            ], width=4, className="border-end"),

                            # COLUMN B: Step Selection (The Checklist)
                            dbc.Col([
                                UI.label_factory("2. Select Pipeline Steps", is_bold=True),
                                dbc.Checklist(
                                    id=UI.ID_STITCH_PPLN_STEPS,
                                    options=UI.PPLN_STEPS,
                                    value=[s["value"] for s in UI.PPLN_STEPS[:3]],
                                    inline=False,
                                    switch=True,
                                    className="small custom-checklist"
                                ),
                            ], width=5),

                            # COLUMN C: Actions
                            dbc.Col([
                                dbc.Button([
                                    html.I(className="bi bi-play-circle-fill me-2"), "Run Pipeline"
                                ], id=UI.ID_STITCH_PPLN_BTN, color="danger", className="w-100 mb-2"),

                                dbc.Button([
                                    html.I(className="bi bi-stop-fill me-2"), "Abort"
                                ], id="abort-pipeline-btn", color="secondary", outline=True, size="sm",
                                    className="w-100"),
                            ], width=3, className="d-flex flex-column justify-content-center"),
                        ]),
                    ]),
                ], className="shadow-sm mt-4 border-danger")
            ], width=12)
        ]),

        # 3. CONSOLE & PROGRESS (Refined)
        dbc.Row([
            dbc.Col([
                html.Div(id="pipeline-status-bar", className="mt-3"),  # Shows "Step 2/5: Building Masks..."
                html.Div(
                    id=UI.ID_STITCH_PPLN_CONSOLE,
                    className="bg-dark text-white p-3 rounded mt-2",
                    style={
                        "height": "300px", "overflowY": "auto",
                        "fontFamily": "monospace", "fontSize": "11px",
                        "border": "1px solid #444"
                    }
                ),
                dbc.Progress(id=UI.ID_STITCH_PPLN_PROGRESS, value=0, striped=True, animated=True, className="mt-2",
                             style={"height": "10px"})
            ], width=12)
        ]),

        dcc.Interval(id=UI.ID_STITCH_PPLN_PROGRESS_INT, interval=1000, disabled=True),
        dcc.Store(id="scroll-trigger-dummy")
    ], fluid=True)