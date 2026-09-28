import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from .parameter_config import AppConfig, ExpConfig


class ExperimentRegistryError(Exception):
    """Base exception for the entire experiment registry errors"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ExperimentRegistry:
    def __init__(self):
        self.app_cfg = AppConfig()
        self.load_from_disk()

    def add(self, exp_config: ExpConfig) -> None:

        # Project name check
        if exp_config.name in self.app_cfg.projects:
            raise ExperimentRegistryError(
                f"Project name '{exp_config.name}' already exists. Choose a different name!"
            )

        # Processing directory check
        proc_dirs = [exp.proc_dir for exp in self.app_cfg.projects.values()]
        if exp_config.proc_dir in proc_dirs:
            raise ExperimentRegistryError(
                f"Processing directory '{exp_config.proc_dir}' is already used for a different project. "
                f"Choose a different processing directory name!"
            )

        self.app_cfg.projects[exp_config.name] = exp_config
        return None

    def delete(
        self, name: str, quarantine_proc_dir: bool = False
    ) -> Tuple[bool, Optional[str], bool]:
        """Deletes an experiment from the registry and optionally quarantines proc_dir.

        Args:
            name: The unique experiment name to delete.
            quarantine_proc_dir: If True, renames proc_dir to .trash_<name>_<timestamp>.

        Returns:
            A tuple of (success, trashed_path_or_none, proc_dir_existed).
        """
        if name not in self.app_cfg.projects:
            raise ExperimentRegistryError(
                f"Experiment '{name}' does not exist in registry."
            )

        exp = self.app_cfg.projects[name]
        trashed_path = None
        proc_dir_existed = False

        if exp.proc_dir:
            proc_path = Path(exp.proc_dir).resolve()
            acq_path = Path(exp.acq_dir).resolve() if exp.acq_dir else None

            # Safety validations
            if acq_path and proc_path == acq_path:
                raise ExperimentRegistryError(
                    f"Safety Error: proc_dir '{proc_path}' is identical to acq_dir '{acq_path}'."
                )

            if proc_path == Path(proc_path.anchor) or proc_path == Path.home():
                raise ExperimentRegistryError(
                    f"Safety Error: Refusing to quarantine root or home directory '{proc_path}'."
                )

            if proc_path.exists() and proc_path.is_dir():
                proc_dir_existed = True
                if quarantine_proc_dir:
                    target_trash = (
                        proc_path.parent / f".trash_{name}_{int(time.time())}"
                    )
                    try:
                        os.rename(str(proc_path), str(target_trash))
                        trashed_path = str(target_trash)
                        logging.info(
                            f"Quarantined processing directory '{proc_path}' -> '{target_trash}'"
                        )
                    except OSError as e:
                        logging.warning(
                            f"Failed to quarantine proc_dir '{proc_path}': {e}"
                        )
                        raise ExperimentRegistryError(
                            f"Failed to move processing directory to trash: {e}"
                        )
            else:
                proc_dir_existed = False
                if quarantine_proc_dir:
                    logging.warning(
                        f"Processing directory '{proc_path}' does not exist or is not a directory. Skipping quarantine."
                    )

        del self.app_cfg.projects[name]
        self.save_user_experiments()
        return True, trashed_path, proc_dir_existed

    def save_user_experiments(self, path_out: str = None) -> None:
        """Saves a clean, human-readable YAML without python-specific tags."""
        if path_out is None:
            path_out = self.app_cfg.exp_yaml_path
        os.makedirs(os.path.dirname(os.path.abspath(path_out)), exist_ok=True)
        raw_data = {
            name: cfg.model_dump() for name, cfg in self.app_cfg.projects.items()
        }
        clean_data = self._prepare_for_yaml(raw_data)
        with open(path_out, "w") as f:
            yaml.safe_dump(clean_data, f, default_flow_style=False, sort_keys=False)
        return None

    def _prepare_for_yaml(self, obj):
        """Recursively converts tuples to lists and Paths to strings."""
        if isinstance(obj, dict):
            return {k: self._prepare_for_yaml(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._prepare_for_yaml(item) for item in obj]
        elif hasattr(obj, "__fspath__"):  # Catches Path objects
            return str(obj)
        return obj

    def load_from_disk(self) -> None:
        """Loads previously saved experiments. Auto-initializes the file if missing."""
        cfg_path = Path(self.app_cfg.exp_yaml_path)
        if not cfg_path.is_file():
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cfg_path, "w") as f:
                yaml.safe_dump({}, f)

        try:
            with open(cfg_path, "r") as f:
                data = yaml.safe_load(f) or {}
                for name, fields in data.items():
                    self.app_cfg.projects[name] = ExpConfig.model_validate(fields)
        except Exception as e:
            logging.error(f"Error loading experiments from {cfg_path}: {e}")

    @property
    def config_path(self) -> Path:
        """Returns the Path to the active experiments.yaml configuration file."""
        return Path(self.app_cfg.exp_yaml_path)

    def get_all(self) -> Dict[str, ExpConfig]:
        return self.app_cfg.projects


def get_experiments_yaml_path() -> Path:
    """Returns the resolved Path to the active experiments.yaml configuration file."""
    registry = ExperimentRegistry()
    return registry.config_path


def get_experiment_configurations() -> Dict[str, ExpConfig]:
    registry = ExperimentRegistry()
    return registry.get_all()


def delete_experiment_configuration(
    name: str, quarantine_proc_dir: bool = False
) -> Tuple[bool, Optional[str], bool]:
    registry = ExperimentRegistry()
    return registry.delete(name, quarantine_proc_dir=quarantine_proc_dir)


@dataclass(frozen=True)
class PurgeCommandVariant:
    """Represents a context-specific terminal purge command."""

    label: str
    icon: str
    path: str
    command: str


def get_purge_command_variants(path: str) -> List[PurgeCommandVariant]:
    """Generates context-aware terminal purge commands for a quarantined directory.

    If the directory path starts with a client mount prefix (such as macOS '/Volumes/'),
    both local (client mount) and remote (Linux server / cluster / SSH) purge commands are provided.
    If no prefix difference exists, returns a single canonical command.
    """
    path_str = str(path).strip()
    if not path_str:
        return []

    def make_rm_command(p: str) -> str:
        safe_p = p.replace("'", "'\\''")
        return f"rm -rf '{safe_p}'"

    local_cmd = make_rm_command(path_str)

    # 1. Check custom mount mapping from environment if provided
    remote_path = None
    custom_map_str = os.environ.get("EM_REMOTE_MOUNT_MAP", "")
    if custom_map_str:
        try:
            import json

            mapping = json.loads(custom_map_str)
            for k, v in mapping.items():
                if path_str.startswith(k):
                    remote_path = v + path_str[len(k) :]
                    break
        except Exception:
            for pair in custom_map_str.split(","):
                if ":" in pair:
                    k, v = pair.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k and path_str.startswith(k):
                        remote_path = v + path_str[len(k) :]
                        break

    # 2. Check standard macOS /Volumes/ prefix
    if remote_path is None:
        if path_str.startswith("/Volumes/"):
            remote_path = path_str[len("/Volumes") :]
        else:
            storage_prefix_mac = os.environ.get(
                "EM_STORAGE_PREFIX_MAC", "/Volumes/storage/"
            )
            storage_base = os.environ.get("EM_STORAGE_BASE", "/storage/")
            if storage_prefix_mac in path_str:
                remote_path = path_str.replace(storage_prefix_mac, storage_base)

    # 3. Assemble variants
    variants: List[PurgeCommandVariant] = []

    if remote_path and remote_path != path_str:
        variants.append(
            PurgeCommandVariant(
                label="macOS / Client Mount",
                icon="bi bi-apple",
                path=path_str,
                command=local_cmd,
            )
        )
        variants.append(
            PurgeCommandVariant(
                label="Linux Server / Cluster (SSH)",
                icon="bi bi-terminal",
                path=remote_path,
                command=make_rm_command(remote_path),
            )
        )
    else:
        variants.append(
            PurgeCommandVariant(
                label="Terminal Purge Command",
                icon="bi bi-terminal",
                path=path_str,
                command=local_cmd,
            )
        )

    return variants


if __name__ == "__main__":
    print(get_experiments_yaml_path())
