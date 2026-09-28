# 股票综合看盘系统 · 七层雷达 + 多主体模拟

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Release](https://img.shields.io/github/v/release/lllaaa999/stock-dashboard)](https://github.com/lllaaa999/stock-dashboard/releases)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)

A股综合看盘工具，覆盖大盘行情、隔夜外盘、情绪指数、板块资金、两融、快讯、个股体检、K线图、缠论、情绪周期定位、九方势力多主体推演、世界模拟、形态选股。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Web 仪表盘

```bash
cd web
python main.py
```

然后浏览器打开 **http://127.0.0.1:8001**

桌面也有「启动股票看盘.bat」一键启动。

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

# 九方势力多主体推演（无参=大盘；带代码=个股资金博弈）
python stock_dashboard.py agents
python stock_dashboard.py agents 600664

# 世界模拟v2（势力记忆+交互传染+情景注入）
python stock_dashboard.py sim
python stock_dashboard.py sim 外盘暴跌

# 四策略选股（龙头梯队/主力介入/异动放量/龙虎榜）
python stock_dashboard.py screener all

# 十二策略选股（日常用 auto，按情绪周期自动启停）
python strategies_lib.py auto
python strategies_lib.py all    # 全策略跑一遍（复盘用）

# 八形态选股（涨停首板/连板/均线多头/金叉/放量突破等）
python screener.py
```

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
`基准10 + 涨停广度30 + 连板高度25 + 封板质量20 - 跌停惩罚15`

分档：`<30冰点 / 30-50退潮 / 50-70中性 / 70-85活跃 / >85亢奋`

### 多主体模拟（九方势力）
国家队 / 机构 / 游资 / 团伙控盘 / 散户 / 北向 / 量化 / 产业资本 / 大散户，各有加权。世界模拟v2 三机制：势力记忆 + 交互传染（3轮阻尼）+ 情景注入。

### 选股系统
- **strategies_lib.py**（12策略，推荐）：E低位首板 / F断板反包 / G超跌反弹 / H N字反包 / I均线趋势加速 / J板块梯队+中军 / K撬板地天板 / L游资接力 + M情绪周期总开关
- **screener.py**（8形态）：涨停首板 / 连板 / 均线多头 / 均线金叉 / 放量突破 / 平台突破 / 强势回踩 / 底部放量

---

## 目录结构

```
finance-stock-dashboard/
├── README.md                 ← 本文件
├── requirements.txt          ← Python 依赖
├── SKILL.md                  ← 开发文档（面向 Agent/开发者）
├── data/
│   ├── stock_list.json       ← 股票代码表（每日自动缓存）
│   └── stock_data/
│       ├── sentiment_history.jsonl  ← 情绪指数历史存档
│       └── agents_state.json        ← 九方势力记忆存档
├── scripts/
│   ├── stock_dashboard.py    ← 主程序（七层雷达+缠论+模拟+选股）
│   ├── strategies_lib.py     ← 十二策略选股库（推荐日常用）
│   ├── screener.py           ← 八形态选股器
│   ├── stock_daily_note.py   ← 每日看盘笔记→Obsidian
│   └── sync_check.ps1        ← 多拷贝同步检查（SHA256校验）
└── web/
    ├── main.py               ← FastAPI 后端
    └── templates/
        └── index.html        ← ECharts 可视化仪表盘
```

---

## Web API

| 接口 | 说明 |
|---|---|
| `GET /` | 仪表盘首页 |
| `GET /api/market` | 大盘全景（指数+情绪+外盘+板块+两融+快讯） |
| `GET /api/emotion/history` | 情绪指数历史曲线 |
| `GET /api/screen?patterns=` | 形态选股（约1-2分钟） |
| `GET /api/sim?scenario=&code=` | 多主体模拟/情景注入 |
| `GET /api/stock/{code}` | 个股体检（行情+K线+资金流+公告） |

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
