import time
from dataclasses import dataclass
from dash import html, dcc
import dash_bootstrap_components as dbc

import parameter_config as pcfg
from parameter_config import DEF_CT, DEF_PX_SIZE, FN_STITCHING_CFG, RegistrationConfig, MaskingConfig, StitchingConfig


@dataclass(frozen=True)
class OverlapType:
    HORIZONTAL = "H"
    VERTICAL = "V"

class Task:
    # 1. THE KEYS (Internal IDs)
    COARSE_OFFSETS = "coarse_offsets"
    COARSE_MESH    = "coarse_mesh"
    MARGIN_MASKS   = "margin_masks"
    FINE_FLOWS     = "fine_flows"
    FINE_MESHES    = "fine_meshes"
    WARP_SECTION   = "warp_section"
    DOWNSCALE      = "downscale_warped_section"

    @classmethod
    def get_master_order(cls):
        """Returns the strict execution sequence."""
        return [
            # cls.COARSE_OFFSETS,
            cls.COARSE_MESH,
            cls.MARGIN_MASKS,
            cls.FINE_FLOWS,
            cls.FINE_MESHES,
            cls.WARP_SECTION,
            cls.DOWNSCALE,
        ]

    @classmethod
    def get_ui_options(cls):
        """Returns metadata for the Dash Checklist."""
        labels = {
            # cls.COARSE_OFFSETS: "Compute Coarse Offsets",
            cls.COARSE_MESH:    "Compute Coarse Meshes",
            cls.MARGIN_MASKS:   "Build Margin Masks",
            cls.FINE_FLOWS:     "Compute Fine Flows",
            cls.FINE_MESHES:    "Get Fine Meshes",
            cls.WARP_SECTION:   "Warp Section",
            cls.DOWNSCALE:      "Downscale Warped Section",
        }
        return [{"label": labels[t], "value": t} for t in cls.get_master_order()]


class MSG:
    # Titles & Headers
    PPLN_START = "🚀 Pipeline Started | Mode: {mode}"
    PPLN_SCOPE = "Scope: {count} sections ({first} to {last})"
    PPLN_TASKS = "Tasks: {tasks}"
    PPLN_DIVIDER = "-" * 40

    # Modes
    MODE_PARALLEL = "Parallel (Multi-Core)"
    MODE_SEQUENTIAL = "Sequential (Single-Thread)"

    # Warnings & Errors
    PARALLEL_WARN = "⚡ Utilizing ProcessPoolExecutor for concurrent I/O."
    SETUP_ERROR = "❌ Setup Error: {error}"
    NO_STEPS_ERROR = "❌ Error: No steps selected."

    # Logic-based messages
    IO_RETRY = "s{sec}: Remote I/O Error ({err}). Retrying in {t:.2f}s..."
    IO_FAIL = "s{sec}: Final I/O failure after {retries} attempts: {err}"

    @staticmethod
    def format_tasks(tasks: list) -> str:
        """Standardizes task naming for the console output."""
        return ", ".join([t.replace('_', ' ').title() for t in tasks])


