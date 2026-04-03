import dash
import dash_bootstrap_components as dbc
from constants import UI

# Initialize App without a layout yet
app = dash.Dash(
    __name__,
    external_stylesheets=[UI.THEME_LIGHT, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True  # CRITICAL for multi-page apps
)
app.config.suppress_callback_exceptions = True # Double-down on the stitch_config
server = app.server
