import logging
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from sofima.mesh import IntegrationConfig

from Section_refactored import CoarseStitchConfig, Section
from constants import Task, UI
from inspection_utils_refactor import parse_section_range, validate_section_numbers, make_hashable_params, save_img
from parameter_config import StitchingConfig, RegistrationConfig, AcquisitionConfig, ExpConfig


class PipelineOrchestrator:
    def __init__(self, dat_service):
        self.ppln_service = dat_service


    def run_sequential_pipeline(
            self,
            section_numbers,
            selected_tasks,
            config: StitchingConfig,
    ):
        """
        The Master Thread for the UI. Orchestrates tasks across sections.
        """
        # 1. Initialize State
        self.ppln_service.stitch_status["active"] = True
        self.ppln_service.stitch_status["progress"] = 0
        self.ppln_service.stitch_status["error"] = None
        self.ppln_service.abort_requested = False

        total_work = len(section_numbers) * len(selected_tasks)
        current_work = 0

        try:
            for task_key in Task.get_master_order():
                if task_key not in selected_tasks:
                    continue

                # Update UI header for the current stage
                self.ppln_service.stitch_status["message"] = f"Current Stage: {task_key.upper()}"
                self.ppln_service.stitch_status["pending_messages"].append(
                    UI.log_row(f"▶️ Starting {task_key.replace('_', ' ')}", type="info")
                )

                for sec_num in section_numbers:
                    if self.ppln_service.abort_requested:
                        self.ppln_service.stitch_status["message"] = "Pipeline Aborted by User"
                        self.ppln_service.stitch_status["pending_messages"].append(
                            UI.log_row("🛑 Pipeline Aborted", type="warning")
                        )
                        return  # Exit the thread

                    # 2. Execute the specific worker logic
                    # This function handles the Section init and task dispatch
                    self.ppln_service.execute_fine_alignment_step(sec_num, task_key, config)

                    # 3. Update Progress
                    current_work += 1
                    # Ensure we don't divide by zero if input is weird
                    progress_pct = int((current_work / total_work) * 100) if total_work > 0 else 0
                    self.ppln_service.stitch_status["progress"] = progress_pct

            # 4. Final Success State
            self.ppln_service.stitch_status["progress"] = 100
            self.ppln_service.stitch_status["message"] = "Pipeline Finished Successfully."
            self.ppln_service.stitch_status["pending_messages"].append(
                UI.log_row("🏁 ALL STITCHING TASKS COMPLETE", type="success")
            )

        except Exception as e:
            # Catch unexpected crashes and report to UI
            logging.error(f"Pipeline Failure: {e}")
            self.ppln_service.stitch_status["error"] = str(e)
            self.ppln_service.stitch_status["message"] = "Pipeline Failed"
            self.ppln_service.stitch_status["pending_messages"].append(
                UI.log_row(f"❌ CRITICAL ERROR: Section {sec_num} {e}", type="error")
            )

        finally:
            # 5. KILL SWITCH: This tells the Dash Poller to stop the Interval
            self.ppln_service.stitch_status["active"] = False


    def validate_and_prepare(
            self,
            range_str,
            config_path,
            ui_params_raw: dict | None = None
    ) -> tuple[list[int], StitchingConfig]:

        """Logic-only: Validates sections and prepares params."""
        if not self.ppln_service.exp_config:
            raise ValueError("No active experiment found.")

        # 1. Section Validation
        first, last = self.ppln_service.exp_config.first_sec, self.ppln_service.exp_config.last_sec
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
            section_numbers,
            selected_tasks,
            stitch_config: StitchingConfig,
    ):
        self.ppln_service.stitch_status["active"] = True
        self.ppln_service.stitch_status["progress"] = 0

        if not self.ppln_service.service_initialized:
            self.ppln_service.initialize_experiment_from_config(stitch_config.exp_config)


        # Limit workers to avoid OOM (Out of Memory)
        num_workers = min(len(section_numbers), 20)

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            # Submit all sections as individual futures
            future_to_sec = {
                executor.submit(
                    section_worker_wrapper,
                    self.ppln_service.get_sec_path(n),
                    selected_tasks,
                    stitch_config,
                )
                : n for n in section_numbers
            }

            for i, future in enumerate(as_completed(future_to_sec)):
                sec_num, success, message = future.result()

                if success:
                    self.ppln_service.stitch_status["pending_messages"].append(
                        UI.log_row(f"✅ Section {sec_num} finished", type="success")
                    )
                else:
                    self.ppln_service.stitch_status["pending_messages"].append(
                        UI.log_row(f"❌ Section {sec_num} failed: {message}", type="error")
                    )

                # Update Progress based on completed sections
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
        section.feed_section_data()
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

            # Compute flows between overlaps
            if task_name == Task.FINE_FLOWS:
                section.compute_fine_flows(
                    ff_config=config.fine_flows_config,
                    masking=True,
                    store=True,
                    overwrite=True,
                    ext=None,
                )


            if task_name == Task.WARP_SECTION:
                wconfig = config.warp_config

                clahe_kwargs = dict(
                    kernel_size=wconfig.kernel_size,
                    clip_limit=wconfig.clip_limit,
                    nbins=wconfig.nbins
                )

                section.warp_section(
                    stride=config.fine_flows_config.stride,
                    margin=wconfig.margin,
                    use_clahe=wconfig.use_clahe,
                    clahe_kwargs=clahe_kwargs,
                    parallelism=wconfig.warp_parallelism,
                    margin_masking=wconfig.margin_masking,
                    zarr_store=True,
                )

            # Downscale stitched .zarr section
            if task_name == Task.DOWNSCALE:
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