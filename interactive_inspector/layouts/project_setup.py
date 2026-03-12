from dash import html
import dash_bootstrap_components as dbc

def layout():
    return dbc.Row([
        dbc.Col([
            html.H3("Step 1: Project Definition & Parsing"),
            html.P("This module will handle cxyz structure parsing and metadata initialization."),
            dbc.Alert("Status: Under Construction", color="info")
        ], width=12)
    ])