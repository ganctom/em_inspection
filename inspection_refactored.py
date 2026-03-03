import json
import logging
import multiprocessing
import os
from platform import system
from pathlib import Path
from typing import Optional, Iterable, Union, Sequence, Dict, Iterator, Tuple
from functools import partial

import jax
import numpy as np
from tqdm import tqdm

import experiment_configs as cfg
import inspection_utils_refactor as utils

from Section_refactored import Section, fine_align_section, Vector, cached_read_image
from coarse_offset_processor import CoarseOffsetProcessor

UniPath = Union[str, Path]

### Set up logging
logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.DEBUG)
# logging.basicConfig(level=logging.INFO)
logging.basicConfig(level=logging.WARNING)


class Inspection:
    def __init__(self, config: cfg.ExpConfig):
        self.config = config
        self.root = Path(config.path)
        self.grid_nr = config.grid_num
        self.first_sec = config.first_sec
        self.last_sec = config.last_sec
        self.grid_shape = config.grid_shape
        self.acq_dir = utils.cross_platform_path(config.acq_dir)
        self.os_name = system()

        self._initialize_directories()
        self._initialize_paths()
        self._initialize_section_data()
        self._initialize_stitched_data()
        self._setup_offset_processor_paths()

        self.co_processor = CoarseOffsetProcessor(self.config, self.offset_processor_paths)
        self.co_processor.load_all_offsets_and_tile_id_maps_from_npz()

    def __str__(self):
        return (
            f"acq. dir: {self.acq_dir}\n"
            f"root dir: {self.root}\n"
            f"sec. dir: {self.dir_sections}\n"
            f"sec. range: {self.first_sec, self.last_sec}\n"
            f"grid shape: {self.grid_shape}\n"
            f"OS: {self.os_name}\n"
        )

    def _initialize_directories(self):
        self.dir_sections = self.root / 'sections'
        self.dir_stitched = self.root / 'stitched-sections'
        self.dir_inspect = self.root / '_inspect'
        self.dir_downscaled = self.dir_inspect / 'downscaled'
        self.dir_overlaps = self.dir_inspect / 'overlaps'
        self.dir_outliers = self.dir_inspect / 'overlaps_outliers'
        self.dir_inf_overlaps = self.dir_inspect / 'inf_overlaps'
        # self.dir_coarse_stacks = self.root / 'coarse-stacks'
        self.create_inspection_dirs()

    def _initialize_paths(self):
        self.path_cxyz = self._get_inspect_path('all_offsets.npz')
        self.path_id_maps = self._get_inspect_path('all_tile_id_maps.npz')
        self.fp_missing_sections = self.root / 'missing_sections.yaml'
        self.fp_co_outliers = self.dir_inspect / 'coarse_offset_outliers.txt'
        self.fp_inf_vals = self.dir_inspect / 'inf_vals.txt'
        # self.fp_eval_ov = self._get_overlaps_path('overlap_quality_smr.npz')
        # self.fp_est_ff_cfg = self.root / 'fine_alignment_config.yaml'

    def _setup_offset_processor_paths(self):
        """Single Source of Truth for the filesystem structure."""
        self.offset_processor_paths = {
            'inspect': self.dir_inspect,
            'cxyz': self.path_cxyz,
            'tid_maps': self.path_id_maps,
            'co_outliers': self.fp_co_outliers
        }


    def _initialize_section_data(self):
        self.section_dirs: Optional[list[Path]] = None
        self.section_names: Optional[list[str]] = None
        self.section_nums: Optional[list[int]] = None
        self.section_dicts: Optional[dict[int, str]] = None
        # self.section_nums_duplicates: Optional[list[str]] = None
        # self.section_nums_skip: Optional[list[str]] = None
        self.missing_sections: Optional[list[int]] = None
        ...

    def _initialize_stitched_data(self):
        self.stitched_dirs: Optional[list[Path]] = None
        self.stitched_names: Optional[list[str]] = None
        self.stitched_nums: Optional[list[int]] = None
        # self.stitched_nums_valid: Optional[list[int]] = None
        self.stitched_dicts: Optional[dict[int, str]] = None
        # self.cross_aligned_nums: Optional[list[int]] = None
        ...

    def _get_inspect_path(self, filename: str) -> Path:
        return self.dir_inspect / filename
    
    def _get_overlaps_path(self, filename: str) -> Path:
        return self.dir_overlaps / filename

    def init_experiment(self) -> None:
        """Perform initial data processing for Inspection class"""
        # self.read_exp_notes()
        self.list_all_section_dirs()
        self.get_missing_sections()


        return

    def list_all_section_dirs(self) -> None:
        """Lists all section and .zarr folders stored in 'sections' and 'stitched' folders
        """

        if self.os_name not in {"Windows", "Linux", "Darwin"}:
            print(f"list_all_section_dirs failed: unknown OS-system ({self.os_name}).")
            return

        # Sections folder
        sections_dir = str(self.dir_sections)
        stitched_dir = str(self.dir_stitched)

        if self.os_name in ("Windows", "Darwin"):
            res = utils.process_dirs(sections_dir, utils.filter_and_sort_sections)
            res_st = utils.process_dirs(stitched_dir, utils.list_stitched)
        elif self.os_name == "Linux":
            res, res_st = map(utils.process_dirs_unix, (sections_dir, stitched_dir))
        else:
            logging.error(f"Failed to list all sections: not supported processing platform!")
            return

        if res is not None:
            (self.section_dirs,
             self.section_names,
             self.section_nums,
             self.section_dicts) = res

        # Stitched sections folder
        if res_st is not None:
            (self.stitched_dirs,
             self.stitched_names,
             self.stitched_nums,
             self.stitched_dicts) = res_st

        return

    def get_missing_sections(self) -> None:
        """Identify section numbers discontinuities in section folder"""
        if self.section_dirs is None:
            self.list_all_section_dirs()

        if self.section_dirs is None:
            return

        missing_nums = []
        if len(self.section_dirs) > 1 and self.section_dirs:
            first: int = self.first_sec
            last: int = self.last_sec
            section_range = set(range(first, last + 1))
            missing_nums = sorted(list(section_range - set(self.section_nums)))

        if len(missing_nums) > 0:
            utils.write_dict_to_yaml(str(self.fp_missing_sections), missing_nums)
            is_are = 'is' if len(missing_nums) == 1 else 'are'
            logging.warning(f"There {is_are} {len(missing_nums)} missing sections in 'sections' folder!")

        self.missing_sections = missing_nums
        return

    def create_inspection_dirs(self):
        new_dirs = ('overlaps', 'traces', 'downscaled', 'inf_overlaps')
        logging.debug(f'Creating inspection infrastructure {new_dirs}')
        for leaf in new_dirs:
            create_directory(self.dir_inspect / leaf)
        return

    @staticmethod
    def verify_single_section(section: Section) -> Optional[int]:
        if not section.verify_tile_id_map(print_ids=False):
            return section.section_num
        return None

    def verify_tile_id_maps(self) -> list[int]:

        # Init experiment
        if not self.section_nums:
            self.init_experiment()

        # Construct section objects to be aligned
        section_paths = list(self.section_dirs)
        sections = [Section(p) for p in section_paths]

        # Create a pool of processes and map the verify_single_section function over section_nums
        num_proc = min(3, len(self.section_nums))
        with multiprocessing.Pool(processes=num_proc) as pool:
            results = pool.map(self.verify_single_section, sections)

        # Filter None results to collect failed section numbers
        failed_sec_nums = [num for num in results if num is not None]
        return failed_sec_nums

    def backup_coarse_offsets(self):
        """Stores all coarse offset arrays into a .npz file within inspect directory"""

        # Collect all offsets
        fn_coarse_offsets = "cx_cy.json"
        offsets, missing_files = utils.aggregate_coarse_offsets(self.section_dirs, fn_coarse_offsets)
        logging.debug(f'len missing files {len(missing_files)}')
        for p in missing_files:
            logging.debug(p)

        fp_out = self.dir_inspect / "all_offsets.npz"
        np.savez(fp_out, **offsets)
        logging.info(f'Coarse offsets saved to: {fp_out}')

        fp_out2 = fp_out.with_name("all_offsets_missing_files.txt")
        with open(fp_out2, "w") as f:
            f.writelines("\n".join(missing_files))
        logging.info(f'Missing offsets saved to: {fp_out2}')
        return

    def backup_tile_id_maps(self):
        # Collect all tile ID maps
        tile_id_maps, missing_files = utils.aggregate_tile_id_maps(self.section_dirs)
        logging.debug(f'len missing files {len(missing_files)}')
        for p in missing_files:
            logging.debug(p)

        fp_out = self.dir_inspect / "all_tile_id_maps.npz"
        np.savez(fp_out, **tile_id_maps)
        logging.info(f'Tile ID maps saved to: {fp_out}')

        fp_out2 = fp_out.with_name("all_missing_tile_id_maps.txt")
        with open(fp_out2, "w") as f:
            f.writelines("\n".join(missing_files))
        logging.info(f'Missing tile ID maps saved to: {fp_out2}')
        return


    @staticmethod
    def load_outliers(path_outliers: UniPath) -> dict[int, list[tuple[int, int]]]:
        """
        Load outliers data from a text file.

        :param path_outliers: Path to the file containing outliers data
        :return: A dictionary where keys are slice numbers and values are
        lists of tuples, each containing two integers (TileID, TileID_nn).
        """

        if not Path(path_outliers).exists():
            logging.warning(f"Failed to load outliers from file: {path_outliers}")
            return {}

        outliers_data = {}

        with open(path_outliers, 'r') as f:
            # Skip the header line
            next(f)

            # Read data line by line
            for line in f:
                parts = line.strip().split('\t')
                slice_num = int(parts[0])
                tile_id = int(parts[-2])
                tile_id_nn = int(parts[-1])

                # Check if the key already exists in the dictionary
                if slice_num in outliers_data:
                    # If the key exists, append the new outlier data to the existing list
                    outliers_data[slice_num].append((tile_id, tile_id_nn))
                else:
                    # If the key does not exist, create a new list with the outlier data
                    outliers_data[slice_num] = [(tile_id, tile_id_nn)]

        # Check if outliers_data is empty
        if not outliers_data:
            raise ValueError("No data found in the input file.")

        return outliers_data



    def fix_false_offsets_trace(
            self,
            tid_pair: [tuple[int, int]],
            align_args: dict,
            inf=False,
            custom_sec_nums: Optional[Iterable[int]] = None
    ) -> None:

        sec_nums = []
        fp = self.fp_co_outliers
        if inf:
            fp = self.fp_inf_vals

        if not Path(fp).exists():
            logging.info(f'No outliers/inf values fetched from {fp}')

        if not custom_sec_nums:
            try:
                outliers = self.load_outliers(path_outliers=fp)
            except ValueError as _:
                logging.warning(f'Empty list of outliers/inf values in {fp}')
                return

            sec_nums = list(outliers.keys())

        if custom_sec_nums is not None:
            sec_nums = custom_sec_nums
            # sec_nums = [num for num in sec_nums if num in custom_sec_nums]

        if not sec_nums:
            logging.warning(f'Fixing false offsets: nothing to fix in specified range of section numbers and tile-pair IDs.')
            return

        for sec_num in sec_nums:
            print(f'Aligning s{sec_num} tid_pair: {tid_pair}')
            tid_a, tid_b = tid_pair
            align_tile_pair(self, sec_num, tid_a, tid_b, **align_args)

        # for sec_num in sec_nums:
        #     for val in set(outliers[sec_num]):
        #         if val == tid_pair:
        #             tid_a, tid_b = tid_pair
        #             align_tile_pair(self, sec_num, tid_a, tid_b,  **align_args)

        # seams_scores = []
        # for sec_num in sec_nums:
        #     tid_a, tid_b = tid_pair
        #     ov_score = align_tile_pair(self, sec_num, tid_a, tid_b, **align_args)
        #     seams_scores.append(ov_score)
        #
        # # Store and plot results
        # mssim_tuples = [(num, score) for num, score in zip(sec_nums, seams_scores)]
        # dir_out = self.dir_inf_overlaps
        # process_eval_ov_results(mssim_tuples, tid_pair[0], tid_pair[1], dir_out, sort=False)
        return


    def plot_all_ovs_par(
            self,
            sec_nums,
            num_processes: int = 4
    ) -> None:

        num_processes = min(len(sec_nums), num_processes)

        if len(sec_nums) == 0:
            logging.warning('plot_ovs: Nothing to plot. Invalid section range.')
            return

        # Create dict of all sections and all tile_id pairs
        ov_dict: dict[int, list[tuple[int, int]]] = dict()

        # Get valid tile-id neighbor pairs and add them to final dict
        for num in sec_nums:
            sec_path = self.section_dicts.get(num)
            if sec_path is not None:
                my_sec = Section(sec_path)
                my_sec.read_tile_id_map()
                ov_dict[num] = utils.get_neighbour_pairs(my_sec.tile_id_map)

        with multiprocessing.Pool(processes=num_processes) as pool:
            plot_partial = partial(self.plot_ov_for_section, ov_dict=ov_dict)
            pool.map(plot_partial, sec_nums)

        return


    def plot_ov_for_section(self, sec_num: int, ov_dict: dict):
        sec_dict = {sec_num: ov_dict.get(sec_num)}
        self.plot_specific_ovs(sec_dict)
        return


    def plot_specific_ovs(self,
                          ov_dict: dict[int, list[tuple[int, int]]],
                          dir_name_out: Optional[str] = None,
                          refine=False,
                          est_vec: Optional[Vector] = None,
                          shift_abs_dev: Optional[float] = 15.
                          ) -> None:

        # Process parent dir for stored images
        if dir_name_out is None:
            dir_name_out = 'overlaps'

        dir_out = self.dir_inspect / dir_name_out
        utils.create_directory(dir_out)

        # Plot overlaps
        for sec_num, tid_list in ov_dict.items():
            if sec_num not in self.section_nums:
                continue

            sec_path = self.section_dicts[sec_num]
            sec = Section(sec_path)
            sec.feed_section_data()

            # Specify custom shift vector here
            # shift_vec = (0, 0)

            # Filter duplicate tile-id pairs
            seen = set()
            unique_tid_list = [x for x in tid_list if x not in seen and not seen.add(x)]

            # skip = [(860, 900), (941, 981)]
            skip = []
            # unique_tid_list = [(651, 683),] # (624, 656)
            for (tid_a, tid_b) in unique_tid_list:
                if (tid_a, tid_b) not in skip:
                    print(f'Plotting s{sec.section_num} t{tid_a}-t{tid_b}')
                    logging.info(f'Plotting s{sec.section_num} t{tid_a}-t{tid_b}')

                    if refine:
                        logging.info(f'Refining coarse offset of s{sec.section_num} t{tid_a}-t{tid_b}')
                        refine_kwargs = dict(tid_a=tid_a, tid_b=tid_b, masking=False, levels=3,
                                             max_ext=80, stride=12, clahe=True, store=True,
                                             plot=False, show_plot=False, est_vec=None)
                        shift_vec = sec.refine_pyramid(**refine_kwargs)
                        # print(f'Refined vector: {shift_vec}')

                    # # Verify if coarse offset is within limits, otherwise skip
                    # axis = 1 if utils.pair_is_vertical(sec.tile_id_map, tid_a, tid_b) else 0
                    # offset = sec.get_coarse_offset(tid_a, axis)
                    # offset_valid, _ = utils.vector_dist_valid(offset, est_vec, shift_abs_dev)
                    offset_valid = True

                    # Set to False if plotting inf overlaps
                    # offset_valid = False
                    # if offset_valid:
                    #     logging.info(f's{sec.section_num} t{tid_a}-t{tid_b} coarse offset deviation within limits.')
                    #     break

                    # Set shift_vec if plotting inf overlaps
                    shift_vec = (0, 0)
                    shift_vec = (0, 0) if np.inf in shift_vec else shift_vec
                    shift_vec = None

                    args = dict(tid_a=tid_a,
                                tid_b=tid_b,
                                shift_vec=shift_vec,
                                dir_out=dir_out,
                                show_plot=False,
                                clahe=True,
                                blur=1.0)
                    sec.plot_ov(**args)
        return

    def plot_specific_ovs_refactored(
            self,
            ov_dict: dict[int, list[tuple[int, int]]],
            dir_name_out: Optional[str] = None,
    ) -> None:

        # Process parent dir for stored images
        if dir_name_out is None:
            dir_name_out = 'overlaps'

        dir_out = self.dir_inspect / dir_name_out
        utils.create_directory(dir_out)

        # Plot overlaps
        shift_vec = (None, None)  # plotting from cx_cy.json
        for sec_num, tid_list in ov_dict.items():
            if sec_num not in self.section_nums:
                continue

            sec_path = self.section_dicts[sec_num]
            sec = Section(sec_path)
            sec.feed_section_data()

            # Filter duplicate tile-id pairs
            seen = set()
            unique_tid_list = [x for x in tid_list if x not in seen and not seen.add(x)]

            skip = []
            for (tid_a, tid_b) in unique_tid_list:
                if (tid_a, tid_b) not in skip:
                    # print(f'Plotting overlap s{sec.section_num} t{tid_a}-t{tid_b}')
                    logging.info(f'Plotting overlap s{sec.section_num} t{tid_a}-t{tid_b}')

                    args = dict(tid_a=tid_a,
                                tid_b=tid_b,
                                shift_vec=shift_vec,
                                dir_out=dir_out,
                                show_plot=False,
                                clahe=True,
                                blur=1.0)
                    sec.plot_ov(**args)
        return


