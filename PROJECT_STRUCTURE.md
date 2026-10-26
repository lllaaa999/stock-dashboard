# 股票综合看盘系统 · 项目地图与现状体检

> 本文是**唯一权威的项目结构说明**（2026-10-25 全量复核）。
> 旧的「目录树 + 审查建议」版本已整体重写：补全了 10 个此前漏登记的脚本、28 个 API 端点、
> 15 个前端组件，并把实测发现的缺陷与半成品集中列在第 6 节。
> 所有数字均为**实测**（`wc -l` / 接口实测 / 测试实跑），不是估算。

---

## 0. 一句话定位与规模

A 股短线/情绪周期的**本地看盘 + 量化决策系统**：Python 抓数算分，React 呈现，全离线可跑。

| 维度 | 实测规模 |
|---|---|
| 后端 Python | 20,600+ 行（core 553 / scripts 13,582 / web 2,459 / tests 2,495 / benchmarks 1,070） |
| 前端 | 16,568 行（15 个 React 组件 + 3,171 行 `ultraShortQuant.ts` 计算内核） |
| HTTP 接口 | **29 个 `/api/*`** + 1 个 `/ws` WebSocket |
| 自动化测试 | 20 个文件 / **54 个用例，全绿 0.9 秒** |
| 数据存档 | 情绪历史 **38 条**（20260804 ~ 20261023，已去重），其中 11 条带 `algo=v2` |
| 运行环境 | **Python 3.12**（3.10+ 才支持 dataclass slots）+ Node/bun 构建前端 |

---

## 1. 分层架构

```text
                 ┌──────────────────────────────────────────────┐
   上游免费源     │ 腾讯 qt.gtimg.cn  新浪 hq.sinajs.cn           │
  （无需付费）    │ 东财 push2ex/push2  datacenter  同花顺 d.10jqka│
                 └───────────────┬──────────────────────────────┘
                                 ▼
  ┌────────────────────────────────────────────────────────────┐
  │ scripts/  数据接入层（24 个 py + 1 个 ps1）                  │
  │  data_feed（四源容灾+TTL缓存）  data_layer（日K四级降级）     │
  │  market_gateway(web/) L1五档    ths_extractor（题材库）      │
  └───────────────┬────────────────────────────────────────────┘
                  ▼
  ┌────────────────────────────────────────────────────────────┐
  │ core/  纯算力层（无网络、无磁盘 IO，可脱机单测）              │
  │  chan.py 缠论    quality.py 涨停质量分    emotion.py 情绪打分 │
  └───────────────┬────────────────────────────────────────────┘
                  ▼
  ┌────────────────────────────────────────────────────────────┐
  │ scripts/  业务决策层                                         │
  │  情绪/梯队：stock_dashboard（God Object, 1765 行）           │
  │  竞价：auction_radar → auction_audit（次日对账）              │
  │  选股：strategies_lib(12策略)  screener(8形态)               │
  │  风控：abnormal_volatility  position_gate  strategic_decision │
  │  交易：paper_trading  backtest_engine                        │
  └───────────────┬────────────────────────────────────────────┘
                  ▼
  ┌────────────────────────────────────────────────────────────┐
  │ web/  FastAPI（28 端点 + /ws 推流 + 分时段 TTL 缓存）         │
  │  main.py 1195 行 / quant_data_service 731 / market_gateway 533│
  └───────────────┬────────────────────────────────────────────┘
                  ▼
  ┌────────────────────────────────────────────────────────────┐
  │ frontend/src/  React 19 + Vite + Tailwind（15 组件）          │
  │  Canvas 主图 / 竞价雷达 / 超短作战室 / 龙虎榜拓扑 / PWA        │
  │  bun run build → closeBundle 钩子自动同步 → web/dist          │
  └────────────────────────────────────────────────────────────┘
```

---

## 2. 目录逐项清单

### 2.1 `core/` — 纯算力层（553 行）

| 文件 | 行 | 职责 |
|---|---|---|
| `chan.py` | 315 | 缠论：包含合并 → 分型 → 笔 → 中枢 → 背驰 → 买卖点 |
| `quality.py` | 108 | 涨停质量分 0~10（封板时间 0.35 + 封单/流通 0.35 + 连板结构 0.30，炸板扣分） |
| `emotion.py` | 110 | 情绪打分 v1/v2、区间映射、背离判定、`effect_flat` 存档扁平化 |
| `__init__.py` | 20 | 统一导出；`scripts/*` 一律 `from core.x import y` |

**关键约束**：这一层不允许出现 `requests` / `open()`，全部可脱机断言（`tests/test_core_algorithms.py` 0.002 秒跑完 12 个用例）。

### 2.2 `scripts/` — 数据接入 + 业务决策（24 py，13,582 行）

