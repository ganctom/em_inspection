import logging
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback, no_update
from dash_extensions import EventListener

# 1. Setup logging
# logging.basicConfig(level=logging.DEBUG)
logging.basicConfig(level=logging.WARNING)

# 2. Import the app instance and standardized constants
from app import app
from constants import Nav, UIConstants

# 3. Import layouts
from layouts import setup_layout, coarse_align_layout, stitching_layout, inspection_layout
from data_service import service

# 4. Register all callbacks
import callbacks.stitching_callbacks
import callbacks.coarse_align_callbacks
import callbacks.inspection_callbacks
import callbacks.setup_callbacks

# --- GLOBAL APP SHELL ---
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),

    # GLOBAL DATA STORES
    dcc.Store(id='selection-store', data=[], storage_type='session'),
    dcc.Store(id='active-item-index', data=None, storage_type='session'),
    dcc.Store(id='manual-nudge-store', data={'dx': 0, 'dy': 0}),

    EventListener(
        id="keyboard-listener",
        events=[{"event": "keydown", "props": ["key", "n_events"]}],
        logging=False
    ),

    # Main wrapper
    html.Div([
        # REDESIGNED TOP BAR
        dbc.Navbar(
            dbc.Container([
                dbc.NavbarBrand(
                    UIConstants.NAME_WORKFLOW,
                    className="me-4 fw-bold",
                    style={"fontSize": "15px"}
                ),
                # The Nav items are generated from the WorkflowNav class
                dbc.Nav(Nav.get_nav(), navbar=True, className="flex-row"),
            ], fluid=True, className="justify-content-start"),
            color="dark",
            dark=True,
            className="flex-shrink-0 shadow-sm py-0",
            style={"height": "35px"}
        ),

        # DYNAMIC CONTENT AREA
        html.Div(
            id='page-content',
            className="flex-grow-1",
            style={
                "height": "calc(100vh - 35px)",
                "overflow": "auto"
            }
        )
    ], style={"height": "100vh", "display": "flex", "flexDirection": "column"})
])


# --- ROUTING CALLBACK ---
@callback(
    [Output('page-content', 'children'),
     Output('url', 'pathname')],  # Added URL Output for clean redirection
    Input('url', 'pathname')
)
def display_page(pathname):
    """
    Swaps the layout based on the URL and handles redirects for the cold-start.
    Returns: (Layout, Pathname)
    """

    # 0. Handle Cold Start / Root Redirect
    # If the user hits '/' or None, push them to the setup URL formally
    if pathname == "/" or pathname is None:
        return setup_layout.layout(), UIConstants.TAB_1_URL

    # 1. Setup Page
    if pathname == UIConstants.TAB_1_URL:
        return setup_layout.layout(), no_update

    # 2. Coarse Align Page
    elif pathname == UIConstants.TAB_2_URL:
        # Check if project is initialized
        if service.exp_config and service.acq_config:
            return coarse_align_layout.layout(active_service=service), no_update

        # Fallback if Step 1 is incomplete
        return coarse_align_layout.layout(), no_update

    # 3. Inspection Page
    elif pathname == UIConstants.TAB_3_URL:
        if service.processor is None:
            return dbc.Container([
                dbc.Alert(UIConstants.TAB_3_ALERT, color="warning", className="mt-5")
            ]), no_update
        return inspection_layout.layout(), no_update

    # 4. Stitching Page
    elif pathname == UIConstants.TAB_4_URL:
        if service.exp_config and service.acq_config:
            return stitching_layout.layout(active_service=service), no_update

        # Fallback if Step 1 is incomplete
        return dbc.Container([
            dbc.Alert(UIConstants.TAB_4_ALERT, color="warning", className="mt-5")
        ], className="p-5"), no_update


    # 5. 404 Fallback
    else:
        return html.Div([
            html.H1("404", className="text-danger"),
            html.P(f"Path '{pathname}' not found.")
        ], className="p-5 text-center"), no_update


if __name__ == '__main__':
    # '0.0.0.0' allows access from other machines in the lab network
    app.run(debug=True, port=8050, host='0.0.0.0')