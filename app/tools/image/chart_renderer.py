from io import BytesIO
from typing import Literal

from PIL import Image

ChartType = Literal["radar", "bar", "form_bar"]


def render_chart_figure(
    data: dict,
    chart_type: ChartType,
) -> Image.Image:
    """Render a chart as an in-memory PIL Image (not saved to disk).
    The result is passed to composite() as the content_zone.
    """
    if chart_type == "radar":
        return _render_radar(data)
    if chart_type == "bar":
        return _render_bar(data)
    return _render_bar(data)  # fallback


def _render_radar(data: dict) -> Image.Image:
    """Radar chart for player stat comparison using mplsoccer."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mplsoccer import Radar

        params = data.get("params", [])
        values_a = data.get("values_a", [])
        values_b = data.get("values_b", [])
        label_a = data.get("label_a", "Player A")
        label_b = data.get("label_b", "Player B")
        low = data.get("low", [0] * len(params))
        high = data.get("high", [1] * len(params))

        radar = Radar(params, low, high, num_rings=4, ring_width=1, center_circle_radius=1)
        fig, ax = radar.setup_axis()
        fig.patch.set_facecolor("#12121c")
        ax.set_facecolor("#12121c")

        radar.draw_circles(ax=ax, facecolor="#1e1e2e", edgecolor="#3a3a4a")
        radar.draw_radar_compare(
            values_a, values_b, ax=ax,
            kwargs_radar={"facecolor": "#00c3ff", "alpha": 0.4},
            kwargs_compare={"facecolor": "#ff6b6b", "alpha": 0.4},
        )
        radar.draw_param_labels(ax=ax, color="#ffffff", fontsize=11)
        ax.legend(
            [label_a, label_b],
            loc="lower center",
            fontsize=12,
            facecolor="#12121c",
            labelcolor="white",
        )
        return _fig_to_pil(fig)
    except Exception:
        return _fallback_image("Radar chart unavailable")


def _render_bar(data: dict) -> Image.Image:
    """Horizontal bar chart for stat comparison."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = data.get("labels", [])
        values_a = data.get("values_a", [])
        values_b = data.get("values_b", [])
        label_a = data.get("label_a", "Player A")
        label_b = data.get("label_b", "Player B")
        metric = data.get("metric", "Value")

        x = range(len(labels))
        fig, ax = plt.subplots(figsize=(10, 6), facecolor="#12121c")
        ax.set_facecolor("#1e1e2e")
        width = 0.35
        ax.bar([i - width / 2 for i in x], values_a, width, label=label_a, color="#00c3ff", alpha=0.85)
        ax.bar([i + width / 2 for i in x], values_b, width, label=label_b, color="#ff6b6b", alpha=0.85)
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, color="white", fontsize=11)
        ax.tick_params(colors="white")
        ax.spines[:].set_color("#3a3a4a")
        ax.set_ylabel(metric, color="white")
        ax.legend(facecolor="#12121c", labelcolor="white")
        fig.tight_layout()
        return _fig_to_pil(fig)
    except Exception:
        return _fallback_image("Bar chart unavailable")


def _fig_to_pil(fig) -> Image.Image:
    import matplotlib.pyplot as plt
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).copy()


def _fallback_image(message: str) -> Image.Image:
    img = Image.new("RGB", (1080, 600), (18, 18, 28))
    return img
