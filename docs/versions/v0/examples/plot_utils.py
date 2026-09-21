"""示例共享绘图保存工具。"""

from pathlib import Path
import matplotlib.pyplot as plt

__all__ = ["save_figure"]

_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def save_figure(name):
    """保存当前 matplotlib 图表到 screenshots 目录。"""
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = _SCREENSHOT_DIR / f"{name}.png"
    plt.tight_layout(pad=1.5)
    plt.savefig(str(p), dpi=150, bbox_inches="tight")
    print(f"[plot] saved: {p}")
    plt.close()
