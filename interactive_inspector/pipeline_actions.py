import logging
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List

from sofima.mesh import IntegrationConfig

from Section_refactored import CoarseStitchConfig, Section
from constants import Task, UI
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params, save_img, get_tile_dicts
from parameter_config import StitchingConfig, RegistrationConfig


class PipelineOrchestrator:
    def __init__(self, dat_service):
        self.ppln_service = dat_service

    def run_sequential_pipeline(
            self,
            section_numbers: List[int],
            selected_tasks,
            config: StitchingConfig,
    ):
        """
        Refactored to maintain Section object state across tasks.
        """
        # 1. Initialize State
        self.ppln_service.stitch_status.update({
            "active": True,
            "progress": 0,
            "error": None,
            "message": "Initializing Pipeline..."
        })
        self.ppln_service.abort_requested = False

        # Determine ordered tasks based on master pipeline logic
        ordered_tasks = [t for t in Task.get_master_order() if t in selected_tasks]

        total_work = len(section_numbers) * len(ordered_tasks)
        current_work = 0
        sec_num = section_numbers[0]
        try:
            for sec_num in section_numbers:
                if self.ppln_service.abort_requested:
                    self._handle_abort()
                    return

                # Initialize the section object
                sec_path = self.ppln_service.inspection.section_dicts.get(sec_num)
                section = Section(sec_path)
                section.tile_dicts = get_tile_dicts(section.path)
                section.read_tile_id_map()

                # INNER LOOP: Tasks (The Operations)
                for task_key in ordered_tasks:
                    if self.ppln_service.abort_requested:
                        self._handle_abort()
                        return

                    self.ppln_service.stitch_status["message"] = f"s{sec_num}: {task_key.upper()}"

                    # 2. Execute worker logic passing the LIVE section object
                    self.ppln_service.execute_fine_alignment_step(
                        section=section,
                        task_name=task_key,
                        config=config
                    )

                    # 3. Update Progress
                    current_work += 1
                    progress_pct = int((current_work / total_work) * 100) if total_work > 0 else 0
                    self.ppln_service.stitch_status["progress"] = progress_pct

            # 4. Final Success State
            self.ppln_service.stitch_status.update({
                "progress": 100,
                "message": "Pipeline Finished Successfully."
            })
            self.ppln_service.stitch_status["pending_messages"].append(
                UI.log_row("🏁 ALL STITCHING TASKS COMPLETE", type="success")
            )

        except Exception as e:
            self._handle_failure(e, sec_num)

        finally:
            self.ppln_service.stitch_status["active"] = False
            del section

    def _handle_abort(self):
        self.ppln_service.stitch_status["message"] = "Pipeline Aborted by User"
        self.ppln_service.stitch_status["pending_messages"].append(
            UI.log_row("🛑 Pipeline Aborted", type="warning")
        )

    def _handle_failure(self, e, sec_num):
        logging.error(f"Pipeline Failure at Section {sec_num}: {e}")
        self.ppln_service.stitch_status.update({
            "error": str(e),
            "message": f"Pipeline Failed at s{sec_num}"
        })
        self.ppln_service.stitch_status["pending_messages"].append(
            UI.log_row(f"❌ CRITICAL ERROR: Section {sec_num} - {e}", type="error")
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
            target=self.ppln_service.run_coarse_align_thread,
            args=(sec_nums, reg_params),
            daemon=True
        )
        thread.start()
        return thread


    def run_parallel_pipeline(
            self,
            section_numbers: List[int],
            selected_tasks,
            stitch_config: StitchingConfig,
    ):
        self.ppln_service.stitch_status["active"] = True
        self.ppln_service.stitch_status["progress"] = 0

        # Ensure tasks are ordered correctly before passing to workers
        ordered_tasks = [t for t in Task.get_master_order() if t in selected_tasks]

        # Limit workers to avoid OOM
        num_workers = min(len(section_numbers), 20)

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_sec = {
                executor.submit(
                    section_worker_wrapper,
                    self.ppln_service.get_sec_path(n),
                    ordered_tasks,
                    stitch_config,
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


def section_worker_wrapper(
        sec_path: str,
        task_keys: list,
        config: StitchingConfig,
):
    """
    Standalone worker. Initializes its own Section instance to ensure
    memory isolation between processes.
    """
    try:
        # 1. Initialize a clean Section instance for this process
        section = Section(sec_path)
        section.tile_dicts = get_tile_dicts(section.path)
        section.read_tile_id_map()
    except NotADirectoryError as _:
        logging.error(f'Failed to load section at path: {sec_path}')
        return None

    try:
        # 2. Dispatch based on Task
        for task_name in task_keys:

            if task_name == Task.COARSE_MESH:
                # Convert Pydantic sub-model to the Frozen Dataclass (IntegrationConfig)
                cfg_yaml = config.mesh_integration_config

                cfg = IntegrationConfig(
                    dt=cfg_yaml.dt,  # dt=cfg_yaml.dt
                    gamma=cfg_yaml.gamma,
                    k0=0.0,  # unused
                    k=cfg_yaml.k,
                    stride=(1, 1),  # unused
                    num_iters=cfg_yaml.num_iters,
                    max_iters=cfg_yaml.max_iters,
                    stop_v_max=cfg_yaml.stop_v_max,
                    dt_max=cfg_yaml.dt_max,
                )

                section.compute_coarse_mesh(conf=cfg, overwrite=True)

            if task_name == Task.MARGIN_MASKS:
                section.build_margin_masks(
                    grid_shape=config.acquisition_config.grid_shape,
                    margin=config.mask_config.mask_margin,
                    rim_size=config.mask_config.rim_size,
                    overwrite=True
                )

            # COMPUTE FINE FLOWS
            if task_name == Task.FINE_FLOWS:
                section.compute_fine_flows(
                    config=config.registration_config,
                    stride=config.mesh_integration_config.stride,
                    masking=True,
                    store=True,
                    overwrite=True,
                    ext=None,
                )

            # COMPUTE FINE MESH
            if task_name == Task.FINE_MESH:
                section.compute_fine_mesh(
                    reg_config=config.registration_config,
                    mesh_config=config.mesh_integration_config
                )

            # WARP SECTION
            if task_name == Task.WARP_SECTION:
                section.warp_section(
                    stride=config.mesh_integration_config.stride,
                    config=config.warp_config,
                )

            # Downscale stitched .zarr section
            if task_name == Task.DOWNSCALE_SECTION:
                if section.image is None:
                    img = section.load_image()
                    if img is None:
                        return sec_path, False, f"FAILED at {task_name}: Image load failed after retries"

                fct = config.pipeline_config.downscale_factor
                print(f"fct: {fct}")
                save_img(
                    path=section.path_thumb,
                    data=section.downscale_section(fct)
                )

        return sec_path, True, "Success"

    except Exception as e:
        logging.error(f"Worker process crash on {sec_path}: {e}")
        return sec_path, False, f"CRITICAL: {str(e)}"

    finally:
        if section is not None:
            try:
                section.close_resource()
                logging.info(f"Resources closed for {sec_path}")
            except Exception as cleanup_err:
                logging.warning(f"Cleanup failed for {sec_path}: {cleanup_err}")