| 文件 | 行 | 职责 |
|---|---|---|
| `stock_dashboard.py` | 1765 | **God Object**：七层雷达、涨停池、情绪、梯队、板块、新闻、选股、战略决策 |
| `strategies_lib.py` | 927 | 12 策略选股库（E~L + M 情绪总开关），`auto` 按周期自动启停 |
| `ultrashort_metrics.py` | 883 | VW-DVR 贝叶斯收缩、正交化打分、封单强度与空间测算 |
| `backtest_engine.py` | 820 | 轻量回测引擎（4 套预置策略） |
| `data_feed.py` | 802 | 四源容灾矩阵（腾讯→同花顺→新浪→东财）+ 内存 TTL/LRU 缓存 |
| `paper_trading.py` | 741 | 纸上交易撮合与风控 |
| `abnormal_volatility.py` | 705 | 交易所异动红线与「最高安全价」反推（含除权折算） |
| `auction_radar.py` | 703 | 9:25 竞价雷达：弱转强/抢筹/假高开/大面榜 |
| `news_events.py` | 672 | 7x24 快讯采集 + 去重 + 事件结构化 |
| `quant_engine_daemon.py` | 636 | 量化引擎守护进程（CPU 绑核） |
| `strategic_decision.py` | 630 | 战略战术决策中枢（周期阶段/开火门禁/持仓风控） |
| `data_layer.py` | 566 | 日K四级降级：TDX → baostock → AKShare → 腾讯 HTTP |
| `resonance_engine.py` | 541 | 点面共振五态标签（共振/孤立/逆势/双子星/卡位） |
| `dynamic_theme_sync.py` | 469 | 题材共振传导矩阵 |
| `ths_extractor.py` | 456 | 同花顺免密接口解析（VWAP 黄线 + 题材库） |
| `lhb_orthogonal_evaluator.py` | 399 | 龙虎榜席位「反套皮」正交验身 |
| `auction_audit.py` | 366 | 竞价候选快照 + 收盘对账 + 打脸账本 |
| `screener.py` | 357 | 8 大 K 线形态选股 |
| `daily_auto_iteration.py` | 257 | 每日盘后流水线（情绪归档→消息面→对账→阈值校准） |
| `position_gate.py` | 250 | 大盘趋势仓位闸门（ADX + 周期） |
| `trading_calendar.py` | 211 | 交易日历校验与「最近交易日」回溯 |
| `paper_cli.py` | 173 | 纸上交易 CLI |
| `threshold_evidence.py` | 128 | 阈值分位数实证核查（拒绝修辞通胀） |
| `stock_daily_note.py` | 125 | 看盘笔记 → Obsidian |
| `sync_check.ps1` | — | 存档单点校验（防多副本分叉） |

### 2.3 `web/` — 服务端（2,459 行，28 个 `/api` 端点）

| 文件 | 行 | 职责 |
|---|---|---|
| `main.py` | 1195 | 全部路由、分时段 TTL 缓存、字段映射到前端契约 |
| `quant_data_service.py` | 731 | 梯队断层/晋级率/题材共振/龙虎榜数据加工 |
| `market_gateway.py` | 533 | L1 五档与逐笔、K线网关、熔断器 |
| `dist/` | — | **唯一线上 UI**（vite build 产物，入库托管） |

端点分组（实测 29 个）：

| 域 | 端点 |
|---|---|
| 行情（8） | `/api/market`、`/market/search`、`/market/quote/{symbol}`、`/market/snapshot`、`/market/klines/{symbol}`、`/market/scenario`(POST)、`/stock/{code}`、`/watchlist` |
| 量化（8） | `/quant/auction_radar`、`/quant/regulatory`、`/quant/dragon_tiger`、`/quant/ladder`、`/quant/theme_resonance`、`/quant/chan/{symbol}`、`/screen`、`/strategies` |
| 竞价（3） | `/auction`、`/auction/audit`、`/auction/audit/ledger` |
| 决策（3） | `/emotion/history`、`/strategic_decision`、`/data_status` |
| 交易回测（6） | `/backtest/presets`、`/backtest/run`(仅 GET)、`/paper/replay`、`/paper/tick`、`/paper/report`、`/paper/reset` |
| 运维（1） | `/api/health` |
| 实时 | `/ws`（五档/逐笔推流） |

### 2.4 `frontend/src/` — 客户端（16,568 行，15 组件）

