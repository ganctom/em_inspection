from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import functools as ft
import gc
from math import isclose
from zipfile import BadZipFile

import jax
import jax.numpy as jnp
import logging

from matplotlib import pyplot as plt
import numpy as np
import numpy.typing as npt
import skimage
from pathlib import Path
import pickle

from scipy import ndimage
from skimage.metrics import structural_similarity as ssim
from sofima import mesh, stitch_rigid, stitch_elastic, warp, flow_utils
import time
from typing import Union, Optional, Any, Dict, Tuple, Iterable

import experiment_configs as cfg
import inspection_utils_refactor as utils
import mask_utils as mutils
from parameter_config import WarpConfigStitching, MeshIntegrationConfig, RegistrationConfig
from schema import InspectionSchema as IS
from Tile_refactored import Tile


### Set up logging
logging.basicConfig(level=logging.DEBUG)
# logging.basicConfig(level=logging.INFO)
# logging.basicConfig(level=logging.WARNING)

UniPath = Union[str, Path]
TileXY = tuple[int, int]
Vector = Union[tuple[int, int], tuple[int, int, int], Union[tuple[int], tuple[Any, ...]]]  # [z]yx order
GridXY = tuple[Any, Any, Any]
TileFlow = Dict[TileXY, np.ndarray]
TileOffset = Dict[TileXY, Vector]
TileMap = Dict[TileXY, np.ndarray]
FineFlow = Union[Tuple[TileFlow, TileOffset], None]
FineFlows = Tuple[Optional[FineFlow], Optional[FineFlow]]
MaskMap = Dict[TileXY, Optional[np.ndarray]]
TileFlowData = Tuple[np.ndarray, TileFlow, TileOffset]
MarginOverrides = Dict[TileXY, Tuple[int, int, int, int]]


class DataServiceError(Exception):
    """Base exception for the entire data service domain."""
    pass

class SectionInfrastructureError(DataServiceError):
    """Raised when critical section files are missing or corrupted."""
    def __init__(self, section_num: int, message: str):
        self.section_num = section_num
        super().__init__(f"[Section {section_num}] {message}")


@ft.lru_cache(maxsize=32)
def cached_read_image(path: str):
    # This ensures that if the same tile is requested twice,
    # it returns the numpy array from RAM instantly.
    return skimage.io.imread(path)

@dataclass(frozen=False)
class CoarseStitchConfig:
    """Encapsulates hyper-parameters for rigid stitching alignment."""
    overlaps_xy: Tuple[Tuple[int, ...], Tuple[int, ...]] = ((200, 300), (200, 300))
    min_range: Tuple[int, ...] = (10, 100, 0)
    min_overlap: int = 20
    filter_size: int = 10
    apply_clahe: bool = True
    clip_limit: float = 2.0
    kernel_size: int = 128

    @property
    def clahe_params(self) -> dict[str, Any]:
        return {
            "clip_limit": self.clip_limit,
            "kernel_size": self.kernel_size,
        }

