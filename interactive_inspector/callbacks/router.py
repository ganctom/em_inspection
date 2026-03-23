from dash import Input, Output
from app import app

@app.callback(
    [Output("nav-setup", "active"),
     Output("nav-stitch", "active"),
     Output("nav-inspect", "active"),
     Output("nav-proc", "active")],
    [Input("url", "pathname")]
)
def update_active_nav(pathname):
    return [
        pathname == "/setup",
        pathname == "/stitching",
        pathname == "/inspection",
        pathname == "/post-processing"
    ]