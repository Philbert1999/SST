from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config import APP_CONFIG
from data.akshare_provider import AkshareProvider
from performance import evaluate_snapshot, list_snapshots, load_snapshot, save_screening_snapshot, summarize_evaluation
from strategy_framework import (
    ScannerFilterConfig,
    StockScanner,
    StrengthScoreStrategy,
    StrongPullbackStrategy,
    VolumeBreakoutStrategy,
)
from ui.charts import forward_return_chart, kline_chart
from ui.components import (
    apply_dashboard_style,
    csv_download_button,
    render_metric_cards,
    render_results_table,
    render_stock_detail,
    risk_footer,
)


STRATEGY_FACTORIES = {
    "\u653e\u91cf\u7a81\u7834": VolumeBreakoutStrategy,
    "\u5f3a\u52bf\u56de\u8e29": StrongPullbackStrategy,
    "\u5f3a\u5ea6\u6253\u5206": StrengthScoreStrategy,
}
DATA_CACHE_VERSION = "akshare_fallback_v3"


@st.cache_resource(show_spinner=False)
def get_data_provider() -> AkshareProvider:
    return AkshareProvider()


@st.cache_data(show_spinner=False, ttl=60 * 10)
def load_stock_list(_provider: AkshareProvider, cache_version: str) -> pd.DataFrame:
    data = _provider.get_stock_list()
    if data.empty:
        raise RuntimeError("股票列表暂时无法获取，请刷新连接后重试。")
    return data


@st.cache_data(show_spinner=False, ttl=60 * 10)
def load_daily_data(_provider: AkshareProvider, code: str, start_date: date, end_date: date, cache_version: str) -> pd.DataFrame:
    data = _provider.get_daily_data(code, start_date, end_date)
    if data.empty:
        raise RuntimeError("日线数据暂时不可用，请稍后重试。")
    return data


def build_sidebar() -> dict:
    with st.sidebar.form("scan_filters"):
        st.header("\u7b5b\u9009\u6761\u4ef6")
        st.caption("修改条件后点击运行筛选，统一提交；旧结果会保留到新一轮成功完成。")

        today = date.today()
        default_start = today - timedelta(days=APP_CONFIG.ui.default_history_days)
        default_end = today
        start_date = st.date_input(
            "\u5f00\u59cb\u65e5\u671f",
            value=default_start,
            max_value=today,
            key="scan_start_date",
        )
        end_date = st.date_input(
            "\u7ed3\u675f\u65e5\u671f",
            value=default_end,
            max_value=today,
            key="scan_end_date",
        )
        start_date, end_date, date_valid, date_message = normalize_scan_dates(start_date, end_date, today)
        if not date_valid:
            st.error(date_message)
        elif (end_date - start_date).days < 45:
            st.warning("\u65e5\u671f\u8de8\u5ea6\u8f83\u77ed\uff0c\u90e8\u5206\u7b56\u7565\u53ef\u80fd\u56e0\u6837\u672c\u4e0d\u8db3\u800c\u65e0\u6cd5\u89e6\u53d1\u3002")

        selected_strategy_names = st.multiselect(
            "\u7b56\u7565\u9009\u62e9",
            options=list(STRATEGY_FACTORIES),
            default=list(STRATEGY_FACTORIES),
        )

        min_amount_yi = st.number_input(
            "\u6700\u4f4e\u6210\u4ea4\u989d\uff08\u4ebf\u5143\uff09",
            min_value=0.0,
            value=APP_CONFIG.ui.default_min_amount_yi,
            step=0.5,
        )
        min_price = st.number_input(
            "\u6700\u4f4e\u80a1\u4ef7\uff08\u5143\uff09",
            min_value=0.0,
            value=APP_CONFIG.ui.default_min_price,
            step=0.5,
        )
        max_price = st.number_input(
            "\u6700\u9ad8\u80a1\u4ef7\uff08\u5143\uff09",
            min_value=1.0,
            value=APP_CONFIG.ui.default_max_price,
            step=5.0,
        )
        exclude_st = st.checkbox("\u6392\u9664 ST", value=APP_CONFIG.ui.default_exclude_st)
        exclude_new = st.checkbox("\u6392\u9664\u65b0\u80a1\uff08\u4e0a\u5e02\u4e0d\u8db3 60 \u5929\uff09", value=APP_CONFIG.ui.default_exclude_new_stock)
        exclude_star_market = st.checkbox("\u6392\u9664\u79d1\u521b\u677f", value=APP_CONFIG.ui.default_exclude_star_market)

        run_scan = st.form_submit_button("\u8fd0\u884c\u7b5b\u9009", type="primary", use_container_width=True)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "selected_strategy_names": selected_strategy_names,
        "min_amount": min_amount_yi * 100_000_000,
        "min_price": min_price,
        "max_price": max_price,
        "exclude_st": exclude_st,
        "exclude_new": exclude_new,
        "exclude_star_market": exclude_star_market,
        "run_scan": run_scan,
        "date_valid": date_valid,
        "date_message": date_message,
    }


