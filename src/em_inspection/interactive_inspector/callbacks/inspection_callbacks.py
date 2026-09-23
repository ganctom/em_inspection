from dash import html, Input, Output, State, ctx, no_update, ALL

from app import app
from data_service import service
from interactive_inspector.constants import UIConstants
from workflows.inspection_workflow import InspectionWorkflowManager


# =============================================================================
# PLOT TILE OVERLAP
# =============================================================================
@app.callback(
    [
        Output("integrated-overlap-graph", "figure"),
        Output("integrated-ov-status", "children"),
    ],
    [Input("active-item-index", "data"), Input("manual-nudge-store", "data")],
    [State("selection-store", "data")],
    prevent_initial_call=True,
)
def replot_overlap_view(active_idx, nudge_trigger, selection_data):
    return InspectionWorkflowManager.handle_tile_overlap_replot(
        active_idx=active_idx,
        nudge_trigger=nudge_trigger,
        selection_data=selection_data,
    )


# =============================================================================
# OVERLAP FLOW FIELD VISUALIZATION
# =============================================================================
@app.callback(
    [
        Output("integrated-overlap-graph", "figure", allow_duplicate=True),
        Output("integrated-ov-status", "children", allow_duplicate=True),
        Output("registration-log", "children", allow_duplicate=True),
    ],
    [
        Input({"type": UIConstants.ID_BTN_FLOW, "index": ALL}, "n_clicks"),
        Input({"type": UIConstants.ID_BTN_CLEAN_FLOW, "index": ALL}, "n_clicks"),
    ],
    [
        State("selection-store", "data"),
        State(UIConstants.ID_GLOBAL_SETTINGS_STORE, "data"),
    ],
    prevent_initial_call=True,
)
def render_flow_visualizations(
    _flow_clicks, _clean_clicks, selection_data, settings_data
):
    if not ctx.triggered_id or not selection_data:
        return no_update, no_update, no_update

    return InspectionWorkflowManager.handle_flow_visualization(
        triggered_id=ctx.triggered_id,
        triggered_events=ctx.triggered,
        selection_data=selection_data,
        settings_data=settings_data,
    )


# =============================================================================
# RANGE MASKS VISUALIZATION CALLBACK
# =============================================================================
@app.callback(
    [
        Output("integrated-overlap-graph", "figure", allow_duplicate=True),
        Output("integrated-ov-status", "children", allow_duplicate=True),
        Output("registration-log", "children", allow_duplicate=True),
    ],
    [Input({"type": UIConstants.ID_BTN_RANGE_MASKS, "index": ALL}, "n_clicks")],
    [State("selection-store", "data")],
    prevent_initial_call=True,
)
def render_range_mask_visualizations(_range_clicks, selection_data):
    if not ctx.triggered_id or not selection_data:
        return no_update, no_update, no_update

    return InspectionWorkflowManager.handle_range_masks_visualization(
        triggered_id=ctx.triggered_id,
        triggered_events=ctx.triggered,
        selection_data=selection_data,
    )


# =============================================================================
# RAW TILE IMAGE VISUALIZATION CALLBACK
# =============================================================================
@app.callback(
    [
        Output("integrated-overlap-graph", "figure", allow_duplicate=True),
        Output("integrated-ov-status", "children", allow_duplicate=True),
        Output("registration-log", "children", allow_duplicate=True),
    ],
    [Input({"type": UIConstants.ID_BTN_TILE_IMAGE, "index": ALL}, "n_clicks")],
    [State("selection-store", "data")],
    prevent_initial_call=True,
)
def render_raw_tile_image_visualizations(_tile_clicks, selection_data):
    if not ctx.triggered_id or not selection_data:
        return no_update, no_update, no_update

    return InspectionWorkflowManager.handle_raw_tile_visualization(
        triggered_id=ctx.triggered_id,
        triggered_events=ctx.triggered,
        selection_data=selection_data,
    )


