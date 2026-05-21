import os

import dash
import dash_bootstrap_components as dbc
from constants import UI
from os import makedirs

# Create app_data directory to store user_experiments.yaml
DIRNAME_APP_DATA = "app_data"

makedirs(f"./{DIRNAME_APP_DATA}", exist_ok=True)

# Initialize App without a layout yet
app = dash.Dash(
    __name__,
    external_stylesheets=[UI.THEME_LIGHT, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True  # CRITICAL for multi-page apps
)
app.config.suppress_callback_exceptions = True # Double-down on the stitch_config
server = app.server
