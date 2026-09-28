"""em_inspection: Interactive inspection and processing of SBEM datasets."""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

if TYPE_CHECKING:
    from em_inspection.experiment_configs import get_experiments_yaml_path


def __getattr__(name: str):
    if name == "get_experiments_yaml_path":
        from em_inspection.experiment_configs import get_experiments_yaml_path

        return get_experiments_yaml_path
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["get_experiments_yaml_path", "__version__"]
