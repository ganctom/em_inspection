import threading

from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params
from parameter_config import StitchingConfig, RegistrationConfig


class PipelineOrchestrator:
    def __init__(self, service):
        self.service = service

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