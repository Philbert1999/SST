"""Plotly chart helpers for the stock screening dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def kline_chart(df: pd.DataFrame, title: str = "") -> go.Figure:
    """Render candlestick chart with MA5, MA10, MA20, and volume."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_heights=[0.72, 0.28])

    if df is None or df.empty:
        fig.update_layout(title="\u6682\u65e0 K \u7ebf\u6570\u636e", height=560, template="plotly_white")
        return fig

    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"]).sort_values("date")
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data["MA5"] = data["close"].rolling(5, min_periods=5).mean()
    data["MA10"] = data["close"].rolling(10, min_periods=10).mean()
    data["MA20"] = data["close"].rolling(20, min_periods=20).mean()

    fig.add_trace(
        go.Candlestick(
            x=data["date"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            name="K\u7ebf",
            increasing_line_color="#ef4444",
            decreasing_line_color="#10b981",
            increasing_fillcolor="#fecaca",
            decreasing_fillcolor="#bbf7d0",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Scatter(x=data["date"], y=data["MA5"], name="MA5", line=dict(color="#f59e0b", width=1.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=data["date"], y=data["MA10"], name="MA10", line=dict(color="#2563eb", width=1.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=data["date"], y=data["MA20"], name="MA20", line=dict(color="#7c3aed", width=1.4)), row=1, col=1)
    fig.add_trace(go.Bar(x=data["date"], y=data["volume"], name="\u6210\u4ea4\u91cf", marker_color="#94a3b8"), row=2, col=1)

    fig.update_layout(
        title=title,
        height=580,
        template="plotly_white",
        margin=dict(l=10, r=10, t=46, b=10),
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="\u4ef7\u683c", row=1, col=1, showgrid=True, gridcolor="#eef2f7")
    fig.update_yaxes(title_text="\u6210\u4ea4\u91cf", row=2, col=1, showgrid=True, gridcolor="#eef2f7")
    return fig


def forward_return_chart(summary: dict, horizon: int = 5) -> go.Figure:
    """Render average forward returns and win rates for D1-D5."""
    days = list(range(1, horizon + 1))
    avg_returns = [summary.get(f"avg_return_d{day}", 0.0) for day in days]
    win_rates = [summary.get(f"win_rate_d{day}", 0.0) for day in days]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=[f"D{day}" for day in days],
            y=avg_returns,
            name="\u5e73\u5747\u6536\u76ca\u7387",
            marker_color=["#ef4444" if value >= 0 else "#10b981" for value in avg_returns],
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=[f"D{day}" for day in days],
            y=win_rates,
            name="\u4e0a\u6da8\u5360\u6bd4",
            mode="lines+markers",
            line=dict(color="#2563eb", width=2),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        height=360,
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_yaxes(title_text="\u5e73\u5747\u6536\u76ca\u7387\uff08%\uff09", secondary_y=False)
    fig.update_yaxes(title_text="\u4e0a\u6da8\u5360\u6bd4\uff08%\uff09", secondary_y=True, range=[0, 100])
    return fig