| 组件 | 行 | 说明 |
|---|---|---|
| `UltraShortQuantWorkbench.tsx` | 1855 | 超短作战室（总览/竞价/梯队/龙虎榜/共振/异动/承接） |
| `FinancialChart.tsx` | 1370+ | 原生 Canvas 主图：分时 + 5/15 分 + 日/周/月K，MA/EMA/BOLL + VOL/MACD/KDJ/RSI；**缠论图层（笔/中枢/买卖点，可开关）** |
| `DragonTigerNetworkGraph.tsx` | 1047 | 龙虎榜席位拓扑 |
| `ThemeResonanceMonitorPanel.tsx` | 989 | 题材共振监测 |
| `CallAuctionRadarPlugin.tsx` | 879 | 9:25 竞价雷达 |
| `RegulatoryMonitorPanel.tsx` | 872 | 法定异动监管 |
| `PriceAlertModal.tsx` | 481 | 价格预警 |
| `WatchlistPanel.tsx` | 401 | 自选股 |
| `CommandPaletteModal.tsx` | 272 | 命令面板（键盘精灵） |
| `StockQuoteHeader.tsx` | 227 | 个股报价头 |
| `TradeTicksAndMetricsPanel.tsx` | 205 | 成交明细 + 基本面 |
| `PWAInstallModal.tsx` | 203 | PWA 安装 |
| `OrderBook5Panel.tsx` | 190 | 五档盘口/委比委差 |
| `TopNavBar.tsx` | 127 | 顶部导航 |
| `IndexTickerBar.tsx` | 54 | 指数滚动条 |

支撑层：`utils/ultraShortQuant.ts`（3171 行计算内核）、`utils/marketCalc.ts`（502）、`store/useMarketStore.ts`（745，Zustand 面板级订阅）、`services/wsClient.ts`（192）。

### 2.5 `tests/` — 自动化测试（20 文件 / 54 用例）

```bash
py -3.12 -m unittest discover -s tests -t .     # 一键全量：54 passed, 0.9s
```

覆盖：core 纯算法、异常波动状态机、战略决策 8 场景、竞价对账、日历并发、缠论加固、情绪 None 安全、仓位闸门、回测、纸上交易、共振、LHB 正交、VW-DVR。

### 2.6 `benchmarks/` — 离线压测与实证（8 个脚本，1,070 行）

`quant_validation.py`（5 道硬门禁：IC/单调性/OOS/归因/置换）、`benchmark_tdx.py`、`compare_gate.py`、`validate_gate_honest.py`、`four_states_5year_evidence.py`、`kawai_5year_evidence.py`、`smoke_paper_live.py`、`smoke_paper_replay.py`。

### 2.7 `data/` — 字典与运行档案（约 14 MB）

| 路径 | 内容 |
|---|---|
| `stock_names.json` / `stock_list.json` | A 股代码↔名称/清单（每日缓存） |
| `ths_concepts.json` | 同花顺 1571+ 题材词典 |
| `stock_data/sentiment_history.jsonl` | **权威情绪存档**（38 条，按 date 唯一） |
| `stock_data/strategy_decisions.jsonl` | 战略决策账本 |
| `stock_data/auction_records/` | 竞价候选快照 + 对账台账 |
| `stock_data/paper_*.jsonl` / `paper_state.json` | 纸上交易持仓与流水 |
| `news/` `llm/` | 消息面归档、推演/对账归档（均已 gitignore） |

### 2.8 根目录

| 文件 | 说明 |
|---|---|
| `README.md` | 面向使用者：功能清单、CLI 手册、数据源 |
| `SKILL.md` | 面向 Agent/开发者的规范 + 踩坑记录（含收口更新） |
| `PROJECT_STRUCTURE.md` | 本文件：项目地图与现状体检 |
| `一键启动股票看盘.bat` | 启动 Web（固定 `STOCK_DATA_HOME`，自动挑 3.10/3.11/3.12） |
| `一键每日自迭代.bat` | 盘后流水线 |
| `paper_cli.py` | 根级转发器 → `scripts/paper_cli.py` |
| `requirements.txt` | Python 依赖 |

---

## 3. 一条数据的完整链路

```
涨停池(push2ex) ─┬─→ n_zt/n_zb/n_dt/max_lb ─→ core.emotion.emotion_score_v2
                 │                              ├→ 0~100 分 + 区间 + 背离
                 │                              ├→ 写 sentiment_history.jsonl（门禁：交易日+非盘中+非回吐）
                 │                              └→ cycle_position（MA3/MA7，只比同 algo 记录）
                 ├─→ analyze_ladder_faults ─→ 断层诊断 ─→ /api/quant/ladder
                 └─→ 晋级率 _promotion_rate ─→ 情绪「赚钱效应」项

9:25 竞价 ─→ auction_radar（昨涨停∪昨炸板 为扫描域）─→ 弱转强/抢筹/大面
            └→ 候选快照落盘 ─→ 收盘 auction_audit 对账 ─→ /api/auction/audit/ledger

情绪 + 梯队 + 资金 + 消息面 ─→ strategic_decision（周期/仓位/开火门禁）─→ /api/strategic_decision
```

