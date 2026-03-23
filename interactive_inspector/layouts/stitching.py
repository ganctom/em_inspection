from dash import html
import dash_bootstrap_components as dbc

def layout():
    return dbc.Row([
        dbc.Col([
            html.H3("Step 2: Section Stitching"),
            html.P("This module will utilize ..."),
            dbc.Alert("Status: Pending Inspection Sign-off", color="warning")
        ], width=12)
    ])