# =============================================================================
# BATCH COARSE OFFSETS CALCULATION CALLBACK
# =============================================================================
@app.callback(
    [
        Output("registration-log", "children", allow_duplicate=True),
        Output("integrated-overlap-graph", "figure", allow_duplicate=True),
        Output("integrated-ov-status", "children", allow_duplicate=True),
    ],
    [Input("run-batch-btn", "n_clicks")],
    [
        State("selection-store", "data"),
        State("active-item-index", "data"),
        State("manual-nudge-store", "data"),
        State("guess-mode-select", "value"),
        State("manual-dx", "value"),
        State("manual-dy", "value"),
        State(UIConstants.ID_INP_SEARCH_RAD, "value"),
    ],
    prevent_initial_call=True,
)
def execute_batch_processing(
    n_clicks,
    selection_data,
    active_idx,
    nudge_trigger,
    guess_mode,
    m_dx,
    m_dy,
    search_rad,
):
    return InspectionWorkflowManager.handle_batch_calculation(
        n_clicks=n_clicks,
        selection_data=selection_data,
        active_idx=active_idx,
        nudge_trigger=nudge_trigger,
        guess_mode=guess_mode,
        m_dx=m_dx,
        m_dy=m_dy,
        search_rad=search_rad,
    )


# =============================================================================
# SINGLE CALCULATION CALLBACK
# =============================================================================
@app.callback(
    [
        Output("registration-log", "children", allow_duplicate=True),
        Output("integrated-overlap-graph", "figure", allow_duplicate=True),
        Output("integrated-ov-status", "children", allow_duplicate=True),
    ],
    [Input({"type": "compute-single-btn", "index": ALL}, "n_clicks")],
    [
        State("selection-store", "data"),
        State("active-item-index", "data"),
        State("manual-nudge-store", "data"),
        State(UIConstants.ID_INP_SEARCH_RAD, "value"),
    ],
    prevent_initial_call=True,
)
def execute_single_calculation(
    single_clicks, selection_data, active_idx, nudge_trigger, search_rad
):
    if (
        not ctx.triggered_id
        or not selection_data
        or active_idx is None
        or active_idx >= len(selection_data)
    ):
        return "Waiting for selection...", no_update, no_update

    return InspectionWorkflowManager.handle_single_calculation(
        triggered_id=ctx.triggered_id,
        triggered_events=ctx.triggered,
        selection_data=selection_data,
        active_idx=active_idx,
        nudge_trigger=nudge_trigger,
        search_rad=search_rad,
    )


@app.callback(
    Output("selection-store", "data"),
    [
        Input("quad-plot", "selectedData"),
        Input("clear-selection", "n_clicks"),
        Input(UIConstants.ID_BTN_IMPORT_INF, "n_clicks"),
        Input({"type": "remove-btn", "index": ALL}, "n_clicks"),
    ],
    [State("selection-store", "data"), State("master-grid", "clickData")],
    prevent_initial_call=True,
)
def handle_selection_state(
    sel_data, clear_n, import_n, remove_n, current_store, grid_click
):
    if not ctx.triggered:
        return no_update

    return InspectionWorkflowManager.handle_selection_state_mutation(
        triggered_id=ctx.triggered_id,
        sel_data=sel_data,
        clear_n=clear_n,
        import_n=import_n,
        remove_n=remove_n,
        current_store=current_store,
        grid_click=grid_click,
    )


@app.callback(
    Output("selection-list-container", "children"), Input("selection-store", "data")
)
def sync_selection_ui(data):
    return InspectionWorkflowManager.sync_basket_ui_container(data)


@app.callback(
    Output("quad-plot", "figure"),
    [
        Input("master-grid", "clickData"),
        Input("selection-store", "data"),
        Input("theme-switch", "value"),
    ],
)
def render_main_visuals(grid_click, selection_store, dark_mode):
    if not ctx.triggered:
        return no_update

    return InspectionWorkflowManager.handle_main_quad_visualization(
        grid_click=grid_click, selection_store=selection_store, dark_mode=dark_mode
    )


@app.callback(
    Output("registration-log", "children", allow_duplicate=True),
    Input("save-cxyz-btn", "n_clicks"),
    prevent_initial_call=True,
)
def handle_persist_to_disk(n_clicks):
    if not n_clicks:
        return no_update
    try:
        service.processor.save_offsets_to_disk_db()
        return html.Div(
            [
                html.P("💾 CXYZ File Updated", className="text-warning mb-0 fw-bold"),
                html.Small(
                    "Modifications persisted to disk.", className="text-white-50"
                ),
            ]
        )
    except Exception as e:
        return html.Div(f"Save Failed: {str(e)}", className="text-danger")


