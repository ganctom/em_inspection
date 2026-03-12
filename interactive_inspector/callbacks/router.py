from dash import Input, Output
from interactive_inspector.app import app

@app.callback(
    [Output("nav-setup", "active"),
     Output("nav-proc", "active"),
     Output("nav-inspect", "active"),
     Output("nav-stitch", "active")],
    [Input("url", "pathname")]
)
def update_active_nav(pathname):
    return [
        pathname == "/setup",
        pathname == "/processing-step",
        pathname == "/inspection",
        pathname == "/stitching"
    ]