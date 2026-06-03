"""Render an OHLCV frame to a candlestick PNG for the Chart Vision agent.

The Vision agent needs *an image*. In production that is a TradingView-style
screenshot supplied by the data layer; for the runnable demo we render the
synthetic candles ourselves so the agent has something real to read with a
single OpenAI key and no external tooling.

Pure Pillow (already a dependency) — no matplotlib. Degrades to ``None`` if
Pillow is unavailable, in which case the Vision agent abstains cleanly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd


def render_candles(
    df: pd.DataFrame,
    *,
    out_path: str | Path | None = None,
    last: int = 120,
    width: int = 1100,
    height: int = 560,
    title: str = "XAUUSD",
) -> str | None:
    """Render the last ``last`` candles of ``df`` to a PNG; return its path.

    Returns ``None`` if Pillow is not installed (the caller then skips Vision).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # pragma: no cover - optional dependency
        return None

    data = df.tail(last)
    if data.empty:
        return None

    bg, grid, up, down, axis = (18, 22, 30), (40, 46, 58), (38, 166, 91), (224, 67, 67), (150, 158, 172)
    pad_l, pad_r, pad_t, pad_b = 12, 78, 34, 22
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b

    hi, lo = float(data["high"].max()), float(data["low"].min())
    span = (hi - lo) or 1.0
    hi, lo = hi + span * 0.04, lo - span * 0.04  # headroom
    span = hi - lo

    def y(price: float) -> float:
        return pad_t + (hi - price) / span * plot_h

    img = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default()
    except Exception:  # pragma: no cover
        font = None

    # Horizontal price grid + right-axis labels.
    for i in range(5):
        price = hi - span * i / 4
        yy = y(price)
        d.line([(pad_l, yy), (pad_l + plot_w, yy)], fill=grid, width=1)
        d.text((pad_l + plot_w + 6, yy - 6), f"{price:,.1f}", fill=axis, font=font)

    n = len(data)
    slot = plot_w / n
    body = max(1.0, slot * 0.6)
    for i, (_, row) in enumerate(data.iterrows()):
        cx = pad_l + slot * (i + 0.5)
        o, h, lw, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        color = up if c >= o else down
        d.line([(cx, y(h)), (cx, y(lw))], fill=color, width=1)  # wick
        y0, y1 = y(max(o, c)), y(min(o, c))
        d.rectangle([cx - body / 2, y0, cx + body / 2, max(y1, y0 + 1)], fill=color)

    d.text((pad_l, 8), f"{title}  ·  {n} bars  ·  last {float(data['close'].iloc[-1]):,.2f}", fill=(220, 224, 232), font=font)

    if out_path is None:
        fd, out_path = tempfile.mkstemp(prefix="goldmind_chart_", suffix=".png")
        import os

        os.close(fd)
    out_path = str(out_path)
    img.save(out_path)
    return out_path
