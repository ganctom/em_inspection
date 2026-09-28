# Configuration Parameters Reference

This document provides a comprehensive technical reference for all configuration models, YAML parameters, and numeric thresholds utilized across the `em_inspection` pipeline.

---

## 1. Experiment & Acquisition Settings (`ExpConfig` / `AcquisitionConfig`)

Stored in `~/.em_inspection/experiments.yaml` or loaded into the active project context.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | `str` | `""` | Unique experiment identifier (e.g., `all-01240_22814`). |
| `acq_dir` | `str` | `""` | Absolute filesystem path to the raw SBEM acquisition directory. |
| `proc_dir` | `str` | `""` | Absolute filesystem path to the output/processing directory. |
| `grid_num` | `int` | `1` | Grid index integer (corresponds to `g0001`). |
| `grid_shape` | `(int, int)` | `(30, 25)` | Mosaic tile grid dimensions as `(columns, rows)` ($X, Y$). |
| `first_sec` | `int` | `0` | Physical section starting index ($Z_{start}$). |
| `last_sec` | `int` | `1000` | Physical section ending index ($Z_{end}$). |
| `pixel_size` | `float` | `10.0` | In-plane lateral sampling resolution in nanometers ($nm$). |
| `cut_thickness` | `float` | `30.0` | Microtome physical advance per cut in nanometers ($nm$). |

---

## 2. Coarse Alignment Parameters (`RegistrationConfig.coarse_params`)

Governs translational normalized cross-correlation across adjacent tile overlaps in Tab 2 and Tab 3.

| Parameter | Type | Default | Recommended Range | Description |
| :--- | :--- | :--- | :--- | :--- |
| `overlaps_x` | `list[int]` | `[200, 300, 400]` | `[150, 300, 450]` | Candidate horizontal overlap ribbon widths searched during peak cross-correlation. |
| `overlaps_y` | `list[int]` | `[200, 300, 400]` | `[150, 300, 450]` | Candidate vertical overlap ribbon heights searched during peak cross-correlation. |
| `min_range` | `list[int]` | `[10, 100, 0]` | `[15, 60, 0]` | Minimum dynamic range thresholds. Filters out untextured resin borders with flat histograms. |
| `min_overlap`| `int` | `20` | `10 - 50` | Minimum overlap width in pixels required to calculate a valid correlation peak. |
| `filter_size`| `int` | `10` | `5 - 25` | Gaussian smoothing kernel diameter applied to raw tile borders before correlation. |
| `clahe` | `bool` | `False` | `True` or `False` | Enables Contrast Limited Adaptive Histogram Equalization prior to correlation. |
| `clip_limit` | `float` | `2.0` | `0.05 - 2.0` | Threshold for contrast limiting in CLAHE. Lower values prevent noise over-amplification. |
| `kernel_size`| `int` | `128` | `128 - 512` | Grid tile dimensions for CLAHE local histogram equalization. |

---

## 3. Fine Patch Optical Flow Parameters (`RegistrationConfig.stitch_params`)

Controls dense block matching across tile overlaps in Stage 4.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `patch_size` | `list[int, int]` | `[120, 120]` | Dimensions of local square patches evaluated during block matching. |
| `batch_size` | `int` | `512` | Number of patch pairs evaluated concurrently on CPU or GPU/Metal workers. |
| `min_peak_ratio` | `float` | `1.6` | Ratio between the primary cross-correlation peak and the secondary peak. Discards ambiguous matches. |
| `min_peak_sharpness` | `float` | `1.6` | Sharpness metric of the correlation peak. Rejects broad, flat correlation surfaces. |
| `max_deviation` | `int` | `6` | Maximum permissible vector deviation (in pixels) from median neighbor flow. |
| `max_magnitude` | `int` | `0` | Absolute upper limit for flow magnitude (0 disables hard thresholding). |
| `min_patch_size` | `int` | `10` | Minimum patch size accepted during multi-scale hierarchical flows. |
| `max_gradient` | `float` | `12.0` | Maximum spatial flow gradient before a displacement vector is flagged as non-physical shear. |
| `reconcile_flow_max_deviation` | `float` | `-1.0` | Tolerance for forward-backward consistency checks (-1 disables). |
| `step_patch_size`| `int` | `10` | Sampling stride between adjacent patches. |

---

## 4. Elastic Spring Mesh Integration (`MeshIntegrationConfig`)

Controls the numerical relaxation of the 2D spring-mass system in SOFIMA.

$$\mathbf{F}_{\text{net}} = -k (\mathbf{x}_i - \mathbf{x}_j - \mathbf{d}_{ij}) - \gamma \mathbf{v}_i$$

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `dt` | `float` | `0.001` | Time integration step size for the solver. Smaller values increase stability on large distortions. |
| `gamma` | `float` | `0.05` | Damping coefficient that absorbs kinetic energy and prevents perpetual oscillation. |
| `k` | `float` | `0.1` | Elastic spring stiffness between adjacent mesh nodes. Higher values enforce rigid tile geometry. |
| `stride` | `int` | `40` | Spacing in pixels between mesh nodes. |
| `num_iters` | `int` | `1000` | Minimum iteration steps per relaxation run. |
| `max_iters` | `int` | `20000` | Maximum iteration cutoff if convergence criteria are not satisfied. |
| `stop_v_max` | `float` | `0.001` | Velocity convergence criterion. Relaxation halts when max node velocity drops below this threshold. |
| `dt_max` | `float` | `100.0` | Upper bound for adaptive time-step acceleration. |
| `prefer_orig_order` | `bool` | `True` | Preserves nominal tile order when resolving ambiguous boundary conditions. |
| `remove_drift` | `bool` | `True` | Subtracts global net translation and rotation accumulated during mesh relaxation. |

---

## 5. Warping & Output Masking (`WarpConfigStitching` / `MaskingConfig`)

Governs the final pixel interpolation and thumbnail generation.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `margin` | `int` | `0` | Extra padding (in pixels) added around the section bounding box. |
| `mask_margin` | `int` | `0` | Trims outer tile border pixels before blending. Useful for eliminating objective vignetting. |
| `rim_size` | `int` | `40` | Width of the smooth cosine/linear feathering rim applied along overlap seams. |
| `use_clahe` | `bool` | `True` | Applies global contrast normalization to raw tiles before final warping. |
| `warp_parallelism` | `int` | `6` | Number of worker processes allocated to parallel spline warping per section. |
| `downscale_factor` | `float` | `0.3` | Downscaling factor for overview thumbnails (`thumb_sXXXXX_gYYYY.tif`). |