def normalize_scan_dates(start_date, end_date, today: date) -> tuple[date, date, bool, str]:
    """Normalize and validate sidebar scan dates."""
    try:
        start = pd.to_datetime(start_date).date()
        end = pd.to_datetime(end_date).date()
    except Exception:
        return today - timedelta(days=APP_CONFIG.ui.default_history_days), today, False, "\u65e5\u671f\u683c\u5f0f\u65e0\u6548\uff0c\u8bf7\u91cd\u65b0\u9009\u62e9\u3002"

    if start > today or end > today:
        return min(start, today), min(end, today), False, "\u65e5\u671f\u4e0d\u80fd\u8d85\u8fc7\u4eca\u5929\u3002"
    if start > end:
        return start, end, False, "\u5f00\u59cb\u65e5\u671f\u4e0d\u80fd\u665a\u4e8e\u7ed3\u675f\u65e5\u671f\u3002"
    return start, end, True, ""


def init_state() -> None:
    defaults = {
        "scan_results": pd.DataFrame(),
        "stock_list": pd.DataFrame(),
        "scanner_errors": [],
        "scanner_skipped": [],
        "last_scan_count": 0,
        "last_snapshot_path": "",
        "last_evaluation": pd.DataFrame(),
        "last_scan_options": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def run_scan(provider: AkshareProvider, options: dict) -> None:
    if not options.get("date_valid", True):
        st.error(options.get("date_message") or "\u65e5\u671f\u9009\u62e9\u65e0\u6548\u3002")
        return
    if not options["selected_strategy_names"]:
        st.warning("\u8bf7\u81f3\u5c11\u9009\u62e9\u4e00\u4e2a\u7b56\u7565\u3002")
        return

    if options["min_price"] > options["max_price"]:
        st.error("最低股价不能高于最高股价；上次筛选结果已保留。")
        return
    try:
        with st.spinner("正在获取股票列表…"):
            stock_list = load_stock_list(provider, DATA_CACHE_VERSION)
    except Exception as exc:
        st.error(f"股票列表获取失败：{exc}。上次筛选结果已保留，可用侧栏刷新按钮重试。")
        return

    strategies = [STRATEGY_FACTORIES[name]() for name in options["selected_strategy_names"]]
    filter_config = ScannerFilterConfig(
        exclude_st=options["exclude_st"],
        exclude_delisting_risk=True,
        min_listing_days=APP_CONFIG.filter.exclude_new_stock_days if options["exclude_new"] else 0,
        min_price=float(options["min_price"]),
        max_price=float(options["max_price"]),
        min_amount=float(options["min_amount"]),
        max_recent_gain_pct=APP_CONFIG.filter.max_20d_gain,
        exclude_star_market=options["exclude_star_market"],
    )

    progress = st.progress(0, text="\u51c6\u5907\u5f00\u59cb\u626b\u63cf...")

    def on_progress(done: int, total: int, code: str, status: str) -> None:
        progress.progress(done / total, text=f"\u626b\u63cf\u8fdb\u5ea6 {done}/{total}\uff1a{code} {status}")

    scanner = StockScanner(
        stock_list=stock_list,
        data_provider=provider,
        strategies=strategies,
        start_date=options["start_date"],
        end_date=options["end_date"],
        filter_config=filter_config,
        progress_callback=on_progress,
    )

    with st.spinner("\u6b63\u5728\u83b7\u53d6\u884c\u60c5\u5e76\u8fd0\u884c\u7b56\u7565..."):
        results = scanner.scan()

    progress.empty()
    st.session_state.scanner_errors = scanner.errors
    st.session_state.scanner_skipped = scanner.skipped
    if results.empty and scanner.errors:
        st.error(f"本轮有 {len(scanner.errors)} 只股票读取失败，且未得到候选。上次结果已保留；详见扫描日志。")
        return
    st.session_state.last_scan_options = dict(options)
    st.session_state.stock_list = stock_list
    st.session_state.scan_results = results
    st.session_state.last_scan_count = len(stock_list)
    try:
        snapshot_path = save_screening_snapshot(results, options["end_date"], options)
    except OSError as exc:
        snapshot_path = None
        st.warning(f"筛选结果可继续查看与导出，但快照保存失败：{exc}")
    st.session_state.last_snapshot_path = str(snapshot_path or "")

    st.success(f"\u7b5b\u9009\u5b8c\u6210\uff0c\u5165\u9009 {len(results)} \u53ea\u80a1\u7968\u3002")
    if scanner.errors:
        st.warning(f"本轮有 {len(scanner.errors)} 只股票读取失败，结果仅涵盖读取成功的股票，详见扫描日志。")
    if snapshot_path:
        st.info(f"\u5df2\u4fdd\u5b58\u590d\u76d8\u5feb\u7167\uff1a{snapshot_path.name}")


def render_main(provider: AkshareProvider, options: dict) -> None:
    results = st.session_state.scan_results
    scan_count = int(st.session_state.last_scan_count or len(st.session_state.stock_list))
    selected_count = len(results)
    avg_score = float(results["total_score"].mean()) if selected_count else 0.0
    max_score = float(results["total_score"].max()) if selected_count else 0.0

    render_metric_cards(scan_count, selected_count, avg_score, max_score)

    with st.expander("\u626b\u63cf\u65e5\u5fd7", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.caption("\u5f02\u5e38\u8bb0\u5f55")
            if st.session_state.scanner_errors:
                st.dataframe(pd.DataFrame(st.session_state.scanner_errors), use_container_width=True, hide_index=True)
            else:
                st.write("\u6682\u65e0\u5f02\u5e38\u3002")
        with col2:
            st.caption("\u8fc7\u6ee4\u8bb0\u5f55")
            skipped = pd.DataFrame(st.session_state.scanner_skipped)
            if not skipped.empty:
                st.dataframe(skipped.head(200), use_container_width=True, hide_index=True)
            else:
                st.write("\u6682\u65e0\u8fc7\u6ee4\u8bb0\u5f55\u3002")

    st.subheader("\u5019\u9009\u6c60\u7ed3\u679c")
    st.markdown(
        '<div class="subtle-note">\u70b9\u51fb\u8868\u683c\u4e2d\u7684\u80a1\u7968\u884c\uff0c\u53ef\u67e5\u770b\u89e6\u53d1\u539f\u56e0\u3001\u98ce\u9669\u63d0\u793a\u548c K \u7ebf\u8d70\u52bf\u3002</div>',
        unsafe_allow_html=True,
    )
    if results.empty and st.session_state.last_scan_count == 0:
        st.info("尚未运行筛选。先在左侧设置日期与条件，再点击运行筛选；连接失败可点击刷新股票列表重试。")
        return
    selected_index = render_results_table(results)
    csv_download_button(results, f"stock_candidates_{pd.Timestamp.now():%Y%m%d_%H%M%S}.csv")

    if results.empty:
        return

    scan_options = st.session_state.last_scan_options or options
    st.caption(f"显示已完成筛选：{scan_options['start_date']} 至 {scan_options['end_date']}。修改条件后需点击运行筛选。")
    sorted_results = results.sort_values("total_score", ascending=False).reset_index(drop=True)
    if selected_index is None:
        selected_index = 0
    selected_row = sorted_results.iloc[selected_index]

    st.divider()
    left, right = st.columns([0.92, 1.28], gap="large")
    with left:
        render_stock_detail(selected_row)

    with right:
        code = str(selected_row["code"]).zfill(6)
        try:
            chart_data = load_daily_data(provider, code, scan_options["start_date"], scan_options["end_date"], DATA_CACHE_VERSION)
        except Exception as exc:
            st.warning(f"K 线暂时无法加载：{exc}。筛选结果仍可查看与导出。")
            chart_data = pd.DataFrame()
        st.plotly_chart(kline_chart(chart_data, f"{code} {selected_row['name']} K\u7ebf"), use_container_width=True)




def render_performance_review(provider: AkshareProvider) -> None:
    st.subheader("\u7b5b\u9009\u8d28\u91cf\u590d\u76d8")
    st.markdown(
        '<div class="subtle-note">\u9009\u62e9\u67d0\u6b21\u7b5b\u9009\u5feb\u7167\uff0c\u68c0\u67e5\u5165\u9009\u80a1\u7968\u5728\u4e4b\u540e 1-5 \u4e2a\u4ea4\u6613\u65e5\u7684\u6536\u76ca\u8868\u73b0\u3002\u6536\u76ca\u6309\u7b5b\u9009\u65e5\u6536\u76d8\u4ef7\u5230\u540e\u7eed\u6536\u76d8\u4ef7\u8ba1\u7b97\u3002</div>',
        unsafe_allow_html=True,
    )

    snapshots = list_snapshots()
    if not snapshots:
        st.info("\u8fd8\u6ca1\u6709\u5386\u53f2\u7b5b\u9009\u5feb\u7167\u3002\u5148\u5230\u201c\u5019\u9009\u7b5b\u9009\u201d\u9875\u8fd0\u884c\u4e00\u6b21\u7b5b\u9009\u3002")
        return

    labels = [item.label() for item in snapshots]
    selected_label = st.selectbox("\u9009\u62e9\u5386\u53f2\u7b5b\u9009\u5feb\u7167", labels)
    selected_snapshot = snapshots[labels.index(selected_label)]
    snapshot = load_snapshot(selected_snapshot.path)
    horizon = st.radio(
        "\u6307\u6807\u7edf\u8ba1\u5929\u6570",
        options=[1, 2, 3, 4, 5],
        index=4,
        format_func=lambda value: f"D{value}",
        horizontal=True,
    )
    st.caption("\u8868\u683c\u59cb\u7ec8\u4fdd\u7559 D1-D5 \u6536\u76ca\u660e\u7ec6\uff1b\u4e0a\u65b9\u6307\u6807\u548c\u56fe\u8868\u6309\u4f60\u9009\u62e9\u7684\u5929\u6570\u5207\u6362\u3002")

    c1, c2, c3 = st.columns(3)
    c1.metric("\u5feb\u7167\u65e5\u671f", selected_snapshot.signal_date or "-")
    c2.metric("\u5019\u9009\u80a1\u6570", f"{len(snapshot):,}")
    c3.metric("\u521b\u5efa\u65f6\u95f4", selected_snapshot.created_at or "-")

    if st.button(f"\u8ba1\u7b97\u672a\u6765 1-5 \u4e2a\u4ea4\u6613\u65e5\u8868\u73b0\uff08\u5f53\u524d\u805a\u7126 D{horizon}\uff09", type="primary", use_container_width=True):
        progress = st.progress(0, text="\u6b63\u5728\u590d\u76d8\u5019\u9009\u80a1...")

        def on_progress(done: int, total: int, code: str) -> None:
            progress.progress(done / total, text=f"\u590d\u76d8\u8fdb\u5ea6 {done}/{total}\uff1a{code}")

        with st.spinner("\u6b63\u5728\u83b7\u53d6\u540e\u7eed\u884c\u60c5\u5e76\u8ba1\u7b97\u6536\u76ca..."):
            evaluation = evaluate_snapshot(snapshot, provider, horizon=5, progress_callback=on_progress)
        progress.empty()
        st.session_state.last_evaluation = evaluation
        st.session_state.last_evaluation_snapshot = selected_snapshot.name

    evaluation = st.session_state.get("last_evaluation", pd.DataFrame())
    if st.session_state.get("last_evaluation_snapshot") != selected_snapshot.name:
        evaluation = pd.DataFrame()
    if evaluation.empty:
        st.markdown("**\u5feb\u7167\u660e\u7ec6**")
        st.dataframe(snapshot, use_container_width=True, hide_index=True)
        return

    summary = summarize_evaluation(evaluation, horizon=horizon)
    available_days = pd.to_numeric(evaluation.get("available_forward_days"), errors="coerce").max()
    available_days = int(available_days) if pd.notna(available_days) else 0
    if available_days < 5:
        st.info(
            f"\u5f53\u524d\u884c\u60c5\u6570\u636e\u6700\u591a\u53ea\u8986\u76d6\u5230 D{available_days}\u3002"
            "\u8fd9\u901a\u5e38\u662f\u56e0\u4e3a\u7b5b\u9009\u65e5\u4e4b\u540e\u8fd8\u6ca1\u8d70\u5b8c 5 \u4e2a\u4ea4\u6613\u65e5\uff0c"
            "\u540e\u7eed\u4ea4\u6613\u65e5\u6536\u76d8\u540e\u91cd\u65b0\u70b9\u51fb\u590d\u76d8\u6309\u94ae\u5c31\u4f1a\u8865\u4e0a\u3002"
        )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("\u590d\u76d8\u6837\u672c", f"{summary['sample_count']:,}")
    m2.metric(f"D{horizon} \u5e73\u5747\u6536\u76ca", f"{summary['avg_return_selected']:.2f}%")
    m3.metric(f"D{horizon} \u4e0a\u6da8\u5360\u6bd4", f"{summary['win_rate_selected']:.1f}%")
    m4.metric(f"D{horizon} \u6700\u9ad8/\u6700\u4f4e", f"{summary['best_return_selected']:.2f}% / {summary['worst_return_selected']:.2f}%")

    st.plotly_chart(forward_return_chart(summary, horizon=horizon), use_container_width=True)

    show_cols = [
        "code",
        "name",
        "total_score",
        "triggered_strategies",
        "base_date",
        "base_close",
        "available_forward_days",
        "date_d1",
        "return_d1",
        "date_d2",
        "return_d2",
        "date_d3",
        "return_d3",
        "date_d4",
        "return_d4",
        "date_d5",
        "return_d5",
        "max_return_5d",
        "min_return_5d",
        "positive_any_5d",
        "eval_error",
    ]
    st.dataframe(evaluation[[col for col in show_cols if col in evaluation.columns]], use_container_width=True, hide_index=True)
    csv_download_button(evaluation, f"performance_review_{pd.Timestamp.now():%Y%m%d_%H%M%S}.csv")


def main() -> None:
    st.set_page_config(page_title="\u0041\u80a1\u77ed\u7ebf\u5019\u9009\u6c60\u7b5b\u9009\u5668", layout="wide")
    apply_dashboard_style()
    init_state()

    st.title("\u0041\u80a1\u77ed\u7ebf\u5019\u9009\u6c60\u7b5b\u9009\u5668")
    st.markdown(
        '<div class="subtle-note">\u77ed\u7ebf\u7b56\u7565\u5019\u9009\u6c60\u3001\u8bc4\u5206\u3001\u89e6\u53d1\u539f\u56e0\u4e0e\u98ce\u9669\u63d0\u793a\u4eea\u8868\u76d8\u3002</div>',
        unsafe_allow_html=True,
    )

    provider = get_data_provider()
    options = build_sidebar()
    if st.sidebar.button("刷新股票列表 / 重试连接", use_container_width=True):
        load_stock_list.clear()
        try:
            with st.spinner("正在重新连接数据源…"):
                refreshed = provider.get_stock_list(force_refresh=True)
            if refreshed.empty:
                st.sidebar.error("数据源仍不可用，请稍后重试。已有结果未清除。")
            else:
                st.sidebar.success(f"股票列表已更新：{len(refreshed):,} 只。")
        except Exception as exc:
            st.sidebar.error(f"连接失败：{exc}。已有结果未清除。")

    tab_scan, tab_review = st.tabs(["\u5019\u9009\u7b5b\u9009", "\u6548\u679c\u590d\u76d8"])
    with tab_scan:
        if options["run_scan"]:
            run_scan(provider, options)
        render_main(provider, options)
    with tab_review:
        render_performance_review(provider)
    risk_footer()


if __name__ == "__main__":
    main()
