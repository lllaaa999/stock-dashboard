# 股票综合看盘系统 · 七层雷达

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Release](https://img.shields.io/github/v/release/lllaaa999/stock-dashboard)](https://github.com/lllaaa999/stock-dashboard/releases)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

A股综合看盘工具，覆盖大盘行情、隔夜外盘、情绪指数、板块资金、两融、快讯、个股体检、K线图、缠论、情绪周期定位、形态选股。

> **如果这个项目对你有帮助，欢迎点个 ⭐ Star —— 它能被更多做 A 股量化研究的人看到。**

### 为什么值得用

- **一次调用拿到全景**：`python stock_dashboard.py market` 约 2-3 秒聚合 7 类数据源，省掉在多个财经网站间反复切换。
- **把"情绪"变成可算的数字**：0-100 分情绪指数有独立加权算法并可存档回溯，情绪周期定位（冰点→修复→主升→亢奋→退潮）不靠感觉，靠数据。
- **工程上抗限流**：curl_cffi 伪装 Chrome TLS → urllib 双通道回退 + host 级熔断 + 三域名轮换，接口抖动不会直接打断看盘。
- **纯本地运行**：不依赖付费行情 API，数据取自公开接口，持仓与配置留在自己机器上。

### 适合谁

做 A 股短线 / 情绪周期研究的个人开发者；想学"如何把交易逻辑写成可验证代码"的人；需要一块随时能改的本地看盘面板的量化爱好者。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Web 仪表盘

需要 **Python 3.10+**（3.9 会因 dataclass slots 报错）。本机实测可用解释器是 `py -3.12`：

```bash
# Windows（推荐，等价于双击「一键启动股票看盘.bat」）
set STOCK_DATA_HOME=D:\股票看盘\data
py -3.12 web/main.py

# 或手动跑 uvicorn
cd web
set STOCK_DATA_HOME=D:\股票看盘\data
py -3.12 -m uvicorn main:app --port 8001
```

然后浏览器打开 **http://127.0.0.1:8001**

桌面也有「启动股票看盘.bat」一键启动。

服务端只托管 React 构建产物 `web/dist`（已随仓库提供，无需先构建）。改动前端源码后需要重新构建：

```bash
cd frontend
bun install      # 首次
bun run build    # vite build 结束会自动同步 dist → ../web/dist
```

`GET /api/health` 可确认前端产物是否就绪（`frontend: "react-dist"`）。

### 2.5 跑测试

```bash
py -3.12 -m unittest discover -s tests -t .    # 51 个用例，约 3 秒
```

### 2.8 K线图上的缠论图层

日/周/月K 主图上可叠加缠论结构（默认开启，工具栏「缠论」按钮可一键开关）：

- **金色折线** = 缠论笔（分型 → 笔，含顶/底分型圆点）
- **金色虚线框** = 中枢区间（标注 `中枢 lo~hi`）
- **红/绿箭头 + 标签** = 买卖点（底背驰 / 一买候选 / 顶背驰 / 一卖警戒）
- 数据来自 `/api/quant/chan/{symbol}`（`core/chan.py` 纯算力 + 同源日K，按 symbol 缓存 5 分钟）

### 3. 命令行使用

所有命令在 `scripts/` 目录下执行：

```bash
# 大盘全景（指数+外盘+情绪+周期+板块资金+两融+快讯，约2-3秒）
python stock_dashboard.py market

# 9:25 集合竞价雷达与亏钱效应大面榜（昨日涨停溢价/弱转强异动/日内天地大面）
python stock_dashboard.py auction

# 个股体检（行情/均线/缠论/主力资金/融资/公告/席位画像）
python stock_dashboard.py stock 600664

# 个股 + 60日K线图PNG
python stock_dashboard.py stock 600664 --chart

# 情绪指数（可查历史任意交易日；周末自动回溯最近交易日）
python stock_dashboard.py emotion --date 2026-08-21

# 情绪周期定位（冰点→修复→主升→亢奋→退潮）
python stock_dashboard.py cycle

# 缠论日线结构化分析（分型包含合并/笔/中枢/三买三卖/顶底背驰）
python stock_dashboard.py chan 600664

# 四策略选股（龙头梯队/主力介入/异动放量/龙虎榜）
python stock_dashboard.py screener all

# 十二策略选股（日常用 auto，按情绪周期自动启停）
python strategies_lib.py auto
python strategies_lib.py all    # 全策略跑一遍（复盘用）

# 八形态选股（涨停首板/连板/均线多头/金叉/放量突破等）
python screener.py

# 7x24 消息面采集与事件结构化（落盘 data/news/）
python stock_dashboard.py news

# 预判闭环：存档自己的判断，次日自动对账（save / check / stats）
python stock_dashboard.py pred save --dir 多 --score-lo 55 --score-hi 70
python stock_dashboard.py pred check
python stock_dashboard.py pred stats
```

`stock_dashboard.py` 全部子命令：`market / stock / auction / emotion / cycle / chan / screener / news / pred`。

---

## 功能清单

### 七层雷达（大盘全景）
| 层 | 内容 | 数据源 |
|---|---|---|
| 1 | A股/港美指数实时行情 | 腾讯 qt.gtimg.cn |
| 2 | 隔夜外盘（A50期货/纳指期货/金银油/USDCNH） | 新浪 hq.sinajs.cn |
| 3 | 情绪指数（0-100分）+ 周期定位 | 东方财富涨跌停池 |
| 4 | 板块主力资金流入/流出 | 东方财富 push2 |
| 5 | 两融余额 | 东方财富 datacenter |
| 6 | 财经快讯 | 东方财富 + 新浪7x24 |
| 7 | 个股体检 | 腾讯+东财+akshare |

### 情绪指数算法
**主用 v2**：`基准10 + 广度18(平方根去饱和,饱和点120家) + 高度17(平方根) + 封板质量12 + 赚钱效应25 - 跌停惩罚15`
赚钱效应 = `0.6×昨日涨停今均溢价(±5%缩尾归一) + 0.4×1进2晋级率`。

v1（`基准10 + 广度30 + 高度25 + 封板质量20 - 跌停惩罚15`）仅作历史对照留档。

分档：`<30冰点 / 30-50退潮 / 50-70中性 / 70-85活跃 / ≥85亢奋`
> 已知缺口：v2 权重合计上限为 82 分，85 分亢奋线实际不可达（详见 `PROJECT_STRUCTURE.md` 第 6 节 #12）。

### 选股系统
- **strategies_lib.py**（12策略，推荐）：E低位首板 / F断板反包 / G超跌反弹 / H N字反包 / I均线趋势加速 / J板块梯队+中军 / K撬板地天板 / L游资接力 + M情绪周期总开关
- **screener.py**（8形态）：涨停首板 / 连板 / 均线多头 / 均线金叉 / 放量突破 / 平台突破 / 强势回踩 / 底部放量

---

## 目录结构

```
D:\股票看盘\
├── README.md                 ← 本文件（面向使用者）
├── SKILL.md                  ← 开发文档与踩坑记录（面向 Agent/开发者）
├── PROJECT_STRUCTURE.md      ← 项目地图 + 现状体检（唯一权威结构说明）
├── requirements.txt          ← Python 依赖（需 Python 3.10+，本机用 py -3.12）
├── core/                     ← 纯算力层：缠论 / 涨停质量分 / 情绪打分（无网络无 IO）
├── scripts/                  ← 数据接入 + 业务决策（24 个模块）
│   ├── stock_dashboard.py    ← 主采集器（七层雷达 + 情绪 + 梯队 + 选股 + 战略决策）
│   ├── data_feed.py          ← 四源容灾 + TTL/LRU 缓存
│   ├── data_layer.py         ← 日K四级降级（TDX→baostock→AKShare→腾讯）
│   ├── auction_radar.py      ← 9:25 竞价雷达；auction_audit.py 收盘对账
│   ├── strategies_lib.py     ← 12 策略选股库（auto 按情绪周期自动启停）
│   ├── screener.py           ← 8 形态选股
│   ├── abnormal_volatility.py← 异动红线与最高安全价反推
│   ├── position_gate.py      ← 仓位闸门；strategic_decision.py 决策中枢
│   ├── paper_trading.py      ← 纸上交易；backtest_engine.py 回测
│   └── daily_auto_iteration.py ← 盘后全自动流水线
├── web/                      ← FastAPI 服务端（28 个 /api + /ws）
│   ├── main.py               ← 路由 / 缓存 / 字段映射
│   ├── market_gateway.py     ← L1 五档与逐笔、K线网关
│   ├── quant_data_service.py ← 梯队 / 题材 / 龙虎榜加工
│   └── dist/                 ← 前端构建产物（唯一线上 UI）
├── frontend/                 ← React 19 + Vite + Tailwind 源码（15 组件）
│   └── src/utils/ultraShortQuant.ts ← 超短计算内核（3171 行）
├── tests/                    ← 19 文件 / 51 用例（unittest）
├── benchmarks/               ← 离线压测与实证脚本
├── config/                   ← 本地配置（llm.local.json 已 gitignore）
└── data/                     ← 字典库与运行档案（情绪存档 / 竞价台账 / 纸上交易）
```

---

## Web API

共 28 个 `/api/*` + 1 个 `/ws` 实时推流。常用：

| 接口 | 说明 |
|---|---|
| `GET /` | 看盘首页（React 构建产物 `web/dist`） |
| `GET /api/health` | 健康检查（前端产物是否就绪） |
| `GET /api/market` | 大盘全景（指数+情绪+外盘+板块+两融+快讯） |
| `GET /api/market/quote/{symbol}` | 单只 L1 报价（五档、委比） |
| `GET /api/market/klines/{symbol}` | K线/分时 |
| `GET /api/quant/ladder` | 连板梯队、断层诊断、晋级率 |
| `GET /api/quant/auction_radar` | 9:25 竞价雷达 |
| `GET /api/quant/theme_resonance` | 题材共振 |
| `GET /api/quant/regulatory` | 法定异动监管逆推 |
| `GET /api/quant/dragon_tiger` | 龙虎榜席位正交验身 |
| `GET /api/emotion/history` | 情绪指数历史曲线（返回数组） |
| `GET /api/strategic_decision` | 周期阶段 / 仓位 / 开火门禁 |
| `GET /api/screen?patterns=` | 形态选股（约 1-2 分钟） |
| `GET /api/strategies?mode=auto` | 12 策略选股（120s 缓存） |
| `GET /api/stock/{code}` | 个股体检（行情+K线+缠论+资金+公告） |
| `GET /api/data_status` | 数据源健康度与缓存命中 |
| `GET /api/backtest/presets` `GET /api/backtest/run` | 回测预置与执行（仅 GET） |
| `GET /api/paper/{replay,tick,report,reset}` | 纸上交易 |
| `GET /api/auction` `/api/auction/audit` `/api/auction/audit/ledger` | 竞价雷达 / 收盘对账 / 累计台账 |

> 前端目前只接入了其中 9 个，其余端点有数据但无视图（见 `PROJECT_STRUCTURE.md` 第 6 节 #7）。

---

## 数据源

| 数据 | 源 | 备注 |
|---|---|---|
| A股/港美指数·个股行情 | 腾讯 qt.gtimg.cn | GBK 编码 |
| A50期货/外盘/金银油 | 新浪 hq.sinajs.cn | 需 Referer |
| 板块主力资金 | 东方财富 push2 | 三域名轮换防限流 |
| 涨停/炸板/跌停池 | 东方财富 push2ex | 可查历史 |
| 两融/龙虎榜/大宗交易 | 东方财富 datacenter | |
| 快讯 | 东方财富 + 新浪7x24 | 三级回退 |
| 个股资金流 | akshare（兜底） | |
| K线 | 腾讯 fqkline | 前复权 |

网络层：curl_cffi（伪装 Chrome TLS）→ urllib 双通道自动回退 + host 级熔断。

---

## 注意事项

- 数据仅供参考，**不构成投资建议**
- 周末/节假日运行时，数据为最近交易日收盘
- 东方财富接口偶有限流，已内置域名轮换和重试；持续失败会自动回退
- 情绪指数存档不足 8 条时，周期定位置信度低，结果仅供参考
- 每日笔记功能需要 Obsidian 库路径 `D:\hermes-knowledge\股票日记`
