import logging
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback
from dash_extensions import EventListener
from data_service import service

### Set up logging
# logging.basicConfig(level=logging.DEBUG)
# logging.basicConfig(level=logging.INFO)
logging.basicConfig(level=logging.WARNING)


# 1. Import the app instance first
from app import app

# 2. Import layouts (Ensure the filenames match your actual files)
from layouts.coarse_inspection import create_layout
from layouts import project_setup, stitching_setup
from data_service import service
from constants import Nav, UIConstants

# 3. Register all callbacks by importing the module
import callbacks

# 4. Define the Global App Shell
# Updated index.py layout section
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
                dbc.Nav(Nav.get_nav(), navbar=True, className="flex-row"),
            ], fluid=True, className="justify-content-start"),
            color="dark",
            dark=True,
            className="flex-shrink-0 shadow-sm py-0",
            style={"height": "35px"}
        ),

        # 3. THE DYNAMIC CONTENT
        html.Div(
            id='page-content',
            className="flex-grow-1",
            style={
                "height": "calc(100vh - 35px)",
                "overflow": "auto"  # Changed to auto so pages can scroll if content is long
            }
        )
    ], style={"height": "100vh", "display": "flex", "flexDirection": "column"})
])


# --- ROUTING CALLBACKS ---
@callback(
    Output('page-content', 'children'),
    Input('url', 'pathname')
)
def display_page(pathname):
    """Swaps the layout based on the URL."""

    # Default/Setup path
    if pathname == UIConstants.TAB_1_URL or pathname == '/' or pathname is None:
        return project_setup.layout()

    elif pathname == UIConstants.TAB_2_URL:
        if service.exp_config is not None and service.acq_config is not None:
            return stitching_setup.layout(active_service=service)
        else:
            if service.acq_config is None:
                logging.debug(f'AcqConfig not initialized.')
            return stitching_setup.layout()

    elif pathname == UIConstants.TAB_3_URL:
        if service.processor is None:
            return dbc.Container([
                dbc.Alert(UIConstants.TAB_3_ALERT, color="warning", className="mt-5")
            ])
        return create_layout()

    elif pathname == UIConstants.TAB_4_URL:
        return html.Div([
            html.H3(UIConstants.TAB_4_DSCR),
            dbc.Alert(UIConstants.TAB_X_DSCR, color="secondary")
        ], className="p-5")

    elif pathname == UIConstants.TAB_5_URL:
        return html.Div([
            html.H3(UIConstants.TAB_5_DSCR),
            dbc.Alert(UIConstants.TAB_X_DSCR, color="secondary")
        ], className="p-5")

    else:
        return html.Div([
            html.H1("404"),
            html.P(f"Path '{pathname}' not found.")
        ], className="p-5 text-center")


@callback(
    [Output(UIConstants.TAB_1_NAV_ID, "active"),
     Output(UIConstants.TAB_2_NAV_ID, "active"),
     Output(UIConstants.TAB_3_NAV_ID, "active"),
     Output(UIConstants.TAB_4_NAV_ID, "active"),
     Output(UIConstants.TAB_5_NAV_ID, "active")],
    [Input("url", "pathname")]
)
def update_stepper_style(pathname):
    """Visually highlights the current step in the top nav."""
    return [
        (pathname == UIConstants.TAB_1_URL or pathname == "/"),
        (pathname == UIConstants.TAB_2_URL),
        (pathname == UIConstants.TAB_3_URL),
        (pathname == UIConstants.TAB_4_URL),
        (pathname == UIConstants.TAB_5_URL),
    ]

if __name__ == '__main__':
    # Using '0.0.0.0' makes it accessible on your local network
    app.run(debug=True, port=8050)