class UIConstants:

    THEME = dbc.themes.BOOTSTRAP
    PRIMARY_COLOR = "#007bff"
    TRACE_COLOR = "#2c3e50"
    HIGHLIGHT_COLOR = "red"

    # Use SLATE for a professional "Lab" dark mode, or DARKLY for high contrast
    THEME_LIGHT = dbc.themes.BOOTSTRAP
    THEME_DARK = dbc.themes.SLATE

    # Graph Colors
    BG_DARK = "#1e1e1e"
    GRID_DARK = "#333333"
    TEXT_DARK = "#f8f9fa"

    # Grid Navigator
    CLR_GRID_TILES_ACTIVE = "#0dcaf0"
    CLR_GRID_TILES_ACTIVE_ID = "#212529"
    CLR_GRID_BASE_HTMP = '#e9ecef'
    CLR_BASE = 'rgba(0,0,0,0)'
    CLR_DIM = "rgba(0, 0, 0, 0.1)"
    SIZE_TEXT_GRID_TILE_ID = 11
    SIZE_MARKER_GRID_FCT = 1.3
    SIZE_NAVIGATOR = 320

    SELECTION_MAP = {
        0: OverlapType.HORIZONTAL, 1: OverlapType.HORIZONTAL,
        2: OverlapType.VERTICAL, 3: OverlapType.VERTICAL
    }

    # --- CONFIG FILENAMES --- #
    FN_CFG_TILE_STITCHING = FN_STITCHING_CFG

    # --- LABELS ---
    NAME_WORKFLOW = "SBFI WORKFLOW"
    NAME_BTN_ADD_EXP = "Add Experiment"
    NAME_BTN_PARSE = "Parse Experiment"
    NAME_BTN_INIT = "Initialize Project"
    NAME_BTN_BCKP_CO = "Store coarse offsets for Inspection"

    NAME_INP_NAME = "Experiment Name"
    NAME_INP_ACQ = "Acquisition Directory (Absolute Path)"
    NAME_INP_PROC = "Processing Directory (Absolute Path)"
    NAME_INP_GRID_NUM = "Grid nr."
    NAME_INP_GRID_SIZE = "Grid shape (X, Y)"
    NAME_INP_SEC_RANGE = "Section range"
    NAME_INP_PX_SIZE = "Pixel size (nm)"
    NAME_INP_CT = "Cutting thickness (nm)"
    LBL_CFG_PATH_YAML = "Config File Path (.yaml)"
    LBL_ACQ_RNG = "Acquisition & Range"
    LBL_PPLN_CFG = "Pipeline Config"
    LBL_OUT_DIR = "Output Directory"
    LBL_COL_COARSE_INP = "Section Selection for Coarse Offsets Estimation"
    LBL_COARSE_TAB_REG = "Registration (SOFIMA)"
    LBL_RESCALE_FCT = "Warped Section Downscale Factor"

    # --- IDs ---
    ID_INP_NAME = "new-exp-name"
    ID_INP_ACQ = "new-exp-acq"
    ID_INP_PROC = "new-exp-proc"
    ID_BTN_ADD_EXP = "add-new-exp-btn"
    ID_BTN_PARSE = "parse-exp-btn"
    ID_BTN_PARSE_WRAPPER = "parse-btn-wrapper"
    ID_TTP_PARSE = "parse-btn-tooltip"
    ID_BTN_INIT = "load-stitch_config-btn"
    ID_INP_PX_SIZE = "new-exp-px-size"
    ID_INP_CT = "new-exp-ct"
    ID_INP_GS_X = "new-exp-grid-size-x"
    ID_INP_GS_Y = "new-exp-grid-size-y"
    ID_INP_GRID_NUM = "new-exp-grid-num"
    ID_INP_FIRST_SEC = "new-exp-first-sec"
    ID_INP_LAST_SEC = "new-exp-last-sec"
    ID_SEL_EXPERIMENT = "experiment-select"
    ID_BTN_BCKP_CO = "init-exp-backup-co"
    ID_TTP_BCKP = "bckp-btn-tooltip"
    ID_BTN_BCKP_WRAPPER = "bckp-btn-wrapper"
    ID_INP_SEARCH_RAD= "search-radius-input"
    ID_TAB_PPLN = "stitch_config-ppln-cfg"
    ID_TAB_PPLN_CFG = "tab-ppln-cfg"
    ID_RESCALE_FCT = "resize-fct"


    # --- Messages ---
    MSG_PARSE_DISABLED = "Add a new experiment or initialize an existing one before parsing acquired data."
    MSG_PARSE_READY = "Click to start parsing the acquired dataset and validation."
    MSG_BCKP_CO_DISABLED = "Initialize the project to enable coarse offsets backup or downstream workflow steps."
    MSG_BCKP_CO_READY = "Aggregates and stores coarse offsets and tile-id maps from all sections to enable Inspection."

    # Standard Label Style
    LBL_CFG = {"className": "small mb-0"}

    # --- THE FACTORIES ---

    @staticmethod
    def _base_cfg(id, placeholder, persistence=True):
        """Shared logic for all setup inputs."""
        return {
            "id": id,
            "size": "sm",
            "placeholder": placeholder,
            "persistence": persistence,
            "persistence_type": "local",
            "className": "mb-2"
        }

    @classmethod
    def numeric_factory(cls, id, value=None, placeholder="", is_int=False):
        cfg = cls._base_cfg(id, placeholder)
        cfg["type"] = "number"
        if value is not None:
            cfg["value"] = value
        if not is_int:
            cfg["step"] = "any"
        return cfg

    @classmethod
    def text_factory(cls, id, placeholder=""):
        cfg = cls._base_cfg(id, placeholder)
        cfg["type"] = "text"
        return cfg

    @classmethod
    def button_factory(cls, id, children, color="primary", outline=True, **kwargs):
        """Standardizes all buttons for the app."""
        cfg = {
            "id": id,
            "children": children,
            "color": color,
            "outline": outline,
        }
        cfg.update(kwargs)
        return cfg


    @classmethod
    def select_factory(cls, id, placeholder, persistence=True, **kwargs):
        """Standardizes dropdown menus for the app."""
        cfg = {
            "id": id,
            "placeholder": placeholder,
            "persistence": persistence,
            "persistence_type": "local",
            "className": "mb-3"
        }
        cfg.update(kwargs)
        return cfg


    @classmethod
    def tooltip_factory(cls, id, target, children, placement="bottom"):
        """Standardizes tooltip behavior across the app."""
        return {
            "id": id,
            "target": target,
            "children": children,
            "placement": placement,
            "trigger": "hover",
            "delay": {"show": 300, "hide": 0},
            "className": "small shadow-sm"
        }

    @classmethod
    def tab_factory(cls, label, tab_id, children):
        """Standardizes the look and feel of configuration tabs."""
        return dbc.Tab(
            label=label,
            tab_id=tab_id,
            children=[
                html.Div(
                    children=children,
                    className="p-3 border-start border-end border-bottom",
                    style={"backgroundColor": "white"}  # Optional: keeps it distinct from background
                )
            ]
        )

    @classmethod
    def label_factory(cls, text, is_bold=False):
        className = "small mb-1" + (" fw-bold" if is_bold else "")
        return dbc.Label(text, className=className)

    # --- COMPONENT REGISTRY ---
    @property
    def INP_NAME(self):
        return self.text_factory(self.ID_INP_NAME, "e.g. FISH_ID_1")

    @property
    def INP_ACQ(self):
        return self.text_factory(self.ID_INP_ACQ, "/Volumes/.../sbem_acq-dir")

    @property
    def INP_PROC(self):
        return self.text_factory(self.ID_INP_PROC, "/Volumes/.../run-01")

    @property
    def INP_PX_SIZE(self):
        return self.numeric_factory(self.ID_INP_PX_SIZE, DEF_PX_SIZE)

    @property
    def INP_CT(self):
        return self.numeric_factory(self.ID_INP_CT, DEF_CT)

    @property
    def INP_GS_X(self):
        return self.numeric_factory(self.ID_INP_GS_X, is_int=True)

    @property
    def INP_GS_Y(self):
        return self.numeric_factory(self.ID_INP_GS_Y, is_int=True)

    @property
    def INP_GRID_NUM(self):
        return self.numeric_factory(self.ID_INP_GRID_NUM, 0, is_int=True)

    @property
    def INP_FIRST_SEC(self):
        return self.numeric_factory(self.ID_INP_FIRST_SEC, placeholder="Start", is_int=True)

    @property
    def INP_LAST_SEC(self):
        return self.numeric_factory(self.ID_INP_LAST_SEC, placeholder="End", is_int=True)

    @property
    def BTN_ADD_EXP(self):
        return self.button_factory(self.ID_BTN_ADD_EXP, self.NAME_BTN_ADD_EXP)

    @property
    def BTN_PARSE(self):
        return self.button_factory(self.ID_BTN_PARSE, self.NAME_BTN_PARSE, disabled=True)

    @property
    def BTN_INIT(self):
        return self.button_factory(self.ID_BTN_INIT, self.NAME_BTN_INIT, className="w-100 mt-3", disabled=True)

    @property
    def BTN_BCKP_CO(self):
        return self.button_factory(self.ID_BTN_BCKP_CO, self.NAME_BTN_BCKP_CO, className="w-100 mt-3", disabled=True)

    @property
    def SEL_EXPERIMENT(self):
        return self.select_factory(self.ID_SEL_EXPERIMENT, "Choose an experiment...")

    @property
    def TTP_PARSE(self):
        return self.tooltip_factory(
            id=self.ID_TTP_PARSE,
            target=self.ID_BTN_PARSE_WRAPPER,
            children=self.MSG_PARSE_DISABLED
        )

    # --- COARSE ALIGNMENT SECTION PROPERTIES ---

    @classmethod
    def TAB_ACQUISITION(cls, active_service=None):
        """Generates the Acquisition & Range tab with dynamic initial values."""
        # Calculate dynamic values from ppln_service
        initial_output_dir = cls.get_proj_dir(active_service)

        # Pull defaults from the ppln_service stitch_config if available, otherwise None
        start_val = active_service.exp_config.first_sec if active_service and active_service.exp_config else None
        end_val = active_service.exp_config.last_sec if active_service and active_service.exp_config else None

        # Define the inner content
        content = [
            cls.label_factory(cls.LBL_OUT_DIR),
            dbc.Input(id="conf-output-dir", value=initial_output_dir, size="sm"),
            dbc.Row([
                dbc.Col([
                    cls.label_factory("Start Section"),
                    dbc.Input(**cls.numeric_factory("conf-start", value=start_val, is_int=True))
                ], width=6),
                dbc.Col([
                    cls.label_factory("End Section"),
                    dbc.Input(**cls.numeric_factory("conf-end", value=end_val, is_int=True))
                ], width=6),
            ], className="mt-2"),
        ]

        # Wrap in your existing tab_factory
        return cls.tab_factory(
            label=cls.LBL_ACQ_RNG,
            tab_id="tab-acq",
            children=content
        )

    @classmethod
    def TAB_PPLN_CONFIG(cls):
        """Generates the Acquisition & Range tab with dynamic initial values."""

        content = [
            cls.label_factory(cls.LBL_RESCALE_FCT),
            dbc.Input(
                id=cls.ID_RESCALE_FCT,
                value=DataConstants.DEF_SCALE_FCT,
                size="sm"
            ),
        ]

        return cls.tab_factory(
            label=cls.LBL_PPLN_CFG,
            tab_id=cls.ID_TAB_PPLN_CFG,
            children=content
        )

    @classmethod
    def TAB_MASKING(cls):
        """Unified Mesh Integration and Warping configuration tab."""
        m_def = MaskingConfig()

        content = [
            html.H6("Margin masks parameters", className="small fw-bold mt-2 mb-3 text-primary"),

            # Row 1: Core Physics Params
            dbc.Row([
              dbc.Col([cls.label_factory("Margin"),
                       dbc.Input(**cls.numeric_factory(cls.ID_CONF_MASK_MARGIN, value=m_def.mask_margin))],
                      width=3),
              dbc.Col([cls.label_factory("Rim size"),
                       dbc.Input(**cls.numeric_factory(cls.ID_CONF_MASK_RIM_SIZE, value=m_def.rim_size))],
                      width=3),
            ], className="mb-3"),
        ]

        return cls.tab_factory(
            label="Masking",
            tab_id="tab-mask",
            children=content
        )

    @classmethod
    def TAB_REGISTRATION(cls, active_service=None):
        """Generates the Registration (SOFIMA) tab using defaults from RegistrationConfig."""

        # Access the defaults from the Pydantic model
        defaults = RegistrationConfig()

        # Helper to convert list defaults to CSV strings for placeholders
        def to_csv(val_list):
            return ", ".join(map(str, val_list))

        content = [
            dbc.Row([
                dbc.Col([
                    cls.label_factory("Overlaps X (csv)"),
                    dbc.Input(**cls.text_factory(
                        cls.ID_CONF_OVERLAPS_X,
                        placeholder=to_csv(defaults.overlaps_x)
                    ))
                ], width=6),

                dbc.Col([
                    cls.label_factory("Overlaps Y (csv)"),
                    dbc.Input(**cls.text_factory(
                        cls.ID_CONF_OVERLAPS_Y,
                        placeholder=to_csv(defaults.overlaps_y)
                    ))
                ], width=6),

                dbc.Col([
                    cls.label_factory("Min Range (csv)"),
                    dbc.Input(**cls.text_factory(
                        cls.ID_CONF_MIN_RANGE,
                        placeholder=to_csv(defaults.min_range)
                    ))
                ], width=6),

                # Pure Numeric Inputs
                dbc.Col([
                    cls.label_factory("Min Overlap"),
                    dbc.Input(**cls.numeric_factory(
                        cls.ID_CONF_MIN_OVERLAP,
                        placeholder=str(defaults.min_overlap),
                        is_int=True
                    ))
                ], width=6),

                dbc.Col([
                    cls.label_factory("Filter Size"),
                    dbc.Input(**cls.numeric_factory(
                        cls.ID_CONF_FILTER_SIZE,
                        placeholder=str(defaults.filter_size),
                        is_int=True
                    ))
                ], width=6),
            ]),
        ]

        return cls.tab_factory(
            label="Registration (SOFIMA)",
            tab_id="tab-reg",
            children=content
        )

    @classmethod
    def TAB_STITCHING_PARAMS(cls):
        """Refactored Registration Tab: Now 'Stitching Parameters'."""
        defaults = pcfg.RegistrationConfig()

        def to_csv(val_list):
            return ", ".join(map(str, val_list))

        content = [
            dbc.Row([
                # Row 1
                dbc.Col([cls.label_factory("Patch Size (csv)"),
                         dbc.Input(**cls.text_factory(cls.ID_CONF_PATCH, to_csv(defaults.patch_size)))], width=6),
                dbc.Col([cls.label_factory("Batch Size"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_BATCH, value=defaults.batch_size, is_int=True))],
                        width=6),
                # Row 2
                dbc.Col([cls.label_factory("Min Peak Ratio"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MIN_PKR, value=defaults.min_peak_ratio))],
                        width=6),
                dbc.Col([cls.label_factory("Min Peak Sharpness"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MIN_PKS, value=defaults.min_peak_sharpness))],
                        width=6),
                # Row 3
                dbc.Col([cls.label_factory("Max Deviation"), dbc.Input(
                    **cls.numeric_factory(cls.ID_CONF_MAX_DEV, value=defaults.max_deviation, is_int=True))], width=6),
                dbc.Col([cls.label_factory("Max Magnitude"), dbc.Input(
                    **cls.numeric_factory(cls.ID_CONF_MAX_MAG, value=defaults.max_magnitude, is_int=True))], width=6),
                # Row 4
                dbc.Col([cls.label_factory("Min Patch Size"), dbc.Input(
                    **cls.numeric_factory(cls.ID_CONF_MIN_PATCH, value=defaults.min_patch_size, is_int=True))],
                        width=6),
                dbc.Col([cls.label_factory("Max Gradient"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MAX_GRAD, value=defaults.max_gradient))], width=6),
                # Row 5
                dbc.Col([cls.label_factory("Rec. Flow Max Dev"), dbc.Input(
                    **cls.numeric_factory(cls.ID_CONF_REC_FLOW_MAX_GRAD, value=defaults.reconcile_flow_max_deviation))],
                        width=12),
            ], className="g-2")
        ]

        return cls.tab_factory(label="Stitching Parameters", tab_id="tab-stitch-params", children=content)

    @classmethod
    def TAB_MESH_WARP(cls):
        """Unified Mesh Integration and Warping configuration tab."""
        m_def = pcfg.MeshIntegrationConfig()
        w_def = pcfg.WarpConfigStitching()

        content = [
            html.H6("Mesh Integration (Elastic Solver)", className="small fw-bold mt-2 mb-3 text-primary"),

            # Row 1: Core Physics Params
            dbc.Row([
                dbc.Col([cls.label_factory("dt"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_DT, value=m_def.dt))], width=3),
                dbc.Col([cls.label_factory("gamma"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_GAMMA, value=m_def.gamma))], width=3),
                dbc.Col([cls.label_factory("k0"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_K0, value=m_def.k0))], width=3),
                dbc.Col([cls.label_factory("k"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_K, value=m_def.k))], width=3),
            ], className="mb-3"),

            # Row 2: Iteration & Step Control
            dbc.Row([
                dbc.Col([cls.label_factory("Stride"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_STRIDE, value=m_def.stride, is_int=True))],
                        width=3),
                dbc.Col([cls.label_factory("Num Iters"),
                         dbc.Input(
                             **cls.numeric_factory(cls.ID_CONF_MESH_NUM_ITERS, value=m_def.num_iters, is_int=True))],
                        width=3),
                dbc.Col([cls.label_factory("Max Iters"),
                         dbc.Input(
                             **cls.numeric_factory(cls.ID_CONF_MESH_MAX_ITERS, value=m_def.max_iters, is_int=True))],
                        width=3),
                dbc.Col([cls.label_factory("Stop v Max"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_STOP_V, value=m_def.stop_v_max))], width=3),
            ], className="mb-3"),

            # Row 3: Limits & Caps (The Missing Entries)
            dbc.Row([
                dbc.Col([cls.label_factory("DT Max"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_DT_MAX, value=m_def.dt_max))], width=4),
                dbc.Col([cls.label_factory("Start Cap"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_START_CAP, value=m_def.start_cap))], width=4),
                dbc.Col([cls.label_factory("Final Cap"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_MESH_FINAL_CAP, value=m_def.final_cap))], width=4),
            ], className="mb-3"),

            # Row 4: Switches
            dbc.Row([
                dbc.Col([
                    dbc.Checklist(id=cls.ID_CONF_MESH_ORIG_ORDER,
                                  options=[{"label": "Prefer Orig Order", "value": True}],
                                  value=[True] if m_def.prefer_orig_order else [], switch=True, className="small")
                ], width=4),
                dbc.Col([
                    dbc.Checklist(id=cls.ID_CONF_MESH_REMOVE_DRIFT,
                                  options=[{"label": "Remove Drift", "value": True}],
                                  value=[True] if m_def.remove_drift else [], switch=True, className="small")
                ], width=4),
            ], className="mb-3"),

            # Warping
            html.Hr(),
            html.H6("Warping (Image Rendering)", className="small fw-bold mt-2 mb-3 text-primary"),
            dbc.Row([
                dbc.Col([cls.label_factory("Margin"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_WARP_MARGIN, value=w_def.margin, is_int=True))],
                        width=4),
                dbc.Col([cls.label_factory("Parallelism"), dbc.Input(
                    **cls.numeric_factory(cls.ID_CONF_WARP_PARALLEL, value=w_def.warp_parallelism, is_int=True))],
                        width=4),
                dbc.Col([cls.label_factory("Kernel Size"), dbc.Input(
                    **cls.numeric_factory(cls.ID_CONF_WARP_KERNEL, value=w_def.kernel_size, is_int=True))], width=4),
            ], className="mb-3"),

            dbc.Row([
                dbc.Col([cls.label_factory("Clip Limit"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_WARP_CLIP, value=w_def.clip_limit))], width=4),
                dbc.Col([cls.label_factory("nbins"),
                         dbc.Input(**cls.numeric_factory(cls.ID_CONF_WARP_NBINS, value=w_def.nbins, is_int=True))],
                        width=4),
                dbc.Col([
                    dbc.Checklist(id=cls.ID_CONF_WARP_CLAHE, options=[{"label": "Use CLAHE", "value": True}],
                                  value=[True] if w_def.use_clahe else [], switch=True, className="small")
                ], width=4),
            ])
        ]
        return cls.tab_factory(label="Mesh & Warp", tab_id="tab-mesh", children=content)



    @property
    def TTP_BCKP_CO(self):
        """Factory-generated stitch_config for the Backup Tooltip."""
        return self.tooltip_factory(
            id=self.ID_TTP_BCKP,
            target=self.ID_BTN_BCKP_WRAPPER,
            children=self.MSG_BCKP_CO_DISABLED
        )

    @property
    def INP_RUN_ESTIM(self):
        return self.text_factory(self.ID_RUN_ESTIM_INP, "e.g. 0-100 or 'all'")

    @property
    def BTN_RUN_ESTIM(self):
        return self.button_factory(
            id=self.ID_RUN_ESTIM_BTN,
            children=[html.I(className="bi bi-play-fill me-2"), "Run Estimation"],
            color="danger",
            outline=False,
            className="w-100 mb-2",
            size="sm"
        )

    @property
    def CONSOLE_COARSE(self):
        """Unified Console for Coarse Alignment."""
        return html.Div(
            id=self.ID_RUN_ESTIM_CONSOLE,
            children=[],
            className="bg-dark text-white p-3 rounded",
            style={
                "height": "350px",
                "overflowY": "auto",
                "fontFamily": "monospace",
                "fontSize": "12px",
                "whiteSpace": "pre-wrap",
                "border": "1px solid #444",
                "display": "flex",
                "flexDirection": "column",
            }
        )

    @property
    def PROGRESS_COARSE(self):
        """Standardized progress area for the coarse alignment page."""
        return html.Div(id="stitch-progress-container", className="mt-2", children=[
            dcc.Interval(id="stitch-progress-interval", interval=1000, disabled=True),
            dbc.Progress(
                id="stitch-progress-bar",
                value=0,
                striped=True,
                animated=True,
                className="mb-2",
                style={"height": "10px", "display": "none"}
            ),
            html.Small(id="stitch-progress-text", className="text-muted", style={"fontSize": "11px"})
        ])

    @property
    def COL_COARSE_INP(self):
        return dbc.Col([
           self.label_factory(self.LBL_COL_COARSE_INP, is_bold=True),
           dbc.Input(**self.INP_RUN_ESTIM),
           html.P("Iterates through overlaps within specified layers.",
                  className="text-muted mb-0", style={"fontSize": "11px"}),
       ], width=6)

    @property
    def COL_COARSE_BCKP_CO(self):
        # Notice the ** inside Button and Tooltip
        return dbc.Col([
            html.Span([
                dbc.Button(**self.BTN_BCKP_CO)
            ], id=self.ID_BTN_BCKP_WRAPPER, className="d-grid"),
            dbc.Tooltip(**self.TTP_BCKP_CO),
        ], width=12)

    @classmethod
    def INP_STITCH_CFG(cls, active_service=None):
        """Generates the stitch_config path input with the correct initial value."""
        stitch_yaml_path = cls.get_stitching_config_path(active_service)

        # Start with the base factory dictionary
        inp_cfg = cls.text_factory(
            id=cls.ID_STITCH_CONFIG_PATH,
            placeholder=f"/Volumes/.../{pcfg.FN_STITCHING_CFG}"
        )

        # Inject the path if the ppln_service provides one
        if stitch_yaml_path:
            inp_cfg["value"] = stitch_yaml_path

        return inp_cfg

    @classmethod
    def PATH_SELECTOR_STITCH(cls, active_service=None):
        """Standardized Path Input Group with Load/Save buttons."""
        return dbc.Row([
            dbc.Col([
                cls.label_factory(cls.LBL_CFG_PATH_YAML, is_bold=True),
                dbc.InputGroup([
                    dbc.Input(**cls.INP_STITCH_CFG(active_service)),
                    dbc.Button("Load", id=cls.ID_STITCH_LOAD_YAML, color="primary", size="sm"),
                    dbc.Button("Save / Export", id=cls.ID_STITCH_SAVE_YAML, color="success", size="sm"),
                ]),
                html.Div(id="stitch_config-load-status", className="small mt-1 text-muted")
            ], width=12, className="mb-3")
        ])

    # ---- STITCHING PAGE ----  #
    # --- Stitching IDs ---
    ID_STITCH_CONFIG_PATH = "stitch_config-path"
    ID_STITCH_LOAD_YAML = "btn-load-yaml"
    ID_STITCH_SAVE_YAML = "btn-save-yaml"

    # Registration IDs
    ID_CONF_OVERLAPS_X = "conf-overlaps-x"
    ID_CONF_OVERLAPS_Y = "conf-overlaps-y"
    ID_CONF_MIN_OVERLAP = "conf-min-overlap"
    ID_CONF_MIN_RANGE = "conf-min-range"
    ID_CONF_FILTER_SIZE = "conf-filter-size"
    ID_CONF_PATCH = "conf-patch"
    ID_CONF_BATCH = "conf-batch"
    ID_CONF_MIN_PKR = "conf-min-pkr"
    ID_CONF_MIN_PKS = "conf-min-pks"
    ID_CONF_MAX_DEV = "conf-max-dev"
    ID_CONF_MAX_MAG = "conf-max-mag"
    ID_CONF_MIN_PATCH = "conf-min-patch"
    ID_CONF_MAX_GRAD = "conf-max-grad"
    ID_CONF_REC_FLOW_MAX_GRAD = "conf-rec-flow-max-grad"

    # Masking IDs
    ID_CONF_MASK_MARGIN = "conf-mask-margin"
    ID_CONF_MASK_RIM_SIZE = "conf-mask-rim-size"

    # Mesh IDs
    ID_CONF_MESH_DT = "conf-mesh-dt"
    ID_CONF_MESH_GAMMA = "conf-mesh-gamma"
    ID_CONF_MESH_K0 = "conf-mesh-k0"
    ID_CONF_MESH_K = "conf-mesh-k"
    ID_CONF_MESH_STRIDE = "conf-mesh-stride"
    ID_CONF_MESH_NUM_ITERS = "conf-mesh-num-iters"
    ID_CONF_MESH_MAX_ITERS = "conf-mesh-max-iters"
    ID_CONF_MESH_STOP_V = "conf-mesh-stop-v"
    ID_CONF_MESH_DT_MAX = "conf-mesh-dt-max"
    ID_CONF_MESH_START_CAP = "conf-mesh-start-cap"
    ID_CONF_MESH_FINAL_CAP = "conf-mesh-final-cap"
    ID_CONF_MESH_BLOCK_SIZE = "conf-mesh-block-size"
    ID_CONF_MESH_ORIG_ORDER = "conf-mesh-orig-order"
    ID_CONF_MESH_REMOVE_DRIFT = "conf-mesh-remove-drift"

    # Warp IDs
    ID_CONF_WARP_MARGIN = "conf-warp-margin"
    ID_CONF_WARP_PARALLEL = "conf-warp-parallel"
    ID_CONF_WARP_KERNEL = "conf-warp-kernel"
    ID_CONF_WARP_CLIP = "conf-warp-clip"
    ID_CONF_WARP_NBINS = "conf-warp-nbins"
    ID_CONF_WARP_CLAHE = "conf-warp-clahe"

    # Execution IDs
    ID_RUN_ESTIM_BTN = "run-estim-btn"
    ID_RUN_ESTIM_CONSOLE = "run-estim-console"
    ID_RUN_ESTIM_INP = "run-estim-input"

    ID_STITCH_PPLN_RUN = "stitch-ppln-run-btn"
    NAME_STITCH_PPLN_RUN = "Run Pipeline"
    ID_STITCH_PPLN_CONSOLE = "stitch-ppln-console"
    ID_STITCH_PPLN_INP = "stitch-ppln-inp"
    ID_STITCH_PPLN_STEPS = "stitch-ppln-steps"
    ID_STITCH_PPLN_PROGRESS = "stitch-ppln-progress"
    ID_STITCH_PPLN_PROGRESS_INT = "stitch-ppln-progress-int"
    ID_STITCH_PPLN_PARALLEL_TOGGLE = "stitch-ppln-parallel-toggle"

    ID_STITCH_PPLN_ABORT = "stitch-ppln-abort-btn"
    NAME_STITCH_PPLN_ABORT = "Abort"


    # --- HEADER ---
    @property
    def STITCH_PPLN_HEADER(self):
        return dbc.CardHeader([
            html.I(className="bi bi-cpu-fill me-2"),
            "Stitching Pipeline Controller"
        ], className="fw-bold bg-danger text-white")

    # --- COLUMN A: Section Selection ---
    @property
    def COL_STITCH_TARGETS(self):
        return dbc.Col([
            self.label_factory("1. Target Sections", is_bold=True),
            dbc.Input(id=self.ID_STITCH_PPLN_INP, placeholder="e.g. 0-100 or 'all'", size="sm"),
            html.P("Define the range for the operations below.", className="text-muted small mb-0"),
        ], width=4, className="border-end")

    # --- COLUMN B: Step Selection ---
    @property
    def COL_STITCH_STEPS(self):
        return dbc.Col([
            self.label_factory("2. Select Pipeline Steps", is_bold=True),
            dbc.Checklist(
                id=self.ID_STITCH_PPLN_STEPS,
                options=Task.get_ui_options(),
                value=[s["value"] for s in Task.get_ui_options()[:3]],
                inline=False,
                switch=True,
                className="small custom-checklist"
            ),
        ], width=5)

    # Pipeline execution buttons
    @property
    def BTN_STITCH_PPLN_RUN(self):
        """Factory-generated stitch_config for the Run button."""
        children = [html.I(className="bi bi-play-circle-fill me-2"), self.NAME_STITCH_PPLN_RUN]
        return self.button_factory(
            id=self.ID_STITCH_PPLN_RUN,
            children=children,
            color="danger",
            outline=False,
            className="w-100 mb-2"
        )

    @property
    def BTN_STITCH_PPLN_ABORT(self):
        """Factory-generated stitch_config for the Abort button."""
        children = [html.I(className="bi bi-stop-fill me-2"), self.NAME_STITCH_PPLN_ABORT]
        return self.button_factory(
            id=self.ID_STITCH_PPLN_ABORT,
            children=children,
            color="secondary",
            outline=True,
            size="sm",
            className="w-100"
        )

    # --- CONSOLE & PROGRESS PROPERTIES ---

    @property
    def STITCH_PPLN_CONSOLE(self):
        """The dark-themed log output area."""
        return html.Div(
            id=self.ID_STITCH_PPLN_CONSOLE,
            className="bg-dark text-white p-3 rounded mt-2",
            style={
                "height": "300px",
                "overflowY": "auto",
                "fontFamily": "monospace",
                "fontSize": "11px",
                "border": "1px solid #444"
            }
        )

    @property
    def STITCH_PPLN_PROGRESS_BAR(self):
        """The animated progress indicator."""
        return dbc.Progress(
            id=self.ID_STITCH_PPLN_PROGRESS,
            value=0,
            striped=True,
            animated=True,
            className="mt-2",
            style={"height": "10px"}
        )


    STITCH_STATUS = {
        "active": True,
        "progress": 0,
        "message": "Initializing SOFIMA...",
        "error": None,
        "current_sections": ""
    }


    @classmethod
    def _get_active_proc_dir(cls, service) -> str | None:
        """Internal helper to safely extract proc_dir from the ppln_service."""
        if service and hasattr(service, 'exp_config') and service.exp_config:
            return getattr(service.exp_config, 'proc_dir', None)
        return None

    @classmethod
    def get_stitching_config_path(cls, service) -> str:
        proc_dir = cls._get_active_proc_dir(service)
        if proc_dir:
            return f"{proc_dir}/{cls.FN_CFG_TILE_STITCHING}"
        return cls.FN_CFG_TILE_STITCHING

    @classmethod
    def get_proj_dir(cls, service) -> str:
        return cls._get_active_proc_dir(service) or ""

    @staticmethod
    def log_row(msg, type="info"):
        """Creates a styled row for the log window."""
        colors = {
            "info": "text-white",
            "success": "text-success",
            "warning": "text-warning",
            "error": "text-danger"
        }
        timestamp = time.strftime("%H:%M:%S")
        return html.Div([
            html.Span(f"[{timestamp}] ", className="text-muted me-2", style={"fontSize": "10px"}),
            html.Span(msg, className=colors.get(type, "text-white"))
        ], className="border-bottom border-secondary pb-1 mb-1", style={"fontSize": "12px"})



    # --- PAGE NAVIGATION FACTORY ---
    TAB_1_NAME = "1. SETUP"
    TAB_2_NAME = "2. COARSE ALIGNMENT"
    TAB_3_NAME = "3. INSPECTION"
    TAB_4_NAME = "4. STITCHING"
    TAB_5_NAME = "5. FINE ALIGNMENT"

    TAB_1_DSCR = "Step 1. Experiment selection and parsing."
    TAB_2_DSCR = "Step 2. Tile coarse-alignment."
    TAB_3_DSCR = "Step 3. Inspection of tile coarse-alignment."
    TAB_4_DSCR = "Step 4: Section Stitching"
    TAB_5_DSCR = "Step 5: Section Fine-Alignment"
    TAB_X_DSCR = "Background processing engine placeholder."

    TAB_3_ALERT = f"No experiment loaded. Please go to {TAB_1_NAME} first and load experiment."
    TAB_4_ALERT = TAB_3_ALERT

    TAB_1_URL = "/setup"
    TAB_2_URL = "/coarse-alignment"
    TAB_3_URL = "/inspection"
    TAB_4_URL = "/stitching"
    TAB_5_URL = "/fine-alignment"

    TAB_1_NAV_ID = "step-1"
    TAB_2_NAV_ID = "step-2"
    TAB_3_NAV_ID = "step-3"
    TAB_4_NAV_ID = "step-4"
    TAB_5_NAV_ID = "step-5"


