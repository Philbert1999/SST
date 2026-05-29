# A 股短线候选池筛选器

## 项目简介

这是一个使用 Python 构建的 A 股短线候选股筛选项目。项目通过 AKShare 获取行情数据，使用可扩展的策略框架对股票进行过滤、打分和汇总，并通过 Streamlit 提供一个简洁的可视化页面。

本项目的定位是“辅助观察工具”，不是自动交易系统。它只输出候选股票、策略评分、触发原因和风险提示，不提供任何买卖指令，也不包含真实下单功能。

## 功能特点

- 使用 AKShare 获取 A 股股票列表、日线行情、实时行情和板块数据。
- 使用统一的 `DataProvider` 抽象，后续可以替换为 Tushare、同花顺 iFinD 或其他数据源。
- 使用面向对象的策略框架，每个策略继承 `BaseStrategy`。
- 支持批量扫描多个股票，并自动合并同一只股票触发的多个策略得分。
- 支持基础股票池过滤：ST、退市风险、新股、低价股、低成交额、短期过热股票。
- Streamlit 页面支持策略选择、参数设置、结果表格、详情查看、K 线图和 CSV 导出。
- K 线图展示 MA5、MA10、MA20 和成交量。
- 单只股票数据异常不会中断整个扫描流程，会记录错误并继续运行。

## 安装方法

建议使用 Python 3.10 或更高版本。

```bash
cd stock_short_term
python -m venv .venv
```

Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

## 运行方法

启动 Streamlit 页面：

```bash
streamlit run app.py
```

启动后，浏览器会打开类似下面的地址：

```text
http://localhost:8501
```

也可以测试数据源模块：

```bash
python data/akshare_provider.py
```

也可以测试策略框架示例：

```bash
python strategy_framework/example_usage.py
```

## 项目目录说明

```text
stock_short_term/
├── app.py                         # Streamlit 主页面
├── scanner.py                     # 扫描器便捷入口
├── config.py                      # 旧版全局配置
├── requirements.txt               # 项目依赖
├── README.md                      # 项目说明文档
├── data/
│   ├── data_provider.py           # 数据源抽象类
│   ├── akshare_provider.py        # AKShare 数据源实现
│   └── cache.py                   # 文件缓存工具
├── strategy_framework/
│   ├── base.py                    # BaseStrategy 抽象基类
│   ├── config.py                  # 策略参数配置
│   ├── strategies.py              # 放量突破、强势回踩、强度打分策略
│   ├── scanner.py                 # 批量扫描器
│   ├── engine.py                  # 多策略执行器
│   └── example_usage.py           # 策略框架示例
├── ui/
│   ├── components.py              # Streamlit UI 组件
│   └── charts.py                  # Plotly K 线图
├── core/                          # 早期核心模块，保留兼容
└── strategies/                    # 早期策略模块，保留兼容
```

初学者主要关注这几个文件：

- `app.py`：页面入口。
- `data/akshare_provider.py`：数据怎么来。
- `strategy_framework/strategies.py`：策略怎么写。
- `strategy_framework/scanner.py`：如何批量扫描股票。
- `ui/components.py` 和 `ui/charts.py`：页面怎么展示。

## 策略说明

### 放量突破

放量突破策略主要寻找“价格突破 + 成交量放大”的短线候选股。

典型条件包括：

- 今日涨幅处于合理区间，例如 2% 到 7%。
- 今日成交量明显高于过去 5 日平均成交量。
- 今日收盘价突破过去 20 日最高收盘价。
- MA5 大于 MA10，说明短期均线较强。
- 收盘价位于当日振幅的上方区域，说明收盘位置较强。

注意：突破不等于一定上涨，突破后回落也可能是假突破。

### 强势回踩

强势回踩策略主要寻找“前期较强，短线回踩但趋势尚未破坏”的股票。

典型条件包括：

- 最近 10 日涨幅大于一定阈值，例如 8%。
- 今日最低价接近 MA5 或 MA10。
- 今日成交量小于昨日成交量，表示缩量回踩。
- 今日收盘价重新站上 MA5 或 MA10。
- 今日跌幅没有过大，例如不低于 -3%。

注意：回踩策略依赖原有趋势，如果跌破关键均线，需要重新判断。

### 强度打分

强度打分策略不是简单判断“是否满足全部条件”，而是对多个维度加分。

打分项目包括：

- 今日涨幅在 3% 到 8%，加分。
- 今日量比大于 1.5，加分。
- 收盘价接近最高价，加分。
- MA5 > MA10 > MA20，加分。
- 成交额大于 3 亿，加分。
- 换手率在 3% 到 20%，加分。

最后得分超过设定阈值时，才认为 `signal=True`。

注意：高分只表示短线形态和流动性较好，不代表未来一定上涨。

### 板块热度

板块热度策略用于观察个股是否处于强势板块中。项目早期策略模块中保留了 `sector_hot.py`，可以用于参考或扩展。

常见思路包括：

- 获取行业或概念板块涨跌幅排名。
- 优先关注排名靠前的板块。
- 个股上涨与板块上涨形成共振时加分。
- 板块热度退潮时降低候选优先级。

注意：板块热度变化很快，适合作为辅助因素，不适合作为唯一依据。

