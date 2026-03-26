from dash import html, dcc
import dash_bootstrap_components as dbc
from constants import UI
from parameter_config import MeshIntegrationConfig, WarpConfigStitching

# Initialize defaults from Pydantic models
default_mesh = MeshIntegrationConfig()
default_warp = WarpConfigStitching()


def layout(active_service=None):

    # Determine the initial path(s)
    initial_output_dir = UI.get_proj_dir(active_service)
    stitch_yaml_path = UI.get_stitching_config_path(active_service)
    inp_stitch_cfg = UI.INP_STITCH_CFG
    if stitch_yaml_path:
        inp_stitch_cfg["value"] = stitch_yaml_path
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H3("Step 2: Section Stitching", className="mt-3"),
                html.P("Configure SOFIMA alignment and perform coarse offset estimation.",
                       className="text-muted small"),
            ], width=12)
        ]),

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
                                        dbc.Button("Save / Export", id=UI.ID_STITCH_SAVE_YAML, color="success", size="sm"),
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
                                            dbc.Col([UI.label_factory("Start Section"), dbc.Input(id="conf-start", type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("End Section"), dbc.Input(id="conf-end", type="number", size="sm")], width=6),
                                        ], className="mt-2"),
                                    ], className="p-3 border-start border-end border-bottom")
                                ]),

                                # REGISTRATION TAB
                                dbc.Tab(label="Registration (SOFIMA)", tab_id="tab-reg", children=[
                                    html.Div([
                                        dbc.Row([
                                            dbc.Col([UI.label_factory("Overlaps X (csv)"), dbc.Input(id=UI.ID_CONF_OVERLAPS_X, placeholder="200, 300, 400", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Overlaps Y (csv)"), dbc.Input(id=UI.ID_CONF_OVERLAPS_Y, placeholder="200, 300, 400", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Range (csv)"), dbc.Input(id=UI.ID_CONF_MIN_RANGE, placeholder="10, 100, 0", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Overlap"), dbc.Input(id=UI.ID_CONF_MIN_OVERLAP, placeholder="20",  type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Filter Size"), dbc.Input(id=UI.ID_CONF_FILTER_SIZE, placeholder="10",  type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Patch Size (csv)"), dbc.Input(id=UI.ID_CONF_PATCH, placeholder="120, 120", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Batch Size"), dbc.Input(id=UI.ID_CONF_BATCH, placeholder="8000", type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Peak Ratio"), dbc.Input(id=UI.ID_CONF_MIN_PKR, placeholder="1.0", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Peak Sharpness"), dbc.Input(id=UI.ID_CONF_MIN_PKS, placeholder="1.0", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Max Deviation"), dbc.Input(id=UI.ID_CONF_MAX_DEV, placeholder="6", type="number", size="sm")], width=6),
                                        ]),
                                        dbc.Row([
                                            dbc.Col([UI.label_factory("Max Magnitude"), dbc.Input(id=UI.ID_CONF_MAX_MAG, placeholder="0", type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Min Patch Size"), dbc.Input(id=UI.ID_CONF_MIN_PATCH, placeholder="10", type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Max Gradient"), dbc.Input(id=UI.ID_CONF_MAX_GRAD, placeholder="12", type="number", size="sm")], width=6),
                                            dbc.Col([UI.label_factory("Rec. Flow Max Dev"), dbc.Input(id=UI.ID_CONF_REC_FLOW_MAX_GRAD, placeholder="-1", type="number", size="sm")], width=6),
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
                ], active_item="config-manager", className="shadow-sm mb-3")
            ], width=12)
        ]),

        # 2. EXECUTION SECTION (COLLAPSIBLE)
        dbc.Row([
            dbc.Col([
                dbc.Accordion([
                    dbc.AccordionItem(
                        item_id="execution-control",
                        title=html.Div([html.I(className="bi bi-play-circle-fill me-2"), "Execution Control & Console"]),
                        children=[
                            dbc.Row([
                                dbc.Col([
                                    UI.label_factory("Section Selection for Estimation", is_bold=True),
                                    dbc.Input(id=UI.ID_STITCH_SECTION_INP, placeholder="e.g. 0-100, 105, 106 or 'all'", size="sm"),
                                    html.P("Iterates through all overlaps within the specified layers.", className="text-muted mb-0", style={"fontSize": "11px"}),
                                ], width=8),
                                dbc.Col([
                                    dbc.Button([html.I(className="bi bi-play-fill me-2"), "Run Estimation"],
                                               id=UI.ID_STITCH_RUN_BTN, color="danger", className="w-100 h-100", size="sm"),
                                ], width=4),
                            ]),
                            html.Hr(),
                            html.Div(
                                id=UI.ID_STITCH_CONSOLE,
                                children=[],
                                className="bg-dark text-white p-3 rounded",  # p-3 for a bit of internal padding
                                style={
                                    "height": "350px",  # Fixed height creates the "window"
                                    "overflowY": "auto",  # Shows scrollbar only when needed
                                    "fontFamily": "monospace",  # Essential for that CLI look
                                    "fontSize": "12px",
                                    "whiteSpace": "pre-wrap",  # Preserves line breaks and wrapping
                                    "border": "1px solid #444",
                                    "display": "flex",
                                    "flexDirection": "column",  # Standard top-to-bottom flow
                                }
                            ),
                            dcc.Store(id="scroll-trigger-dummy"),
                            html.Div(id="stitch-progress-container", children=[
                                dcc.Interval(id="stitch-progress-interval", interval=1000, disabled=True),
                                dbc.Progress(id="stitch-progress-bar", value=0, striped=True, animated=True,
                                             className="mb-2", style={"display": "none"}),
                                html.Small(id="stitch-progress-text", className="text-muted")
                            ])
                        ]
                    )
                ], active_item="execution-control", className="shadow-sm border-danger")
            ], width=12)
        ])
    ], fluid=True)


