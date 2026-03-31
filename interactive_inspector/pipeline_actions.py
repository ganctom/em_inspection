import logging
import threading

from Section_refactored import CoarseStitchConfig
from constants import Task, UI
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params
from parameter_config import StitchingConfig, RegistrationConfig

class PipelineOrchestrator:
    def __init__(self, service):
        self.service = service


    def run_sequential_pipeline(self, section_numbers, selected_tasks, config: StitchingConfig):
        """
        The Master Thread for the UI. Orchestrates tasks across sections.
        """
        # 1. Initialize State
        self.service.stitch_status["active"] = True
        self.service.stitch_status["progress"] = 0
        self.service.stitch_status["error"] = None
        self.service.abort_requested = False

        total_work = len(section_numbers) * len(selected_tasks)
        current_work = 0

        try:
            for task_key in Task.get_master_order():
                if task_key not in selected_tasks:
                    continue

                # Update UI header for the current stage
                self.service.stitch_status["message"] = f"Current Stage: {task_key.upper()}"
                self.service.stitch_status["pending_messages"].append(
                    UI.log_row(f"▶️ Starting {task_key.replace('_', ' ')}", type="info")
                )

                for sec_num in section_numbers:
                    if self.service.abort_requested:
                        self.service.stitch_status["message"] = "Pipeline Aborted by User"
                        self.service.stitch_status["pending_messages"].append(
                            UI.log_row("🛑 Pipeline Aborted", type="warning")
                        )
                        return  # Exit the thread

                    # 2. Execute the specific worker logic
                    # This function handles the Section init and task dispatch
                    self.service.execute_fine_alignment_step(sec_num, task_key, config)

                    # 3. Update Progress
                    current_work += 1
                    # Ensure we don't divide by zero if input is weird
                    progress_pct = int((current_work / total_work) * 100) if total_work > 0 else 0
                    self.service.stitch_status["progress"] = progress_pct

            # 4. Final Success State
            self.service.stitch_status["progress"] = 100
            self.service.stitch_status["message"] = "Pipeline Finished Successfully."
            self.service.stitch_status["pending_messages"].append(
                UI.log_row("🏁 ALL STITCHING TASKS COMPLETE", type="success")
            )

        except Exception as e:
            # Catch unexpected crashes and report to UI
            logging.error(f"Pipeline Failure: {e}")
            self.service.stitch_status["error"] = str(e)
            self.service.stitch_status["message"] = "Pipeline Failed"
            self.service.stitch_status["pending_messages"].append(
                UI.log_row(f"❌ CRITICAL ERROR: Section {sec_num} {e}", type="error")
            )

        finally:
            # 5. KILL SWITCH: This tells the Dash Poller to stop the Interval
            self.service.stitch_status["active"] = False


    def validate_and_prepare(self, range_str, config_path, ui_params_raw) -> tuple[list[int], StitchingConfig]:
        """Logic-only: Validates sections and prepares params."""
        if not self.service.exp_config:
            raise ValueError("No active experiment found.")

        # 1. Section Validation
        first, last = self.service.exp_config.first_sec, self.service.exp_config.last_sec
        if str(range_str).lower() == 'all':
            sec_nums = list(range(first, last + 1))
        else:
            sec_nums_req = parse_section_range(range_str)
            sec_nums = validate_section_numbers(first, last, sec_nums_req)

        if not sec_nums:
            raise ValueError("No valid sections selected.")

        # 2. Param Prep
        hashable_ui = make_hashable_params(ui_params_raw)
        stitching_config = self.service.prepare_stitching_params(
            config_path=config_path,
            ui_params=hashable_ui
        )
        return sec_nums, stitching_config

    def start_coarse_align(self, sec_nums: list[int], reg_cfg: RegistrationConfig):
        """Launches the thread via DataService."""

        reg_params = CoarseStitchConfig(
            overlaps_xy=(tuple(reg_cfg.overlaps_x), tuple(reg_cfg.overlaps_y)),
            min_range=tuple(reg_cfg.min_range),
            min_overlap=int(reg_cfg.min_overlap),
            filter_size=int(reg_cfg.filter_size),
            apply_clahe=True
        )

        thread = threading.Thread(
            target=self.service.run_coarse_align_thread,
            args=(sec_nums, reg_params),
            daemon=True
        )
        thread.start()
        return thread