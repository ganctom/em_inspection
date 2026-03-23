from dataclasses import dataclass
import dash_bootstrap_components as dbc

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


    # --- NAMES ---
    NAME_BTN_ADD_EXP = "Add Experiment"
    NAME_BTN_PARSE = "Parse Experiment"
    NAME_BTN_INIT = "Initialize Project"

    NAME_INP_NAME = "Experiment Name"
    NAME_INP_ACQ = "Acquisition Directory (Absolute Path)"
    NAME_INP_PROC = "Processing Directory (Absolute Path)"
    NAME_INP_GRID_NUM = "Grid nr."
    NAME_INP_GRID_SIZE = "Grid shape (X, Y)"
    NAME_INP_SEC_RANGE = "Section range"
    NAME_INP_PX_SIZE = "Pixel size (nm)"
    NAME_INP_CT = "Cutting thickness (nm)"

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

    # --- Messages ---
    MSG_PARSE_DISABLED = "Please add a new experiment or initialize an existing one before parsing."
    MSG_PARSE_READY = "Click to start parsing and validation."

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
    def SEL_EXPERIMENT(self):
        return self.select_factory(self.ID_SEL_EXPERIMENT, "Choose an experiment...")

    @property
    def TTP_PARSE(self):
        return self.tooltip_factory(
            id=self.ID_TTP_PARSE,
            target=self.ID_BTN_PARSE_WRAPPER,
            children=self.MSG_PARSE_DISABLED
        )


# Create a single instance to use properties easily
UI = UIConstants()


class DataConstants:
    CACHED_BASKET_ITEMS = 15

@dataclass()
class KeyboardShortcuts:
    KEY_GRID_NAV_SLIDER_PLUS: str = "w"
    KEY_GRID_NAV_SLIDER_MINUS: str = "s"