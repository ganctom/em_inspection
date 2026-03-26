from dataclasses import dataclass
from dash import html
import dash_bootstrap_components as dbc

import parameter_config
from parameter_config import DEF_CT, DEF_PX_SIZE


@dataclass(frozen=True)
class OverlapType:
    HORIZONTAL = "H"
    VERTICAL = "V"


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
    FN_CFG_TILE_STITCHING = "tile_stitching_config.yaml"

    # --- LABELS ---
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
    LBL_OUT_DIR = "Output Directory"

    # --- IDs ---
    ID_INP_NAME = "new-exp-name"
    ID_INP_ACQ = "new-exp-acq"
    ID_INP_PROC = "new-exp-proc"
    ID_BTN_ADD_EXP = "add-new-exp-btn"
    ID_BTN_PARSE = "parse-exp-btn"
    ID_BTN_PARSE_WRAPPER = "parse-btn-wrapper"
    ID_TTP_PARSE = "parse-btn-tooltip"
    ID_BTN_INIT = "load-config-btn"
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

    # --- Messages ---
    MSG_PARSE_DISABLED = "Add a new experiment or initialize an existing one before parsing acquired data."
    MSG_PARSE_READY = "Click to start parsing the acquired dataset and validation."
    MSG_BCKP_CO_DISABLED = "Initialize the project to enable coarse offsets backup or downstream workflow steps."
    MSG_BCKP_CO_READY = "Click to aggregate and store offsets and tile-id maps to enable inspection."

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

    @property
    def INP_STITCH_CFG(self):
        return self.text_factory(
            self.ID_STITCH_CONFIG_PATH, f"/Volumes/.../run-01/{parameter_config.FN_STITCHING_CFG}"
        )

    # ---- STITCHING PAGE ----  #


    # --- Stitching IDs ---
    ID_STITCH_CONFIG_PATH = "config-path"
    ID_STITCH_LOAD_YAML = "btn-load-yaml"
    ID_STITCH_SAVE_YAML = "btn-save-yaml"

    # Registration IDs
    ID_CONF_OVERLAPS_X = "conf-overlaps-x"
    ID_CONF_OVERLAPS_Y = "conf-overlaps-y"
    ID_CONF_MIN_OVERLAP = "conf-min-overlap"
    ID_CONF_MIN_RANGE = "conf-min-range"
    ID_CONF_PATCH = "conf-patch"
    ID_CONF_BATCH = "conf-batch"
    ID_CONF_MIN_PKR = "conf-min-pkr"
    ID_CONF_MIN_PKS = "conf-min-pks"
    ID_CONF_MAX_DEV = "conf-max-dev"
    ID_CONF_MAX_MAG = "conf-max-mag"
    ID_CONF_MIN_PATCH = "conf-min-patch"
    ID_CONF_MAX_GRAD = "conf-max-grad"
    ID_CONF_REC_FLOW_MAX_GRAD = "conf-rec-flow-max-grad"

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
    ID_STITCH_RUN_BTN = "run-stitching-btn"
    ID_STITCH_CONSOLE = "stitching-results-console"
    ID_STITCH_SECTION_INP = "section-selection-input"

    @classmethod
    def label_factory(cls, text, is_bold=False):
        className = "small mb-1" + (" fw-bold" if is_bold else "")
        return dbc.Label(text, className=className)

    @classmethod
    def _get_active_proc_dir(cls, service) -> str | None:
        """Internal helper to safely extract proc_dir from the service."""
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


# Create a single instance to use properties easily
UI = UIConstants()


class DataConstants:
    CACHED_BASKET_ITEMS = 15

@dataclass()
class KeyboardShortcuts:
    KEY_GRID_NAV_SLIDER_PLUS: str = "w"
    KEY_GRID_NAV_SLIDER_MINUS: str = "s"