class Section:
    def __init__(self, path: Union[Path, str]):

        self.path = Path(utils.cross_platform_path(str(path)))
        self.section_num = int(str(self.path.name).split("_g")[0][1:])
        if not self.path.is_dir():
            m = f"Section init failed: input path is not a directory or does not exist: \n {path}"
            raise SectionInfrastructureError(self.section_num, m)

        self.path_stitched: Path = self.resolve_dir_stitched()
        self.image: np.ndarray | None = None
        self.path_cxy = str(self.path / IS.FILE_COARSE_OFFSETS)
        self.path_section_yaml = str(self.path / IS.FILE_SECTION_CONFIG)
        self.path_margin_masks = str(self.path / IS.FILE_MARGIN_MASKS)
        self.path_cmesh = str(self.path / IS.FILE_COARSE_MESH)
        self.path_thumb = self.resolve_path_thumb()
        self.path_fmesh = str(self.path / IS.FILE_MESHES)

        self.tile_id_map: npt.NDArray[np.int_] | None = None
        self.tile_shape = utils.get_tile_shape(self.path_section_yaml)
        self.tile_dicts: Optional[dict[int, str]] = None

        self.mesh_offsets: Optional[np.ndarray[float]] = None
        self.cxy: Optional[np.ndarray[float]] = None
        self.coarse_mesh: Optional[np.ndarray[float]] = None
        self.fflows: Optional[FineFlows] = None  # flow array is 4-dim (y, x, peak sharpness, peak ratio)
        self.fflows_recon: Optional[FineFlows] = None  # flow array is 2-dim (y, x)
        self.fmesh: Dict[TileXY, np.ndarray] | None = None

        self.mask_map: MaskMap | None = None
        self.roi_mask_map: MaskMap = {}
        self.smr_mask_map: MaskMap = {}
        self.tile_map: MaskMap | None = None
        self.margin_masks: MaskMap | None = None

        self.path_thumb = self.resolve_path_thumb()
        self.thumb: np.ndarray | None = None
        self.height: int | None = None
        self.width: int | None = None

    @property
    def section_shape(self) -> tuple[int, int]:
        """The shape of the section as (height, width)."""
        if self.tile_id_map is None:
            self.read_tile_id_map()
        return self.tile_id_map.shape


    def resolve_dir_stitched(self) -> Path:
        return self.path.parent.parent / IS.DIR_STITCHED / (str(self.path.name) + ".zarr")


    def feed_section_data(self):
        self.tile_dicts = utils.get_tile_dicts(self.path)
        self.read_tile_id_map()
        _ = self.get_coarse_mat()
        return


    def get_coarse_mat(self) -> Optional[np.ndarray]:
        """
        Load coarse matrix (cx, cy) from file if it exists and is readable.
        Returns (2,) array or None if file is missing / corrupted.
        """
        path = Path(self.path_cxy)

        if not path.is_file():
            raise FileNotFoundError(f"Coarse matrix file does not exist: {path}")

        try:
            data = utils.read_coarse_mat(path)

            # Most common failure modes guarded here
            if not hasattr(data, 'cx') or not hasattr(data, 'cy'):
                raise ValueError("Coarse data missing 'cx' or 'cy' attribute")

            cx = data.cx
            cy = data.cy

            cxy = np.asarray((cx, cy), dtype=float)
            self.cxy = cxy
            return cxy

        except Exception as exc:
            logging.warning(
                f"Section {self.section_num}: failed to read coarse offsets {path.name!r} "
                f"→ {type(exc).__name__}: {exc}"
            )
            return None


    def resolve_path_thumb(self) -> str:
        ext = f'_mini.jpg'
        name_end = "_" + str(self.path.name).split("_")[1]
        zfilled = str(self.section_num).zfill(5)
        new_name = "s" + zfilled + name_end
        thumb_fn = self.path.parent.parent / IS.DIR_INSPECTION / IS.DIR_DOWNSCALED / (new_name + ext)
        return str(thumb_fn)


    def verify_tile_id_map(self, print_ids: bool = False) -> bool:

        # Get tile IDs from section yaml file
        yaml_tile_ids: set[int] = set(utils.get_tile_ids_from_yaml(self.path))

        if not yaml_tile_ids:
            logging.warning(f'Verify tile_id_map: No tile IDs found in section .yaml file.')
            return False

        # Get tile IDs form section tile_id_map.json
        if not self.tile_id_map:
            self.read_tile_id_map()

        if not isinstance(self.tile_id_map, np.ndarray):
            logging.warning(f'Verify tile_id_map: No tile IDs found in section tile_id_map.json')
            return False

        map_ids = set(np.unique(self.tile_id_map))
        map_ids.discard(-1)

        eq = yaml_tile_ids == map_ids
        if not eq and print_ids:
            self._log_id_mismatch(self.section_num, yaml_tile_ids, map_ids)

        return eq


    @staticmethod
    def _log_id_mismatch(sec_num, yaml_tile_ids, tile_id_map_ids):
        ids = yaml_tile_ids.symmetric_difference(tile_id_map_ids)
        logging.warning(f'section s{sec_num} yaml tile IDs: {sorted(list(yaml_tile_ids))}')
        logging.warning(f'section s{sec_num} tile_id_map IDs: {sorted(list(tile_id_map_ids))}')
        logging.warning(f'missing s{sec_num} tile ids: {sorted(list(ids))}')


    def read_tile_id_map(self) -> None:
        fp = self.path / IS.FILE_TILE_ID_MAP
        try:
            self.tile_id_map = utils.get_tile_id_map(fp)
        except (FileNotFoundError, ValueError) as e:
            logging.error(f"Failed to load tile-id map for section {self.section_num}: {e}")


    def downscale_section(self, factor: float) -> Optional[np.ndarray]:
        """Downscale the section/image by the specified factor and store as thumbnail."""
        if self.image is None:
            self.image = self.load_image()

        if self.image is None:
            logging.warning("No image available for downscaling.")
            return None

        try:
            if isclose(factor, 1.0):
                return self.image
            self.thumb = utils.downscale_image(self.image, factor)
            logging.debug(f"Thumbnail shape: {self.thumb.shape}")
            return self.thumb
        except ValueError as e:
            logging.error(f"Downscaling failed: {e}")
            return None


    def load_image(self) -> Optional[np.ndarray]:

        if self.path.resolve().suffix == '.tif':
            data = cached_read_image(str(self.path))

        elif self.path.resolve().suffix == '.zarr':
            fp = self.path / '0'
            logging.info(f'Loading: {fp}')
            data = utils.read_zarr_volume(fp)
        else:
            logging.info(f'Loading: {self.path_stitched}')
            data = utils.read_zarr_volume(self.path_stitched)

        if data is None:
            logging.warning(f'Load image: failed to load s{self.section_num}.')
            return None

        self.image = np.asarray(data['0'])

        try:
            self.height, self.width = self.image.shape
        except ValueError as _:
            logging.warning(f'Loading s{self.section_num} image-data failed: Wrong image dimensionality.')
            return None

        logging.info(f'Image of section s{self.section_num} loaded.')
        return self.image


    def close_resource(self):
        """Explicitly drop references to Zarr arrays to close background threads."""
        try:
            if hasattr(self.image, 'store'):
                self.image.store.close()
        except:
            pass
        self.image = None
        # Force a small sleep to allow asyncio loop to heartbeat
        time.sleep(0.1)


    def get_coarse_mesh_offset(self, tile_id: int, axis: int = 0) -> Optional[Vector]:
        if self.tile_id_map is None:
            self.feed_section_data()

        coord = np.where(self.tile_id_map == tile_id)
        try:
            y, x = int(coord[0][0]), int(coord[1][0])
        except IndexError:
            return None

        co = self.mesh_offsets[axis, :, y, x]

        # Convert to a tuple of integers, handling np.nans
        co = tuple(int(x) if not (np.isinf(x) | np.isnan(x)) else x for x in co)
        logging.debug(f'tile_id_map: {self.tile_id_map}')
        logging.debug(f'y, x: {y, x}')
        logging.debug(f'loaded offset: {co}')
        return co


    def load_coarse_mesh(self) -> None:
        try:
            with open(self.path_cmesh, 'rb') as f:
                self.coarse_mesh = pickle.load(f)
            logging.info(f"s{self.section_num} coarse mesh loaded")
        except EOFError:
            print("EOFError: Ran out of input while reading the pickled data.")
        except FileNotFoundError:
            print(f"File '{self.path_cmesh}' not found.")
        except Exception as e:
            print(f"An error occurred while reading cmesh {self.path_cmesh}: {e}")


    def build_margin_masks(
            self,
            grid_shape: tuple[int, int],
            margin: int = 20,
            rim_size: int = 60,
            overwrite: bool = False,
            mesh_config: Optional[mesh.IntegrationConfig] = None
    ) -> None:
        """ Creates masks for section rendering.

        Margin masks allow to render overlap regions with better quality. Charging
        and deformations are most often related to multiple-exposed regions. Margin
        masks build on this fact and assign higher rendering priority to image-data
        acquired on fresh sample surface. Procedure requires coarse offsets to be
        computed and saved in advance.

        grid_shape: Total number of rows and columns in the SBEMimage grid
        margin: masks deformed borders of tiles due to elastic transformation
        rim_size: Size of safety margin added to the coarse offset
                to avoid holes in warped image. Defaults to 60 pixels.
        """

        def _tile_mask_junction(
                tile_id: int,
                row_is_odd: bool,
                grid: np.ndarray,
                rim: int,
                min_rim: int = 5,
                n_smr_lines: int = 40
        ) -> Optional[np.ndarray[bool]]:
            """Create tile mask for rendering

            :param n_smr_lines:
            :param rim: Size of safety margin added to the coarse offset
                        to avoid holes in warped image.
            :param min_rim: minimal masked extent from each edge of a tile
            """

            mask = np.full(self.tile_shape, fill_value=True)
            y, x = np.where(tile_id == grid)
            y, x = int(y[0]), int(x[0])

            # Determine the next tile ID based on row parity
            try:
                tid = grid[y, x + (1 if row_is_odd else -1)]
            except IndexError:
                tid = -1

            if row_is_odd:
                # if margin != 0:
                #     mask[:, :margin] = False
                if tid != -1:
                    offset = self.get_coarse_mesh_offset(tile_id)
                    dx, dy = mutils.eval_(offset[0], rim, min_rim, margin), offset[1]
                    if dy >= 0:
                        dyr = dy + rim if dy + rim > min_rim else min_rim
                        # print(f'tile_id: {tile_id} dyr+: {dyr} dx: {dx}')
                        mask[dyr:, dx:] = False
                    else:
                        dyr = dy - rim if abs(dy - rim) > min_rim else -min_rim
                        # print(f'tile_id: {tile_id} dyr-: {dyr} dx: {dx}')
                        mask[:dyr, dx:] = False

            # Even rows
            else:
                # if margin != 0:
                #     mask[:, -margin:] = False
                if tid != -1:
                    offset = self.get_coarse_mesh_offset(tile_id - 1)
                    dx, dy = mutils.eval_(offset[0], rim, min_rim, margin), offset[1]
                    if dy >= 0:
                        dyy = int(-dy - rim)
                        dyr = dyy if abs(dyy) > min_rim else -min_rim
                        mask[:dyr, :abs(dx)] = False
                    else:
                        dyy = int(abs(dy) + rim)
                        dyr = dyy if dyy > min_rim else min_rim
                        mask[dyr:, :abs(dx)] = False

            # Set the top tile-edges mask

            # Mask elastic deformation on bottom edge  (WHY?)
            if margin != 0:
                try:
                    tid_nn_y = int(grid[y + 1, x])
                except IndexError:
                    tid_nn_y = -1
                if tid_nn_y != -1:
                    mask[-margin:, :] = False

            # Mask top tile-edges
            try:
                tid_nn_y = int(grid[y - 1, x])
            except IndexError:
                tid_nn_y = -1

            if tid_nn_y != -1:
                offset = self.get_coarse_mesh_offset(tid_nn_y, axis=1)
                dx, dy = offset[0], mutils.eval_(offset[1], rim, min_rim, margin)
                if tile_id not in (400000,):
                    dy = min(offset[1] + rim, 0)  # Testing phase
                    # dy = offset[1]
                else:
                    dy = min(offset[1] + rim + 16, 0)  # Testing phase

                mask[:n_smr_lines] = False  # Testing phase

                if dx >= 0:
                    dxr = int(dx + rim) if int(dx + rim) != 0 else min_rim
                    # print(f'tile_id: {tile_id} dxr-: {dxr} dxy: {dx},{dy}')
                    mask[:abs(dy), :-dxr] = False

                else:
                    dxr = int(abs(dx) + rim) if int(abs(dx) + rim) != 0 else min_rim
                    # print(f'tile_id: {tile_id} dxr-: {dxr} dxy: {dx},{dy}')
                    mask[:abs(dy), dxr:] = False

            return mask

        def _create_margin_masks(tile_space: tuple[TileXY], rim: int):

            self.margin_masks = {}

            sbem_grid = mutils.create_sbem_grid(grid_shape, self.tile_id_map)
            for tile_xy in tile_space:
                x, y = tile_xy
                tile_id = int(self.tile_id_map[y, x])

                # Find the indices of the tile_id in sbem_grid
                indices = np.where(tile_id == sbem_grid)
                if len(indices[0]) == 0:  # Tile not found in sbem_grid
                    continue

                row, col = indices[0][0], indices[1][0]
                odd_row = row % 2 != 0  # Checking for odd row directly

                self.margin_masks[tile_xy] = _tile_mask_junction(tile_id, odd_row, sbem_grid, rim)
            return

        def _store_margin_masks():
            if self.margin_masks is None:
                logging.warning(f's{self.section_num} skipping storing None margin masks.')
                return
            data = {str(k): v for k, v in self.margin_masks.items()}
            logging.debug(f'Storing margin masks to: {self.path_margin_masks}')
            np.savez_compressed(self.path_margin_masks, **data)
            return

        if Path(self.path_margin_masks).exists() and not overwrite:
            print('Skipping margin mask computation. File exists and overwriting is disabled.')
            self.margin_masks = utils.load_mapped_npz(self.path_margin_masks)
            return

        if self.tile_id_map is None:
            self.feed_section_data()

        if self.coarse_mesh is None:
            self.load_coarse_mesh()

        if self.mesh_offsets is None:
            self.build_mesh_offsets(mesh_config=mesh_config, overwrite=False)

        if self.mesh_offsets is None:
            logging.warning(f'Section s{self.section_num} mesh offsets could not be computed.')
            return

        tile_space = utils.build_tiles_coords(self.tile_id_map)
        _create_margin_masks(tile_space, rim_size)
        _store_margin_masks()
        return


    def build_mesh_offsets(
            self,
            mesh_config: Optional[mesh.IntegrationConfig] = None,
            overwrite: Optional[bool] = True
    ) -> None:
        """Creates coarse offset matrix from coarse mesh values

        Create coarse mesh offset array in form of individual tile offsets
        in same notation as coarse offsets. These values will be used to create
        margin overrides for section warping.
        """

        def diff_mat(mat: np.ndarray, row_mode=False) -> np.ndarray:
            if row_mode:
                result = [[np.round(mat[i][j] - mat[i - 1][j]) for j in range(len(mat[i]))] for i in range(1, len(mat))]
            else:
                result = [[np.round(mat[i][j] - mat[i][j - 1]) for j in range(1, len(mat[i]))] for i in range(len(mat))]
            return np.array(result)

        def make_mesh_offsets() -> Optional[np.ndarray]:

            if self.cxy is None:
                _ = self.get_coarse_mat()

            if Path(self.path_cmesh).exists():
                self.load_coarse_mesh()
            else:
                self.compute_coarse_mesh(mesh_config, overwrite=overwrite)

            if self.coarse_mesh is None:
                return None

            cxx = diff_mat(self.coarse_mesh[0, 0, ...], row_mode=False)
            cxy = diff_mat(self.coarse_mesh[1, 0, ...], row_mode=False)
            cyx = diff_mat(self.coarse_mesh[0, 0, ...], row_mode=True)
            cyy = diff_mat(self.coarse_mesh[1, 0, ...], row_mode=True)

            mo = np.full_like(self.cxy, fill_value=np.nan)
            nr, nc = cxx.shape
            mo[0, 0, 0:nr, 0:nc] = cxx
            mo[0, 1, 0:nr, 0:nc] = cxy

            nr, nc = cyx.shape
            mo[1, 0, 0:nr, 0:nc] = cyx
            mo[1, 1, 0:nr, 0:nc] = cyy

            mask = np.isnan(self.cxy)
            mo[mask] = np.nan
            return mo

        self.mesh_offsets = make_mesh_offsets()
        return


    def compute_coarse_mesh(self, conf: Optional[mesh.IntegrationConfig] = None, store=True, overwrite=False) -> None:

        if conf is None:
            conf = mesh.IntegrationConfig(
                dt=0.001,
                gamma=0.0,
                k0=0.0,  # unused
                k=0.1,
                stride=(1, 1),  # unused
                num_iters=1000,
                max_iters=100000,
                stop_v_max=0.001,
                dt_max=100,
            )

        if self.check_and_load_coarse_mesh() and not overwrite:
            return

        logging.info('Computing coarse mesh ...')
        try:
            cx, cy = self.get_coarse_mat()
        except TypeError as _:
            logging.warning(f's{self.section_num} coarse mesh not computed')
            return

        if cx.ndim != 4:
            cx = cx[:, np.newaxis, ...]
            cy = cy[:, np.newaxis, ...]

        self.coarse_mesh = stitch_rigid.optimize_coarse_mesh(cx, cy, conf)

        if self.coarse_mesh is None:
            logging.warning(f'Section s{self.section_num} coarse mesh not computed.')
        elif store:
            logging.info(f'Storing coarse mesh.')
            with open(self.path_cmesh, 'wb') as f:
                pickle.dump(self.coarse_mesh, f)

        return


    def check_and_load_coarse_mesh(self) -> bool:
        try:
            if Path(self.path_cmesh).exists():
                self.load_coarse_mesh()
                return self.coarse_mesh is not None
            else:
                logging.info(f"File '{self.path_cmesh}' does not exist.")
                return False
        except Exception as e:
            logging.error(f"An error occurred while checking and loading '{self.path_cmesh}': {e}")
            return False


    def get_coarse_offset(self, tile_id: int, axis: int) -> Optional[Vector]:
        if self.tile_id_map is None:
            self.feed_section_data()

        coord = np.where(self.tile_id_map == tile_id)

        try:
            y, x = int(coord[0][0]), int(coord[1][0])
            co = self.cxy[axis, :, y, x]
        except TypeError:
            logging.warning(f'Coarse offset s{self.section_num} t{tile_id} not defined!')
            return None
        except IndexError:
            logging.warning(f'Coarse offset could not be retrieved: s{self.section_num} t{tile_id} axis: {axis}')
            return None

        # Convert to a tuple of integers, handling np.nans
        co = tuple(int(x) if not (np.isinf(x) | np.isnan(x)) else x for x in co)

        logging.debug(f'tile_id_map: {self.tile_id_map}')
        logging.debug(f'y, x: {y, x}')
        logging.info(f'Loaded coarse offset: {co}')
        return co

    def plot_ov(self,
                tid_a: int,
                tid_b: int,
                shift_vec: Optional[Vector] = None,
                dir_out: Optional[UniPath] = None,
                blur: float = 0,
                show_plot=False,
                clahe=False,
                rotate_vert=False,
                store_to_root=False,
                return_img: bool = False
        ) -> Optional[np.ndarray]:

        """Visualize overlap region of a tile-pair. Shift vector must be
        computed in advance.

        :param dir_out: parent directory where overlap image will be stored
        :param shift_vec: Optional tuple of two ints
                - if None, do not plot anything
                - if any of values in the input is None, shift vector will be
                  read form cx_cy.json
                - if shift_vec is specified, stitch tile-pair using it
        :param tid_a: tile_id of the first tile
        :param tid_b: tile_id of the second tile
        :param show_plot: visualize output
        :param clahe: apply CLAHE before visualization
        :param blur: apply Gaussian blur to output image
        :param rotate_vert: rotate stored overlap of horizontal tile-pair by 90 deg
                            clockwise
        :param store_to_root: If True, save resulting image into a dir_out folder
                                otherwise create a sub-folder in dir_out.
        :param return_img: If True, return overlap image as np.ndarray
        :return: img array if return_img is set to True
        """
        assert tid_a != tid_b

        if self.tile_dicts is None:
            self.feed_section_data()

        if tid_a not in self.tile_dicts or tid_b not in self.tile_dicts:
            logging.info('plot_ov: wrong tile_ids specification')
            return None

        # Fix ordering of tiles
        tid_a, tid_b = min(tid_a, tid_b), max(tid_a, tid_b)

        path_a = self.tile_dicts[tid_a]
        path_b = self.tile_dicts[tid_b]

        if not Path(path_a).exists() or not Path(path_b).exists():
            logging.warning("Image files could not be loaded:")
            logging.warning(path_a)
            logging.warning(path_b)
            return None

        # Load image data
        img_a = cached_read_image(str(path_a))
        img_b = cached_read_image(str(path_b))
        if clahe:
            img_a, img_b = [utils.apply_clahe(img) for img in (img_a, img_b)]
        is_vert = utils.pair_is_vertical(self.tile_id_map, tid_a, tid_b)

        # Construct tile-map
        tile_map = {(0, 0): img_a}
        if is_vert:
            axis = 1
            tile_map[(0, 1)] = img_b
        else:
            tile_map[(1, 0)] = img_b
            axis = 0

        if not tile_map:
            logging.info("Tile_map is empty!")
            return None

        # Get shift vector if not specified in input
        if shift_vec is None or None in shift_vec:
            shift_vec = utils.get_shift(self.cxy, self.tile_id_map, tid_a, axis)
            logging.info(f's{self.section_num} loaded coarse offset: {shift_vec}')

        # Visualize and store overlap image
        if shift_vec is None:
            logging.info(f"t{tid_a}: nothing to plot")
            return None

        path_plot = None  # Do not store the OV image to HDD
        if dir_out is not None:
            dir_ov = Path(dir_out)
            str_tid_a, str_tid_b = f't{tid_a:04d}', f't{tid_b:04d}'
            if not store_to_root:
                dir_ov = Path(dir_out) / f'{str_tid_a}_{str_tid_b}'
                utils.create_directory(dir_ov)

            # Create plot filename
            plot_name = f's{self.section_num:04d}_{str_tid_a}_{str_tid_b}_ov.jpg'
            path_plot = str(dir_ov / plot_name)
            logging.info(f'plotting: {path_plot}')

        # Get stitched image
        img_pair = utils.plot_tile_pair(
            tile_map, shift_vec, show_plot=False,
            path_plot=None, blur=1.0, img_only=True
        )

        # Crop overlap from stitched image and save it
        if img_pair is not None:
            ov_img = utils.plot_thin_image(
                img_pair,
                is_vert,
                path_plot,
                show_plot,
                blur,
                rotate_vert,
                return_array=return_img
            )
            if return_img:
                return ov_img
        return None

    def load_image_pair(self,
                        id_a: int,
                        id_b: int,
                        clahe: bool = True,
                        blur_fct: float = 1.0
                        ) -> Optional[tuple[Tile, Tile]]:

        if self.tile_dicts is None:
            self.feed_section_data()

        tiles = []
        for tid in (id_a, id_b):
            try:
                tile = Tile(self.tile_dicts[tid])
                tile.load_image(clahe)
                if blur_fct > 1:
                    tile.img_data = skimage.filters.gaussian(tile.img_data, sigma=blur_fct)
                tiles.append(tile)
            except KeyError:
                logging.warning(f'Tile t{tid} not present in s{self.section_num}')
                return None

        return tuple(tiles)



    def plot_tile_pair(self, tid_a: int, tid_b: int, clahe: bool = True,
                       shift_vec: Optional[Vector] = None, masking=False,
                       blur: float = 1.0, img_only=False) -> None:

        logging.info(f'Plotting t{tid_a}-t{tid_b} tiles')

        assert tid_a != tid_b
        if self.tile_dicts is None:
            self.feed_section_data()

        tiles = self.load_image_pair(tid_a, tid_b, clahe=clahe)
        if tiles is None:
            logging.warning('Tile reading failed')
            return None

        a, b = tiles
        is_vert = utils.pair_is_vertical(self.tile_id_map, tid_a, tid_b)
        axis = 1 if is_vert else 0

        # Get shift vector if not specified in input
        if shift_vec is None or None in shift_vec:
            shift_vec = utils.get_shift(self.cxy, self.tile_id_map, tid_a, axis)
            logging.info(f's{self.section_num} loaded coarse offset: {shift_vec}')

        if shift_vec is None:
            print(f's{self.section_num} t{tid_a}_t{tid_b}: shift vector contains Inf value.')
            shift_vec = (np.inf, np.inf)

        # Load and apply masks
        if masking:
            def apply_mask(image, mask):
                modified = image.copy()
                modified = modified.astype(np.float32)
                modified[mask] = np.nan
                return modified

            self.load_masks()
            self.read_tile_id_map()

            default_mask = np.full_like(a, fill_value=False, dtype=np.bool_)

            y, x = np.where(tid_a == self.tile_id_map)
            mask_a = self.mask_map.get((int(x[0]), int(y[0])), default_mask)

            y, x = np.where(tid_b == self.tile_id_map)
            mask_b = self.mask_map.get((int(x[0]), int(y[0])), default_mask)

            a.img_data = apply_mask(a.img_data, mask_a)
            b.img_data = apply_mask(b.img_data, mask_b)

        # Get tile map
        tile_map = {(0, 0): a.img_data}
        if is_vert:
            tile_map[(0, 1)] = b.img_data
        else:
            tile_map[(1, 0)] = b.img_data

        # Create plot filename
        str_sec = 's' + str(self.section_num).zfill(4)
        plot_name = str_sec + '_' + str(tid_a) + '_' + str(tid_b) + '_ov.jpg'
        path_plot = str(self.path / plot_name)

        _ = utils.plot_tile_pair(tile_map, shift_vec, show_plot=False,
                                  blur=blur, path_plot=path_plot)
        return


    def load_masks(self):
        """Loads binary masks associated to each tile within section"""

        fns = IS.FILE_ROI_MASKS, IS.FILE_SMR_MASKS, IS.FILE_TILE_MASKS
        maps = self.roi_mask_map, self.smr_mask_map, self.mask_map

        for fn, i_map in zip(fns, maps):
            path_mask = self.path / fn
            if not path_mask.exists():
                logging.info(f's{self.section_num} {fn} does not exist!')
                continue
            try:
                data = np.load(path_mask, allow_pickle=True)
                for key, item in data.items():
                    i_map[eval(key)] = item if item.size != 1 else None
            except FileNotFoundError:
                logging.info(f"s{self.section_num}: {path_mask} not loaded.")
            except Exception as e:
                print(f"An error occurred: s{self.section_num} {fn}.", e)
        # self.margin_masks = utils.load_mapped_npz(self.path_margin_masks)
        return

    def refine_pyramid(self, tid_a: int, tid_b: int, masking: bool,
                       levels: int, max_ext: int, stride: int, clahe: bool, store: bool,
                       plot: bool, show_plot: bool, est_vec: Optional[Vector] = None,
                       custom_mask_params=(0, 0, 0, 0)
                       ) -> Optional[Vector]:

        """Refine the coarse offset vector between two tiles.

        Args:
            tid_a (int): Tile ID of the first tile.
            tid_b (int): Tile ID of the second tile.
            masking (bool): Load and apply ROI and smearing masks to input images.
            levels (int): number of pyramid search levels for coarse offset refinement.
            max_ext (int): Maximum extent of coarse shift vector search space.
            stride (int): Stride for search.
            clahe (bool): Whether to use CLAHE.
            store (bool): Whether to store the refined vector in cx_cy.json.
            plot (bool): Whether to plot the seam quality maps.
            show_plot (bool): Whether to show the plot.
            est_vec (Vector): Refine shift vector in the vicinity of predefined coarse offset.
            custom_mask_params (Tuple): Each number defines custom mask for ov in eval_ov (top, bottom, left, right)

        Returns:
            Optional[Vector]: Refined offset vector if successful, else None.

        """
        fmsg = f's{self.section_num:04d} t{tid_a}-t{tid_b}'

        # Load image data and original coarse shift vector
        try:
            tile_map, _, is_vert, orig_co = self.get_masked_img_pair(
                tid_a, tid_b, masking=masking, blur_fct=6.0, clahe=clahe,
                shift_vec=None, custom_params=custom_mask_params
            )
            axis = 1 if is_vert else 0
        except TypeError as _:
            print(f'Refine pyramid for {fmsg} failed: masked tile-pair could not be loaded.')
            return None

        t1, t2 = Tile(self.tile_dicts[tid_a]), Tile(self.tile_dicts[tid_b])
        t1.img_data, t2.img_data = tile_map.values()

        msg = f'{fmsg}: original shift vector: {orig_co}'
        logging.info(msg), print(msg)

        # Treat non-reliable offsets and estimate mean shift vector from neighboring sections
        # est_vec = None  # !!!
        # if est_vec is None:
        #     est_vec = self.analyze_offset(orig_co, tid_a, axis, before=10, after=10, std_band=4)
        #
        #     shift_vec = est_vec if est_vec is not None else orig_co
        #     if est_vec is None:
        #         msg = 'Mean shift vector from neighbors could not be estimated. Trying original one:'
        #         print(f'{msg} {orig_co}'), logging.info(msg + f' {orig_co}')
        #     else:
        #         msg = f'{fmsg}: mean shift vector from neighbors: {tuple(est_vec)}'
        #         print(msg), logging.info(msg)
        # elif est_vec == (1000, 1000):
        #     shift_vec = orig_co
        #     msg = f'{fmsg}: refining based on original coarse offset: {shift_vec}'
        #     print(msg), logging.info(msg)
        # else:
        #     shift_vec = est_vec
        #     msg = f'{fmsg}: refining based on custom coarse offset: {shift_vec}'
        #     print(msg), logging.info(msg)

        # Treat non-reliable offsets and estimate mean shift vector from neighboring sections
        if est_vec is None:
            est_vec = self.analyze_offset(orig_co, tid_a, axis, before=10, after=10, std_band=4)

            if est_vec is None:
                shift_vec = orig_co
                msg = "Mean shift vector from neighbors could not be estimated. Trying original one:"
            else:
                shift_vec = est_vec
                msg = f"{fmsg}: mean shift vector from neighbors: {tuple(map(int, est_vec))}"
        else:
            if est_vec == (1000, 1000):
                shift_vec = orig_co
                msg = f"{fmsg}: refining based on original coarse offset: {shift_vec}"
            else:
                shift_vec = est_vec
                msg = f"{fmsg}: refining based on custom coarse offset: {shift_vec}"

        # Log and print the message
        logging.info(msg), print(msg)

        # Terminate in case no mean shift vector could be estimated for Inf orig. coarse offset
        if np.inf in shift_vec:
            logging.warning(f'{fmsg}: coarse offset refinement not performed.')
            return None

        # Force using original vector
        # shift_vec = orig_co

        # Run refining using pyramidal search
        for i, (max_ext, stride) in enumerate(utils.get_pyramid(
                levels, max_ext, stride)
        ):
            try:
                shift_vec, interp_data = self.refine_coarse_offset(
                    shift_vec, tid_a, tid_b, (t1, t2), is_vert,
                    max_ext, stride, orig_co, tile_map
                )
            except TypeError as _:
                shift_vec = (np.nan, np.nan)  # Refining offset failed for some reason
                continue
            if plot:
                path_plot = str(self.path / str(f'refined_offsets_{fmsg}_{i}.jpg'))
                utils.plot_refined_grid(interp_data, path_plot, show_plot)

        # # Evaluate new seam quality
        # kwargs = dict(tile_map=tile_map, img_a=t1.img_data, img_b=t2.img_data,
        #               tid_a=tid_a, tid_b=tid_b, orig_co=orig_co, new_co=shift_vec,
        #               is_vert=is_vert)
        #
        # # quality_passed: bool = self.ov_quality_check(utils.eval_ov_static, kwargs)
        # # quality_passed: bool = self.ov_quality_check(self.eval_seam, kwargs)
        quality_passed = True

        # Store refined vector into cx_cy.json only if vector does not contain Inf values
        if store and np.inf not in shift_vec and quality_passed:
            y, x = np.where(self.tile_id_map == tid_a)
            coord4d = (axis, 0, int(y[0]), int(x[0]))
            # shift_vec = (-278, 20)  # To write custom offset into cxcy.json
            self.replace_coarse_offset(coord4d, shift_vec, store)

        print(f'{fmsg}: orig. shift vec.: {orig_co}, new shift vec.: {shift_vec}')

        # shift_vec = orig_co  # for inf plotting
        return shift_vec



    def replace_coarse_offset(self,
                              coord: tuple[int, ...],
                              offset: Union[float, tuple[float, float]],
                              store: bool) -> None:
        """
        Replace coarse offsets in cx_cy.json at the specified coordinate
        with the given offset vector.

        Parameters:
        - coord (Tuple[int, int, int, int]): The 4D coordinate (C, Z, X, Y).
        - offset (Union[float, Tuple[float, float]]): The offset value or a tuple of offsets.

        Returns:
        - None
        """

        _ = self.path / 'cx_cy.json'
        assert len(coord) == 4

        c, z, y, x = coord

        if c == 0:
            tile_id_a = self.tile_id_map[y, x]
            tile_id_b = self.tile_id_map[y, x + 1]
        else:
            tile_id_a = self.tile_id_map[y, x]
            tile_id_b = self.tile_id_map[y + 1, x]

        logging.info(f"Section {self.section_num} tile-pair IDs: {int(tile_id_a), int(tile_id_b)}")

        # Read coarse mat if not already loaded
        if self.cxy is None and Path(self.path_cxy).exists():
            _, cx, cy = utils.read_coarse_mat(Path(self.path_cxy))
            self.cxy = np.array((cx, cy))

        # Check if there's anything to replace
        if self.cxy is None:
            print('Nothing to replace. Coarse offsets .json is missing.')
            return

        if len(offset) == 2:
            self.cxy[c, :, y, x] = offset
            logging.info(f'Replacing original coarse offset with {offset}')
        else:
            self.cxy[coord] = offset
            logging.info(f'Replacing coarse vector {self.cxy[coord]} at '
                         f'coordinate: {coord}')

        # Save coarse mat
        if store:
            utils.save_coarse_mat(self.cxy, Path(self.path_cxy).parent, file_format="json")
        else:
            logging.warning('Storing is disabled. Coarse offset will not be written out.')
        return

    def get_masked_img_pair(self, tid_a: int, tid_b: int,
                            masking: bool,
                            clahe: bool = True,
                            blur_fct: float = 1.0,
                            shift_vec: Optional[Vector] = None,
                            custom_params: tuple[int, int, int, int] = (0, 0, 0, 0)
                            ) -> Optional[tuple[TileMap, TileXY, bool, Vector]]:

        def get_mask(x, y, mask_map, default_mask, custom_mask):
            if custom_mask:
                return np.copy(default_mask)
            ma = mask_map.get((x, y), default_mask)
            return default_mask if ma is None else ma

        def apply_mask(image, mask):
            modified = image.copy()
            modified = modified.astype(np.float32)
            modified[mask] = np.nan
            return modified

        def make_custom_mask(input_mask: np.ndarray,
                             top: int,
                             bottom: int,
                             left: int,
                             right: int):
            """Mask lines or columns (for 'eval_ov' procedure)"""
            if all(custom_params):
                if tid_b == utils.get_vert_tile_id(self.tile_id_map, tid_a):
                    top, bottom = 0, 0
                else:
                    left, right = 0, 0

            if top == 0:
                input_mask[:, -right:] = True
                input_mask[:, :left] = True
            if left == 0:
                input_mask[:top] = True
                input_mask[-bottom:] = True
            return input_mask

        # Determine tile-pair orientation
        msg = f'Specified tile_ids {tid_a}, {tid_b} are not neighbors!'
        assert tid_a != tid_b, msg
        is_vert = utils.pair_is_vertical(self.tile_id_map, tid_a, tid_b)
        if is_vert is None:
            logging.warning(msg)
            return None

        if self.tile_dicts is None:
            self.feed_section_data()

        tiles = self.load_image_pair(tid_a, tid_b, clahe, blur_fct)
        if tiles is None:
            logging.warning(f'Unable to load tile image data (s{self.section_num}: t{tid_a}, t{tid_b}).')
            return None

        # Get shift vector if not specified in input
        axis = 1 if is_vert else 0
        if shift_vec is None or None in shift_vec:
            shift_vec = self.get_coarse_offset(tid_a, axis)
            logging.info(f's{self.section_num} t{tid_a}-t{tid_b} loaded coarse offset: {shift_vec}')

        if shift_vec is None:
            print(f's{self.section_num} t{tid_a}_t{tid_b}: shift vector contains Inf value.')
            shift_vec = (np.inf, np.inf)

        a, b = tiles
        # Load and apply masks
        if masking:
            custom_mask = any(custom_params)
            if len(self.mask_map) == 0 and not custom_mask:
                self.load_masks()

            # Get masks
            default_mask = np.full_like(a.img_data, fill_value=False, dtype=np.bool_)
            ya, xa = np.where(tid_a == self.tile_id_map)
            yb, xb = np.where(tid_b == self.tile_id_map)
            mask_a = get_mask(xa[0], ya[0], self.roi_mask_map, default_mask, custom_mask)
            mask_b = get_mask(xb[0], yb[0], self.roi_mask_map, default_mask, custom_mask)

            # Custom mask definition
            if custom_mask:
                mask_a = make_custom_mask(mask_a, *custom_params)
                mask_b = make_custom_mask(mask_b, *custom_params)

            a.img_data = apply_mask(a.img_data, mask_a)
            b.img_data = apply_mask(b.img_data, mask_b)

        # Get tile map
        tile_map = {(0, 0): a.img_data}
        if is_vert:
            tile_map[(0, 1)] = b.img_data
            pair_id_map = np.array([[tid_a], [tid_b]])
        else:
            tile_map[(1, 0)] = b.img_data
            pair_id_map = np.array([[tid_a, tid_b]])

        tile_space: tuple[int, ...] = np.shape(pair_id_map)
        # tile_space = (0, 0)
        # tile_map = {}

        return tile_map, tile_space, is_vert, shift_vec



    def analyze_offset(self, offset: Vector, tile_id: int, axis: int,
                       before=15, after=15, std_band=6) -> Optional[Vector]:

        try:
            mean_offset, std = self.estimate_offset(tile_id, axis, before, after)
        except TypeError:
            return None

        # Check if offset is within bounds
        mean_offset, std = map(np.array, (mean_offset, std_band))
        low_bound = mean_offset - std * std_band
        up_bound = mean_offset + std * std_band

        if np.any((offset > up_bound) | (offset < low_bound)):
            m1 = f"Original coarse offset is out of stddev. bounds."
            b1 = (up_bound[0] - mean_offset[0], low_bound[0] - mean_offset[0])
            b2 = (up_bound[1] - mean_offset[1], low_bound[1] - mean_offset[1])
            vec1 = f"{mean_offset[0]:g} +/- {tuple(map(int, b1))}"
            vec2 = f"{mean_offset[1]:g} +/- {tuple(map(int, b2))}"
            m2 = f"Average estimated offset x: {vec1}, y: {vec2}"
            m12 = (m1, m2) if np.inf not in offset else (m2,)
            for m in m12:
                print(m)
                logging.info(m)

        return mean_offset


    def estimate_offset(self,
                        tile_id: int,
                        axis: int,
                        before: int = 10,
                        after: int = 10
                        ) -> Optional[tuple[Vector, Vector]]:

        """Compute mean coarse offset vector from neighboring sections.

        Args:
            tile_id (int): Tile for which the mean coarse shift should be computed.
            axis (int): Orientation of a tile pair (to be used for slicing cxy).
            before (int, optional): Number of sections before the current section
                                    to consider. Defaults to 10.
            after (int, optional): Number of sections after the current section
                                    to consider. Defaults to 10.

        Returns:
            Optional[Tuple[int, int]]: Mean coarse offset vector if computed, else None.
        """

        def get_sec_dirs() -> list[str]:
            exp_dir = str(Path(self.path).parent)
            exp_dir = Path(utils.cross_platform_path(exp_dir))
            grid_num = int(Path(self.path).name[-1])

            # Select sections to be used for mean vector estimation
            sec_num = utils.get_section_num(self.path)
            start = max(sec_num - before, 0)
            end = sec_num + after
            sec_nums = set(range(start, end))

            dirs = [str(exp_dir / f"s{num}_g{grid_num}") for num in sec_nums]
            return dirs

        def aggregate_offsets(sec_dirs: list[str]) -> list[np.ndarray[float]]:
            shift_vecs = []
            for sec_dir in sec_dirs:
                if Path(sec_dir).exists():
                    sec = Section(sec_dir)
                    sec.read_tile_id_map()
                    _ = sec.get_coarse_mat()
                    try:
                        coord = np.where(sec.tile_id_map == tile_id)
                        y, x = int(coord[0][0]), int(coord[1][0])
                    except IndexError:
                        continue

                    try:
                        shift_vec = sec.cxy[axis, :, y, x]
                    except TypeError:
                        continue

                    # Omit Inf offsets to be able to compute mean vector
                    if shift_vec is not None and not any(np.isinf(shift_vec)):
                        shift_vecs.append(shift_vec)
            return shift_vecs

        section_dirs = get_sec_dirs()
        vecs = aggregate_offsets(section_dirs)

        if len(vecs) == 0:
            logging.warning(f's{self.section_num} t{tile_id}: average coarse offset could not be estimated.')
            return None

        # np.nanmean is necessary due to missing offset values if tile has no neighbor
        if np.all(np.isnan(np.array(vecs))):
            logging.warning(f's{self.section_num} t{tile_id}: only NaN values found during mean vec. estimation')
            return None

        mean = np.nanmean(np.array(vecs), axis=0)
        std = np.nanstd(np.array(vecs), axis=0)
        mean = tuple(map(int, np.round(mean)))
        std = tuple(map(int, np.round(std)))

        return mean, std


    def refine_coarse_offset_eval_ov(
            self,
            offset: Vector,
            tile_pair: tuple[Tile, Tile],
            is_vert: bool,
            max_ext: int,
            stride: int,

    ) -> Optional[tuple[Vector, tuple[GridXY, GridXY]]]:

        # Create set of shift vectors
        shift_grid, gx, gy = utils.get_shift_grid(max_ext, stride, offset, is_vert)

        # Refine offset and return best result
        gz = []
        for offset in shift_grid:
            seam_ssim = self.eval_ov(tile_pair=tile_pair, offset=offset)
            if seam_ssim is None:
                break
            seam_res = 1 / seam_ssim
            gz.append(seam_res)
        if not gz:
            logging.warning(f'Refining offset not successful. Check image masks and consider disabling them.')
            return None

        # Select best offset from computed offset field
        best_offset, refine_data = utils.interp_coarse_grid((gx, gy), gz)
        logging.debug(f'estimated offset: {best_offset}')

        return best_offset, refine_data


    def refine_coarse_offset(
            self,
            offset: Vector,
            tid_a: int,
            tid_b: int,
            tile_pair: tuple[Tile, Tile],
            is_vert,
            max_ext,
            stride,
            orig_co: Optional[Vector] = None,
            tile_map: Optional[TileMap] = None,
    ) -> Optional[tuple[Vector, tuple[GridXY, GridXY]]]:

        # Create set of shift vectors
        shift_grid, gx, gy = utils.get_shift_grid(max_ext, stride, offset, is_vert)

        # Refine offset and return best result
        gz = []
        for offset in shift_grid:
            # # Method 1
            seam_ssim = self.eval_ov(tile_pair=tile_pair, offset=offset)
            if seam_ssim is None:
                break
            seam_res = 1 / seam_ssim

            # # # Method 2
            # seam_res = self.eval_seam(tile_map, tid_a, tid_b, offset, is_vert)
            # seam_res = seam_res[0]

            gz.append(seam_res)
        if not gz:
            logging.warning(f'Refining offset not successful. Check image masks and consider disabling them.')
            return None

        # Select best offset from computed offset field
        best_offset, refine_data = utils.interp_coarse_grid((gx, gy), gz)
        logging.debug(f'estimated offset: {best_offset}')

        return best_offset, refine_data


    def eval_ov(
            self,
            tile_pair: tuple[Tile, Tile],
            offset: Vector,
            plot_pair=False,
            half_width=50
    ) -> float:

        def check_zero_dimension(image_array):
            return any(dim == 0 for dim in image_array.shape)

        def plot_eval_pair(a, b):
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
            ax1.imshow(a, cmap='gray')
            ax1.set_title('Image 1')
            ax2.imshow(b, cmap='gray')
            ax2.set_title('Image 2')
            plt.show()
            return

        MIN_OV_WIDTH = 15

        tile_a, tile_b = tile_pair
        logging.debug(f'eval_ov tile-pair: {tile_a.tile_id, tile_b.tile_id}')

        is_vert = utils.pair_is_vertical(
            self.tile_id_map, tile_a.tile_id, tile_b.tile_id)

        # Pre-process images
        if tile_a.img_data is None:
            tile_a.load_image(clahe=False)
        if tile_b.img_data is None:
            tile_b.load_image(clahe=False)

        tile_a.denoise().clahe()
        tile_b.denoise().clahe()

        # Use processed images for evaluation
        img_a = tile_a.processed
        img_b = tile_b.processed

        # Rotate vertical tile-pair to work with horizontal stripe
        axis = 0
        if is_vert:
            img_a = np.rot90(img_a, k=1)
            img_b = np.rot90(img_b, k=1)
            offset = (-offset[0], offset[1])
            axis = 1

        # Crop common area
        h, _ = np.shape(img_a)
        ov_a = img_a[max(0, offset[1 - axis]):min(h, h + offset[1 - axis])]
        ov_a = ov_a[:, -abs(offset[axis]):]
        ov_b = img_b[max(0, -offset[1 - axis]):min(h, h - offset[1 - axis])]
        ov_b = ov_b[:, :abs(offset[axis])]

        if check_zero_dimension(ov_a):
            logging.warning('Cropping first overlap overlap resulted in error')
            return np.nan
        if check_zero_dimension(ov_b):
            logging.warning('Cropping second overlap overlap resulted in error')
            return np.nan

        # Remove masked regions
        ov_stacked = np.rot90(np.hstack((ov_a, ov_b)), k=-1)
        ov_stacked = utils.crop_nan(ov_stacked)
        logging.debug(f'eval_ov: cropped stack ov shape {ov_stacked.shape}')

        if any((size < MIN_OV_WIDTH for size in ov_stacked.shape)):
            logging.info(f'eval_ov: s{self.section_num} cropped ov-shape is under limit ({MIN_OV_WIDTH} pixels)')
            return np.nan

        # Split stacked ov-images
        ov_ac = ov_stacked[:ov_a.shape[1]]
        ov_bc = ov_stacked[ov_a.shape[1]:]
        # utils.plot_images_with_overlay(ov_ac, ov_bc)

        # Perform crop around intended seam position
        ov_h = np.shape(ov_ac)[0]
        seam_pos = int(ov_h / 2)
        hw_ov = min(half_width, ov_h // 2)
        if ov_h > 2 * MIN_OV_WIDTH:
            ov_ac = ov_ac[seam_pos - hw_ov:seam_pos + hw_ov]
            ov_bc = ov_bc[seam_pos - hw_ov:seam_pos + hw_ov]

        # Compute SSIM over area
        ov_ac, ov_bc = map(utils.norm_img, (ov_ac, ov_bc))
        mssim = ssim(ov_ac, ov_bc)
        mssim = (mssim + 1) / 2
        logging.debug(f'mssim: {mssim:.3f}')

        if plot_pair:
            plot_eval_pair(ov_ac, ov_bc)

        return mssim



    def compute_coarse_offset(self,
                              id_a: int,
                              id_b: int,
                              refine: bool,
                              store: bool,
                              clahe: bool,
                              overlaps_xy=((200, 300), (200, 300)),
                              min_range=(10, 100, 0),
                              min_overlap=10,
                              filter_size=10,
                              masking=False,
                              max_valid_offset=350,
                              est_vec: Optional[Vector] = None,
                              custom_mask_params: tuple[int, int, int, int] = (0, 0, 0, 0),
                              co_score_lim: Optional[float] = None,
                              co_lim_dist: Optional[float] = None,
                              refine_params: Optional[dict] = None
                              ) -> Optional[Union[tuple[int, ...], np.ndarray[Any, np.dtype[Any]]]]:

        def co_score_valid(co: Optional[Vector] = None,
                           lim_val: Optional[float] = None
                           ) -> bool:
            # Compute current seam quality and skip refinement if meets criteria
            if lim_val is None:
                return False

            if np.nan not in co or np.inf not in co and co is not None:
                tile_pair = self.load_image_pair(id_a, id_b, blur_fct=6.0)
                co_score = self.eval_ov(tile_pair, co)
                if co_score > co_score_lim:
                    msg = f's{self.section_num} t{id_a}-t{id_b} coarse offset vector quality already sufficient ({co_score}>{co_score_lim})'
                    print(msg), logging.warning(msg)
                    return True
            return False

        def co_dist_valid(co: Optional[Vector] = None,
                          est_vec: Optional[Vector] = None,
                          co_lim_dist: Optional[float] = 15.
                          ) -> bool:
            # Verifies that the absolute pixel distance of current coarse offset is within limits from estimated vector

            if est_vec is None or co is None:
                return False

            abs_diff = np.abs(np.asarray(co) - np.asarray(est_vec))
            abs_dist = np.linalg.norm(abs_diff)
            vec_valid = abs_dist < co_lim_dist
            if not vec_valid:
                msg = f's{self.section_num:04d} t{id_a}-t{id_b}: coarse offset vector deviation from est. vec. too large ({int(abs_dist)} pix., limit={int(co_lim_dist)} pix.)'
                print(msg), logging.warning(msg)
            return vec_valid

        refine_params_nominal = {'masking': masking,
                                 'levels': 1,
                                 'max_ext': 50,
                                 'stride': 10,
                                 'clahe': True,
                                 'store': True,
                                 'plot': False,
                                 'show_plot': False,
                                 'est_vec': (0, 0),
                                 'custom_mask_params': (1, 1, 1, 1)
                                 }

        logging.info(f'Section s{self.section_num:04d} - computing coarse offset t{id_a} - t{id_b}')

        # Load image data
        if self.tile_dicts is None:
            self.feed_section_data()

        # Get tile-map and tile-space of a tile-pair
        is_vert = utils.pair_is_vertical(self.tile_id_map, id_a, id_b)
        if is_vert is None:
            logging.info(f'Specified tile_ids are not neighbors or one of the tile-ids are missing!')
            return

        axis = 1 if is_vert else 0

        # Refine any coarse shifts using refine pyramid method
        if refine:

            # offset = self.get_coarse_offset(id_a, axis)

            # if co_score_valid(offset, co_score_lim):
            #     return offset
            #
            # if co_dist_valid(offset, est_vec, co_lim_dist):
            #     return offset
            refine_params_op = refine_params_nominal.copy()
            if refine_params is not None:
                for k, v in refine_params.items():
                    if k in refine_params_op.keys():
                        refine_params_op[k] = refine_params[k]

            refine_params_op['tid_a'] = id_a
            refine_params_op['tid_b'] = id_b
            shift_vec = self.refine_pyramid(**refine_params_op)

        else:
            tiles = self.load_image_pair(id_a, id_b, clahe)
            if tiles is None:
                logging.debug(f'Unable to load tile image data (s{self.section_num:04d}: t{id_a}, t{id_b}).')
                return None

            tile_a, tile_b = tiles
            tile_map = {(0, 0): tile_a.img_data}
            if is_vert:
                tile_map[(0, 1)] = tile_b.img_data
                pair_id_map = np.array([[id_a], [id_b]])
            else:
                tile_map[(1, 0)] = tile_b.img_data
                pair_id_map = np.array([[id_a, id_b]])

            if not masking:
                mask_map = None
            else:
                self.load_masks()

                # For dummy mask map indices
                k0: (int, int) = tuple(np.squeeze(np.where(self.tile_id_map == id_a))[::-1])
                k1: (int, int) = tuple(np.squeeze(np.where(self.tile_id_map == id_b))[::-1])
                mask_map = {(0, 0): self.mask_map[k0]}

                top, bottom = 1000, 1
                left, right = 80, 80
                top, bottom, left, right = custom_mask_params

                assert 0 not in (top, bottom, left, right)

                mask_map[(0, 0)][:top] = True  # Custom mask
                mask_map[(0, 0)][-bottom:] = True  # Custom mask
                #
                # mask_map[(0, 0)][:, :left] = True  # Custom mask
                # mask_map[(0, 0)][:, -right:] = True  # Custom mask

                if is_vert:
                    mask_map[(0, 1)] = self.mask_map[k1]
                    mask_map[(0, 1)][:, :left] = True  # Custom mask
                    mask_map[(0, 1)][:, -right:] = True  # Custom mask
                else:
                    mask_map[(1, 0)] = self.mask_map[k1]
                    mask_map[(1, 0)][:top] = True
                    mask_map[(1, 0)][-bottom:] = True

            # for mm in mask_map.values():
            #     plt.imshow(mm*255, cmap='gray')
            #     plt.show()

            tile_space: Union[tuple[int, int], tuple[int, ...]]
            tile_space = np.shape(pair_id_map)

            # Read coarse offset if refining is desired
            co = self.get_coarse_offset(id_a, axis) if refine else None
            if co is not None:
                logging.info(f'Original coarse offset (to be refined): {co}')

            # Check if co is not None and does not contain NaN
            co = co if co is None or not any(np.isnan(x) for x in co) else None

            # Compute offset
            cx, cy = stitch_rigid.compute_coarse_offsets(
                yx_shape=tile_space,
                tile_map=tile_map,
                mask_map=mask_map,
                co=co,
                overlaps_xy=overlaps_xy,
                min_range=min_range,
                min_overlap=min_overlap,
                filter_size=filter_size,
                max_valid_offset=max_valid_offset,
            )

            # # Compute offset (Original)
            # cx, cy = stitch_rigid.compute_coarse_offsets(
            #     yx_shape=tile_space,
            #     tile_map=tile_map,
            #     mask_map=mask_map,
            #     overlaps_xy=overlaps_xy,
            #     min_range=min_range,
            #     min_overlap=min_overlap,
            #     filter_size=filter_size
            # )
            logging.debug(cx, cy)

            # Get final shift vector
            cx, cy = map(np.squeeze, (cx, cy))
            shift_vec = cy[:, 0] if is_vert else cx[:, 0]

        try:
            shift_vec = tuple(map(int, shift_vec))
        except OverflowError as _:
            logging.info(f's{self.section_num:04d} t{id_a}-t{id_b} Inf value in coarse shift shift_vector.')
            return np.inf, np.inf
        except ValueError as _:
            logging.info(f's{self.section_num:04d} t{id_a}-t{id_b} NaN value in coarse shift shift_vector.')
            return np.inf, np.inf

        if store:
            y, x = np.where(self.tile_id_map == id_a)
            id_a_coord = (axis, 0, int(y[0]), int(x[0]))
            self.replace_coarse_offset(id_a_coord, shift_vec, store)

        return shift_vec

#---- LOADING TILE-MAP ----

    def load_tile_map(
            self,
            gauss: bool = False,
            clahe: bool = False,
            clahe_params: dict[str, Any] | None = None,
            parallel: bool = False,
            max_workers: Optional[int] = None
    ) -> None:
        """
        Orchestrates tile loading with atomic failure guarantee and coordinate filtering.
        """
        self.tile_map = {}

        # Handle potential scalar or malformed tile-id map
        if self.tile_id_map is None:
            raise ValueError(
                f"Section {self.section_num}: tile_id_map is not valid."
            )

        # Extract only coordinates where tiles were recorded
        valid_indices = np.argwhere(self.tile_id_map != -1)
        positions = [tuple(pos) for pos in valid_indices]

        if valid_indices.size == 0:
            raise ValueError(f"Section {self.section_num} has no recorded tiles!")

        logging.info(f"Loading {len(positions)} tiles for s{self.section_num} (parallel={parallel})")
        try:
            if parallel:
                workers = max_workers or min(8, len(positions))
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results = list(
                        executor.map(lambda p: self._get_tile_data(p, clahe, clahe_params, gauss), positions)
                    )
            else:
                results = [self._get_tile_data(p, clahe, clahe_params, gauss) for p in positions]

            for pos_tuple, img_data in results:
                if img_data is not None:
                    self._update_tile_map_single((pos_tuple, img_data))

        except Exception as e:
            raise utils.TileLoadingError(
                f"Atomic load failed for section {self.section_num} during "
                f"{'parallel' if parallel else 'sequential'} ingestion: {e}"
            ) from e

        # Final Integrity Check
        if len(self.tile_map) != len(positions):
            raise utils.TileLoadingError(
                f"Integrity mismatch for s{self.section_num}: "
                f"Expected {len(positions)} tiles, but map size is {len(self.tile_map)}."
            )

    def _get_tile_data(
            self,
            pos: tuple[int, int],
            clahe: bool,
            clahe_params: dict[str, Any] | None = None,
            gauss: bool = False,
    ) -> tuple[tuple[int, int], Optional[np.ndarray]]:
        """Encapsulates tile lookup, I/O, and post-processing logic."""
        y, x = pos

        try:
            tile_id = int(self.tile_id_map[y, x])
        except (ValueError, TypeError, IndexError) as e:
            logging.error(f"Invalid tile_id at {pos}: {e} (raw value: {self.tile_id_map[y, x]})")
            return (x, y), None

        if tile_id == -1:
            return (x, y), None

        # === Tile dictionary lookup ===
        try:
            tile_path = self.tile_dicts[tile_id]
        except (KeyError, IndexError, ValueError) as e:
            logging.error(f"Critical Mapping Error: ID {tile_id} not in tile_dicts.")
            raise  # Re-raising is correct here to trigger the 'Atomic Failure'

        # === Normal processing (these errors can be swallowed) ===
        try:
            path = Path(tile_path)

            if not path.exists():
                raise FileNotFoundError(f"Tile file not found: {path}")

            img = utils.io_read_tif(path)

            if gauss:
                img = ndimage.gaussian_filter(img, sigma=0.7)

            if clahe:
                img = utils.apply_clahe(img, **(clahe_params or {}))

            return (x, y), img

        except Exception as e:
            logging.error(f"Failed to load tile at position {pos} (tile_id={tile_id}): {e}")
            return (x, y), None


    def _update_tile_map_single(self, result: Tuple[Tuple[int, int], Optional[np.ndarray]]) -> None:
        """Update tile_map with a single result. Safe even if tile_map is None."""
        if self.tile_map is None:
            self.tile_map = {}

        (x, y), img = result
        if img is not None:
            self.tile_map[(x, y)] = img


    def ensure_tile_map_ready(
            self,
            apply_clahe: bool = False,
            clahe_params: dict[str, Any] | None = None
    ) -> None:
        """Ensure tile map is loaded. Raises if loading fails."""
        if self.tile_map is not None and len(self.tile_map) > 0:
            return

        try:
            denoise = True if apply_clahe else False

            self.load_tile_map(
                gauss=denoise,
                clahe=apply_clahe,
                clahe_params=clahe_params,
                parallel=True,
                max_workers=8
            )

        except ValueError as e:
            logging.error(e)

        except Exception as e:
            logging.error(e)


# ---- EOF LOADING TILE-MAP ----


# ---- Coarse offsets ----

    def _is_cache_valid(self, overwrite: bool) -> bool:
        return Path(self.path_cxy).exists() and not overwrite

    def compute_coarse_offsets_section(
            self,
            config: CoarseStitchConfig
    ) -> Optional[np.ndarray]:
        """Pure computational bridge to the stitch_rigid backend."""
        try:
            cx, cy = stitch_rigid.compute_coarse_offsets(
                yx_shape=self.section_shape,
                tile_map=self.tile_map,
                overlaps_xy=config.overlaps_xy,
                min_range=config.min_range,
                min_overlap=config.min_overlap,
                filter_size=config.filter_size,
                mask_map=self.mask_map,
            )

            # Store result and return
            self.cxy = np.array([np.squeeze(cx), np.squeeze(cy)])
            return self.cxy

        except ValueError as e:
            logging.error(f"Algorithmic failure in S{self.section_num}: {e}")
            return None


# ---- EOFCoarse offsets ----

# ---- FineFlows ----

    def compute_fine_flows(self, config: RegistrationConfig, **kwargs) -> None:
        """Proxy method to the Orchestrator service."""
        logging.info(f'flow config: ps={config.patch_size}, stride={kwargs.get('stride')}')
        orchestrator = FlowFieldOrchestrator(self)
        logging.info('ff_orchestrator OK')
        orchestrator.compute_fine_flows(config, **kwargs)

    def load_fflows(self, ext: Optional[str] = None) -> None:
        ext = '' if ext is None else ext
        fp_fflows = self.path / f'fflows{ext}.pkl'
        logging.info(f's{self.section_num}: loading fine flows from {fp_fflows}.')

        try:
            with open(fp_fflows, 'rb') as f:
                self.fflows = pickle.load(f)

        except FileNotFoundError:
            logging.warning(f's{self.section_num} fine flows file not found: {fp_fflows}')
        except EOFError:
            logging.warning(f's{self.section_num}: EOFError - Ran out of input while reading {fp_fflows}.')
        except pickle.UnpicklingError as e:
            logging.error(f's{self.section_num}: Error while unpickling {fp_fflows}: {e}')
        except Exception as e:
            logging.error(f"An error occurred while reading '{fp_fflows}': {e}")

# ---- EOF FineFlows ----

# ----  FINE MESH ----

    def compute_fine_mesh(
            self,
            reg_config: RegistrationConfig,
            mesh_config: MeshIntegrationConfig,
    ) -> None:
        """
        Computes a high-resolution elastic mesh using JAX-accelerated relaxation.
        """
        start_time = time.perf_counter()

        # 1. Resource Validation & Dependency Loading
        self._ensure_fine_mesh_resources()
        self.clean_and_reconcile_fflows(reg_config)

        # 2. Computation Block
        try:
            logging.info(f"[Section {self.section_num}] Starting Fine Mesh computation")

            # Extract coordinate grids and reconciled flows
            cx, cy = np.squeeze(self.cxy)

            ffx, ffxo = self.fflows_recon[0]
            ffy, ffyo = self.fflows_recon[1]

            data_x = (cx, ffx, ffxo)
            data_y = (cy, ffy, ffyo)

            stride_tuple = (mesh_config.stride, mesh_config.stride)

            sample_tile_shape = next(iter(self.tile_map.values())).shape

            fx, fy, nds, nbors, key_to_idx = stitch_elastic.aggregate_arrays(
                data_x, data_y,
                list(self.tile_map.keys()),
                self.coarse_mesh[:, 0, ...],
                stride=stride_tuple,
                tile_shape=sample_tile_shape
            )

            @jax.jit
            def prev_fn(nds):
                target_fn = ft.partial(
                    stitch_elastic.compute_target_mesh, x=nds, fx=fx, fy=fy, stride=stride_tuple
                )
                nds = jax.vmap(target_fn)(nbors)
                return jnp.transpose(nds, [1, 0, 2, 3])

            # Initialize SOFIMA integration config via attribute mapping
            config_attrs = mesh_config.model_dump()
            config_attrs['stride'] = stride_tuple

            config_sofima = mesh.IntegrationConfig(**config_attrs)

            logging.info(f"[Section {self.section_num}] Executing JAX mesh relaxation...")
            res, _, _ = mesh.relax_mesh(nds, None, config_sofima, prev_fn=prev_fn)

            # 3. Inverse Mapping (Index -> Tuple Key)
            idx_to_key = {v: k for k, v in key_to_idx.items()}
            self.fmesh = {
                idx_to_key[i]: np.array(res[:, i:i + 1, :])
                for i in range(res.shape[1])
            }

            # 4. Persistence
            logging.info(f"[Section {self.section_num}] Serializing mesh to {self.path_fmesh}")
            meshes_to_save = {str(k): v for k, v in self.fmesh.items()}
            np.savez(self.path_fmesh, **meshes_to_save)

            # 5. Resource Teardown
            del fx, fy, nds, nbors, res
            jax.clear_caches()
            gc.collect()

            elapsed = time.perf_counter() - start_time
            logging.info(f"[Section {self.section_num}] Fine mesh complete. Duration: {elapsed:.2f}s")

        except Exception as e:
            logging.error(f"[Section {self.section_num}] Critical failure: {e}", exc_info=True)
            jax.clear_caches()
            raise


    def _ensure_fine_mesh_resources(self) -> None:
        """Ensure all required resources for fine mesh processing are loaded and ready.

        This is a hardened dependency loader. It fails fast on critical missing data
        but is idempotent (safe to call multiple times).

        Raises:
            MeshResourceError: If any critical resource is missing or invalid.
        """
        self.ensure_tile_dicts()
        self._ensure_coarse_offsets()
        self._ensure_tile_map()
        self._ensure_coarse_mesh()
        self.ensure_fflows()

    def ensure_tile_dicts(self) -> None:
        if self.tile_dicts is not None:
            return

        logging.warning("Tile dicts not loaded. Loading now for section %s", self.section_num)
        self.tile_dicts = utils.get_tile_dicts(self.path)
        self.read_tile_id_map()


    def _ensure_coarse_offsets(self) -> None:
        if self.cxy is not None:
            return

        try:
            _ = self.get_coarse_mat()
        except (FileNotFoundError, ValueError) as exc:
            raise utils.MeshResourceError(
                f"Coarse offset array (cxy) missing or corrupted for section {self.section_num}"
            ) from exc

    def _ensure_tile_map(self) -> None:
        if self.tile_map is not None:
            return

        logging.info("Loading tile map for section %s (CLAHE + parallel)", self.section_num)
        try:
            self.load_tile_map(clahe=True, parallel=True)
        except utils.TileLoadingError as e:
            raise utils.MeshResourceError(
                f"Aborting section {self.section_num}: missing tile-map data"
            ) from e

        if not self.tile_map:
            raise utils.MeshResourceError(
                f"Tile map loading returned empty for section {self.section_num}"
            )

    def _ensure_coarse_mesh(self) -> None:
        if self.coarse_mesh is not None:
            return

        try:
            self.load_coarse_mesh()
        except (EOFError, FileNotFoundError) as e:
            raise utils.MeshResourceError(
                f"Failed to load coarse mesh for section {self.section_num}"
            ) from e
        except Exception as e:  # fallback for unexpected errors
            raise utils.MeshResourceError(
                f"Unexpected error loading coarse mesh for section {self.section_num}"
            ) from e

    def ensure_fflows(self) -> None:
        if self.fflows is not None:
            return
        try:
            self.load_fflows()
        except FileNotFoundError as e:
            raise utils.MeshResourceError(e)
        if not self.fflows:
            raise utils.MeshResourceError(
                f"Failed to load fine flows for section {self.section_num}"
            )


    def clean_and_reconcile_fflows(self, config: RegistrationConfig) -> None:

        if self.fflows is None:
            raise ValueError (f"s{self.section_num} clean_fflows failed: fine flows not available.")

        fine_x, offsets_x = self.fflows[0]
        fine_y, offsets_y = self.fflows[1]

        # Clean flows
        kwargs = config.clean_kwargs
        fine_x = {k: flow_utils.clean_flow(v[:, np.newaxis, ...], **kwargs)[:, 0, :, :] for k, v in fine_x.items()}
        fine_y = {k: flow_utils.clean_flow(v[:, np.newaxis, ...], **kwargs)[:, 0, :, :] for k, v in fine_y.items()}

        # Reconcile flows
        kwargs = config.recon_kwargs
        fine_x = {k: flow_utils.reconcile_flows([v[:, np.newaxis, ...]], **kwargs)[:, 0, :, :] for k, v in
                  fine_x.items()}
        fine_y = {k: flow_utils.reconcile_flows([v[:, np.newaxis, ...]], **kwargs)[:, 0, :, :] for k, v in
                  fine_y.items()}

        ffx = fine_x, offsets_x
        ffy = fine_y, offsets_y

        self.fflows_recon = (ffx, ffy)


# ----  EOF FINE MESH ----

# ---- WARP SECTION ----

    def warp_section(
            self,
            stride: int,
            config: WarpConfigStitching,
    ) -> None:
        """
        Orchestrates high-memory warping and stitching operations.
        """
        start_time = time.perf_counter()

        # 1. Resource Validation
        try:
            self._ensure_warping_resources(config)
        except (FileNotFoundError, ValueError) as e:
            logging.error(f"[Section {self.section_num}] Resource initialization failed: {e}")
            raise  # Propagate to pipeline master to record the failure

        # 2. Execution Setup
        clahe_params = dict(
            kernel_size=config.kernel_size,
            clip_limit=config.clip_limit,
            nbins=config.nbins
        )

        try:
            logging.info(
                f"[Section {self.section_num}] Starting Render: stride={stride}, parallelism={config.warp_parallelism}")

            stitched, _ = warp.render_tiles(
                tiles=self.tile_map,
                coord_maps=self.fmesh,
                stride=(stride, stride),
                margin=config.margin,
                use_clahe=config.use_clahe,
                clahe_kwargs=clahe_params,
                tile_masks=self.margin_masks if config.margin_masking else None,
                parallelism=config.warp_parallelism
            )

            # 3. Persistence
            self._persist_warped_result(stitched)

            # 4. Mandatory Cleanup
            del stitched
            gc.collect()

            elapsed = time.perf_counter() - start_time
            logging.info(f"[Section {self.section_num}] Warp complete. Duration: {elapsed:.2f}s")

        except Exception as e:
            logging.error(f"[Section {self.section_num}] Critical failure during warp/store: {e}", exc_info=True)
            raise


    def _ensure_warping_resources(self, config: WarpConfigStitching) -> None:
        """Hardened dependency loader with integrity checks."""

        # Fine Mesh Validation
        if self.fmesh is None:
            try:
                self.fmesh = utils.load_mapped_npz(self.path_fmesh)
            except FileNotFoundError:
                raise FileNotFoundError(f"Mesh missing for section {self.section_num}: {self.path_fmesh}")
            except BadZipFile as e:
                logging.critical(f"Integrity check failed: {e}")
                raise RuntimeError(f"Section {self.section_num} fine mesh data is unrecoverable.") from e

        if not self.fmesh:
            raise ValueError(f"Mesh data for s{self.section_num} is empty.")

        # Metadata Injection
        if self.tile_dicts is None:
            self.tile_dicts = utils.get_tile_dicts(self.path)

        if self.tile_id_map is None:
            self.read_tile_id_map()

        # Image Buffer Loading
        if self.tile_map is None:
            try:
                clahe = config.use_clahe
                clahe_params = None
                if clahe:
                    clahe_params = {
                        "kernel_size": config.kernel_size,
                        "clip_limit": config.clip_limit
                    }

                self.load_tile_map(
                    gauss=False, clahe=clahe, clahe_params=clahe_params,
                    parallel=True, max_workers=config.warp_parallelism
                )

            except utils.TileLoadingError as e:
                raise RuntimeError(f"Aborting section {self.section_num} due to missing tile-map data.") from e

        if not self.tile_map:
            raise RuntimeError(f"Tile map loading returned empty for section {self.section_num}")

        # Optional margin masks
        if config.margin_masking and self.margin_masks is None:
            try:
                self.margin_masks = utils.load_mapped_npz(self.path_margin_masks)
            except (FileNotFoundError, BadZipFile):
                logging.warning(f"Margin masking skipped for s{self.section_num} - Resource unavailable.")

    def _persist_warped_result(self, data: np.ndarray):
        """Handles Zarr serialization logic."""
        path_stitched = self.path_stitched.parent
        section_name = Path(self.path).name + '.zarr'
        utils.store_section_zarr(data, section_name, path_stitched)
        self.image = data


# ---- EOF WARP SECTION ----


class FlowFieldOrchestrator:

    def __init__(self, section: 'Section'):
        self.section = section

    def compute_fine_flows(
            self,
            config: RegistrationConfig,
            stride: int,
            masking: bool = False,
            store: bool = True,
            overwrite: bool = False,
            ext: Optional[str] = None,
    ) -> None:
        """High-level orchestration for fine flow computation."""

        # 1. Pre-computation Guards & State Check
        if not overwrite and self._try_load_existing_fflows():
            logging.info(f"Skipping s{self.section.section_num}: fflows already exist.")
            return

        if not self._prepare_infrastructure(masking=masking, apply_clahe=True):
            logging.error(f"Infrastructure failure for s{self.section.section_num}.")
            return

        # 2. Execution
        try:
            logging.info(f'Computing fine-flows with stride: {stride}')
            self.section.fflows = (
                self._run_iterative_flow_estimation(config, stride))
        except RuntimeError as e:
            logging.error(f"Flow estimation failed: {e}")
            return

        # 3. Persistence
        if store and self.section.fflows:
            self._persist_fflows(self.section.fflows, ext)

    def _prepare_infrastructure(
            self,
            masking: bool,
            apply_clahe: bool = False
    ) -> bool:
        """Ensures all buffers and remote data are ready for computation."""
        if self.section.cxy is None:
            _ = self.section.get_coarse_mat()

        if self.section.cxy is None:
            logging.warning(f"Coarse offset array missing for s{self.section.section_num}")
            return False

        try:
            self.section.ensure_tile_map_ready(
                apply_clahe=apply_clahe,
                clahe_params={}
            )
        except Exception:
            return False

        if masking and not self.section.mask_map:
            self.section.load_masks()

        return True

    def _run_iterative_flow_estimation(
            self,
            cfg: RegistrationConfig,
            stride: int,
            max_attempts: int = 5
    ) -> Tuple[Any, Any]:
        """
        Executes the SOFIMA flow estimation with a fallback
        mechanism for negative dimension/ValueError.
        """
        ps = cfg.patch_size[0]
        ps_step = cfg.step_patch_size

        for attempt in range(max_attempts):
            if ps < cfg.min_patch_size:
                break
            try:
                logging.info(f"s{self.section.section_num} computation attempt {attempt} | PS: {ps}")
                flow_x = self._execute_sofima_call(cfg, stride, axis=0)
                flow_y = self._execute_sofima_call(cfg, stride, axis=1)
                return flow_x, flow_y
            except ValueError:
                logging.warning(
                    f"Iterative fine flow computation failed at patch size {ps}. Reducing patch size."
                )

                ps -= ps_step
        raise RuntimeError(f"Flow estimation exhausted all attempts for s{self.section.section_num}")

    def _execute_sofima_call(
            self,
            cfg: RegistrationConfig,
            stride: int, axis: int
    )-> tuple[TileFlow, TileOffset]:
        """Wrapper for the external library call."""

        return stitch_elastic.compute_flow_map(
            tile_map=self.section.tile_map,
            offset_map=self.section.cxy[axis],
            axis=axis,
            patch_size=tuple(cfg.patch_size),
            stride=(stride, stride),
            batch_size=cfg.batch_size,
        )

    def _persist_fflows(self, data: Any, ext: Optional[str]) -> None:
        suffix = ext or ""
        path = self.section.path / f"fflows{suffix}.pkl"
        with open(path, "wb") as f:
            pickle.dump(data, f)
        logging.info(f"Saved fine flows to {path}")

    def _try_load_existing_fflows(self) -> bool:
        """Checks the section for existing data."""
        self.section.load_fflows()
        return self.section.fflows is not None



#### ---------   FUNCTIONS    ---------

def run_plot_ov(
        config: cfg.ExpConfig,
        sec_num: int,
        tid_a: int,
        tid_b: int,
        xy: Optional[tuple[int, int]] = None,
        vert_nn: bool = False,
        shift_vec: Optional[Vector] = None
) -> None:

    ps = Path(config.proc_dir) / 'sections' / f's{sec_num}_g{config.grid_num}'
    section = Section(ps)
    section.feed_section_data()

    if xy is not None:
        x, y = xy
        tid_a = section.tile_id_map[y][x]
        try:
            if not vert_nn:
                tid_b = section.tile_id_map[y][x + 1]
            else:
                tid_b = section.tile_id_map[y + 1][x]
            print(f'plotting tile-pair ov: s{sec_num} t{tid_a}-t{tid_b}')
        except IndexError as _:
            log_str = 'vertical' if vert_nn else 'horizontal'
            print(f'plot_ov failed: tile at index {xy} does not have a {log_str} neighbor')
            return
    else:
        print(f'plotting tile-pair ov: s{sec_num} t{tid_a}-t{tid_b}')

    if shift_vec is None:
        axis = 1 if utils.pair_is_vertical(section.tile_id_map, tid_a, tid_b) else 0
        shift_vec = section.get_coarse_offset(tid_a, axis)

    print(f"Plotting ov s{sec_num} t{tid_a}-t{tid_b} with coarse offset: {shift_vec}")
    section.plot_ov(tid_a=tid_a, tid_b=tid_b, shift_vec=shift_vec, dir_out=str(section.path),
                    show_plot=True, clahe=True, blur=1.1, store_to_root=False)
    return


def main_fine_align_sections(
        config: cfg.ExpConfig,
        sec_nums: Union[list[int], int]
):
    # FINE-ALIGN AND WARP SECTION(S)

    if not isinstance(sec_nums, (int, list)):
        logging.warning("sec_nums must be either an integer or list of integers!")
        return

    if isinstance(sec_nums, int):
        sec_nums = [sec_nums]

    for num in sec_nums:
        path_section = Path(config.proc_dir) / 'sections' / f's{num}_g{config.grid_num}'
        section = Section(path_section)
        section.feed_section_data()
        fine_align_section(section, config.grid_shape, masking=True)
    return


def debug_cxcy():
    section_path = "/Volumes/storage/scratch/team/project/tgan/Stack_alignments/roli-f1/test_align/sections/s1240_g0"
    section = Section(section_path)

    coarse_mat = section.get_coarse_mat()
    print(coarse_mat)
    return

def debug_margin_masks():

    rim_size = 30  # Safety margin to custom overlaps
    margin = max(10, rim_size // 3)  # Cut all tile edges by 'margin'

    section_path = "/Volumes/storage/groups/scratch/team/project/_processing/SOFIMA/nextflow/ganctoma/gfriedri-em-alignment-flows/runs/roli-f1/run-01/sections/s1250_g0"
    section = Section(section_path)
    grid_shape = (30, 25)

    section.build_margin_masks(grid_shape, margin, rim_size, overwrite=True)

    return


def compute_fine_flows(self, ff_config, **kwargs):
    orchestrator = FlowFieldOrchestrator(self)
    return orchestrator.run(ff_config, **kwargs)


def fine_align_section(
        section: Section,
        grid_shape: tuple[int, int],
        masking=False
) -> None:

    patch_size = 120  # For fine-flows
    stride = 20  # fine-flows resolution
    batch_size = 256 # fine-flows

    rim_size = 40  # Safety margin to custom overlaps
    # margin = max(10, rim_size // 3)  # Cut all tile edges by 'margin'
    margin = 0
    # use_clahe = True
    # zarr_store = True  # Store .zarr into stitched-sections folder
    rescale_fct = 0.5 # Store .jpg thumbnail into section folder
    # rescale_fct = None  # Store .jpg thumbnail into section folder
    # parallelism: int = 1
    overwrite = True
    # rot_angle = 0
    # masking = True
    # clahe_kwargs = dict(kernel_size=256, clip_limit=0.5, nbins=64)

    section.feed_section_data()

    # # Pass if section already stitched
    # if section.stitched:
    #     logging.info(f'Skipping s{section.section_num} Section is already stitched.')
    #     print(f'Skipping s{section.section_num} Section is already stitched.')
    #     section.clear_data()
    #     return

    # if section.path_stitched.exists():
    #     logging.info(f'Skipping s{section.section_num} Section is already stitched.')
    #     print(f'Skipping s{section.section_num} Section is already stitched.')
    #     section.clear_data()
    #     return

    # if masking:
    #     try:
    #         section.load_masks()
    #     except Exception as _:
    #         kwargs_masks = dict(
    #             roi_thresh=20,
    #             max_vert_ext=200,
    #             edge_only=True,
    #             n_lines=30,
    #             store=True,
    #             filter_size=50,
    #             range_limit=0
    #         )
    #         section.create_masks(**kwargs_masks)

    # # Computes optimized coarse offset array
    section.compute_coarse_mesh(conf=None, overwrite=overwrite)

    # # Create margin masks for warping
    section.build_margin_masks(grid_shape, margin, rim_size, overwrite=True)

    # # Compute flows between overlaps
    config = RegistrationConfig()
    config['patch_size'] = [patch_size, patch_size],
    config['batch_size'] = batch_size

    ff_orchestrator = FlowFieldOrchestrator(section)
    ff_orchestrator.compute_fine_flows(
        config=config, stride=stride, masking=True, store=True, overwrite=overwrite, ext=None
    )


    # #  Compute fine meshes
    # cfg = mesh.IntegrationConfig(
    #     dt=0.001,
    #     gamma=0.1,
    #     k0=0.01,
    #     k=0.1,
    #     stride=stride,
    #     num_iters=1000,
    #     max_iters=20000,
    #     stop_v_max=0.001,
    #     dt_max=100,
    # )
    # section.get_fine_mesh(section, stride, overwrite, stitch_config=cfg)

    # # WARP SECTION
    # warp_kwargs = (stride, margin, use_clahe, clahe_kwargs, zarr_store, rescale_fct, parallelism, rot_angle)
    # section.warp_section(*warp_kwargs)

    # Downscale and store stitched section
    # if not Path(section.path_thumb).exists():
    mini = section.downscale_section(rescale_fct)
    utils.save_img(section.path_thumb, mini)

    # Derotate stitched .zarr sections
    # section.rotate_and_store_stitched(rot_angle, section.path_stitched_custom.parent)

    # section.clear_section()
    return


if __name__ == "__main__":

    # Accessing individual experiments
    configs = cfg.get_experiment_configurations()
    exp_name = 'ROLI_F1'
    exp = configs[exp_name]

    # # # FINE ALIGN
    sec_nums = list(range(3000, 3005))
    main_fine_align_sections(exp, sec_nums)

    # DEBUG
    # debug_cxcy()
    # debug_margin_masks()

    # PLOTTING, WARPING, FINE ALIGNMENT
    # shift_vec = None
    # run_plot_ov(exp, sec_num=1500, tid_a=464, tid_b=489, xy=None, vert_nn=False, shift_vec=shift_vec)