@app.callback(
    Output("manual-input-container", "style"), Input("guess-mode-select", "value")
)
def toggle_manual_input(mode):
    return {"display": "block"} if mode == "manual" else {"display": "none"}


@app.callback(
    Output("registration-log", "children", allow_duplicate=True),
    Input("export-sections-btn", "n_clicks"),
    prevent_initial_call=True,
)
def handle_export_sections(n_clicks):
    if not n_clicks:
        return no_update

    try:
        service.store_offsets_to_cx_cy_json_files()

        return html.Div(
            [
                html.P(
                    "Storing coarse offsets to section cx_cy files",
                    className="text-info mb-0 fw-bold",
                ),
                html.Small(
                    "Coarse offsets have been stored.", className="text-white-50"
                ),
            ]
        )
    except Exception as e:
        return html.Div(
            [
                html.P("❌ Export Failed", className="text-danger mb-0 fw-bold"),
                html.Small(str(e), className="text-white small"),
            ]
        )


@app.callback(
    [
        Output("section-filter-slider", "value"),
        Output("master-grid", "figure"),
        Output("manual-z-input", "value"),
    ],
    [
        Input("section-filter-slider", "value"),
        Input("master-grid", "clickData"),
        Input("manual-z-input", "value"),
    ],
    [State("selection-store", "data")],
    prevent_initial_call=False,
)
def grid_navigator_callback(slider_val, click_data, manual_z, basket_data):
    return InspectionWorkflowManager.handle_grid_navigation(
        triggered_id=ctx.triggered_id,
        slider_val=slider_val,
        click_data=click_data,
        manual_z=manual_z,
        basket_data=basket_data,
    )


@app.callback(
    Output("section-filter-slider", "value", allow_duplicate=True),
    Input("keyboard-listener", "n_events"),
    State("keyboard-listener", "event"),
    State("section-filter-slider", "value"),
    prevent_initial_call=True,
)
def handle_keyboard_nav(n_events, event, current_slider_val):
    return InspectionWorkflowManager.handle_keyboard_slice_navigation(
        n_events=n_events, event=event, current_slider_val=current_slider_val
    )


@app.callback(
    [Output("manual-nudge-store", "data"), Output("active-item-index", "data")],
    [
        Input({"type": "nudge-btn", "index": ALL}, "n_clicks"),
        Input({"type": "nav-btn", "index": ALL}, "n_clicks"),
        Input({"type": "plot-ov-btn", "index": ALL}, "n_clicks"),
        Input("keyboard-listener", "n_events"),
    ],
    [
        State("keyboard-listener", "event"),
        State({"type": "nudge-stitch_config", "index": ALL}, "value"),
        State("manual-nudge-store", "data"),
        State("active-item-index", "data"),
        State("selection-store", "data"),
    ],
    prevent_initial_call=True,
)
def handle_nudging(
    nudge_clicks,
    nav_clicks,
    ov_clicks,
    n_events,
    key_event,
    step_list,
    current_nudge,
    current_active,
    selection_store,
):
    return InspectionWorkflowManager.handle_nudge_and_basket_navigation(
        triggered_id=ctx.triggered_id,
        key_event=key_event,
        step_list=step_list,
        current_nudge=current_nudge,
        current_active=current_active,
        selection_store=selection_store,
    )


@app.callback(
    Output("selection-list-container", "aria-busy"),
    Input("selection-store", "data"),
    prevent_initial_call=True,
)
def handle_background_preload(selection_data):
    if selection_data and len(selection_data) > 0:
        service.preload_source_images(selection_data)
        return "true"
    return "false"


# --- CALLBACK: CLEAR BASKET & CACHE ---
@app.callback(
    [
        Output("selection-store", "data", allow_duplicate=True),
        Output("active-item-index", "data", allow_duplicate=True),
    ],
    Input("clear-selection", "n_clicks"),
    prevent_initial_call=True,
)
def handle_clear_basket(n):
    if n:
        service.clear_cache()
        return [], None
    return no_update, no_update
