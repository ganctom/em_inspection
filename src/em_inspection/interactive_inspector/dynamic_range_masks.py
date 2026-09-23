import logging
from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np
import tifffile
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pydantic import BaseModel, Field
from scipy import ndimage

# --- Configuration Layer ---

class RangeAnalysisConfig(BaseModel):
    """Encapsulates all hyperparameters for the pipeline with native Pydantic validation."""
    min_range: List[int] = Field(default_factory=lambda: [20, 40, 80])
    filter_size: int = 30
    denoise_sigma: float = 1.2
    use_clahe: bool = True
    clahe_clip: float = 2.0
    clahe_grid: Tuple[int, int] = (8, 8)
    plotly_image_only: bool = True


# --- Logic Layer (Pure Functions) ---

def load_image(path: str) -> np.ndarray:
    if not Path(path).is_file():
        raise FileNotFoundError
    return tifffile.imread(path)


def denoise_image(image: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return image
    ks = int(sigma * 5)
    if ks % 2 == 0: ks += 1
    return cv2.GaussianBlur(image, ksize=(ks, ks), sigmaX=0)


def apply_clahe(image: np.ndarray, clip: float, grid: Tuple[int, int]) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=grid)
    return clahe.apply(image)


def compute_range_masks(
        image: np.ndarray,
        filter_size: int,
        ranges: list[int]
) -> List[np.ndarray]:
    processed = image.astype(float)
    local_max = ndimage.maximum_filter(processed, size=filter_size)
    local_min = ndimage.minimum_filter(processed, size=filter_size)
    local_range = local_max - local_min
    return [local_range < r for r in ranges]


# --- Orchestration & Visualization Layer ---

def load_raw_image(path: str) -> Optional[np.ndarray]:
    """Standalone wrapper handle to fetch and trap exceptions on file ingestion."""
    try:
        return load_image(path)
    except FileNotFoundError as e:
        logging.error(f"Failed to load image from path '{path}': {e}")
        return None


def plot_results(
        orig_img: np.ndarray,
        processed_img: np.ndarray,
        masks: List[np.ndarray],
        config: RangeAnalysisConfig
) -> Optional[go.Figure]:
    """Visualization decoupled from data processing."""

    if config.plotly_image_only:
        n_cols = 1 + len(masks)

        # Build subplot titles dynamically with processed image at index 1
        subplot_titles = [f"Processed<br>σ={config.denoise_sigma}, CLAHE={config.use_clahe}"]
        subplot_titles.extend([f"Range < {r}<br>Filter={config.filter_size}" for r in config.min_range])

        fig = make_subplots(
            rows=1,
            cols=n_cols,
            subplot_titles=subplot_titles
        )

        # Trace 1: Prepend Processed Image Data
        fig.add_trace(
            go.Heatmap(
                z=processed_img,
                colorscale='Gray',
                showscale=False
            ),
            row=1, col=1
        )

        # Traces 2 to N: Append range masks sequentially shifted by 1 index column
        for i, mask in enumerate(masks):
            fig.add_trace(
                go.Heatmap(
                    z=mask.astype(np.uint8),
                    colorscale='Gray',
                    showscale=False,
                    reversescale=False
                ),
                row=1, col=i + 2
            )

        fig.update_xaxes(showticklabels=False, zeroline=False, showgrid=False)
        fig.update_yaxes(showticklabels=False, zeroline=False, showgrid=False, autorange="reversed")

        # Generate bounding border shapes around mask subplots (using paper coordinates)
        shapes = []
        for col_idx in range(2, n_cols + 1):
            # Target the specific subplot reference bounding coordinates dynamically
            shapes.append(
                dict(
                    type="rect",
                    xref=f"x{col_idx} domain",
                    yref=f"y{col_idx} domain",
                    x0=0, y0=0, x1=1, y1=1,
                    line=dict(color="black", width=1)
                )
            )

        fig.update_layout(
            template="plotly_white",
            margin=dict(l=40, r=40, b=40, t=60),
            shapes=shapes
        )
        return fig

    # Default Matplotlib Pipeline Execution
    n_cols = 2 + len(masks)
    fig, axes = plt.subplots(1, n_cols, figsize=(4.5 * n_cols, 5))

    # Input/Output views
    axes[0].imshow(orig_img, cmap='gray', vmin=0, vmax=255)
    axes[0].set_title("Original")

    axes[1].imshow(processed_img, cmap='gray')
    axes[1].set_title(f"Processed\nσ={config.denoise_sigma}, CLAHE={config.use_clahe}")

    # Mask views
    for i, mask in enumerate(masks):
        ax = axes[i + 2]
        limit = config.min_range[i]
        ax.imshow(mask, cmap='gray')
        ax.set_title(f"Range < {limit}\nFilter={config.filter_size}")

        # Add border around matplotlib mask subplots for visual mapping parity
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color('black')
            spine.set_linewidth(1)

    for i, ax in enumerate(axes):
        if i < 2:
            ax.axis('off')

    plt.tight_layout()
    plt.show()
    return None


def create_range_mask_plot(
        raw_img: np.ndarray,
        config: RangeAnalysisConfig
) -> Optional[go.Figure]:
    """Standardized entry point for processing a single image configuration."""
    work_img = denoise_image(raw_img, config.denoise_sigma)

    if config.use_clahe:
        work_img = apply_clahe(work_img, config.clahe_clip, config.clahe_grid)

    masks = compute_range_masks(work_img, config.filter_size, config.min_range)

    return plot_results(raw_img, work_img, masks, config)
