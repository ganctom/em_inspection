from pathlib import Path
from typing import Optional
from skimage.io import imread
import numpy as np

import inspection_utils_refactor as utils

TileXY = tuple[int, int]

class Tile:
    def __init__(self, path: str):
        self.tile_path = Path(utils.cross_platform_path(path))
        self.tile_id: Optional[int] = utils.get_tile_num(self.tile_path)
        self.tile_xy: Optional[TileXY] = None
        self.img_data: Optional[np.ndarray] = None


    def load_image(self, clahe: bool = False) -> None:
        self.img_data = None
        try:
            self.img_data = imread(str(self.tile_path))
        except (FileNotFoundError, OSError):
            print(f"Error loading image from file: {self.tile_path}")

        if clahe and self.img_data is not None:
            self.img_data = utils.apply_clahe(self.img_data)
        return