**为什么竞价只扫 56 只而不是 5000 只**：核心判据（占昨比、昨日封单、昨日形态）全部依赖「昨日涨停/炸板池」，扫全市场反而算不出来。这是设计，不是漏。

---

## 4. 运行与验证

```bash
# 依赖（首次）
pip install -r requirements.txt

# 启动（等价于双击 bat）
STOCK_DATA_HOME=D:/股票看盘/data py -3.12 web/main.py     # 默认 8001
# 或
cd web && STOCK_DATA_HOME=D:/股票看盘/data py -3.12 -m uvicorn main:app --port 8001

# 健康检查：frontend 应为 "react-dist"
curl http://127.0.0.1:8001/api/health

# 前端改动后必须重新构建（产物自动同步到 web/dist）
cd frontend && bun install && bun run build

# 全量测试
py -3.12 -m unittest discover -s tests -t .
```

> ⚠️ 环境坑：系统默认 `python` 可能是 3.9/3.13 且**没有装 fastapi**；本机可用环境是 `py -3.12`（fastapi 0.136.3）。3.9 会因 dataclass slots 直接报错。

### 4.1 CLI 全量命令（`stock_dashboard.py`）

| 命令 | 作用 |
|---|---|
| `market` | 七层雷达全景（指数/外盘/情绪/周期/板块/两融/快讯） |
| `stock <code> [--chart] [--days N]` | 个股体检，`--chart` 出 60 日 PNG |
| `auction` | 9:25 竞价雷达 + 亏钱效应大面榜 |
| `emotion [--date YYYY-MM-DD]` | 情绪指数（可查历史，周末自动回溯） |
| `cycle` | 92 科比五阶段周期定位（写回 `stage`/`stage_meta`） |
| `chan <code>` | 缠论笔/中枢/买卖点/背驰 |
| `screener [all]` | 四策略选股 |
| `news` | 7x24 消息面采集 → `data/news/` |
| `pred save/check/stats` | **预判闭环**：存档自己的判断 → 次日自动对账 → 累计命中率 |

另有 `strategies_lib.py auto|all`（12 策略）、`screener.py`（8 形态）、`paper_cli.py`（纸上交易）。

---

## 5. 当前验证结论（2026-10-25 实测）

**正常**：

- `/api/health` → `frontend: react-dist`，产物与 `index.html` 引用一致
- `/api/quant/ladder` → `maxBoardHeight: 6`，`hasLadderFault: true`（后端数据正确）
- 数据源四路健康（tencent / sina / eastmoney / ths）
- 全量 54 个测试用例通过
- `web/main.py` 无 `except Exception: pass` 静默吞异常

**已确认异常**：见下一节。

---

## 6. 现状缺陷与半成品（按严重度）

### P0 · 会显示「看起来正常但其实是假/空」的数字 —— 已于 2026-10-25 全部收口

| # | 位置 | 现象 | 状态 |
|---|---|---|---|
| 1 | `/api/market/quote/{symbol}` | 只返回 30 个 L1 字段，**没有 `ultraShort`**，前端 `ultraShortQuant.ts:240` 读 `quote.ultraShort.consecutiveBoards` 恒 0 → 竞价页「连板梯队最高 0 板」 | ✅ 已修：后端新增 `get_ultra_short_profile()`（真实涨停池/炸板池），挂在 quote、snapshot、WS INIT 与 `/api/quant/ladder` 的每只成分股上 |
| 2 | `UltraShortQuantWorkbench.tsx:448-476` | 为绕开 #1 硬编码合成 ultraShort（`auctionVolume=12000`、`yesterdayAmount=1.5亿`、`cumDeviation` 按板数查表 89.4/68.2/…） | ✅ 已删：改为「有实时报价就用报价+后端档案；无报价只构造可验证字段（价/昨收/涨跌停价/封单），量额换手 PE 一律 0」 |
| 3 | `quant_data_service.py` 题材共振 | ①审计说的 `zdf/fstime` 其实早已修好；②但**另有一处真硬编码**：领涨股不在涨停池时被编造 `firstSealTime='09:35:00'`、`amount=turnover*0.15`、`consecutiveBoards=1` | ✅ 已修：查得到池子真值就用，查不到返回 `None`。实测成员股首封时间已散开为 09:25:02 / 09:32:47 / 13:09:45… |
| 4 | `main.py` 异动监管 | 审计说指数历史序列被写成 `close=3000` | ✅ 复核为**已修**：现由 `fetch_symbol_klines(idx)` 构建真实 `idx_bars`，并校验与标的的重叠交易日（`match_count==0` 直接报错） |

