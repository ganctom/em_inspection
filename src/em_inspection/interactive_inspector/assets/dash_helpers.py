from functools import wraps
from dash import ctx
from pydantic import BaseModel
import dash_bootstrap_components as dbc
from dash import html
from pydantic import ValidationError
from typing import Optional, Union, List

from constants import UIConstants
from parameter_config import RegistrationConfig, MeshIntegrationConfig, WarpConfigStitching, MaskingConfig, \
    StitchingConfig, AcquisitionConfig


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

            try:
                if hasattr(target_model, 'from_form_data'):
                    kwargs[param_name] = target_model.from_form_data(raw_data)
                else:
                    cleaned = {k: (None if v == "" else v) for k, v in raw_data.items()}
                    kwargs[param_name] = target_model(**cleaned)
            except Exception as e:
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


def parse_stitch_configuration(param_name: str = "stitch_config"):
    """
    Unified decorator that automatically harvests multiple Dash pattern-matching
    type tags, hydrates them into a composite StitchingConfig target model, and
    injects the resulting instance as a named keyword argument.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 1. Initialize payload storage matching known type tags
            form_payloads = {
                UIConstants.TYPE_REG_CFG_FIELD: {},
                UIConstants.TYPE_ACQ_CFG_FIELD: {},
                UIConstants.TYPE_MESH_CFG_FIELD: {},
                UIConstants.TYPE_WARP_CFG_FIELD: {},
                UIConstants.TYPE_MASK_CFG_FIELD: {}
            }

            # 2. Linear payload harvest loop
            for state_group in ctx.states_list:
                if not state_group:
                    continue
                items = state_group if isinstance(state_group, list) else [state_group]
                for item in items:
                    comp_id = item.get('id')
                    if isinstance(comp_id, dict):
                        id_type = comp_id.get('type')
                        if id_type in form_payloads:
                            form_payloads[id_type][comp_id['index']] = item.get('value')

            try:
                # 3. Data Cleansing & Normalization Utilities
                def clean(d):
                    return {k: v for k, v in d.items() if v != "" and v is not None}

                def extract_bool(val):
                    return True in val if isinstance(val, list) else bool(val)

                # --- Section Normalization ---

                # Registration/Stitching Context
                raw_reg = form_payloads[UIConstants.TYPE_REG_CFG_FIELD]
                if "clahe" in raw_reg:
                    raw_reg["clahe"] = extract_bool(raw_reg["clahe"])
                reg_instance = RegistrationConfig.from_form_data(raw_reg)

                # Elastic Mesh Solver Context
                raw_mesh = clean(form_payloads[UIConstants.TYPE_MESH_CFG_FIELD])
                for field in ("prefer_orig_order", "remove_drift"):
                    if field in raw_mesh:
                        raw_mesh[field] = extract_bool(raw_mesh[field])
                mesh_instance = MeshIntegrationConfig(**raw_mesh)

                # Image Rendering Warp Context
                raw_warp = clean(form_payloads[UIConstants.TYPE_WARP_CFG_FIELD])
                if "use_clahe" in raw_warp:
                    raw_warp["use_clahe"] = extract_bool(raw_warp["use_clahe"])
                warp_instance = WarpConfigStitching(**raw_warp)

                # Boundary Masking Context
                mask_instance = MaskingConfig(**clean(form_payloads[UIConstants.TYPE_MASK_CFG_FIELD]))

                # Acquisition Context & Top-Level Field Separation
                raw_acq = clean(form_payloads[UIConstants.TYPE_ACQ_CFG_FIELD])

                # Extract pipeline fields from the dictionary so they don't corrupt AcquisitionConfig
                top_level_output_dir = raw_acq.pop("output_dir", "")
                top_level_start = int(raw_acq.pop("start_section", 0) or 0)
                top_level_end = int(raw_acq.pop("end_section", 0) or 0)

                acq_instance = AcquisitionConfig(**raw_acq)

                # 4. Compose Master Model Context
                payload = StitchingConfig(
                    output_dir=top_level_output_dir,
                    acquisition_config=acq_instance,
                    start_section=top_level_start,
                    end_section=top_level_end,
                    registration_config=reg_instance,
                    mesh_integration_config=mesh_instance,
                    warp_config=warp_instance,
                    mask_config=mask_instance
                )

            except Exception as e:
                payload = e

            # 5. Route the unified model context safely without risk of UnboundLocalError
            kwargs[param_name] = payload

            # Forward the original positional arguments unaltered to satisfy the callback signature
            return func(*args, **kwargs)

        return wrapper
    return decorator