import yaml
from pydantic import BaseModel, field_validator, model_validator
from typing import Tuple, Dict

from inspection_utils_refactor import cross_platform_path

DEF_PX_SIZE = 10.
DEF_CT = 25.

FN_STITCHING_CFG = "tile_stitching_config.yaml"

def save_to_disk(cfg_obj: BaseModel, path_out: str):
    """
    Saves a BaseModel to a clean, standard YAML file.
    Tuples are exported as standard YAML sequences (lists).
    """
    raw_data = cfg_obj.model_dump()
    clean_data = prepare_for_yaml(raw_data)
    with open(path_out, 'w') as f:
        # sort_keys=True ensures the alphabetical ordering you requested
        yaml.safe_dump(clean_data, f, default_flow_style=False, sort_keys=False)


def prepare_for_yaml(obj):
    """
    Recursively converts Paths to strings and ensures
    tuples/lists are handled as standard sequences.
    """
    if isinstance(obj, dict):
        return {k: prepare_for_yaml(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        # Convert both to lists for a uniform YAML sequence output
        return [prepare_for_yaml(item) for item in obj]
    elif hasattr(obj, '__fspath__'):  # Handles Path objects
        return str(obj)
    return obj


class AcquisitionConfig(BaseModel):
    sbem_root_dir: str = ""
    acquisition: str = "run_0"
    tile_grid: str = "g0000"
    grid_shape: tuple[int, int] = (30, 25)
    thickness: float = DEF_CT
    resolution_xy: float = DEF_PX_SIZE

    @field_validator('sbem_root_dir', mode='before')
    @classmethod
    def normalize_paths(cls, v):
        return cross_platform_path(v) if v else v


class ExpConfig(BaseModel):
    name: str
    acq_dir: str
    proc_dir: str
    grid_num: int
    grid_shape: Tuple[int, int]
    first_sec: int
    last_sec: int
    pixel_size: float = DEF_PX_SIZE
    cut_thickness: float = DEF_CT

    @field_validator('acq_dir', 'proc_dir', mode='before')
    @classmethod
    def normalize_paths(cls, v):
        return cross_platform_path(v) if v else v

    @model_validator(mode='after')
    def validate_range(self) -> 'ExpConfig':
        if self.first_sec > self.last_sec:
            raise ValueError(f"first_sec ({self.first_sec}) > last_sec ({self.last_sec})")
        return self


class AppConfig(BaseModel):
    exp_yaml_path: str = "app_data/user_experiments.yaml"
    projects: Dict[str, ExpConfig] = {}


class RegistrationConfig(BaseModel):
    overlaps_x: list[int] = [200, 300, 400]
    overlaps_y: list[int] = [200, 300, 400]
    min_range: list[int] = [10, 100, 0]
    min_overlap: int = 20
    filter_size: int = 10
    patch_size: list[int] = [120, 120]
    batch_size: int = 8000
    min_peak_ratio: float = 1.0
    min_peak_sharpness: float = 1.0
    max_deviation: int = 6
    max_magnitude: int = 0
    min_patch_size: int = 10
    max_gradient: float = 12.0
    reconcile_flow_max_deviation: float = -1.0


class FlowFieldEstimationConfig(BaseModel):
    patch_size: int = 160
    stride: int = 40
    batch_size: int = 256
    min_peak_ratio: float = 1.6
    min_peak_sharpness: float = 1.6
    max_magnitude: float = 80
    max_deviation: float = 20
    max_gradient: float = 0
    min_patch_size: int = 400


class MeshIntegrationConfig(BaseModel):
    dt: float = 0.001
    gamma: float = 0.0
    k0: float = 0.01
    k: float = 0.1
    stride: int = 20
    num_iters: int = 1000
    max_iters: int = 20000
    stop_v_max: float = 0.005
    dt_max: float = 100
    start_cap: float = 0.01
    final_cap: float = 10
    prefer_orig_order: bool = True
    remove_drift: bool = True


class WarpConfig(BaseModel):
    target_volume_name: str = "warped_zyx.zarr"
    start_section: int = 0
    end_section: int = 1
    yx_start: list[int] = list([1000, 2000])
    yx_size: list[int] = list([1000, 1000])
    parallelization: int = 16


class WarpConfigStitching(BaseModel):
    margin: int = 0
    use_clahe: bool = True
    kernel_size: int = 256
    clip_limit: float = 0.08
    nbins: int = 256
    warp_parallelism: int = 6


class StitchingConfig(BaseModel):
    output_dir: str = ""
    acquisition_config: AcquisitionConfig = AcquisitionConfig()
    start_section: int = 0
    end_section: int = 1
    mesh_integration_config: MeshIntegrationConfig = MeshIntegrationConfig()
    registration_config: RegistrationConfig = RegistrationConfig()
    warp_config: WarpConfigStitching = WarpConfigStitching()

    @field_validator('output_dir', mode='before')
    @classmethod
    def normalize_output_path(cls, v):
        return cross_platform_path(v) if v else v