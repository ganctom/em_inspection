import numpy as np
import plotly.express as px


class OverlapPresenter:
    """Pure UI factory for rendering pixel cross-correlation overlays."""

    @classmethod
    def render_overlap_view(
        cls,
        img_array: np.ndarray,
        build_figure_fn: callable,
        tid_a: int,
        tid_b: int,
        overlap_type: str,
        z: int,
    ) -> px.imshow:
        """Proxies image matrix array maps downstream to canvas builders."""
        # This isolates the internal private chart generation of your service
        return build_figure_fn(img_array, tid_a, tid_b, overlap_type, z)
