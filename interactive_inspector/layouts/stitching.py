from dash import html
import dash_bootstrap_components as dbc

def layout():
    return dbc.Row([
        dbc.Col([
            html.H3("Step 4: Section Stitching"),
            html.P("This module will utilize the refined offsets from Step 3 to generate mosaics."),
            dbc.Alert("Status: Pending Inspection Sign-off", color="warning")
        ], width=12)
    ])