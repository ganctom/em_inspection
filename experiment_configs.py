from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional
import inspection_utils_refactor as utils
import logging
import yaml

@dataclass
class ExpConfig:
    path: str
    grid_num: int
    first_sec: int
    last_sec: int
    grid_shape: tuple[int, int]
    acq_dir: Optional[str] = None

    def __post_init__(self):
        # # Validate the types
        # assert isinstance(self.path, str), f"path should be a str, got {type(self.path)}"
        # assert isinstance(self.grid_num, int), f"grid_num should be an int, got {type(self.grid_num)}"
        #
        # # Validate that the path exists
        # assert Path(self.path).exists(), f"Path does not exist: {self.path}"
        pass


class ProjConfig:
    # TODO
    def __init__(self, path):
        self.path_project: Path = path
        self.path_project_cfg: Path = self.path_project / 'project.cfg'
        self.experiments: Optional[List[ExpConfig]] = self.get_exp_configs()

    def get_exp_configs(self) -> Optional[List[ExpConfig]]:
        
        self.load_project()

        if not self.experiments:
            dirs = [d for d in self.path_project.iterdir() if d.is_dir()]
            # Read exp_config file in each folder and return resulting list
            cfgs = []
            return cfgs

    def load_project(self):
        if not self.path_project_cfg.exists():
            logging.warning(f'Project config file not found.')
            return None
        try:
            with open(self.path_project_cfg, "r") as yaml_file:
                data = yaml.safe_load(yaml_file)
                exp_dirs = data['experiments']
            return exp_dirs
        except Exception as e:
            print(f"An error occurred: {e}")
            return None


@dataclass
class ExpNotes:
    Tool: Optional[str] = None
    HV: Optional[float] = None
    Ip: Optional[int] = None
    DT: Optional[float] = None
    Overlap: Optional[int] = None
    Grid_nr: Optional[int] = None
    OV_nr: Optional[int] = None
    Skip: List[int] = field(default_factory=list)
    Duplicates: List[int] = field(default_factory=list)


def parse_number_list(number_list_str: str) -> List[int]:
    numbers = set()

    if ',' not in number_list_str and len(number_list_str) > 0:
        numbers.add(int(number_list_str))
        return list(numbers)

    for part in number_list_str.split(','):
        if '-' in part:
            start, end = map(int, part.split('-'))
            numbers.update(range(start, end + 1))
        else:
            numbers.add(int(part.strip()))
    return sorted(numbers)


def load_exp_notes(yaml_file_path: str) -> Optional[ExpNotes]:
    path = Path(yaml_file_path)
    logging.info(f'Reading experiment notes from: {yaml_file_path}')
    if not path.exists():
        return None

    try:
        with path.open('r') as file:
            content = yaml.safe_load(file)

        config = ExpNotes()

        config.Overlap = content.get('overlap')
        config.Grid_nr = content.get('grid_num')
        config.Pixel_size = content.get('pixel_size')

        skip_str = content.get('skip', '')
        config.Skip = parse_number_list(skip_str)

        duplicates_str = content.get('duplicates', '')
        config.Duplicates = parse_number_list(duplicates_str)

        return config
    except Exception as e:
        print(f"Error loading config: {e}")
        return None