### P1 · 功能缺口

| # | 项 | 说明 |
|---|---|---|
| 5 | `/api/sectors` → **404** | 前端请求了后端不存在的路由（板块数据实际在 `/api/market.sectors`） |
| 6 | 情绪面板未 React 化 | `/api/market.emotion` 有 70 只首板 / 37 个题材 / 四层晋级率 / 断层诊断，前端 `grep emotion` = 0 处引用 |
| 7 | 19 个孤儿端点 | 有数据、无前端入口（`/emotion/history`、`/screen`、`/strategies`、`/paper/*`、`/backtest/*`、`/stock/{code}`…） |
| 8 | 板块资金估算无标识 | 东财失败降级新浪时 `source=sina_estimated`，`flow = 成交额×涨跌幅×0.15` 经验系数；前端未展示该标识 |

### P2 · 口径与硬编码

| # | 位置 | 问题 |
|---|---|---|
| 9 | ~~`main.py` `dumpCount: 0`~~ | ✅ 已改为按 `OVERHEAT_DUMP` 信号实际统计（当前映射未产出该分类，故仍为 0，但不再是硬编码常量） |
| 10 | `main.py:396` | `signal != 'NORMAL'` 恒真（`NORMAL` 从未被赋值） |
| 11 | `quant_data_service.py:431-433` | `ebbTideRiskScore` 只有 78/35 两个常数，不是算出来的 |
| 12 | **情绪 v2 量程缺陷** | v2 权重合计 = 10+18+17+12+25 = **82**，而 `emotion_band` 的亢奋线是 **85** → 「亢奋」永不触发，`M 情绪总开关` 的亢奋分支是死代码。极端牛市样本实测顶到 82.0 |
| 13 | 交易日回退 | 三处逻辑不一致（情绪回溯 7 天 / 梯队 5 天 / 竞价不回溯） |

> **#12 的处理说明**：曾有改动把权重抬到 15/22/18/15/30（上限 100）以让 85 可达，但那样会让**全部历史存档、42/68/65 等实证阈值全部失效**（同一天 20261023 会从 65.02 跳到 81.0）。因此本次**回退了权重**（保留新增的 `eff.score` 越界 clamp），把「85 分不可达」作为已知缺口记录在此。若要真正修，两条路：
> - **A（推荐，改动小）**：把亢奋线从 85 降到 80，其余阈值不动，历史可比性不受影响；
> - **B（彻底，改动大）**：权重升到 100 分制，同时把 `algo` 标记升到 `v3`，并重算 42/68/65 与全部历史分位。

### 工程 / 仓库卫生

| # | 项 | 影响 |
|---|---|---|
| 14 | ~~`web/dist` 新产物未入库~~ | ✅ 已入库：`git add web/dist` 把新 hash 的 js/css 与 index.html/sw.js 一并暂存，旧 hash 的删除同步登记（提交后不会 404） |
| 15 | `frontend/package.json` | 名字还是 `react-example`；`dev`/`start` 指向不存在的 `server.ts`（`bun run dev` 必失败）；`lightweight-charts` / `@google/genai` / `express` / `dotenv` 零引用 |
| 16 | `requirements.txt` | `jinja2` 已无引用（Jinja 模板已删） |
| 17 | `data/llm/` | 残留 `sim-*.json` / `ledger.jsonl`，对应模块 `sim_llm.py` / `sim_score.py` 已删 |
| 18 | `scratch/` | 1.9k+ 文件：10 个 `_server*.log`、6 个 `*_before_*.py`、3 个 `backup_*` 目录；审计文档在 `scratch/audit/` |
| 19 | 文档漂移 | ✅ 已修：SKILL/README/PROJECT_STRUCTURE 三份文档已按实测对齐 |
| 20 | ~~监管面板仍是前端估算~~ | ✅ 已修（2026-10-25 第三轮）：`/api/quant/regulatory` 已接上，并新增 `history` 段返回真实 T-1/T-2；面板顶部新增「交易所法规口径（真实引擎）」区块，本地 2/3 日模型也改用真实日K，取不到时明确打「估算 · 未接真实日K」标 |
| 21 | `frontend` 类型检查此前是坏的 | `bun run lint`（tsc --noEmit）原先就报 `OrderBookLevel` 缺 `level`、`asks: []` 长度不符 —— 说明构建只跑 vite（不做类型检查），类型错误可以静默进产物。现已清零 |

---

## 7. 建议的清理顺序（均未执行，等你确认）

