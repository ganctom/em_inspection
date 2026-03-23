from pydantic import BaseModel, field_validator, model_validator
from typing import Tuple, Dict

from inspection_utils_refactor import cross_platform_path


class AcquisitionConfig(BaseModel):
    sbem_root_dir: str = ""
    acquisition: str = "run_0"
    tile_grid: str = "g0000"
    grid_shape: tuple[int, int] = (30, 25)
    thickness: float = 25
    resolution_xy: float = 10

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
    pixel_size: int = 10
    cut_thickness: int = 25

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
    num_iters: int = 1000
    max_iters: int = 100000
    stop_v_max: float = 0.005
    dt_max: float = 1000
    start_cap: float = 0.01
    final_cap: float = 10
    prefer_orig_order: bool = True
    block_size: int = 50


class WarpConfig(BaseModel):
    target_volume_name: str = "warped_zyx.zarr"
    start_section: int = 0
    end_section: int = 199
    yx_start: list[int] = list([1000, 2000])
    yx_size: list[int] = list([1000, 1000])
    parallelization: int = 16