def exp_configs() -> List[ExpConfig]:
    root = r"/Volumes/storage/scratch/team/project/tgan/Stack_alignments"
    root = Path(utils.cross_platform_path(root))

    mont_1_names = [r"Montano_1/2024_04_16",]
    mont_1_paths = [str(root / n) for n in mont_1_names]

    mont_2_names = [r"Montano_2/20240218"]
    mont_2_paths = [str(root / n) for n in mont_2_names]

    mont_3_names = [r"Montano_3/20240416", ]
    mont_3_paths = [str(root / n) for n in mont_3_names]

    mont_4_names = [r"Montano_4/20240702"]
    mont_4_paths = [str(root / n) for n in mont_4_names]

    roli_1_names = [r"roli-1/2024_05_17"]
    roli_1_paths = [str(root / n) for n in roli_1_names]
    roli_1_gitrepo = r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\gitrepos\gfriedri_dataset-alignment\processed_data\roli-1"
    roli_1_paths.append(roli_1_gitrepo)

    roli_2_names = [r"roli-2", "roli-2-fix_5670", 'run100124']
    p1 = str(root / roli_2_names[0])
    root_roli_2 = r"/mnt/storage/scratch/team/project/_processing/SOFIMA/user/kappjoha/runs"
    p2 = str(Path(root_roli_2) / roli_2_names[2])
    roli_2_paths = [p1, p2]
    # roli_2_paths = [str(root / n) for n in roli_2_names]

    roli_3_names = [r"roli-3\2024_06_11"]
    roli_3_paths = [str(root / n) for n in roli_3_names]

    dp2_names = [r"dp-2\2024_06_12"]
    dp2_paths = [str(root / n) for n in dp2_names]

    roli_b2_1_names = [
        r"roli-b2-1\main",
        r"roli-b2-1\grid_shifting_s5500_s6062",
        r"roli-b2-1\grid_shifting_s5930_s5948",
        r"roli-b2-1\grid_shifting_s5500_s6062_fflows_investigation",
        r"roli-b2-1\grid_shifting_s5500_s6062_new_flows",
        r"roli-b2-1\grid_shifting_s6070_s7236",
    ]
    roli_b2_1_paths = [str(root / n) for n in roli_b2_1_names]

    # ROLI-F1 project
    run_names = [r"roli-f1/test_align"]
    roli_f1_paths = [str(root / n) for n in run_names]
    path_01 = "/Volumes/storage/scratch/team/project/_processing/SOFIMA/nextflow/ganctoma/gfriedri-em-alignment-flows/runs/roli-f1/run-01"
    roli_f1_paths.append(path_01)

    paths = [
        mont_1_paths[0],
        mont_2_paths[0],
        mont_3_paths[0],
        mont_4_paths[0],
        roli_1_paths[0],
        roli_2_paths[1],
        roli_3_paths[0],
        dp2_paths[0],
        roli_b2_1_paths[5],
        roli_f1_paths[1]
    ]

    acq_dirs = [None,
                None,
                None,
                None,
                r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\_EM_acquisitions\20230523_RoLi_IV_130558_run2",
                None,
                r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\_EM_acquisitions\20240319_RoLi_III",
                None,
                r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\_EM_acquisitions\20250701_RoLi_Fish_1_ID_20250528_132139",
                "/Volumes/storage/scratch/team/project/_EM_acquisitions/20260201_RoLi_F1"
    ]

    grid_nums = [0, 1, 0, 0, 1, 1, 0, 1, 0, 0]

    sec_ranges = [[402, 4724], [1027, 5633], [450, 5486], [550, 3690],
                  [282, 8651], [261, 8579], [1, 7245], [253, 10257], [6070, 7236],
                  [1250, 9000]
                  ]

    grid_shapes = [[25, 25], [40, 30], [40, 40], [28, 23],
                   [40, 40], [33, 33], [30, 25], [42, 32],
                   [40, 35],
                   (30, 25)
                   ]

    experiments: List[ExpConfig] = []

    for path, grid_num, (first_sec, last_sec), grid_shape, acq_dir in zip(paths, grid_nums, sec_ranges, grid_shapes, acq_dirs):
        path = utils.cross_platform_path(path)
        exp_conf = ExpConfig(path, grid_num, first_sec, last_sec, grid_shape, acq_dir)
        experiments.append(exp_conf)

    return experiments

class ExperimentName(Enum):
    MONT_1 = 0
    MONT_2 = 1
    MONT_3 = 2
    MONT_4 = 3
    ROLI_1 = 4
    ROLI_2 = 5
    ROLI_3 = 6
    DP2 = 7
    ROLI_B2_1 = 8
    ROLI_F1 = 9

def get_experiment_configurations() -> dict:
    configs = exp_configs()
    return {exp: configs[exp.value] for exp in ExperimentName}

def tst_proj_config():
    # proj_path = r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\tgan\Stack_alignments\Montano_1"
    proj_path = r"\\storage.company.internal\tachyon\scratch\gmicro_sem\gfriedri\tgan\Stack_alignments\roli-b2-1"
    project = ProjConfig(Path(proj_path))
    print(project.path_project)

    target = ['2024_04_16', '2024_05_04', '2024_05_09', '2024_05_17', '2024_05_21']
    target = ['main']
    assert project.experiments == target, f'{project.experiments}\n{target}'

    return


def main_exp_notes():
    path_yaml = r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\tgan\Stack_alignments\Montano_4\exp_notes.yaml"
    exp_notes = load_exp_notes(path_yaml)
    print(exp_notes)
    return

def tst_cross():
    name = r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\_EM_acquisitions\20250701_RoLi_Fish_1_ID_20250528_132139"
    new = utils.cross_platform_path(name)
    print(f'old: {name}')
    print(f'new: {new}')

    root = r"\\nas.company.internal\tungsten\scratch\gmicro_sem\gfriedri\tgan\Stack_alignments"
    root = Path(utils.cross_platform_path(root))
    print(f'root: {root}')

    roli_b2_1_names = [r"roli-b2-1\main"]
    roli_b2_1_paths = [str(root / n) for n in roli_b2_1_names]

    print(roli_b2_1_paths)

    path = utils.cross_platform_path(roli_b2_1_paths[0])
    print(path)

    return


if __name__ == '__main__':
    # main_exp_notes()
    # tst_proj_config()
    a = get_experiment_configurations()
    for k, v in a.items():
        print(v)
    # tst_cross()