1. **补入库**：`git add web/dist/assets/*`（#14，最高优先，属于「一提交就坏」）
2. **删残留**：`scratch/*.log`、`scratch/*_before_*.py`、`data/llm/sim-*.json`（git 历史已可追溯，不需要本地副本）
3. **修依赖清单**：`requirements.txt` 去掉 jinja2；`package.json` 改名 + 修 `dev` 脚本（需重装 lock）
4. **收口半成品**：P0 #1/#2 一起做（后端补 `ultraShort` 真实字段 → 删掉前端硬编码兜底），这是唯一能让「连板梯队」真正可信的路径
5. **补视图 or 下线**：19 个孤儿端点二选一，别长期悬空

---

## 8. 改代码前必读的工程铁律（沿用）

1. **注释与代码必须同源**：注释写「查百亿成交额」，代码就不能是 `price > 0`。
2. **判「今天是不是交易日」只认硬判据**：实时行情的 `trade_time[:8] == ymd` 且 `raw_amount > 0`。
3. **改完先跑验证再报数**：54 个用例不到 1 秒，没有理由不跑。
4. **行尾与编码**：`data_feed.py / web/main.py / .gitignore` 是 **LF**；`stock_dashboard.py / index.html` 是 **CRLF**；`.bat` 必须 **GBK + CRLF + 无 BOM**。Python 文本模式 `write_text()` 会把 `\n` 变 `\r\n`，改文件前先探测原行尾。
5. **存档口径变更 = 计量单位变更**：动打分权重必须同时升 `algo` 版本，否则 MA3/MA7 会混算。
6. **累计指标不能靠追加维护**：账本类写入一律 upsert。

---

## 9. 本次梳理已落地的改动（2026-10-25）

梳理过程中发现的问题里，有 4 处属于「半成品 / 一致性缺口」，已当场收口；其余（第 6 节的 P0~P2）**只登记未动**，等你决定优先级。

| # | 改动 | 涉及文件 | 原因 |
|---|---|---|---|
| 1 | **回退情绪 v2 权重**（15/22/18/15/30 → 10/18/17/12/25），保留新增的 `eff.score` 越界 clamp | `core/emotion.py` | 抬权重那版是半截改动：不升 `algo` 会让新旧尺度在 MA3/MA7 里混算，且 20261023 会从 65.02 变 81.0，42/68/65 三条实证阈值全部失真。回退后用历史数据复算 20261023 = **65.02**，与存档逐位一致 |
| 2 | **情绪存档写入改 upsert + 历史去重** | `scripts/stock_dashboard.py`（新增 `_hist_upsert`）、`data/stock_data/sentiment_history.jsonl` | 实测存档里 **20261022 有两条**（`stage_meta` 一条 adjacent/conf2、一条 stay/conf3），根因是「先判断再 `open('a')` 追加」的 check-then-append 竞态。去重 39 → **38 条**（保留 conf=3 的那条），备份在 `scratch/backup_dedupe_20261025/` |
| 3 | **测试套件可一键跑通** | 新增 `tests/__init__.py`、`tests/test_history_upsert.py`；修 `test_resonance_engine.py` / `test_lhb_orthogonal_evaluator.py` 的 `sys.path` | 原来这 2 个文件直接 `ModuleNotFoundError`，且缺 `__init__.py` 导致 `unittest discover` 根本跑不起来。现在 **54 用例 / 0.9 秒全绿** |
| 4 | **文档与代码对齐** | 本文件（整体重写）、`README.md`、`SKILL.md` | 原文写「39 个接口」「/api/sim 仍在后端」「情绪 v1 是主公式」等均与现状不符；实测为 28 个 `/api`、`/api/sim` 已摘除、v2 为主公式 |

### 9.1 第二轮（按 1 → 3 → 4 执行，同日）

