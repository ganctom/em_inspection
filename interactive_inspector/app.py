import dash
import dash_bootstrap_components as dbc
from constants import UIConstants

# Initialize App without a layout yet
app = dash.Dash(
    __name__,
    external_stylesheets=[UIConstants.THEME_LIGHT, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True  # CRITICAL for multi-page apps
)

server = app.server