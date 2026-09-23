import multiprocessing
from typing import List, Optional
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path
from skimage import filters
from scipy import signal, ndimage
from scipy.ndimage import binary_fill_holes, median_filter
import cv2

from typing import Union, Tuple, List, Mapping, Sequence, Dict, Optional
UniPath = Union[str, Path]
TileXY = Tuple[int, int]
MaskMap = Dict[TileXY, Optional[np.ndarray]]

def eval_dyn_range(a: np.ndarray, range_limit=10, filter_size=10):
  dyn_range = (ndimage.maximum_filter(a, filter_size)
               - ndimage.minimum_filter(a, filter_size))
  return dyn_range


def detect_smearing2d(
  img: np.ndarray,
  segment_width: int = 1000,
  dx: int = 10,
  dy: int = 3,
  sigma=1.5
) -> Optional[np.ndarray]:
  """Detect smearing in the image using cross-correlation between line segments.

  Args:
    img: The image array
    segment_width: Length of the line segment(s) used for cross-correlation
    dx: stride in x-axis of the image; defines the 'resolution' of
      the smearing map in X.
    dy: distance between lines to be correlated in vertical
      direction (in pixels). Must be > 1.
    sigma: Standard deviation for Gaussian blur. Do not use sigma=1.0

  Returns:
    smearing_mask: A binary mask indicating the smeared portions.

  """

  # Initialize the smearing mask with zeros (no smearing)
  smearing_map = np.full(np.shape(img), np.nan)

  # Blur the image to speed up the computation
  img = filters.gaussian(img, sigma=sigma) if sigma > 1 else img.astype(float)

  # Pad the entire image to handle borders
  hw = int(segment_width // 2)
  pad_width = ((0, 0), (hw, hw))
  img_padded = np.pad(img, pad_width, mode='constant')

  h, w = np.shape(img)
  for y in range(h - dy):
    for x in range(0, w, dx):

      sec_a = img_padded[y, x:x + segment_width]
      sec_b = img_padded[y + dy, x:x + segment_width]
      corr = signal.correlate(sec_a, sec_b)

      # Find the shift from peak of cross-correlation &
      # calculate the center position of the corr line
      center = len(sec_a)
      peak_shift = np.argmax(corr) - (center - 1)
      smearing_map[y][x] = int(peak_shift)

  return smearing_map[:-dy]


def plot_smearing(plots: List[np.ndarray], path_plot: str) -> None:
  fig = plt.figure(figsize=(15, 8))
  gs = gridspec.GridSpec(7, 2, width_ratios=[1, 0.1])

  axes = [plt.subplot(gs[i, 0]) for i in range(6)]
  cax = plt.subplot(gs[:, 1])

  im0 = axes[0].matshow(plots[0], cmap='viridis')
  axes[0].set_title('Original cross-correlation map')

  im1 = axes[1].matshow(plots[1], cmap='viridis')
  axes[1].set_title('Interpolated cross-correlation map')

  im2 = axes[2].imshow(plots[2], cmap='gray')
  axes[2].set_title('Mask: Interpolated cross-correlation map')

  im3 = axes[3].imshow(plots[3], cmap='gray')
  axes[3].set_title('Mask: Filled holes')

  im4 = axes[4].imshow(plots[4], cmap='gray')
  axes[4].set_title('Mask: Filled holes + Flooded')

  im5 = axes[5].imshow(plots[5], cmap='gray')
  axes[5].set_title('Mask: Filled holes + Flooded (0.7 threshold) + LineFill')
  axes[5].set_ylabel('Line nr.')
  axes[5].set_xlabel('Column nr.')

  fig.colorbar(im0, cax=cax, orientation='vertical')
  plt.tight_layout()
  plt.savefig(path_plot)
  # plt.show()
  plt.close(fig)
  return

def create_mask(arr, threshold):
  return -threshold > arr


# def fill_holes(mask):
#   num_mask = np.asarray(mask, dtype=int)
#   fill_mask = binary_fill_holes(num_mask).astype(bool)
#   return fill_mask


def blur_mask(mask, sigma: float = 1.5):
  mask = np.asarray(mask, dtype=bool)
  blurred_mask = filters.gaussian(mask.astype(float), sigma=sigma)
  return np.abs(blurred_mask) > 0


def flood_pixels(mask, ratio=0.75):
  result_mask = mask.copy()

  for i in range(mask.shape[0]):
    row = mask[i, :]
    count = np.sum(row)
    threshold = ratio * len(row)
    if count > threshold:
      result_mask[i, :] = True

  return result_mask


def set_lines_above_recursive(mask, row):
  if row > 0 and np.all(mask[row, :]):
    mask[row - 1, :] = True
    set_lines_above_recursive(mask, row - 1)

def set_lines_above_to_true_recursive(mask):
  result_mask = mask.copy()
  for i in range(1, mask.shape[0]):
    if np.all(mask[i, :]):
      result_mask[i - 1, :] = True
      set_lines_above_recursive(result_mask, i - 1)
  return result_mask


def interpolate_nan_2d(arr, min_interp_pts=10):
  """Performs lin. interpolation to replace NaN values in input array along each row.
  Args:
    arr: Input 2D array with NaN values
    min_interp_pts:

  Returns:
    Output 2D array with NaN values replaced by interpolated values.
  """

  interp_arr = arr.copy()
  for i, row in enumerate(arr):
    if np.isnan(row).all() or np.sum(~np.isnan(row)) < min_interp_pts:
      continue
    nan_idx = np.isnan(row)
    indices = np.arange(len(row))
    interp_vals = np.interp(indices, indices[~nan_idx], row[~nan_idx])
    interp_arr[i, nan_idx] = interp_vals[nan_idx]
  return interp_arr


def flood_smearing(mask: np.ndarray, portion: float) -> np.ndarray:
  """

  """

  rows, cols = mask.shape
  win = cols // 3
  result_array = mask.copy()

  for row in range(rows):
    window_sum = np.convolve(mask[row, :], np.ones(win), mode='valid')
    target_sum = portion * win

    condition_met = (window_sum == target_sum)
    if any(condition_met):
      start_index = np.argmax(condition_met)
      result_array[row, start_index:] = True

  return result_array


def remove_isolated(mask: np.ndarray[bool],
                    min_size=300
                    ) -> np.ndarray[bool]:
  """Filters small areas with True value in the 2D-binary mask

  Remove isolated islands of True values in binary mask by finding their
  contours and thresholding their area.

  Args:
    mask: Input binary mask to be filtered
    min_size: Objects smaller than this value (pixels) will be filtered

  Returns:
    Filtered binary mask array
  """

  mask_uint8 = mask.astype(np.uint8)
  contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

  for c in contours:
    if cv2.contourArea(c) < min_size:
      kwargs = {'contours': [c],
                'contourIdx': -1,
                'color': 0,
                'thickness': cv2.FILLED
                }
      cv2.drawContours(mask_uint8, **kwargs)

  return mask_uint8 > 0


def fill_holes(mask: np.ndarray):
  num_mask = np.asarray(mask, dtype=int)
  filled_num_mask = ndimage.binary_fill_holes(num_mask)
  filled_mask = filled_num_mask.astype(bool)
  return filled_mask


def get_smearing_mask(
  img: np.ndarray,
  mask_top_edge: int = 0,
  path_plot: Optional[str] = None,
  plot=False
) -> Optional[np.ndarray]:
  """Computes mask of a smearing distortion appearing at the top of the EM-images.

  Estimate the presence and extent of a smearing distortion at the top of the
  input image and return it as a boolean mask.

  Args:
    img: input image for detection of distortion at its top border
    mask_top_edge: number of lines at the top of the image to be masked entirely
    path_plot: filepath where to save the mask image (if plot=True)
    plot: switch to execute creation of various mask graphs

  Returns:
    Mask of smearing distortion with the shape same as the input image
  """

  det_args = dict(
    img=img,
    segment_width=1000,
    sigma=1.5,
    dx=50,
    dy=4
  )

  # Run smearing detection
  smr_map = detect_smearing2d(**det_args)
  smr_map_interp = interpolate_nan_2d(smr_map)
  # smr_map_interp = filters.gaussian(smr_map_interp, sigma=2)

  # # Normalize offset field
  # def norm_offset_field(field: np.ndarray, win_size=100) -> np.ndarray:
  #   # Calculate the median filter over the window
  #   median_filtered = median_filter(field,
  #                                   size=(win_size, win_size),
  #                                   mode='reflect'
  #                                   )
  #
  #   # Subtract the median filter result from the original array
  #   result = field - median_filtered
  #   return result
  #
  # # smr_map_interp -= np.mean(smr_map_interp, axis=0)
  # # smr_map_interp = norm_offset_field(smr_map_interp, win_size=3)
  # # plt.imshow(smr_map_interp, cmap='viridis')
  # # plt.show()

  mask = create_mask(smr_map_interp, threshold=0.1)

  # is_smearing(smr_map_interp)

  # def analyze_mask():
  #
  #   det_args = dict(
  #     img=img,
  #     segment_width=np.shape(img)[1],
  #     sigma=1.5,
  #     dx=5000,
  #     dy=4
  #   )
  #
  #   # Run smearing detection
  #   smr_map = detect_smearing2d(**det_args)
  #   smr_map_interp = interpolate_nan_2d(smr_map)
  #   smr_map_interp = filters.gaussian(smr_map_interp, sigma=2)
  #
  #   nonzeros = []
  #   for i in range(smr_map.shape[0]):
  #     line = []
  #     for j in range(smr_map.shape[1]):
  #       if not np.isnan(smr_map[i][j]):
  #         line.append(smr_map[i][j])
  #     nonzeros.append(line)
  #
  #   y = [v[0] for v in nonzeros if len(v) > 0]
  #   plt.plot(y)
  #   plt.xlabel('line number')
  #   plt.ylabel('shift between line y and y+4')
  #   plt.show()
  #
  #   plt.imshow(np.array(nonzeros), cmap='viridis')
  #   plt.show()
  #   return
  #
  # analyze_mask()
  # return

  clean_args = dict(
    mask=mask,
    min_size=800,
    portion=1.0,
    max_vert_extent=1500,
    top=mask_top_edge
  )

  def clean_mask(mask, top, min_size, portion, max_vert_extent):

    # Mask entire top lines
    if top > 0:
      mask[:top] = True

    # Mask top right border # TODO investigate if needed
    mask[:, -1] = True

    # Fill binary holes
    mask = fill_holes(mask)

    # Unmask all lines below line nr. 'max_vert_extent'
    if 0 < max_vert_extent < mask.shape[0]:
      mask[max_vert_extent:] = False

    # Mask small masking irregularities
    if portion > 0:
      mask = flood_smearing(mask, portion)

    # Remove True islands with small area
    if min_size > 0:
      mask = remove_isolated(mask, min_size)

    return mask

  # mask_final2 = clean_mask(**clean_args)
  mask_filled = fill_holes(mask)
  # mask_flooded = flood_pixels(mask_filled, ratio=0.4)
  # mask_flood = flood_smearing(mask_flooded, portion=1.0)
  mask_flood = flood_smearing(mask_filled, portion=1.0)
  # mask_flood2 = flood_smearing(mask_flood, portion=.5)
  # mask_final = fill_holes(mask_flood2)
  mask_final = fill_holes(mask_flood)
  mask_final2 = remove_isolated(mask_final, min_size=800)

  if plot:
    to_plot = [smr_map, smr_map_interp, mask_flood,
               mask_flood, mask_final, mask_final2]
    plot_smearing(plots=to_plot, path_plot=path_plot)

  # Fix missing lines as a consequence of parameter dy
  final_mask = np.full_like(img, dtype=bool, fill_value=False)
  h, w = np.shape(mask_final2)
  final_mask[:h, :w] = mask_final2
  return final_mask


def tile_ids_with_all_neighbors(array: np.ndarray) -> List[int]:
  result = []
  h, w = array.shape
  for y in range(1, h - 1):
    for x in range(1, w - 1):
      if array[y, x] != -1:
        neighbors = [array[j, i] for j in range(y - 1, y + 2) for i in range(x - 1, x + 2)]
        if all(n != -1 for n in neighbors):
          result.append(int(array[y, x]))
  return result



def is_smearing(a: np.ndarray):
  """
  Determine whether the shift pattern has smearing characteristics.
  Distinguish between smearing and directional sample features
  Inputs:
    a: 1-D np.array signal
  :return:
  """
  dy = 4

  for ic in range(0, 2000, 500):
    sum = np.cumsum(a[:, ic])
    b = sum[dy:]
    diff = b - sum[:-dy]
    # plt.plot(diff, '*-')
    # plt.show()
  return


def plot_tile_masks(
        mask_map: MaskMap,
        path_plot: UniPath,
        tid_map: np.ndarray,
        show: bool,
        mask_shape: Tuple[int, int]
) -> None:
  """Plots binary masks for whole section.

  The function is to be used for OVs of vertical tile pairs as the main
  purpose was to plot smearing distortion mask and smearing only occurs
  on top of EM-images. EDIT: function has now broader usage for any masks

  Args:
      mask_map: MaskMap object containing mapped binary masks
      path_plot: storage path for plot
      tid_map: loaded tile-id map
      mask_shape: defines size of plotted graphs
      show: render and show the plotted window (disable while computing on cluster)

  """

  # Get the maximum x and y values from the keys
  max_x, max_y = 0, 0
  for coord in mask_map.keys():
    x, y = coord
    max_x = max(max_x, x)
    max_y = max(max_y, y)

  nr, nc = max_x + 1, max_y + 1
  fig, axes = plt.subplots(nc, nr, figsize=(20, 12))

  # Iterate through the dictionary and plot each value
  for subplot_index, (k, mask_data) in enumerate(mask_map.items(), start=1):
    ax = axes.flatten()[int(subplot_index) - 1]

    # Plot binary mask or dummy rectangle
    dummy_img = np.ones(mask_shape, dtype=np.uint8) * 255
    if mask_data is not None:
      ax.imshow(mask_data[:mask_shape[0]], cmap='gray', origin='upper')
    else:
      ax.imshow(dummy_img, cmap='gray', origin='upper', vmin=0, vmax=255)
      ax.set_xticks([])
      ax.set_yticks([])

    # Plot name
    plot_name = ''
    if tid_map is not None:
      tile_id = tid_map.flatten()[int(subplot_index) - 1]
      if tile_id != -1:
        plot_name = f"{k} TileID: {str(tile_id)}"
    ax.set_title(plot_name)

  plt.tight_layout()
  plt.savefig(str(path_plot), dpi=600)
  if show:
    plt.show()
  else:
    plt.close(fig)
  print(f'tile masks saved to: {str(path_plot)}')
  return


def create_sbem_grid(grid_shape, tile_id_map) -> np.ndarray:
  # Create virtual SBEMimage grid of active tiles
  grid = np.full(shape=grid_shape, fill_value=-1)
  rows, cols = grid_shape
  for row_pos in range(rows):
    for col_pos in range(cols):
      tile_index = row_pos * cols + col_pos
      if tile_index in tile_id_map:
        grid[row_pos, col_pos] = tile_index
  return grid


def eval_(xo, rim, min_rim, margin):
  dx_new = xo + rim + margin
  dx_new = -min_rim if dx_new >= 0 else dx_new
  return xo if abs(dx_new) > abs(xo) else dx_new