| # | 改动 | 涉及文件 | 验证 |
|---|---|---|---|
| 1 | **补真实 `ultraShort`**：新增 `get_ultra_short_profile()`，字段全部来自东财涨停池/炸板池 + L1 快照（连板数、昨连板数、首封时间、封单额、封单占流通比、炸板次数、行业、是否触板、竞价开盘价与竞价涨幅、昨日形态），取不到池子返回 `None` 而不是 0 | `web/quant_data_service.py`、`web/main.py` | 实测 002724（海洋王）→ `6连板 / 昨5连板 / 首封 09:53:51 / SPACE_DRAGON`；600519 → `0 连板、未触板`；`/api/quant/ladder` 每只成分股都带 `ultraShort` |
| 1b | **删掉前端硬编码兜底**：工作台不再编 `auctionVolume=12000`、`yesterdayAmount=1.5亿`、`cumDeviation` 按板数查表；无实时报价时只构造可验证字段，量/额/换手/PE 置 0 | `UltraShortQuantWorkbench.tsx`、`types/market.ts`（字段改可选并标注哪些"后端不给"） | `bun run lint` 通过；`bun run build` 产物已同步 |
| 1c | **WS 不再冲掉 `ultraShort`**：`applySnapshotBatch` 由整体替换改为 `{...旧, ...新}` 合并，否则连上 WS 几秒后又回到 0 板 | `store/useMarketStore.ts` | 代码路径核对（INIT 快照已带 `ultraShort`，批量帧只含 L1） |
| 1d | **竞价页改用全市场梯队**：`CallAuctionRadarPlugin` 原先只扫自选股算最高板（自选无涨停即 0），现改为优先取 `/api/quant/ladder` | `CallAuctionRadarPlugin.tsx` | 同上 |
| 3 | **前端产物入库** | `web/dist`（新 `index-Dq7epGlY.js` / `index-CSpBXWEm.css` + `index.html` + `sw.js`） | `git status` 显示新 hash 已 `A`、旧 hash 已 `D`，引用一致 |
| 4 | **复核两项高危口径**：题材共振的 `zdf/fstime` 早已修好；异动监管的指数序列也已换成真实 `idx_bars`（并校验重叠交易日）。但顺手抓到题材共振里**另一处真硬编码**（领涨股不在池时编 `09:35:00` / `amount=turnover*0.15`）并修掉 | `web/quant_data_service.py` | 实测成员股首封时间散开为 `09:25:02 / 09:32:47 / 13:09:45 …`，涨幅分布 `10.0/10.01/9.96/19.99`；`/api/quant/regulatory` 返回真实 `safe_price=13.68` |

> 剩余最大假数字来源已从「连板梯队」转移到 **P1 #20：监管面板的 T-1/T-2 涨跌幅仍是前端 `?? 5.2/4.8` 默认值**。彻底解决要把它接到后端孤儿端点 `/api/quant/regulatory`（有真值，实测冷启动 2.5s、已带 TTL 缓存）。

### 9.2 第三轮：把监管面板接上真实端点

| # | 改动 | 涉及文件 | 验证 |
|---|---|---|---|
| 1 | **后端补 `history`**：`/api/quant/regulatory` 返回体新增 `history`（`stock_return_t1/t2`、`index_return_t1/t2/today`、口径日期），数据取自该端点已拉取的日K，**不额外发请求** | `web/main.py` | 实测 002724：`t1=9.99% / t2=10.01%`，与日K `12.33/11.21`、`11.21/10.19` 逐位一致 |
| 2 | **前端接引擎真值**：新增 `RegulatoryEngineResult` / `RegulatoryHistory` 类型；`calculateRegulatoryDeviation(quote, indexPct?, history?)` 支持真实历史，结果带 `historySource: 'kline' \| 'estimated'` | `types/market.ts`、`utils/ultraShortQuant.ts` | `bun run lint` 通过 |
| 3 | **面板新增真实区块**：安全价 / 今日涨停价 / 距安全价空间 / 近9日已触发 + 绑定窗口 + 引擎建议；估算数据打「估算 · 未接真实日K」标，列表行加 `≈` 前缀 | `RegulatoryMonitorPanel.tsx` | CDP 实测渲染：`今日安全价 1584.34 / 涨停价 1465.68 / 距安全价空间 18.91% / 近9日 0 次`，无 JS 异常 |
| 4 | **统一取数钩子**：`useRealLadder()` / `useRealRegulatory()`（60s 模块级缓存），主图页顶部「六维条」与作战室共用；六维条此前是**另一套独立计算**（只扫自选股 + 无真实 T-1/T-2），这才是「最高标 0 板」在首页一直不消失的真正原因 | `hooks/useRealQuantData.ts`、`UltraShortQuantWorkbench.tsx` | CDP 实测：`最高标 6板(断层缺4/5板)`、`监管异动监测 1563.79元 (+17.14%)`（原为 0 板 + 占位值） |

> 至此，页面上的「连板身位 / 晋级率 / 监管安全价」三类数字都来自真实接口。仍属估算的只有：竞价成交额/未匹配手数/竞价量比（免费源拆不出来）、板块资金降级新浪时的 `sina_estimated`、以及非当前选中标的的 T-1/T-2（列表行有 `≈` 标）。

### 9.3 第四轮：竞价雷达「抢筹」误判（三峡新材 600293 实证）