###  EOF PRIVATE FUNCTIONS  ####




def create_directory(dir_path: Path):
    try:
        os.makedirs(dir_path, exist_ok=True)
        logging.debug(f"Directory '{dir_path}' created successfully.")
    except FileExistsError:
        print(f"Directory '{dir_path}' already exists.")
    except PermissionError:
        print(f"Permission denied. Unable to create directory '{dir_path}'.")
    except OSError as e:
        print(f"Error creating directory '{dir_path}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def main_scan_missing_section_folders(insp: Inspection):
    """SCAN FOR MISSING SECTION ENTRIES IN SECTIONS FOLDER"""
    print(f"Inspecting:\n{insp}")

    if insp.section_nums is None:
        logging.warning(f"No sections numbers in the Inspection. Has it been initialized?")
        return

    print(f'Nr. of section entries in sections folder: {len(insp.section_nums)}')
    print(f'First and last section nr. specified in config: {insp.first_sec, insp.last_sec}')
    print(f'Nr. of missing section folders: {len(insp.missing_sections)}')
    utils.write_dict_to_yaml(str(insp.root / 'missing_sections.yaml'), insp.missing_sections)
    return


def main_verify_tile_id_maps(insp: Inspection):
    failed_sec_nums = insp.verify_tile_id_maps()
    fp = str(exp.root / 'invalid_tile_id_maps.yaml')
    utils.write_dict_to_yaml(fp, failed_sec_nums)
    return


def plot_traces_from_backup(
        path_cxyz: Path | str,
        path_id_maps: Path | str,
        traces_out_dir: Path | str,
        tile_ids: Iterable[int],
        in_parallel: bool = False,
        max_processes: int = 20
) -> None:
    """
    Plot position traces for selected tiles from the cxyz backup file.

    Args:
        path_cxyz: Path to the cxyz.npz backup file
        path_id_maps: Path to the tile-id maps file
        traces_out_dir: Directory where trace plots will be saved
        tile_ids: Iterable of tile IDs to plot
        in_parallel: Whether to use multiprocessing
        max_processes: Maximum number of parallel processes (when in_parallel=True)
    """
    traces_out_dir = Path(traces_out_dir)
    traces_out_dir.mkdir(parents=True, exist_ok=True)

    args_list = []
    for tile_id in sorted(tile_ids):
        plot_name = f"t{tile_id:04d}_trace.png"
        output_path = traces_out_dir / plot_name

        args = (
            str(path_cxyz),
            str(path_id_maps),
            str(output_path),
            tile_id,
            (None, None),
            False,
        )
        args_list.append(args)

    if not args_list:
        logging.info("No traces to plot.")
        return

    if in_parallel:
        num_proc = min(max_processes, len(args_list))
        logging.info(f"Plotting {len(args_list)} traces in parallel using {num_proc} processes...")
        with multiprocessing.Pool(processes=num_proc) as pool:
            pool.starmap(utils.plot_trace_from_backup, args_list)
    else:
        logging.info(f"Plotting {len(args_list)} traces sequentially...")
        for args in args_list:
            tile_id = args[3]
            print(f"Plotting trace of tile nr.: {tile_id}")
            utils.plot_trace_from_backup(*args)

    return None


def postprocess_cxcy(exp: Inspection,
                     plot_traces: bool,
                     locate_inf: bool,
                     trace_ids: Optional[Iterable[int]] = None,
                     in_parallel: bool = False,
                     max_processes: int = 20
                     ):
    """Backs-up all coarse offsets (cx_cy.json files) into a compressed .npz file and generates their plots (optional).

      Args:
          :param exp (Inspection): Inspection object.
          :param plot_traces (bool): Whether to plot traces.
          :param locate_inf (bool): Whether to locate and save inf values from cx_cy.json files.
          :param trace_id (int): plot only specified tile_id trace
          :param in_parallel:
          :param trace_ids:
          :param max_processes:
      """

    # Backup cx_cy
    if not exp.path_cxyz.exists():
        logging.info("backing-up coarse offsets...")
        exp.backup_coarse_offsets()

    # # Override backing-up coarse offsets
    # exp.backup_coarse_offsets()

    if not exp.path_id_maps.exists():
        logging.info("backing-up tile-id maps...")
        exp.backup_tile_id_maps()

    # exp.backup_tile_id_maps()

    # Locate and save inf values from cxyz backup
    if locate_inf:
        logging.info("Detecting infinities in coarse offsets...")
        _ = utils.locate_inf_vals(exp.path_cxyz, exp.dir_inspect, store=True)

    if plot_traces:
        traces_out_dir = exp.dir_inspect / 'traces'
        if trace_ids is None:
            trace_ids = sorted(list(utils.get_tile_ids_set(str(exp.path_id_maps))))

        plot_traces_from_backup(
            path_cxyz=exp.path_cxyz,
            path_id_maps=exp.path_id_maps,
            traces_out_dir=traces_out_dir,
            tile_ids=trace_ids,
            in_parallel=in_parallel,
            max_processes=max_processes,
        )

    return


def main_fix_tile_id_maps(exp: Inspection):
    """ Computes and stores tile-id maps for all sections in sections folder """
    for sec_dir in exp.section_dirs:

        # Read tile-id map
        tile_id_map = utils.read_tile_id_map(sec_dir)
        tile_id_map_filtered = set(tile_id_map.flatten())
        tile_id_map_filtered.discard(-1)
        tile_ids = sorted(list(tile_id_map_filtered))

        # Recompute & store fixed tile-id map
        try:
            new = utils.compute_tile_id_map(exp.grid_shape, tile_ids)
            tile_id_map_list = new.tolist()
            with open(sec_dir / "tile_id_map.json", "w") as f:
                json.dump(tile_id_map_list, f)
        except ValueError as e:
            logging.warning(f'Storing tile-id_map failed: {e}')
            continue

    return

def main_par_multiproc(insp: Inspection):

    nums_to_align = None
    start = 1870  # insp.first_sec
    end = insp.last_sec
    # start, end = 1869, 1869
    sec_nums = tuple(range(start, end+1))
    init_specific_section_dirs(insp, sec_nums)
    end = None

    num_processes = 10
    fine_align_sections_multiproc(
        exp=insp,
        start=start,
        end=end,
        nums_to_align=nums_to_align,
        masking=False,
        num_processes=num_processes
    )

    return

def fine_align_sections_multiproc(
        exp: Inspection,
        start: Optional[int] = None,
        end: Optional[int] = None,
        nums_to_align: Optional[Iterable[int]] = None,
        masking: bool = True,
        num_processes: int = 40
):
    # jax.config.update("jax_platform_name", "cpu")
    if exp.section_dicts is None:
        exp.init_experiment()

    if start is not None and end is not None:
        nums_to_align = list(range(start, end + 1))

    if nums_to_align is None:
        nums_to_align = list(range(exp.first_sec, exp.last_sec + 1))

    nums_to_align = [num for num in nums_to_align if num in exp.section_dicts.keys()]

    section_paths = [exp.section_dicts[num] for num in nums_to_align]
    sections = [Section(p) for p in section_paths]

    # Compute or refine coarse offsets
    if not len(sections):
        print('No sections were selected for processing.')
        logging.warning('No valid sections were selected for processing. Check experiment setting and section numbers.')
        return

    # Compute without parallelization
    if num_processes == 0:
        for s in sections:
            fine_align_section(s, exp.grid_shape, masking)
        logging.info(f'Finished fine-alignment of sections {min(nums_to_align)} - {max(nums_to_align)}')
        return

    # Select mode of alignment
    part_func = partial(fine_align_section, grid_shape=exp.grid_shape, masking=masking)

    # Create map of alignment processes
    with multiprocessing.Pool(processes=num_processes) as pool:
        pool.map(part_func, sections)  # , chunksize=2
    return


def main_fix_outliers_and_infinities(insp: Inspection):
    """FIX OUTLIERS, INFINITIES AND PLOT THEM """

    def _get_sec_nums(_dir_ovs: Path) -> list[int]:
        tid_a, tid_b = tid_pair_to_align
        str_a = str(tid_a).zfill(4)
        str_b = str(tid_b).zfill(4)
        dir_ov = dir_overlaps / ('t' + str_a + '_t' + str_b)
        return utils.get_ov_sec_nums(dir_ov)

    dir_overlaps = exp.dir_outliers
    # dir_overlaps = exp.dir_inspect / 'inf_overlaps'

    # tid_pairs = [(260, 261)]
    est_vec =  (-30, -140) # vert (+x, -y)
    # est_vec = None
    masking = False
    refine = True
    store = True
    plot = True
    fix_infinities = False
    # custom_sec_nums = None
    # custom_mask_params = (500, 500, 700, 700)  # top, bottom, left, right
    custom_mask_params = (0, 0, 1, 1)  # vertical tile-pair
    # custom_mask_params = (1, 1, 0, 0)  # horizontal tile-pair

    tid_pairs = utils.get_ov_tid_pairs(dir_overlaps)
    tid_pairs = [(486, 487)]
    for tid_pair_to_align in tid_pairs:
        custom_sec_nums = _get_sec_nums(dir_overlaps)
        # custom_sec_nums = None

        refine_params = dict(
            levels=3, max_ext=100, stride=20, clahe=True, store=store,
            plot=plot, show_plot=False, est_vec=est_vec,
            custom_mask_params=custom_mask_params
        )

        args = dict(
            masking=masking, store=store, refine=refine, plot=plot,
            refine_params=refine_params
        )

        insp.fix_false_offsets_trace(
            tid_pair=tid_pair_to_align,
            custom_sec_nums=custom_sec_nums,
            inf=fix_infinities,
            align_args=args
        )
    return


def align_tile_pair(
        exp: Inspection,
        sec_num: int,
        tid_a: int,
        tid_b: int,
        masking: bool,
        store: bool,
        refine: bool,
        plot: bool,
        refine_params: dict,
        clahe: bool = True,
) -> Optional[float]:

    sec_dir = exp.dir_sections / f's{sec_num}_g{exp.grid_nr}'

    if not sec_dir.exists():
        logging.warning(f'Section s{sec_num} not found in the sections directory!')
        return None

    my_sec = Section(sec_dir)
    my_sec.feed_section_data()

    if tid_a not in my_sec.tile_id_map and tid_b not in my_sec.tile_id_map:
        logging.warning(f'Section s{sec_num} does not contain tile-pair {tid_a}-{tid_b}!')
        return None

    if masking:
        my_sec.load_masks()

    # Optionally run only refine pyramid with desired settings
    seam_score = None
    if refine:
        offset = my_sec.refine_pyramid(tid_a, tid_b, masking, **refine_params)

        # # Evaluate seam quality using current coarse offset
        # tile_pair = my_sec.load_masked_pair(tid_a, tid_b, roi=True, smr=False, gauss_blur=True, sigma=6.0)
        # axis = 1 if utils.pair_is_vertical(my_sec.tile_id_map, tid_a, tid_b) else 0
        # current_co = my_sec.get_coarse_offset(tid_a, axis)
        # seam_score = my_sec.eval_ov(tile_pair, current_co)
        # if seam_score is not None:
        #     logging.info(f's{my_sec.section_num} t{tid_a}-t{tid_b} ov mssim: {seam_score:.2f}')
        # else:
        #     seam_score = np.nan
        #     logging.warning(
        #         f'eval_ov (t{tid_a}-{tid_b}): estimation of overlap quality failed in section {my_sec.section_num}.')

    else:
        overlaps_xy = ((100, 200, 300), (100, 200, 300))
        min_range = ((0, 50, 100), (0, 50, 100))

        args = dict(overlaps_xy=overlaps_xy,
                    min_range=min_range,
                    min_overlap=2,
                    filter_size=10,
                    masking=masking,
                    max_valid_offset=400)

        offset = my_sec.compute_coarse_offset(tid_a, tid_b, refine, store, clahe, **args)
        logging.info(f's{my_sec.section_num} coarse offset: {offset}')
        print(f'computed coarse offset: {offset}')

    if plot:
        dir_out = utils.cross_platform_path(str(exp.dir_inf_overlaps))
        # offset = (0, 0)
        # Plot zero overlap if Inf in coarse offset
        if offset is None or any(np.isinf(offset)):
            offset = (0, 0)
            print('Offset not determined')
        my_sec.plot_ov(tid_a, tid_b, offset, dir_out, show_plot=False,clahe=clahe, blur=1.0)

    return seam_score


def plot_ov_wrapper(section, **kwargs):
    # print(f'Plotting s{section.section_num}')
    return Section.plot_ov(section, **kwargs)

def par_plot_ov(
        exp: Inspection,
        kwargs: dict,
        num_processes: int,
        nums_to_align: Optional[Iterable[int]] = None
) -> None:

    if exp.section_nums is None:
        exp.init_experiment()

    # If no section range was specified, align pairs from all sections
    if nums_to_align is None:
        start: int = exp.section_nums[0]
        end: int = exp.section_nums[-1]
        nums_to_align = set(range(start, end + 1))
    else:
        nums_to_align = set(nums_to_align)

    nums_to_align = nums_to_align.intersection(exp.section_nums)
    section_paths = [exp.section_dicts[num] for num in nums_to_align]
    sections = [Section(p) for p in section_paths]
    logging.debug(f"len sections: {len(sections)}")

    # Filter sections without any of the requested tile_ids or pair is not neighbouring
    for sec in sections:
        sec.read_tile_id_map()
        tid_a, tid_b = kwargs['tid_a'], kwargs['tid_b']
        is_vert = utils.pair_is_vertical(sec.tile_id_map, tid_a, tid_b)
        if is_vert is None or tid_a not in sec.tile_id_map or tid_b not in sec.tile_id_map:
            sections.remove(sec)

    part_func = partial(plot_ov_wrapper, **kwargs)
    with multiprocessing.Pool(processes=num_processes) as pool:
        pool.map(part_func, sections)

    return None


def run_par_plot_ov(
        exp: Inspection,
        start: Optional[int],
        end: Optional[int],
        tid_a: int,
        tid_b: int,
        num_proc: int,
        dir_out: Optional[str] = None,
        sec_nums: Optional[Iterable[int]] = None
):
    """Plots overlap regions of a specific tile-pair over sections in parallel.
    """
    jax.config.update("jax_platform_name", "cpu")

    if dir_out is None:
        dir_out = exp.dir_inspect / 'overlaps'
        logging.debug(f'storing to: {dir_out}')

    # Select section range (optional)
    nums_to_align = None
    if sec_nums is not None:
        nums_to_align = sec_nums
    elif None not in (start, end):
        nums_to_align = set(range(start, end+1))

    kwargs = dict(
        tid_a=tid_a,
        tid_b=tid_b,
        shift_vec=(0, None),
        dir_out=dir_out,
        show_plot=False,
        clahe=True,
        blur=1.2
    )

    par_plot_ov(
        exp=exp,
        kwargs=kwargs,
        num_processes=num_proc,
        nums_to_align=nums_to_align,
    )
    return


def init_specific_section_dirs(exp: Inspection, sec_nums: Sequence[int]) -> None:
    """
    Initializes section directories based on a provided list of section numbers.
    """
    valid_nums = utils.validate_section_numbers(exp.first_sec, exp.last_sec, sec_nums)

    # ─── Build properties for valid sections ────────────────────────
    grid = exp.grid_nr
    base = Path(exp.dir_sections)

    names = [f"s{n}_g{grid}" for n in valid_nums]
    dirs_ = [base / name for name in names]

    exp.section_nums   = valid_nums
    exp.section_names  = names
    exp.section_dirs   = dirs_
    exp.section_dicts  = {n: str(p) for n, p in zip(valid_nums, dirs_)}
    return None



def _prepare_sections(
        inspection: Inspection,
        start: int,
        end: int
) -> Optional[list[int]]:
    """Helper to handle the repetitive range creation and initialization."""
    try:
        sec_nums = list(range(start, end+1))
        init_specific_section_dirs(inspection, sec_nums)
        return sec_nums
    except ValueError as e:
        logging.error(f"{e}")
        return None


def main_par_plot_ovs_specific_tile_pair(inspection: Inspection):

    start: int = 1360  # inspection.first_sec
    end: int = 1370    # inspection.last_sec
    tid_a: int = 464
    tid_b: int = 489
    num_proc: int = 1
    dir_out: str | None = None

    sec_nums = _prepare_sections(inspection, start, end)
    if not sec_nums:
        return

    run_par_plot_ov(inspection, start, end, tid_a, tid_b, num_proc, dir_out, sec_nums)
    return


def main_plot_ovs_all_tilepairs(inspection: Inspection) -> None:
    # PLOTS IMAGE OVERLAPS OF ALL TILE-PAIRS IN PARALLEL
    start: int = 1860
    end: int = 1875
    num_proc: int = 4

    sec_nums = _prepare_sections(inspection, start, end)
    if not sec_nums:
        return

    exp.plot_all_ovs_par(sec_nums, num_proc)
    return None


def main_get_cxyz_outliers(config: cfg.ExpConfig):

    tile_ids: set[int] | None = {486, 389, 460}
    n_before: int = 40
    n_after: int = 0
    n_sigmas: float = 20.0

    inspection = Inspection(config)
    td = CoarseOffsetProcessor(config, inspection.offset_processor_paths)
    try:
        td.load_all_offsets_and_tile_id_maps_from_npz()  # Load cxyz tensor and all tile-id maps
    except FileNotFoundError as e:
        logging.error(e)

    # Process all tile-IDs
    if not tile_ids:
        td.process_all_tile_ids_outliers(n_before, n_after, n_sigmas)
        td.store_outliers()
        return

    # Process specific tile-IDs
    for tile_id in tile_ids:
        td.process_tile_id_outliers(tile_id, n_before, n_after, n_sigmas)
    td.store_outliers()

    return


def main_postprocess_coarse_shifts(
        exp: Inspection,
        trace_ids: Optional[Iterable[int]] = None,
        plot_traces: bool = True
) -> None:

    if exp.section_nums is None:
        all_sec_nums = tuple(range(exp.first_sec, exp.last_sec+1))
        init_specific_section_dirs(exp, all_sec_nums)

    postprocess_cxcy(
        exp=exp,
        plot_traces=plot_traces,
        locate_inf=True,
        trace_ids=trace_ids,
        in_parallel=True
    )
    return


def plot_ovs_from_out_or_inf_file(inspection: Inspection):
    # Plot overlaps from file 'coarse_offset_outliers.txt' or 'all_inf.txt'

    path_outliers = exp.dir_inspect / 'coarse_offset_outliers.txt'
    dir_name_out = exp.dir_overlaps.name

    # path_outliers = exp.dir_inspect / 'inf_vals.txt'
    # dir_name_out = 'inf_overlaps'

    # Read outliers from file
    ov_dict = utils.load_outliers(path_outliers)
    if not ov_dict:
        print("Nothing to plot (no outliers found)")
        return

    # Initialize sections
    sec_nums = tuple(ov_dict.keys())
    init_specific_section_dirs(inspection, sec_nums)

    # Plot overlaps
    exp.plot_specific_ovs_refactored(ov_dict, dir_name_out)

    return


def _get_update_targets(
    cxyz_file: np.lib.npyio.NpzFile,
    new_cxyz: Dict[str, np.ndarray]
) -> Iterator[Tuple[str, np.ndarray]]:
    """Yields (key, value) from new_cxyz if they differ from backup."""
    for k, v in new_cxyz.items():
        if k in cxyz_file.files and np.array_equal(cxyz_file[k], v, equal_nan=True):
            continue
        yield k, v


def store_cxyz_to_offset_files(
        insp: Inspection,
        new_cxyz: Optional[Dict[str, np.ndarray]] = None
) -> None:
    """Stores updated coarse offset arrays from new_cxyz into section cx_cy.json files"""

    if not new_cxyz: return
    if not insp.path_cxyz.exists():
        logger.error("Backup missing: %s", insp.path_cxyz)
        return

    try:
        with np.load(insp.path_cxyz, mmap_mode='r') as backup:
            targets = list(_get_update_targets(backup, new_cxyz))
            if not targets:
                print(f"All {len(new_cxyz)} items match. Skipping.")
                return

            stats = {"ok": 0, "err": 0}
            for k, v in tqdm(targets, desc="Updating"):
                sec_path = insp.dir_sections / f"s{k}_g{insp.grid_nr}"
                p = utils.cross_platform_path(str(sec_path))
                try:
                    utils.save_coarse_mat(v, p, file_format='json')
                    stats["ok"] += 1
                except (IOError, OSError) as e:
                    logger.error("Error s%s: %s", k, e)
                    stats["err"] += 1

            print(f"\nWritten: {stats['ok']} | Skipped: {len(new_cxyz)-stats['ok']} | Errors: {stats['err']}")
    except Exception as e:
        logger.critical("Failed: %s", e, exc_info=True)


if __name__ == "__main__":

    ### Accessing individual alignment experiments
    configs = cfg.get_experiment_configurations()
    exp_config = configs[cfg.ExperimentName.ROLI_F1]

    ### Initialize experiment
    exp = Inspection(exp_config)
    # exp.init_experiment()
    # print(exp)


    ### PRE- & POST-PROCESS ROUTINES
    # main_scan_missing_section_folders(exp)


    ### FIX TILE-ID MAPS
    # main_fix_tile_id_maps(exp)


    ### VERIFY TILE_ID MAPS
    # main_verify_tile_id_maps(exp)


    ### POSTPROCESS COARSE SHIFTS
    main_postprocess_coarse_shifts(exp, plot_traces=True, trace_ids=None)


    # # MULTIPROCESSING, RENDERING & FINE ALIGNMENT
    # main_par_multiproc(exp)


    ### DETECT BEAD COARSE OFFSETS
    # main_get_cxyz_outliers(config=exp_config)


    # PLOTTING OVs
    # main_par_plot_ovs_specific_tile_pair(exp)
    # main_plot_ovs_all_tilepairs(exp)
    # plot_ovs_from_out_or_inf_file(exp)


    # FIX COARSE OFFSETS
    # main_fix_outliers_and_infinities(exp)




