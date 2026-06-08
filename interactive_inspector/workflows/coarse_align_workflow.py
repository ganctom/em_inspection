import os
import threading
import dash
from dash import no_update
import yaml
from pydantic import ValidationError

from constants import UI
import parameter_config as pcfg
from data_service import service, orchestrator


class CoarseAlignManager:
    """
    Encapsulates Pydantic model serialization, disk IO bindings, asynchronous worker
    threads, and polling state validation loops for microscope alignment pipelines.
    """

    @classmethod
    def load_yaml_config(cls, file_path: str, layout_ids_lists: tuple[list[dict], ...]) -> list[list]:
        """
        Parses a YAML config from disk and maps it dynamically to layout ID sequences
        by evaluating their inner type and index values.
        """
        if not file_path:
            raise ValueError("Please enter a valid path")

        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)

        cfg = pcfg.StitchingConfig(**data)
        service.stitch_config = cfg
        service.reg_config = cfg.registration_config

        to_csv = lambda val: ", ".join(map(str, val)) if isinstance(val, (list, tuple)) else val

        flat_pool = {
            "output_dir": cfg.output_dir,
            "start_section": cfg.start_section,
            "end_section": cfg.end_section,
            **{k: to_csv(v) for k, v in cfg.acquisition_config.model_dump().items()},
            **{k: to_csv(v) for k, v in cfg.registration_config.model_dump().items()},
            **cfg.mesh_integration_config.model_dump(),
            **{k: ([v] if isinstance(v, bool) else v) for k, v in cfg.warp_config.model_dump().items()},
            **cfg.mask_config.model_dump()
        }

        mapped_output_groups = []
        for id_list in layout_ids_lists:
            group_values = [flat_pool.get(comp['index'], no_update) for comp in id_list]
            mapped_output_groups.append(group_values)

        return mapped_output_groups


    @classmethod
    def save_yaml_config(cls, n_clicks: int, path: str, stitch_config: pcfg.StitchingConfig) -> str:
        """Commits a pre-validated and hydrated StitchingConfig model instance to disk."""
        if not path:
            return "Error: No path specified."

        if not isinstance(stitch_config, pcfg.StitchingConfig):
            return f"Save failed: Invalid configuration data object type passed."

        try:
            stitch_config.acquisition_config = service.acq_config
            pcfg.save_to_disk(stitch_config, path)
            return f"Successfully saved to {path}."
        except Exception as e:
            return f"Save failed: {str(e)}"


    @classmethod
    def build_and_serialize_global_store(cls, stitch_config: pcfg.StitchingConfig) -> dict:
        """
        Updates the runtime service layer singleton using model-copying semantics
        and serializes the outcome into a primitive dictionary.
        """
        # A simple type guard ensures headless scripts/tests don't bypass type expectations
        if not isinstance(stitch_config, pcfg.StitchingConfig):
            raise TypeError("Expected fully hydrated StitchingConfig instance.")

        # 1. Update the state provider cleanly
        new_cfg = service.stitch_config.model_copy(
            update={
                "registration_config": stitch_config.registration_config,
                "mesh_integration_config": stitch_config.mesh_integration_config,
                "warp_config": stitch_config.warp_config,
                "mask_config": stitch_config.mask_config,
                "output_dir": stitch_config.output_dir,
                "start_section": stitch_config.start_section,
                "end_section": stitch_config.end_section
            },
            deep=True
        )

        # 2. Sync core runtime reference
        service.stitch_config = new_cfg

        # 3. Return primitive structures suitable for dcc.Store transit
        return new_cfg.model_dump()


    @classmethod
    def run_coarse_alignment_workflow(
            cls,
            range_str: str,
            config_path: str,
            stitch_config: pcfg.StitchingConfig
    ) -> tuple[list[int], any]:  # Returns raw data tokens instead of UI components
        """
        Validates the schema context and spins up the coarse alignment thread pipeline.
        Passes up exceptions and validation tokens cleanly to the caller.
        """
        if isinstance(stitch_config, ValidationError):
            raise stitch_config

        reg_cfg = stitch_config.registration_config
        sec_nums, validated_cfg = orchestrator.validate_and_prepare(
            range_str, config_path, stitch_config
        )

        orchestrator.start_coarse_align(sec_nums, reg_cfg)
        return sec_nums, reg_cfg.coarse_params


    @classmethod
    def execute_offset_backup(cls) -> None:
        """
        Validates business rules and dispatches backup generation logic via worker threads.
        Raises ValueError if infrastructure prerequisites are unmet.
        """
        if not service.exp_config:
            raise ValueError("No active experiment found.")

        threading.Thread(
            target=service.run_offsets_backup_thread,
            kwargs={"overwrite": True},
            daemon=True
        ).start()

    @classmethod
    def poll_unified_progress(
            cls,
            raw_log_history: list[str]
    ) -> tuple[int, str, bool, list[str]]:
        """
        Monitors progress state headlessly.
        Returns:
            progress_value (int)
            status_message (str)
            disable_interval (bool)
            updated_raw_logs (list[str])
        """
        if service.backup_status["active"] or service.backup_status["progress"] > 0:
            status = service.backup_status
            is_backup = True
        else:
            status = service.coarse_align_status
            is_backup = False

        logs = list(raw_log_history) if isinstance(raw_log_history, list) else []

        # 1. Handle explicit error states
        if status.get("error"):
            logs.append(f"🛑 ERROR: {status['error']}")
            return 0, "Failed", True, logs

        prog = status.get("progress", 0)
        msg = status.get("message", "")

        # 2. Check for duplicate messages natively using pure string comparison
        last_msg = logs[-1] if logs else ""
        if msg and msg != last_msg:
            logs.append(msg)

        # 3. Handle successful operation cleanup
        if not status.get("active") and prog >= 100:
            if is_backup:
                service.backup_status["progress"] = 0
            else:
                service.coarse_align_status["progress"] = 0
            return 100, "Operation Finished.", True, logs

        return prog, msg, False, logs


    @classmethod
    def is_backup_ready(cls) -> bool:
        """
        Evaluates system infrastructure status to determine if a coarse
        offset backup sequence can be executed.
        """
        return service.exp_config is not None


