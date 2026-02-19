import matplotlib
matplotlib.use('Agg')
from dash import Dash, html, callback, Output, Input
import dash_bootstrap_components as dbc
from dash_bootstrap_templates import load_figure_template

from constants import UIConstants
from layouts.main_layout import create_layout

# This registers the callback logic without needing to call specific functions
import callbacks.navigation
import callbacks.processing

# 2. Setup Figure Templates
# This allows Plotly graphs to automatically use Bootstrap colors
load_figure_template(["bootstrap", "slate"])

# 3. Initialize App (Fixed: No id argument here)
app = Dash(
    __name__,
    external_stylesheets=[UIConstants.THEME_LIGHT, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True
)

# 4. Set Layout (Put the ID on the container instead)
app.layout = html.Div(
    id="theme-wrapper",
    children=create_layout(),
    className="bg-white text-dark" # Initial state
)

# 5. Global Theme Callback
@callback(
    Output("theme-wrapper", "className"),
    Input("theme-switch", "value")
)
def update_theme_style(dark_mode):
    if dark_mode:
        return "bg-dark text-light"
    return "bg-white text-dark"

# 6. Server Reference for deployment
server = app.server

if __name__ == '__main__':
    app.run(debug=True)