from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict
import inspection_utils_refactor as utils


@dataclass
class ExpConfig:
    name: str
    proc_dir: str
    grid_num: int
    first_sec: int
    last_sec: int
    grid_shape: tuple[int, int]
    acq_dir: Optional[str] = None

    def __post_init__(self):
        self.proc_dir = utils.cross_platform_path(self.proc_dir)
        if self.acq_dir:
            self.acq_dir = utils.cross_platform_path(self.acq_dir)

        # UI Label for Dash components
        self.label = f"{self.name} (Grid {self.grid_num})"


class ExperimentRegistry:
    def __init__(self):
        self._configs: Dict[str, ExpConfig] = {}

    def add(self,
            name: str,
            proc_dir: str,
            grid_num: int,
            secs: List[int],
            shape: tuple[int, int],
            acq: str = None
            ):
        config = ExpConfig(
            name=name,
            proc_dir=proc_dir,
            grid_num=grid_num,
            first_sec=secs[0],
            last_sec=secs[1],
            grid_shape=shape,
            acq_dir=acq
        )
        self._configs[name] = config

    def get_all(self) -> Dict[str, ExpConfig]:
        return self._configs

    def get(self, name: str) -> ExpConfig:
        return self._configs.get(name)



def get_experiment_configurations() -> Dict[str, ExpConfig]:
    registry = ExperimentRegistry()
    root = Path(utils.cross_platform_path(r"/Volumes/storage/scratch/team/project/tgan/Stack_alignments"))

    # Add experiments one by one
    registry.add(
        name="ROLI_1",
        proc_dir=str(root / "roli-1/2024_05_17"),
        grid_num=1,
        secs=[282, 8651],
        shape=(40, 40),
        acq=r"/Volumes/storage/groups/scratch/team/project/_EM_acquisitions/20250701_RoLi_Fish_1_ID_20250528_132139"
    )

    registry.add(
        name="ROLI_F1",
        proc_dir="/Volumes/storage/groups/scratch/team/project/_processing/SOFIMA/nextflow/ganctoma/gfriedri-em-alignment-flows/runs/roli-f1/run-02",
        grid_num=0,
        secs=[1250, 9000],
        shape=(30, 25),
        acq="/Volumes/storage/groups/scratch/team/project/_EM_acquisitions/20260201_RoLi_F1"
    )

    # Add more as needed...
    return registry.get_all()