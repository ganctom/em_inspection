from pathlib import Path
from typing import Optional, Self
import cv2
from skimage.io import imread
import numpy as np

import em_inspection.inspection_utils_refactor as utils

TileXY = tuple[int, int]


class Tile:
    def __init__(self, path: str):
        self.tile_path = Path(utils.cross_platform_path(path))
        self.tile_id: Optional[int] = utils.get_tile_num(self.tile_path)
        self.tile_xy: Optional[TileXY] = None
        self.img_data: Optional[np.ndarray] = None
        self._img_processed: Optional[np.ndarray] = None

    @property
    def processed(self) -> np.ndarray:
        """
        Terminal property that returns the final processed array state.
        If no transformations were chained, it cleanly falls back to raw data.
        """
        if self._img_processed is not None:
            return self._img_processed
        if self.img_data is None:
            self.load_image()
        return self.img_data

    def load_image(self, clahe: bool = False) -> Self:
        """
        Initializes or resets the pipeline by loading the raw data from disk.
        Resets any previous intermediate processed state.
        """
        self.img_data = None
        self._img_processed = None

        try:
            self.img_data = imread(str(self.tile_path))
            if clahe and self.img_data is not None:
                self.img_data = utils.apply_clahe(self.img_data)
        except (FileNotFoundError, OSError) as e:
            print(f"Error loading image {self.tile_path}: {e}")
            raise

        # Seed the processed state register with base data
        self._img_processed = self.img_data.copy() if self.img_data is not None else None
        return self

    def _ensure_loaded(self) -> None:
        """Internal guard clause to preserve lazy loading if load() wasn't called explicitly."""
        if self._img_processed is None:
            self.load_image()
        if self._img_processed is None:
            raise ValueError(f"Underlying image data matrix could not be resolved for: {self.tile_path}")

    def denoise(self, sigma: float = 1.0) -> Self:
        """Applies Gaussian denoising directly on top of the current state register."""
        self._ensure_loaded()
        if sigma > 0:
            self._img_processed = blur_gauss(self._img_processed, sigma)
        return self

    def bin(self, factor: int = 2) -> Self:
        """Downsamples the current state register by a specific spatial binning factor."""
        self._ensure_loaded()
        if factor <= 1:
            return self

        scale = 1.0 / factor
        self._img_processed = cv2.resize(
            self._img_processed,
            dsize=(0, 0),
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA
        )
        return self

    def clahe(self) -> Self:
        """Applies Contrast Limited Adaptive Histogram Equalization on top of current state register."""
        self._ensure_loaded()
        self._img_processed = utils.apply_clahe(self._img_processed)
        return self


def blur_gauss(image: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    """Fast and stable Gaussian blur."""
    if sigma <= 0:
        return image.copy()

    ks = int(sigma * 5) | 1  # ensures odd number
    if ks > 31:  # prevent extremely large kernels
        ks = 31

    return cv2.GaussianBlur(image, ksize=(ks, ks), sigmaX=sigma)

