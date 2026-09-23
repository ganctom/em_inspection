from dash import html, dcc
import dash_bootstrap_components as dbc
from constants import UI


def layout(active_service=None):

    coarse_params = active_service.reg_config.coarse_params
    stitch_params = active_service.reg_config.stitch_params
    mesh_params = active_service.mesh_config
    warp_params = active_service.warp_config
    mask_params = active_service.mask_config

    return dbc.Container(
        [
            # 1. CONFIGURATION SECTION (COLLAPSIBLE)
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Accordion(
                                [
                                    dbc.AccordionItem(
                                        item_id="stitch_config-manager",
                                        title=html.Div(
                                            [
                                                html.I(className="bi bi-sliders2 me-2"),
                                                "Stitching Configuration Manager",
                                                dbc.Badge(
                                                    "Ready",
                                                    color="success",
                                                    className="ms-2",
                                                    id="sync-badge",
                                                ),
                                                html.Small(
                                                    id="header-path-summary",
                                                    className="ms-3 text-muted",
                                                    style={
                                                        "fontSize": "11px",
                                                        "fontWeight": "normal",
                                                    },
                                                ),
                                            ]
                                        ),
                                        children=[
                                            # Path Selection
                                            UI.PATH_SELECTOR_STITCH(active_service),
                                            dbc.Button(
                                                "Sync Settings to Global Store",
                                                id=UI.ID_BTN_FETCH_GLOBAL,
                                                color="primary",
                                                className="mb-3",
                                            ),
                                            # 1. CONFIGURATION SECTION (Final Tabs Assembly)
                                            dbc.Tabs(
                                                [
                                                    UI.TAB_ACQUISITION(active_service),
                                                    UI.TAB_MASKING(mask_params),
                                                    UI.TAB_REGISTRATION(coarse_params),
                                                    UI.TAB_STITCHING(stitch_params),
                                                    UI.TAB_MESH_WARP(
                                                        mesh_params, warp_params
                                                    ),
                                                ],
                                                id="stitch_config-tabs",
                                                active_tab="tab-acq",
                                            ),
                                        ],
                                    )
                                ],
                                active_item="stitch_config-manager",
                                className="shadow-sm mt-4",
                            )
                        ],
                        width=12,
                    )
                ]
            ),
            # 2. EXECUTION SECTION
            dbc.Row(
                [
                    dbc.Col(
                        [
                            dbc.Accordion(
                                [
                                    dbc.AccordionItem(
                                        item_id="execution-control",
                                        title=html.Div(
                                            [
                                                html.I(
                                                    className="bi bi-play-circle-fill me-2"
                                                ),
                                                "Execution Control & Console",
                                            ]
                                        ),
                                        children=[
                                            dbc.Row(
                                                [
                                                    # Input Column
                                                    UI.COL_COARSE_INP,
                                                    # Action Buttons Column
                                                    dbc.Col(
                                                        [
                                                            dbc.Row(
                                                                [
                                                                    # Estimation Button
                                                                    dbc.Col(
                                                                        dbc.Button(
                                                                            **UI.BTN_RUN_ESTIM
                                                                        ),
                                                                        width=12,
                                                                    ),
                                                                    # Backup Button + Tooltip
                                                                    UI.COL_COARSE_BCKP_CO,
                                                                ]
                                                            )
                                                        ],
                                                        width=6,
                                                    ),
                                                ]
                                            ),
                                            html.Hr(),
                                            # The Terminal/Console Window
                                            UI.CONSOLE_COARSE,
                                            # Helper components
                                            dcc.Store(id="scroll-trigger-dummy"),
                                            # Progress Bar and Interval
                                            UI.PROGRESS_COARSE,
                                        ],
                                    )
                                ],
                                active_item="execution-control",
                                className="shadow-sm border-danger",
                            )
                        ],
                        width=12,
                    )
                ]
            ),
        ],
        fluid=True,
    )
