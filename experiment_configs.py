import logging
from typing import Dict
import yaml

from parameter_config import ExpConfig, AppConfig

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


    def save_user_experiments(self, path_out: str = None) -> None:
        """Saves a clean, human-readable YAML without python-specific tags."""
        raw_data = {
            name: cfg.model_dump()
            for name, cfg in self.app_cfg.projects.items()
        }
        clean_data = self._prepare_for_yaml(raw_data)
        with open(path_out, 'w') as f:
            yaml.safe_dump(clean_data, f, default_flow_style=False, sort_keys=False)
        return None


    def _prepare_for_yaml(self, obj):
        """Recursively converts tuples to lists and Paths to strings."""
        if isinstance(obj, dict):
            return {k: self._prepare_for_yaml(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._prepare_for_yaml(item) for item in obj]
        elif hasattr(obj, '__fspath__'):  # Catches Path objects
            return str(obj)
        return obj


    def load_from_disk(self) -> None:
        """Loads previously saved experiments."""
        p = self.app_cfg.exp_yaml_path
        try:
            with open(p, 'r') as f:
                data = yaml.safe_load(f) or {}
                for name, fields in data.items():
                    self.app_cfg.projects[name] = ExpConfig.model_validate(fields)
        except FileNotFoundError as _:
            logging.warning('There are no previous experiments in the application config file!')


    def get_all(self) -> Dict[str, ExpConfig]:
        return self.app_cfg.projects


def get_experiment_configurations() -> Dict[str, ExpConfig]:
    registry = ExperimentRegistry()
    return registry.get_all()