class WorkflowNav:
    """Logic and factory for the navigation system."""

    @classmethod
    def get_schema(cls):
        """The source of truth for the app structure."""
        return [
            {"label": UI.TAB_1_NAME, "href": UI.TAB_1_URL, "nav_id": UI.TAB_1_NAV_ID},
            {"label": UI.TAB_2_NAME, "href": UI.TAB_2_URL, "nav_id": UI.TAB_2_NAV_ID},
            {"label": UI.TAB_3_NAME, "href": UI.TAB_3_URL, "nav_id": UI.TAB_3_NAV_ID},
            {"label": UI.TAB_4_NAME, "href": UI.TAB_4_URL, "nav_id": UI.TAB_4_NAV_ID},
            {"label": UI.TAB_5_NAME, "href": UI.TAB_5_URL, "nav_id": UI.TAB_5_NAV_ID},
        ]

    @classmethod
    def item_factory(cls, label, href, nav_id):
        """Standardized NavLink generator."""
        return dbc.NavItem(
            dbc.NavLink(
                label,
                href=href,
                id=nav_id,
                active="exact",
                className="small px-3 text-white-50",
                style={
                    "fontSize": "15px",
                    "height": "35px",
                    "display": "flex",
                    "alignItems": "center",
                    "textTransform": "uppercase",
                    "letterSpacing": "0.5px"
                }
            )
        )

    @classmethod
    def get_nav(cls):
        """The final assembly used in the layout."""
        return [cls.item_factory(**item) for item in cls.get_schema()]


# Create a single instance to use properties easily
UI = UIConstants()
Nav = WorkflowNav()


class DataConstants:
    scfg = StitchingConfig()
    CACHED_BASKET_ITEMS = 15
    DEF_SCALE_FCT = scfg.pipeline_config.downscale_factor


@dataclass()
class KeyboardShortcuts:
    KEY_GRID_NAV_SLIDER_PLUS: str = "w"
    KEY_GRID_NAV_SLIDER_MINUS: str = "s"

