import threading

from constants import Task
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params
from parameter_config import StitchingConfig, RegistrationConfig

class PipelineOrchestrator:
    def __init__(self, service):
        self.service = service

    def run_sequential_pipeline(self, section_numbers, selected_tasks, config: StitchingConfig):
        """
        The Master Thread for the UI.
        """

        total_work = len(section_numbers) * len(selected_tasks)
        current_work = 0

        for task_key in Task.get_master_order():
            if task_key not in selected_tasks:
                continue

            self.service.stitch_status["message"] = f"Running Stage: {task_key}"

            # Standard sequential loop
            for sec_num in section_numbers:
                if self.service.abort_requested: break

                self.service.execute_fine_alignment_step(sec_num, task_key, config)

                current_work += 1
                self.service.stitch_status["progress"] = int((current_work / total_work) * 100)



    # def _run_parallel_task(self, task_key, section_numbers, config):
    #     """Mimics your fine_align_sections_multiproc logic."""
    #     import multiprocessing
    #
    #     # We use a partial to lock in the task and config
    #     worker = partial(self.service.execute_fine_alignment_step,
    #                      task_name=task_key, config=config)
    #
    #     num_procs = config.warp_config.warp_parallelism
    #     with multiprocessing.Pool(processes=num_procs) as pool:
    #         # We use imap to track progress
    #         for _ in pool.imap_unordered(worker, section_numbers):
    #             if self.service.abort_requested:
    #                 pool.terminate()
    #                 break


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

        reg_params = dict(
            overlaps_xy=tuple((tuple(reg_cfg.overlaps_x), tuple(reg_cfg.overlaps_y))),
            min_range=tuple(reg_cfg.min_range),
            min_overlap=int(reg_cfg.min_overlap),
            filter_size=int(reg_cfg.filter_size),
            clahe=True,
            overwrite_cxcy=True
        )

        thread = threading.Thread(
            target=self.service.run_coarse_align_thread,
            args=(sec_nums, reg_params),
            daemon=True
        )
        thread.start()
        return thread