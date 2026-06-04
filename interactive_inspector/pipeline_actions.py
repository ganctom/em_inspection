import gc
from abc import ABC, abstractmethod
from collections.abc import Callable
import logging
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Final

from sofima.mesh import IntegrationConfig

from Section_refactored import CoarseStitchConfig, Section
from constants import Task, UI
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params, save_img, get_tile_dicts
from parameter_config import StitchingConfig, RegistrationConfig

# Compile-time constants
RESOURCE_INIT: Final[str] = "RESOURCE_INIT"


class TaskHandler(ABC):
    @abstractmethod
    def run(self, section: Section, config: StitchingConfig) -> None:
        """Standard execution interface for all pipeline steps."""
        pass

class TaskRegistry:
    _registry: dict[Task, TaskHandler] = {}

    @classmethod
    def register(cls, task_key: Task):
        def decorator(handler_cls: type[TaskHandler]):
            cls._registry[task_key] = handler_cls()
            return handler_cls
        return decorator

    @classmethod
    def execute(cls, task_key: Task, section: Section, config: StitchingConfig):
        if handler := cls._registry.get(task_key):
            handler.run(section, config)
        else:
            raise NotImplementedError(f"No handler registered for {task_key}")


@TaskRegistry.register(Task.COARSE_MESH)
class CoarseMeshHandler(TaskHandler):
    def run(self, section: Section, config: StitchingConfig) -> None:

        yaml_config = config.mesh_integration_config

        cfg = IntegrationConfig(
            dt=yaml_config.dt,
            gamma=yaml_config.gamma,
            k0=0.0,  # unused
            k=yaml_config.k,
            stride=(1, 1),  # unused
            num_iters=yaml_config.num_iters,
            max_iters=yaml_config.max_iters,
            stop_v_max=yaml_config.stop_v_max,
            dt_max=yaml_config.dt_max,
        )
        section.compute_coarse_mesh(conf=cfg, overwrite=True)

@TaskRegistry.register(Task.MARGIN_MASKS)
class MarginMasksHandler(TaskHandler):
    def run(self, section: Section, config: StitchingConfig):
        section.build_margin_masks(
            grid_shape=config.acquisition_config.grid_shape,
            margin=config.mask_config.mask_margin,
            rim_size=config.mask_config.rim_size,
            overwrite=True
        )

@TaskRegistry.register(Task.FINE_FLOWS)
class FineFlowsHandler(TaskHandler):
    def run(self, section: Section, config: StitchingConfig):
        section.compute_fine_flows(
            config=config.registration_config,
            stride=config.mesh_integration_config.stride,
            masking=True,
            store=True,
            overwrite=True,
            ext=None,
        )

@TaskRegistry.register(Task.FINE_MESH)
class FineMeshHandler(TaskHandler):
    def run(self, section: Section, config: StitchingConfig):
        section.compute_fine_mesh(
            reg_config=config.registration_config,
            mesh_config=config.mesh_integration_config
        )

@TaskRegistry.register(Task.WARP_SECTION)
class WarpSectionHandler(TaskHandler):
    def run(self, section: Section, config: StitchingConfig):
        section.warp_section(
            stride=config.mesh_integration_config.stride,
            config=config.warp_config,
        )

@TaskRegistry.register(Task.DOWNSCALE_SECTION)
class DownscaleHandler(TaskHandler):
    def run(self, section, config):
        self._ensure_image_loaded(section)
        fct = config.pipeline_config.downscale_factor
        save_img(path=section.path_thumb, data=section.downscale_section(fct))

    @staticmethod
    def _ensure_image_loaded(section: Section):
        if section.image is None:
            section.load_image()


# Custom exception to handle controlled worker failures
class RuntimePipelineError(Exception):
    """Raised when a section worker pipeline task fails downstream."""
    pass


