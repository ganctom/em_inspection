import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

from constants import UI


class FlowPresenter:
    """
    Pure Presentation Layer responsible for generating Plotly figures
    for optical flow diagnostics and vector field analysis.
    """

    @staticmethod
    def render_diagnostic_grid(fine_x: dict,
                               fine_y: dict,
                               xy: tuple[int, int],
                               z_range: tuple[float, float] | None = None,
                               transpose: bool = False) -> go.Figure:
        """Assembles a 2x2 multi-channel heatmap grid of fine vector displacements."""
        if xy not in fine_x and xy not in fine_y:
            return go.Figure()

        fig: go.Figure = make_subplots(
            rows=2, cols=2,
            subplot_titles=(
                UI.LBL_FLOW_XH, UI.LBL_FLOW_XV,
                UI.LBL_FLOW_YH, UI.LBL_FLOW_YV
            ),
            horizontal_spacing=0.1,
            vertical_spacing=0.3
        )

        def _add_trace(row: int, col: int, data: np.ndarray) -> None:
            fig.add_trace(
                go.Heatmap(
                    z=data,
                    colorscale='Viridis',
                    zmin=z_range[0] if z_range else None,
                    zmax=z_range[1] if z_range else None,
                    colorbar=dict(
                        thickness=15, len=0.45, yanchor='top',
                        y=1.0 if row == 1 else 0.45,
                        x=0.46 if col == 1 else 1.0
                    )
                ),
                row=row, col=col
            )

        spatial_ndim = 2

        if xy in fine_x:
            d_x: np.ndarray = fine_x[xy][:spatial_ndim, :]
            do_T_x: bool = not transpose
            _add_trace(1, 1, (d_x[0].T if do_T_x else d_x[0])[::-1, ::-1])
            _add_trace(1, 2, (d_x[1].T if do_T_x else d_x[1])[::-1, ::-1])

        if xy in fine_y:
            d_y: np.ndarray = fine_y[xy][:spatial_ndim, :]
            do_T_y: bool = transpose
            _add_trace(2, 1, d_y[0].T if do_T_y else d_y[0])
            _add_trace(2, 2, d_y[1].T if do_T_y else d_y[1])

        fig.update_layout(
            template="plotly_dark",
            height=250,
            margin=dict(l=20, r=0, b=20, t=50),
            paper_bgcolor='black',
            plot_bgcolor='black',
            font=dict(size=10),
            showlegend=False
        )

        axis_style: dict = dict(
            showticklabels=False, showgrid=False, zeroline=False,
            mirror=True, ticks='outside', ticklen=0,
            showline=True, linecolor='white', linewidth=1
        )
        fig.update_xaxes(**axis_style)
        fig.update_yaxes(**axis_style, autorange='reversed')

        return fig