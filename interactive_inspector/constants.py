from dataclasses import dataclass
import dash_bootstrap_components as dbc


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

    # SETUP Page
    NAME_BTN_ADD_EXP = "Add Experiment"
    NAME_BTN_PARSE = "Parse Experiment"
    NAME_BTN_INIT = "Initialize Project"

    ID_BTN_ADD_EXP = "add-new-exp-btn"
    ID_BTN_PARSE = "parse-exp-btn"
    ID_BTN_INIT = "load-config-btn"

    BTN_PARSE_CFG = {
        "children": NAME_BTN_PARSE,
        "id": ID_BTN_PARSE,
        "color": "primary",
        "outline": True
    }

    BTN_ADD_EXP_CFG = {
        "children": NAME_BTN_ADD_EXP,
        "id": ID_BTN_ADD_EXP,
        "color": "primary",
        "outline": True
    }

    BTN_INIT_CFG = {
        "children": NAME_BTN_INIT,
        "id": ID_BTN_INIT,
        "color": "success",
        "className": "w-100 mt-3",
        "disabled": True
    }

    # INSPECTOR PAGE
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
    SIZE_TEXT_GRID_TILE_ID = 10
    SIZE_MARKER_GRID_TILE_ACTIVE = 28

    SELECTION_MAP = {
        0: OverlapType.HORIZONTAL, 1: OverlapType.HORIZONTAL,
        2: OverlapType.VERTICAL, 3: OverlapType.VERTICAL
    }



class DataConstants:
    CACHED_BASKET_ITEMS = 15

@dataclass()
class KeyboardShortcuts:
    KEY_GRID_NAV_SLIDER_PLUS: str = "w"
    KEY_GRID_NAV_SLIDER_MINUS: str = "s"