| 问题 | 根因 | 修复 |
|---|---|---|
| 一字跌停(-9.98%、买盘全空、卖一压 31 万手) 被判「超预期抢筹」 | `auction_boom` 只判量能（量比/一字/封单/占昨比），**不看方向** | 抽出 `is_auction_boom()`：非跌停 + `pct>=0` + `委比>-40` 才可入池 |
| 该股在「大面榜」里也看不见 | `big_loss` 只按 `drop_from_high` 升序取前 12；一字跌停的 high==low，回撤恒 0 → 排最后被截断 | 排序键改为「跌停优先 → 跌幅更深 → 回撤更大」 |
| 即便进了大面榜也拿不到「核按钮」标签 | `main.py` 组装顺序是 弱转强→抢筹→核按钮，`seen` 去重先入先得 | 改为**核按钮优先**，再弱转强，最后抢筹 |
| 「竞价额 3.56 亿 / 占昨 513%」名不副实 | 9:30 后 `amount` 是当日累计成交额，不是竞价额 | 后端新增 `amount_basis`；前端标签按口径切换，估算值标「(估算)」 |

> 回归：`tests/test_auction_helpers.py` 新增 7 条断言（含三峡新材真实样本），全量 54 用例通过。

### 9.4 第五轮：把缠论买卖点搬回 K 线图

**问题**：用户反馈"缠论不见了，K线图上看不到买卖点"。核查结论：**React 版从迁移起就没有这个功能**（`git log -S"缠论" -- frontend/src` 无任何提交；旧 Jinja `web/templates/index.html` + `static/js/dashboard.js` 里才有 12/13 处引用，已随旧 UI 删除）。后端 `core/chan.py` 一直完好，`/api/stock/{code}.chan` 也一直在返回数据。

| 层 | 改动 |
|---|---|
| 后端 | 新增 `GET /api/quant/chan/{symbol}`：取同源日K（默认 200 根）→ `sd.chan_analysis_structured()`，返回 `bi_points / zhongshu_list / signals / divergence`；按 symbol 缓存 5 分钟（冷 0.32s / 热 0.015s） |
| 图表 | `NativeFinancialChartInstance` 新增 `setChanData()` / `setChanVisible()`；`drawKLines` 里画三层：中枢虚线框（K线之下，alpha 0.10）→ 金色笔折线 + 顶底分型圆点 → 买卖点箭头 + 标签。日期→索引映射按 `time.slice(0,10)` 对齐，避免与另一批K线的索引错位 |
| 组件 | `FinancialChart` 随 `selectedSymbol`/`period` 拉取缠论（分时不请求），工具栏新增「缠论」开关（默认开，按钮上带买卖点计数） |
| 类型 | 新增 `ChanAnalysis / ChanSignal / ChanZhongshu / ChanBiPoint` |

**验证**（无头 Chrome + Canvas 像素统计）：开关属性 `bi=14 / zs=3 / sig=4`；画布金色像素 **开启 2576 → 关闭 0 → 再开 2576**；无 JS 异常。截图见 `scratch/_chan_shot.png`。

### 9.5 第六轮：独立审查（外部模型 + 自查）抓出的深层问题

| 级别 | 发现 | 处理 |
|---|---|---|
| **高** | **打脸账本整体前视偏差**：快照全在收盘后抓（12 只"竞价爆量"里 `pct` 全为 +10、`is_zt=True`），等于用结果预测结果 | 已加四条护栏（非交易日拒绝 / 不许伪造补录 / 时点闸门 9:15~9:35 / 合成样本排除统计）。现有历史档案已全部标为合成样本，真实样本归零，从下一个竞价窗口重新积累 |
| **高** | 休市日也会生成对账：周六 20261025 有一条"封板率33.3%"的假记录进了账本 | 已删该日档案与账本行；快照归档改用 `t_date`（盘面实际交易日） |
| 中 | 前端 `?? 42.5`：10日累计偏离度占位值，每只票都显示 42.5% 且参与红黄绿灯判定 | 改可空：未知显示 "—"，未知不参与判定；风险分与文案同步空值安全（新增 `formatNullable`） |
| 中 | 市值单位混乱：store 兜底用元（1e10/8e9），全链路约定却是亿元，UI 直接拼"亿" | 兜底改 0，面板按 <=0 显示 "--"；PE/PB 也不再给默认 15.0/1.5 |
| 低 | `amount_basis` 把 9:30~9:31 也标成竞价 | 已改：9:30 起算连续竞价 |
| 低 | `position_gate` 中 `pdi/mdi` 为 None 时 f-string 会 TypeError；`trading_calendar.pool_fetcher` 未捕获异常；`purge_non_trading_records` 假设每行是 dict；`core/quality._f()` 遇数字字符串返回 0 | 已登记，属防御性小修（除 quality 外均当前不可达） |
| 需核实 | `core/chan.py` 包含合并时把合并K线的日期/索引更新为最后一根 → 笔端点标在合并区间末日而非极值日（图上买卖点位置可能偏 1~3 天） | 待复核，暂未改 |

新增回归：`tests/test_auction_audit.py` 的 `TestAuditIntegrityGuards` 四条护栏用例，全量 **58 用例通过**。