class PipelineOrchestrator:
    def __init__(self, dat_service):
        self.ppln_service = dat_service

    def run_sequential_pipeline(
            self,
            section_numbers: list[int],
            selected_tasks: list[Task],
            config: StitchingConfig,
    ):
        self.ppln_service.stitch_status.update({
            "active": True,
            "progress": 0,
            "error": None,
            "message": "Initializing Pipeline..."
        })
        self.ppln_service.abort_requested = False

        ordered_tasks = [t for t in Task.get_master_order() if t in selected_tasks]
        total_work = len(section_numbers) * len(ordered_tasks)
        current_work = 0

        # Track loop/error states safely across all execution blocks
        pipeline_failed = False
        last_error_msg = ""
        sec_num = None

        def handle_task_success(sec_path: str, task_name: str):
            nonlocal current_work
            current_work += 1
            s_id = Path(sec_path).name
            self.ppln_service.stitch_status["pending_messages"].append(
                UI.log_row(f"✅ [{s_id}] {task_name} complete", type="info")
            )
            progress_pct = int((current_work / total_work) * 100) if total_work > 0 else 0
            self.ppln_service.stitch_status["progress"] = progress_pct

        try:
            for sec_num in section_numbers:
                if self.ppln_service.abort_requested:
                    self._handle_abort()
                    return

                section_path = self.ppln_service.get_sec_path(sec_num)
                if not section_path:
                    continue

                self.ppln_service.stitch_status["message"] = f"s{sec_num}: Processing tasks..."

                _, success, message = section_worker_wrapper(
                    section_path=section_path,
                    task_keys=ordered_tasks,
                    config=config,
                    on_task_complete=handle_task_success
                )

                if not success:
                    self.ppln_service.stitch_status["pending_messages"].append(
                        UI.log_row(f"❌ [{Path(section_path).name}] {message}", type="error")
                    )
                    pipeline_failed = True
                    last_error_msg = message
                    break

            if pipeline_failed:
                self.ppln_service.stitch_status.update({
                    "error": last_error_msg,
                    "message": f"Pipeline Failed at s{sec_num}"
                })
                self.ppln_service.stitch_status["pending_messages"].append(
                    UI.log_row(f"PIPELINE HALTED AT SECTION {sec_num}", type="error")
                )
            else:
                self.ppln_service.stitch_status.update({
                    "progress": 100,
                    "message": "Pipeline Finished Successfully."
                })
                self.ppln_service.stitch_status["pending_messages"].append(
                    UI.log_row("🏁 ALL STITCHING TASKS COMPLETE", type="success")
                )

        except Exception as e:
            self._handle_failure(e, sec_num if sec_num is not None else "UNKNOWN")

        finally:
            self.ppln_service.stitch_status["active"] = False


    def run_parallel_pipeline(
            self,
            section_numbers: list[int],
            selected_tasks: list[Task],
            stitch_config: StitchingConfig,
    ):
        """
        Executes sections in parallel. Fixes the unfilled ParamSpec warning.
        """
        self.ppln_service.stitch_status["active"] = True
        self.ppln_service.stitch_status["progress"] = 0

        ordered_tasks = [t for t in Task.get_master_order() if t in selected_tasks]
        num_workers = min(len(section_numbers), 20)

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_sec = {
                executor.submit(
                    section_worker_wrapper,
                    self.ppln_service.get_sec_path(n),
                    ordered_tasks,
                    stitch_config,
                    None  # Fills the on_task_complete positional/keyword slot
                ): n for n in section_numbers
            }

            for i, future in enumerate(as_completed(future_to_sec)):
                sec_num = future_to_sec[future]
                try:
                    res = future.result()
                    if res is None:
                        success, message = False, "Worker returned None"
                    else:
                        _, success, message = res

                    if success:
                        self.ppln_service.stitch_status["pending_messages"].append(
                            UI.log_row(f"✅ Section {sec_num} finished", type="success")
                        )
                    else:
                        self.ppln_service.stitch_status["pending_messages"].append(
                            UI.log_row(f"❌ Section {sec_num} failed: {message}", type="error")
                        )
                except Exception as e:
                    self.ppln_service.stitch_status["pending_messages"].append(
                        UI.log_row(f"💥 Section {sec_num} crashed: {e}", type="error")
                    )

                self.ppln_service.stitch_status["progress"] = int(((i + 1) / len(section_numbers)) * 100)

        self.ppln_service.stitch_status["active"] = False


    def _handle_abort(self):
        self.ppln_service.stitch_status["message"] = "Pipeline Aborted by User"
        self.ppln_service.stitch_status["pending_messages"].append(
            UI.log_row("🛑 Pipeline Aborted", type="warning")
        )


    def _handle_failure(self, e, sec_num):
        if isinstance(e, RuntimePipelineError):
            error_details = str(e)
        else:
            error_details = f"Unexpected runtime crash: {str(e)}"

        logging.error(f"Pipeline Failure at Section {sec_num}: {error_details}")
        self.ppln_service.stitch_status.update({
            "error": error_details,
            "message": f"Pipeline Failed at s{sec_num}"
        })
        self.ppln_service.stitch_status["pending_messages"].append(
            UI.log_row(f"❌ CRITICAL ERROR: Section {sec_num} - {error_details}", type="error")
        )


    def validate_and_prepare(
            self,
            range_str: str,
            config_path,
            ui_params_raw: dict | None = None
    ) -> tuple[list[int], StitchingConfig]:

        """Logic-only: Validates sections and prepares params."""
        if not self.ppln_service.exp_config:
            raise ValueError("No active experiment found.")

        # 1. Section Validation
        first = self.ppln_service.exp_config.first_sec
        last = self.ppln_service.exp_config.last_sec
        if str(range_str).lower() == 'all':
            sec_nums = list(range(first, last + 1))
        else:
            sec_nums_req = parse_section_range(range_str)
            sec_nums = validate_section_numbers(first, last, sec_nums_req)

        if not sec_nums:
            raise ValueError("No valid sections selected.")

        # 2. Param Prep
        hashable_ui = make_hashable_params(ui_params_raw)

        stitching_config = self.ppln_service.prepare_stitching_params(
            config_path=config_path,
            ui_params=hashable_ui
        )
        return sec_nums, stitching_config


    def start_coarse_align(
            self,
            sec_nums: list[int],
            reg_cfg: RegistrationConfig
    ):
        """Launches the thread via DataService."""

        reg_params = CoarseStitchConfig(
            overlaps_xy=(tuple(reg_cfg.overlaps_x), tuple(reg_cfg.overlaps_y)),
            min_range=tuple(reg_cfg.min_range),
            min_overlap=int(reg_cfg.min_overlap),
            filter_size=int(reg_cfg.filter_size),
            apply_clahe=reg_cfg.clahe,
            clip_limit=reg_cfg.clip_limit,
            kernel_size=reg_cfg.kernel_size,
        )

        thread = threading.Thread(
            target=self.ppln_service.run_coarse_align_thread,
            args=(sec_nums, reg_params),
            daemon=True
        )
        thread.start()
        return thread


