# 股票综合看盘系统 · 项目目录与代码审查指南 (Project Structure & Review Guide)

本压缩包为专为代码审查（Code Review）准备的纯净源码包，已排除所有版本控制信息（`.git`）、Python 字节码缓存（`__pycache__`）、虚拟环境（`.venv`）以及历史每日抓取的临时数据和大体积缓存。

---

## 1. 核心架构分层图

```text
股票看盘/
├── core/                       # [纯算力领域核心层] 100% 纯内存算法，无网络与磁盘 IO 依赖
│   ├── __init__.py             # 统一算力导出出口
│   ├── chan.py                 # 缠论日线级别数学引擎（包含合并/分型/笔/中枢/背驰/买卖点）
│   ├── quality.py              # 涨停板多因子质量评分算法（时间/封单/连板/烂板扣分）
│   └── emotion.py              # 市场短线情绪指数数学模型（v1/v2 去饱和加权、周期映射）
│
├── scripts/                    # [业务逻辑与数据接入层] 负责实时行情抓取、策略执行与命令行交互
│   ├── data_layer.py           # 统一数据层（TDX 二进制协议 40ms 极速 + Baostock 前复权 + 腾讯/东财 HTTP 容灾）
│   ├── abnormal_volatility.py  # 【防守端】A股异常波动监管红线与卡异动最高安全价反推引擎
│   ├── resonance_engine.py     # 【进攻端】点面共振五态标签引擎 (共振/孤立/逆势/双子星/卡位)
│   ├── data_feed.py            # 四源容灾矩阵（腾讯 -> 同花顺 -> 新浪 -> 东财）与内存 TTL 缓存
│   ├── ths_extractor.py        # 同花顺免密接口解析器（带 VWAP 分时黄线与题材库）
│   ├── stock_dashboard.py      # 大盘主控与命令行 CLI 仪表盘（外观 Facade 模式向下兼容）
│   ├── paper_cli.py            # 纸上模拟交易 CLI 主程序
│   ├── paper_trading.py        # 纸上模拟交易撮合与风控引擎
│   ├── auction_audit.py        # 早盘竞价雷达收盘自动对账与打脸账本引擎
│   ├── strategic_decision.py   # 战略战术决策中枢（周期判定、量化开火门禁、持仓风控）
│   ├── auction_radar.py        # 9:25 集合竞价雷达、昨日溢价与亏钱效应大面榜
│   ├── strategies_lib.py       # 12 种短线交易策略选股库
│   ├── screener.py             # 8 大经典 K 线形态筛选器
│   ├── news_events.py          # 7×24 财经快讯解析与重大异动事件提取
│   ├── sim_score.py            # 情绪得分校验与推演
│   └── sim_llm.py              # 大模型辅助推演（可选接入）
│
├── web/                        # [展现与交互层]
│   ├── main.py                 # FastAPI Web 服务器（RESTful 接口、动态时段 TTL 控制）
│   ├── static/
│   │   └── js/
│   │       └── dashboard.js    # 前端解耦核心交互逻辑 (ECharts渲染/轮询/抽屉/对账账本)
│   └── templates/
│       └── index.html          # 现代化前端界面（开盘啦风格连板天梯树 + TradingView 质感）
│
├── tests/                      # [自动化测试套件]
│   ├── test_abnormal_volatility.py # 异常波动状态机重置与10日全滑动窗口卡价单测 (4大严苛用例)
│   ├── test_quant_validation.py   # 5道量化硬门禁流水线合成数据校验单测
│   ├── test_core_algorithms.py     # core/ 纯算力单元测试（9 项核心测试，脱机 0.001s 完成）
│   └── test_strategic_decision.py  # 战略决策与真实场景回归测试（8 项全真实用例覆盖）
│
├── benchmarks/                 # [性能基准与实证分析] 耗时较长的离线压测与实证对比脚本
│   ├── quant_validation.py     # 【量化裁判所】选股与超短稀疏信号 5 道硬门禁流水线 (IC/单调性/OOS/归因/置换)
│   ├── benchmark_tdx.py        # 通达信 (TDX) 连接延迟、K 线与竞价分笔吞吐压测
│   ├── compare_gate.py         # 大盘趋势闸门开闭胜率对比实证
│   ├── validate_gate_honest.py # 闸门选时 Alpha 统计检验
│   ├── smoke_paper_live.py     # 模拟盘实盘巡检冒烟脚本
│   └── smoke_paper_replay.py   # 模拟盘历史回放冒烟脚本
│
├── config/                     # [配置管理]
│   ├── llm.local.json.example  # LLM 与三方接口配置示例
│   └── llm.local.json          # 本地配置项
│
├── data/                       # [静态字典库与核心运行档案]
│   ├── ths_concepts.json       # 官方 1571+ 题材板块词典库
│   ├── stock_names.json        # A 股全量证券代码与中文名称映射
│   ├── stock_list.json         # 股票代码清单
│   └── stock_data/             # 情绪历史轨迹归档与策略判定账本
│
├── requirements.txt            # 项目 Python 依赖声明
├── README.md                   # 完整功能使用说明与 CLI 命令行手册
├── SKILL.md                    # Antigravity 智能体技能标准规范定义
├── 一键启动股票看盘.bat        # Windows 桌面一键启动 Web 服务脚本
└── 一键每日自迭代.bat         # 每日收盘全自动自检与数据归档脚本
```

---

## 2. 代码审查重点建议 (Review Highlights)

1. **纯算力解耦与领域建模 (`core/`)**：
   - 检查 `core/chan.py`：K 线重叠包含处理（向上包含/向下包含）、分型确认、有效笔（间隔 $\ge$ 4 根合并 K 线）、三笔重叠中枢及 MACD 面积背驰检测的严密性。
   - 检查 `core/quality.py`：基于涨停板实证因子（9:25 竞价早盘超额、封单占流通比、2 板黄金 alpha 结构与炸板惩罚）的多因子打分归一化逻辑。
2. **高可用四源容灾矩阵 (`scripts/data_feed.py` & `ths_extractor.py`)**：
   - 上游故障无感切换：主通道（腾讯）异常时，自动毫秒级降级至同花顺、新浪、东财，附带通道健康心跳与动态 TTL 内存缓存。
3. **战略防守与 9:25 开火门禁 (`scripts/strategic_decision.py`)**：
   - 检查在“退潮期/冰点期”如何通过严格事实源阻断冲动交易，以及持仓动态止损核验机制。
4. **前端沉浸式交互 (`web/templates/index.html`)**：
   - 查看开盘啦风格的连板天梯阶梯展示、游资战况多空能量槽、以及等宽金融数字排版。

---

## 3. 自动化测试执行方式

在项目根目录下执行以下命令即可全自动运行验证测试：

```bash
# 1. 运行纯算力领域核心单元测试（脱机秒级跑通）
python tests/test_core_algorithms.py

# 2. 运行战略决策与战备风控回归测试套件
python tests/test_strategic_decision.py
```
