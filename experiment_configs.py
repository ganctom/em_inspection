from pathlib import Path
from typing import Dict
import yaml

from parameter_config import ExpConfig, AppConfig


class ExperimentRegistry:
    def __init__(self):
        self.app_cfg = AppConfig()
        self.load_from_disk()

    def add(self, name, acq_dir, proc_dir, grid_num, grid_shape, first_sec, last_sec, px, ct):

        config = ExpConfig(
            name=name,
            acq_dir=acq_dir,
            proc_dir=proc_dir,
            grid_num=grid_num,
            grid_shape=grid_shape,
            first_sec=first_sec,
            last_sec=last_sec,
            pixel_size=px,
            cut_thickness=ct,
        )
        self.app_cfg.projects[name] = config
        self.save_to_disk(self.app_cfg.exp_yaml_path)

    def save_to_disk(self, path_out: str = None):
        """Saves a clean, human-readable YAML without python-specific tags."""
        raw_data = {
            name: cfg.model_dump()
            for name, cfg in self.app_cfg.projects.items()
        }
        clean_data = self._prepare_for_yaml(raw_data)
        with open(path_out, 'w') as f:
            yaml.safe_dump(clean_data, f, default_flow_style=False, sort_keys=False)

    def _prepare_for_yaml(self, obj):
        """Recursively converts tuples to lists and Paths to strings."""
        if isinstance(obj, dict):
            return {k: self._prepare_for_yaml(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._prepare_for_yaml(item) for item in obj]
        elif hasattr(obj, '__fspath__'):  # Catches Path objects
            return str(obj)
        return obj

    def load_from_disk(self):
        """Loads previously saved experiments."""
        p = self.app_cfg.exp_yaml_path
        with open(p, 'r') as f:
            data = yaml.safe_load(f) or {}
            for name, fields in data.items():
                self.app_cfg.projects[name] = ExpConfig.model_validate(fields)


    def get_all(self) -> Dict[str, ExpConfig]:
        return self.app_cfg.projects


def get_experiment_configurations() -> Dict[str, ExpConfig]:
    registry = ExperimentRegistry()
    return registry.get_all()