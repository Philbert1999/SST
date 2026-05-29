"""Reusable Streamlit components for the stock screening dashboard."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
import streamlit as st


def apply_dashboard_style() -> None:
    """Apply a clean financial-dashboard visual style."""
    st.markdown(
        """
        <style>
        .main .block-container {
            max-width: 1440px;
            padding-top: 1.25rem;
            padding-bottom: 2.5rem;
        }
        h1, h2, h3 { letter-spacing: 0; }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.7rem;
            color: #0f172a;
        }
        .subtle-note {
            color: #64748b;
            font-size: 0.92rem;
            margin-top: -0.45rem;
            margin-bottom: 1rem;
        }
        .score-pill {
            display: inline-block;
            min-width: 86px;
            text-align: center;
            border-radius: 999px;
            padding: 7px 12px;
            font-weight: 700;
            font-size: 1rem;
        }
        .score-high { background: #dcfce7; color: #166534; }
        .score-mid { background: #fef3c7; color: #92400e; }
        .score-low { background: #fee2e2; color: #991b1b; }
        .info-panel {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 14px 16px;
            background: #ffffff;
        }
        .risk-footer {
            margin-top: 1.25rem;
            padding: 12px 14px;
            border-radius: 8px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            color: #475569;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_cards(scan_count: int, selected_count: int, avg_score: float, max_score: float) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("扫描股票数", f"{scan_count:,}")
    c2.metric("入选股票数", f"{selected_count:,}")
    c3.metric("平均得分", f"{avg_score:.1f}" if selected_count else "-")
    c4.metric("最高得分", f"{max_score:.1f}" if selected_count else "-")


def render_score_badge(score: float) -> None:
    if score >= 160:
        css_class = "score-high"
    elif score >= 90:
        css_class = "score-mid"
    else:
        css_class = "score-low"
    st.markdown(f'<span class="score-pill {css_class}">{score:.1f}</span>', unsafe_allow_html=True)


def render_results_table(results: pd.DataFrame):
    """Render selectable result table and return selected row index."""
    if results.empty:
        st.info("暂无入选股票。请调整筛选条件后重新运行。")
        return None

    view = results.sort_values("total_score", ascending=False).reset_index(drop=True)
    event = st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "total_score": st.column_config.ProgressColumn(
                "total_score",
                help="多个策略触发时合并得分",
                min_value=0,
                max_value=max(100, float(view["total_score"].max())),
                format="%.1f",
            ),
            "amount": st.column_config.NumberColumn("amount", format="%.0f"),
            "close": st.column_config.NumberColumn("close", format="%.2f"),
            "pct_chg": st.column_config.NumberColumn("pct_chg", format="%.2f%%"),
            "turnover": st.column_config.NumberColumn("turnover", format="%.2f%%"),
        },
    )
    if event is not None and event.selection.rows:
        return event.selection.rows[0]
    return None


def render_stock_detail(row: pd.Series) -> None:
    st.subheader(f"{row.get('code', '')} {row.get('name', '')}")
    left, right = st.columns([1, 3])
    with left:
        st.caption("综合得分")
        render_score_badge(float(row.get("total_score", 0) or 0))
    with right:
        st.markdown(
            f"""
            <div class="info-panel">
            <b>触发策略</b><br>{row.get("triggered_strategies", "-")}
            </div>
            """,
            unsafe_allow_html=True,
        )

    detail_cols = st.columns(4)
    detail_cols[0].metric("收盘价", _fmt_number(row.get("close"), 2))
    detail_cols[1].metric("涨跌幅", f"{_fmt_number(row.get('pct_chg'), 2)}%")
    detail_cols[2].metric("成交额", format_amount(row.get("amount")))
    detail_cols[3].metric("换手率", f"{_fmt_number(row.get('turnover'), 2)}%")

    st.markdown("**触发原因**")
    _render_text_items(row.get("reasons", ""))
    st.markdown("**风险提示**")
    _render_text_items(row.get("risks", ""))


def csv_download_button(df: pd.DataFrame, filename: str = "stock_candidates.csv") -> None:
    if df.empty:
        return
    buffer = StringIO()
    df.to_csv(buffer, index=False, encoding="utf-8-sig")
    st.download_button(
        "导出 CSV",
        data=buffer.getvalue().encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )


def risk_footer() -> None:
    st.markdown(
        '<div class="risk-footer">本工具仅用于学习和辅助观察，不构成投资建议。</div>',
        unsafe_allow_html=True,
    )


def format_amount(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(amount):
        return "-"
    if amount >= 100_000_000:
        return f"{amount / 100_000_000:.2f} 亿"
    if amount >= 10_000:
        return f"{amount / 10_000:.2f} 万"
    return f"{amount:.0f}"


def _fmt_number(value: Any, digits: int) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(number):
        return "-"
    return f"{number:.{digits}f}"


def _render_text_items(text: Any) -> None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        st.write("-")
        return
    items = [item.strip() for item in str(text).replace("\n", "；").split("；") if item.strip()]
    if not items:
        st.write("-")
        return
    for item in items:
        st.markdown(f"- {item}")
