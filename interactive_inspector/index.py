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
from layouts import project_setup, stitching

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
        # REDESIGNED TOP BAR (Left Aligned)
        dbc.Navbar(
            dbc.Container([
                # Brand/Title on the left
                dbc.NavbarBrand("SBFI WORKFLOW", className="ms-2 fw-bold", style={"fontSize": "14px"}),

                # Links also aligned to the left
                dbc.Nav([
                    dbc.NavItem(dbc.NavLink("1. SETUP", href="/setup", id="step-1", className="small")),
                    dbc.NavItem(dbc.NavLink("2. STITCHING", href="/stitching", id="step-2", className="small")),
                    dbc.NavItem(dbc.NavLink("3. INSPECTION", href="/inspection", id="step-3", className="small")),
                    dbc.NavItem(dbc.NavLink("4. PROCESSING", href="/post-processing", id="step-4", className="small")),
                ], navbar=True, className="ms-4 justify-content-start"),

            ], fluid=True),
            color="primary",
            dark=True,
            className="flex-shrink-0 shadow-sm",
            style={"height": "35px"}  # Adjusted height for a slim profile
        ),

        # 2. THE DYNAMIC CONTENT
        html.Div(
            id='page-content',
            className="flex-grow-1",
            style={
                "height": "calc(100vh - 35px)",  # Match the navbar height
                "overflow": "hidden"
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

    if pathname == '/setup' or pathname == '/' or pathname is None:
        return project_setup.layout()

    elif pathname == '/stitching':
        return stitching.layout()

    elif pathname == '/inspection':
        if service.processor is None:
            return dbc.Container([
                dbc.Alert("No experiment loaded. Please go to '1. Setup' first.", color="warning", className="mt-5")
            ])
        return create_layout()

    elif pathname == '/post-processing':
        return html.Div([
            html.H3("Step 4: Post-processing"),
            dbc.Alert("Background processing engine placeholder.", color="secondary")
        ], className="p-5")
    else:
        return html.Div([
            html.H1("404"),
            html.P(f"Path '{pathname}' not found.")
        ], className="p-5 text-center")

@callback(
    [Output("step-1", "active"),
     Output("step-2", "active"),
     Output("step-3", "active"),
     Output("step-4", "active")],
    [Input("url", "pathname")]
)
def update_stepper_style(pathname):
    """Visually highlights the current step in the top nav."""
    return [
        (pathname == "/setup" or pathname == "/"),
        (pathname == "/stitching"),
        (pathname == "/inspection"),
        (pathname == "/post-processing")
    ]

if __name__ == '__main__':
    # Using '0.0.0.0' makes it accessible on your local network
    app.run(debug=True, port=8050)