def load_section(path: str | Path) -> Section:
    section = Section(Path(path))
    section.tile_dicts = get_tile_dicts(section.path)
    section.read_tile_id_map()
    return section


def section_worker_wrapper(
        section_path: str,
        task_keys: list[Task],
        config: StitchingConfig,
        on_task_complete: Callable[[str, str], None] | None = None,
) -> tuple[str, bool, str]:

    section = None
    task_name: str = RESOURCE_INIT

    try:
        logging.debug("[%s] Initializing section resources", section_path)
        section = load_section(section_path)

        if section is None:
            return section_path, False, "CRITICAL: load_section returned None"

        for task in task_keys:
            task_name = getattr(task, "name", str(task))
            logging.info("[%s] Starting task: %s", section_path, task_name)
            TaskRegistry.execute(task, section, config)
            logging.debug("[%s] Completed task: %s", section_path, task_name)

            if on_task_complete:
                on_task_complete(section_path, task_name)

        return section_path, True, "Success"

    except Exception as e:
        error_msg = f"Failure @ Task [{task_name}]: {e}"
        logging.exception("[%s] %s", section_path, error_msg)
        return section_path, False, error_msg

    finally:
        if section is not None:
            try:
                section.close_resource()
            except Exception as cleanup_err:
                msg = "[%s] Resource cleanup leaked: %s"
                logging.critical(msg, section_path, cleanup_err, exc_info=True)
        gc.collect()
