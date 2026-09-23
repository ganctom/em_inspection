import threading
from dash import no_update
from dash.exceptions import PreventUpdate

from constants import UI, MSG
from data_service import service, orchestrator
from inspection_refactored import init_specific_section_dirs
from parameter_config import StitchingConfig


class StitchingWorkflowManager:
    """
    Orchestration layer isolating pipeline thread management, asynchronous state updates,
    and log formatting from Dash presentation callbacks.
    """

    @classmethod
    def run_pipeline(
        cls,
        n_clicks: int,
        parallel_value: any,
        range_str: str,
        selected_steps: list,
        config_path: str,
        scl_fct: float,
        settings_data: dict,
    ):
        """Validates configuration parameters, initializes directories, and dispatches processing threads."""
        if not n_clicks:
            raise PreventUpdate

        if not selected_steps:
            return [UI.log_row(MSG.NO_STEPS_ERROR, type="error")], 0, True

        if not isinstance(parallel_value, list):
            is_par = bool(parallel_value)
        else:
            is_par = "parallel" in parallel_value

        stitch_config = StitchingConfig(**settings_data)
        stitch_config.pipeline_config.downscale_factor = float(scl_fct)

        try:
            sec_nums, final_config = orchestrator.validate_and_prepare(
                range_str, config_path, stitch_config
            )
        except Exception as e:
            return [UI.log_row(MSG.SETUP_ERROR.format(error=e), type="error")], 0, True

        # Decoupled Domain Operations
        init_specific_section_dirs(service.inspection, sec_nums)

        target_method = (
            orchestrator.run_parallel_pipeline
            if is_par
            else orchestrator.run_sequential_pipeline
        )

        # Thread isolation proxy
        threading.Thread(
            target=target_method,
            args=(sec_nums, selected_steps, final_config),
            daemon=True,
        ).start()

        mode_str = MSG.MODE_PARALLEL if is_par else MSG.MODE_SEQUENTIAL
        tsk_lbl = MSG.format_tasks(selected_steps)

        init_log = [
            UI.log_row(MSG.PPLN_START.format(mode=mode_str), type="info"),
            UI.log_row(MSG.PPLN_TASKS.format(tasks=tsk_lbl)),
            UI.log_row(
                MSG.PPLN_SCOPE.format(
                    count=len(sec_nums), first=sec_nums[0], last=sec_nums[-1]
                )
            ),
        ]

        if is_par:
            init_log.append(UI.log_row(MSG.PARALLEL_WARN, type="warning"))

        init_log.append(UI.log_row(MSG.PPLN_DIVIDER))
        return init_log, 2, False

    @classmethod
    def sync_progress(cls, n_intervals: int, current_logs: list):
        """Pulls internal tracking frames from memory buffers to construct updated log chains."""
        status = service.stitch_status

        new_logs = status.get("pending_messages", [])
        status["pending_messages"] = []  # Clear atomic state bridge context

        updated_logs = (current_logs or []) + new_logs
        progress = status.get("progress", 0)
        msg = status.get("message", "Processing...")
        is_active = status.get("active", False)

        if not is_active and progress >= 100:
            return updated_logs, 100, False, False, True, f"✅ {msg}"

        if not is_active and status.get("error"):
            return (
                updated_logs,
                progress,
                False,
                False,
                True,
                f"❌ Error: {status['error']}",
            )

        return updated_logs, progress, True, True, False, f"⏳ {msg}"

    @classmethod
    def locate_missing_indices(cls, n_clicks: int):
        """Scans underlying disk resources for target coverage fragmentation loops."""
        if not n_clicks:
            return no_update

        missing_indices = service.get_missing_stitched_sections()
        if not missing_indices:
            return [
                UI.log_row(
                    "✨ No missing sections found. Dataset is complete.", type="success"
                )
            ]

        msg = (
            f"Found {len(missing_indices)} missing sections: {missing_indices[:10]}..."
        )
        return [UI.log_row(msg, type="warning")]