## 参数配置说明

项目中主要有两类参数。

### 页面筛选参数

在 Streamlit 侧边栏中可以设置：

- 日期范围：用于获取日线行情。
- 策略多选：选择要启用的策略。
- 最低成交额：过滤流动性不足的股票。
- 最低股价：过滤低价股。
- 是否排除 ST：过滤 ST 和 *ST 股票。
- 是否排除新股：默认排除上市不足 60 天的新股。

### 策略参数

策略参数主要在 `strategy_framework/config.py` 中：

- `BreakoutConfig`：放量突破策略参数。
- `PullbackConfig`：强势回踩策略参数。
- `StrengthScoreConfig`：强度打分策略参数。
- `StrategyFrameworkConfig`：策略配置集合。

例如，想调整放量突破的成交量放大倍数，可以修改：

```python
volume_ratio_threshold = 1.5
```

想调整强度打分的信号阈值，可以修改：

```python
signal_threshold = 70
```

扫描器过滤参数在 `strategy_framework/scanner.py` 的 `ScannerFilterConfig` 中：

```python
min_listing_days = 60
min_price = 3.0
min_amount = 300_000_000
overheat_days = 20
max_recent_gain_pct = 40.0
```

## 如何添加新策略

新增策略通常只需要 4 步。

### 1. 创建策略类

在 `strategy_framework/strategies.py` 中新增一个类，继承 `BaseStrategy`。

```python
from .base import BaseStrategy, EvaluationContext


class MyStrategy(BaseStrategy):
    name = "my_strategy"
    display_name = "我的策略"

    def _evaluate(self, context: EvaluationContext) -> dict:
        df = context.df
        stock_info = context.stock_info

        if len(df) < 20:
            return self._result(
                stock_info=stock_info,
                signal=False,
                score=0,
                reasons=["数据不足，至少需要 20 条日线。"],
                risks=["样本过少，信号不可靠。"],
            )

        latest = df.iloc[-1]
        signal = latest["pct_chg"] > 3

        return self._result(
            stock_info=stock_info,
            signal=signal,
            score=80 if signal else 0,
            reasons=["今日涨幅超过 3%。"] if signal else ["今日涨幅未超过 3%。"],
            risks=["该策略只是示例，不构成投资建议。"],
        )
```

### 2. 添加参数配置

如果策略需要参数，可以在 `strategy_framework/config.py` 中新增 dataclass。

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MyStrategyConfig:
    min_pct_chg: float = 3.0
```

### 3. 在页面中注册策略

在 `app.py` 的 `STRATEGY_FACTORIES` 中加入：

```python
STRATEGY_FACTORIES = {
    "放量突破": VolumeBreakoutStrategy,
    "强势回踩": StrongPullbackStrategy,
    "强度打分": StrengthScoreStrategy,
    "我的策略": MyStrategy,
}
```

### 4. 运行页面验证

```bash
streamlit run app.py
```

如果新策略出现在侧边栏多选框中，就说明注册成功。

## 常见问题

### 1. 为什么股票列表为空？

可能原因：

- 当前网络无法访问 AKShare 或东方财富接口。
- 代理、防火墙或 DNS 设置阻止了请求。
- AKShare 接口临时不可用。

可以稍后重试，或检查网络环境。

### 2. 为什么扫描很慢？

批量扫描需要逐只股票拉取日线数据，速度取决于网络、接口响应和股票数量。项目已经加入缓存，第二次运行通常会更快。

### 3. 为什么某只股票没有被选中？

可能原因：

- 被基础过滤条件排除，例如 ST、新股、低价、低成交额。
- 最近 20 日涨幅过高，被判断为过热。
- 日线数据不足。
- 没有任何策略返回 `signal=True`。

可以在页面的“扫描日志”中查看部分过滤记录。

### 4. 为什么策略结果和行情软件不完全一致？

可能原因：

- 数据源不同。
- 复权方式不同。
- AKShare 数据存在延迟。
- 行情软件对成交额、换手率、板块分类的计算口径不同。

### 5. 是否可以自动下单？

不可以。本项目没有自动下单功能，也不建议直接把筛选结果用于自动交易。它只用于学习、研究和辅助观察。

### 6. 可以替换数据源吗？

可以。实现 `data/data_provider.py` 中的 `DataProvider` 接口即可。需要保证返回字段统一，例如日线数据至少包含：

```text
date, open, high, low, close, volume, amount, pct_chg, turnover
```

## 风险提示

请在使用前认真阅读以下风险提示：

- 本项目仅用于学习、研究和辅助观察，不构成任何投资建议。
- 本项目不保证盈利，也不承诺策略有效性。
- 短线交易风险较高，价格波动可能非常剧烈。
- 数据可能存在延迟、缺失、错误或接口不可用的情况。
- 策略评分只是基于历史行情和简单规则的候选排序，不代表未来走势。
- 使用者需要自行判断、独立决策，并自行承担全部交易风险。
- 本项目不提供自动下单功能，也不对任何实际交易结果负责。

如果你是初学者，建议先把本项目作为学习工具，用于理解数据获取、策略设计、股票池过滤和可视化展示，不要直接用于实盘交易。
