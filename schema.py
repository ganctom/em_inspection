from dataclasses import dataclass


@dataclass(frozen=True)  # frozen=True prevents accidental runtime changes
class InspectionSchema:
    """Namespace for standardized project file and directory names."""

    # Directories (Relative to Project Root)
    DIR_SECTIONS = "sections"
    DIR_STITCHED = "stitched-sections"
    DIR_INSPECTION = "_inspect"
    DIR_DOWNSCALED = "downscaled"
    DIR_OVERLAPS = "overlaps"
    DIR_OVERLAPS_OUTLIERS = "overlaps_outliers"
    DIR_INF_OVERLAPS = "inf_overlaps"

    # Standardized Filenames (Section-specific)
    FILE_SECTION_CONFIG = "section.yaml"
    FILE_COARSE_OFFSETS = "cx_cy.json"
    FILE_TILE_ID_MAP = "tile_id_map.json"

    # Global/Aggregate Filenames
    FILE_ALL_OFFSETS = "all_offsets.npz"
    FILE_ALL_TILE_ID_MAPS = "all_tile_id_maps.npz"
    FILE_INF_VALS = "inf_vals.txt"
    FILE_MISSING_SECTIONS = "missing_sections.yaml"
    FILE_CO_OUTLIERS = "coarse_offset_outliers.txt"
    FILE_MARGIN_MASKS = "margin_masks.npz"
    FILE_COARSE_MESH = "coarse_mesh.pkl"
    FILE_ROI_MASKS = "roi_masks.npz"
    FILE_SMR_MASKS = "smr_masks.npz"
    FILE_TILE_MASKS = "tile_masks.npz"