from functools import wraps
from dash import ctx
from pydantic import BaseModel
import dash_bootstrap_components as dbc
from dash import html
from pydantic import ValidationError
from typing import Optional, Union, List


def parse_form(
        type_tag: str,
        target_model: type[BaseModel],
        param_name: str = "form_model"
):
    """Decorator to automatically inject a validated Pydantic model into a callback."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Automated extraction matching your unified IDs
            raw_data = {}
            for state_group in ctx.states_list:
                if not state_group: continue
                items = state_group if isinstance(state_group, list) else [state_group]
                for item in items:
                    comp_id = item.get('id')
                    if isinstance(comp_id, dict) and comp_id.get('type') == type_tag:
                        raw_data[comp_id['index']] = item.get('value')

            # Automated conversion using your factory method
            try:
                # If your model implements 'from_form_data', call it directly
                if hasattr(target_model, 'from_form_data'):
                    kwargs[param_name] = target_model.from_form_data(raw_data)
                else:
                    cleaned = {k: (None if v == "" else v) for k, v in raw_data.items()}
                    kwargs[param_name] = target_model(**cleaned)
            except Exception as e:
                # Store the validation exception so the callback function can handle it gracefully
                kwargs[param_name] = e

            return func(*args, **kwargs)

        return wrapper

    return decorator


def create_alert(
        title: str,
        message: Optional[str] = None,
        color: str = "danger",
        exception: Optional[Union[Exception, str]] = None,
        bullet_points: Optional[List[str]] = None
) -> dbc.Alert:
    """
    Unified component factory for all application alerts.
    Handles simple text, exceptions, and validation bullet points automatically.
    """
    children = [html.H5(title, className="alert-heading")]

    # 1. Add secondary text message if provided
    if message:
        children.append(html.P(message, className="mb-0"))

    # 2. Extract and append error strings from standard or validation exceptions
    if exception:
        if isinstance(exception, ValidationError):
            # Automatically unpack Pydantic errors if the raw exception is passed
            points = [err['msg'] for err in exception.errors()]
            children.append(html.Ul([html.Li(pt) for pt in points], className="mt-2 mb-0"))
        else:
            # Handle standard Python Exceptions or raw strings
            err_msg = str(exception)
            children.append(html.P(f"Details: {err_msg}", className="small text-muted mt-2 mb-0"))

    # 3. Handle manual bullet points if explicitly passed instead of an exception
    if bullet_points:
        children.append(html.Ul([html.Li(pt) for pt in bullet_points], className="mt-2 mb-0"))

    return dbc.Alert(children, color=color, className="mt-3")
