---
name: finance-stock-dashboard
description: 股票综合看盘系统·七层雷达+多主体模拟：大盘行情/隔夜外盘(A50期货)/情绪指数/板块资金/两融/快讯/个股体检/K线图/缠论/情绪周期定位/九方势力世界模拟。用户说"看盘""盘前""个股 XXX"时使用。
version: 2.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [finance, stock, china-market, dashboard, agent-simulation]
---

# 股票综合看盘 · 七层雷达 + 多主体模拟

## 何时使用
- 用户说"看盘/股票看盘/盘前/复盘/情绪怎么样"
- 用户问某只个股（"XX股票怎么样"/直接给代码）
- 用户问情绪周期阶段、多空博弈、资金推演
- cron 定时任务（盘前 8:30、收盘 15:30）的数据采集步骤

## 核心工具
`scripts/stock_dashboard.py` — 一键采集，纯文本分区输出，单源失败不影响其他分区。
网络层已内置 curl_cffi(伪装Chrome TLS)→urllib 双通道自动回退。

```bash
# 大盘全景（约10秒）：指数+外盘+情绪指数+周期定位+板块资金+两融+快讯
python "<skill_dir>/scripts/stock_dashboard.py" market

# 个股体检：行情/均线/区间/缠论结构/主力资金/融资/公告/席位画像
python "<skill_dir>/scripts/stock_dashboard.py" stock 600664

# 个股 + 60日K线图PNG（用 MEDIA: 路径发给用户）
python "<skill_dir>/scripts/stock_dashboard.py" stock 600664 --chart

# 仅情绪（可查历史任意交易日；周末自动回溯最近交易日）
python "<skill_dir>/scripts/stock_dashboard.py" emotion --date 2026-08-21

# 情绪周期定位（92科比五阶段：冰点->修复->主升->亢奋->退潮）
python "<skill_dir>/scripts/stock_dashboard.py" cycle

# 缠论简化引擎（日线笔/中枢/三买三卖/背驰检测）
python "<skill_dir>/scripts/stock_dashboard.py" chan 600664

# 多主体推演：无参=大盘九方势力；带代码=个股资金博弈
python "<skill_dir>/scripts/stock_dashboard.py" agents
python "<skill_dir>/scripts/stock_dashboard.py" agents 600664

# 世界模拟v2：势力记忆+交互传染3轮+情景注入（情景可选：外盘暴跌/外盘大涨/重磅利好/利空突袭/流动性收紧）
python "<skill_dir>/scripts/stock_dashboard.py" sim
python "<skill_dir>/scripts/stock_dashboard.py" sim 外盘暴跌

# 四策略选股：leader龙头梯队 / fund主力介入 / volume异动放量 / lhb龙虎榜
python "<skill_dir>/scripts/stock_dashboard.py" screener all

# 十二策略选股 v2（strategies_lib.py，与 stock_dashboard.py 同目录硬链）
# E低位首板 F断板反包 G超跌反弹 H N字反包 I均线趋势加速 J板块梯队+中军 K撬板地天板 L游资接力
# M情绪总开关：按 cycle_position 自动启停（冰点→G,K；修复→E,F,H；主升→全开；亢奋→I,L；退潮→G,K）
python "<skill_dir>/scripts/strategies_lib.py" auto   # 只跑周期适配策略（日常用这个）
python "<skill_dir>/scripts/strategies_lib.py" all    # 全策略跑一遍（复盘/回测用）
```

## 数据目录解析（重要）
优先级：`STOCK_DATA_HOME` 环境变量 > `HERMES_HOME` > 脚本上级`data\`(存在时) > `~/.hermes`。
- **Hermes 内运行/cron**：HERMES_HOME 已指向 hermes-home，存档在 `<HERMES_HOME>\stock_data\`
- **独立版 D:\股票看盘**：测试或 web 运行时必须 `$env:STOCK_DATA_HOME='D:\股票看盘\data'`，
  否则会误写 Hermes 存档！两处存档已合并（16条，2026-08-25），此后各自追加会分叉，需定期合并

## 报告组装规范（agent 侧）
1. **大盘**：指数表格 → 外盘包（A50 定调）→ 情绪指数（含周期定位）→ 板块资金 → 两融 → 快讯精选（只留市场相关的）
2. **个股**：行情 → 趋势/区间 → 缠论结构 → 资金/融资/席位画像 → 公告（异动/减持/业绩公告必须点出）→ 结合当日情绪周期给结论
3. **情绪指数**：0-100 分。`<30冰点 30-50退潮 50-70中性 70-85活跃 >85亢奋`；退潮期提示控仓、冰点期提示关注新题材试错信号（谁先走出4连板）
4. **免责**：报告尾注"不构成投资建议"
5. 周末/节假日运行时注明数据为最近交易日收盘

## 情绪指数算法（脚本内置）
`基准10 + 涨停广度30(涨停数/80封顶) + 连板高度25(最高板/8封顶) + 封板质量20(1-炸板率) - 跌停惩罚15(跌停数/15封顶)`
> ⚠️ 上面是 **v1 公式**（`_emotion_score_v1`，2026-09-30 起仅作对照留档）。**主用 v2**：`基准10 + 广度18(平方根, 饱和点120家) + 高度17(平方根) + 封板质量12 + 赚钱效应25 + 跌停惩罚15`，详见文末「收口更新」。
> ⚠️ **v2 量程缺口（2026-10-25 复核确认）**：v2 各项权重合计上限 = 10+18+17+12+25 = **82 分**，而 `emotion_band` 的亢奋线是 **85**，因此「亢奋」在 v2 下**永不触发**（`cycle_position` 的亢奋分支是死代码，`M 情绪总开关` 的亢奋档同理）。极端牛市样本实测顶到 82.0。**不要**靠抬权重来修——那会让 39 条历史存档与 42/68/65 等实证阈值全部失效（20261023 会从 65.02 变 81.0）。正确修法二选一：①把亢奋线降到 80（改动最小）；②权重改 100 分制并同时把 `algo` 升到 `v3`、重算全部阈值。
历史自动存档：sentiment_history.jsonl（date/score/band/zt/zb/dt/max_lb），复盘周报可直接读。

## 周期定位规则（cycle_position）
亢奋(score≥85) / 冰点(score<30 或 涨停≤15且高度≤2) / 退潮(MA3<MA7 且 高度回落2板或涨停缩至7成或score<45) / 主升(MA3≥MA7 且 高度≥4板或5日均涨停≥55) / 其余=修复震荡。
存档不足8条时会输出置信度警告——此时不要把定位当确定性结论写进报告。

## 可视化仪表盘（D:\股票看盘\web 服务端 + D:\股票看盘\frontend React 前端，端口8013测试/8001正式）
前端为 React 19 + Vite + Tailwind（WebSocket 实时推流），服务端只托管 `frontend` 的构建产物 `web/dist`。页面含：指数滚动条/自选股列表/个股报价头/超短五维诊断条/原生 Canvas 主图（分时·5/15分·日/周/月K，MA/EMA/BOLL，VOL/MACD/KDJ/RSI）/五档盘口与委比委差/成交明细与基本面/09:25 竞价雷达/超短作战室（总览·竞价·梯队·龙虎榜·共振·异动·VW-DVR 承接）/预警弹窗与键盘精灵；<768px 自动降级为单列 + 分屏 + 抽屉。
**`/api/sim` 与九方推演已整体摘除**（2026-10-25 复核：`grep /api/sim web/` = 0 命中，`scripts/sim_llm.py` / `sim_score.py` / `stock_dashboard.py sim` 均已删）。`data/llm/` 下残留的 `sim-*.json`、`ledger.jsonl` 属历史归档，不再产生新数据；`config/llm.local.json` 目前无代码读取。
后端直接 import stock_dashboard，依赖四个采集函数的返回值(global_markets/sector_flow/margin_total/news 已返回结构化数据)。
启动服务：桌面「启动股票看盘.bat」或 `$env:STOCK_DATA_HOME='D:\股票看盘\data'; python -m uvicorn main:app --port 8001`(workdir=D:\股票看盘\web，需 Python 3.10+，3.9 会因 dataclass slots 报错)。
改前端：`cd frontend && bun install && bun run build`，构建结束自动同步 `dist → ../web/dist`；健康检查 `GET /api/health`。

## 数据源清单（均已验证 2026-08）
| 数据 | 源 | 备注 |
|---|---|---|
| A股/港美指数·个股行情 | qt.gtimg.cn | GBK 编码；字段 f[3]价 f[31]涨跌 f[32]% f[37]成交额(万) |
| A50期货/纳指期货/金银油/USDCNH | hq.sinajs.cn | 必须带 Referer: finance.sina.com.cn；hf_CHA50CFD 是开盘定调核心 |
| 板块主力资金 | push2.eastmoney.com clist/get | fs=m:90+t:2, fid=f62；已配三域名轮换 |
| 涨停/炸板/跌停池 | push2ex.eastmoney.com getTopic{ZT,ZB,DT}Pool | ut=7eea3edcaed734bea9cbfc24409ed989, date=YYYYMMDD 可查历史 |
| 两融 | datacenter-web RPTA_RZRQ_LSHJ | 个股用 RPTA_WEB_RZRQ_GGMX |
| 快讯 | np-listapi.eastmoney.com getNewsByColumns | 三级回退：column→fastNewsList→新浪7x24 |
| 个股资金流 | akshare stock_individual_fund_flow | 字段"主力净流入-净额/净占比" |
| K线 | web.ifzq.gtimg.cn fqkline/get | qfq 前复权 |
| 龙虎榜席位 | datacenter-web RPT_BILLBOARD_DAILYDETAILS{BUY,SELL} | 席位分类映射 _LHB_FIXED/_YZ_KW |
| 大宗交易折溢价 | datacenter-web RPT_BLOCKTRADE_STA | 产业资本立场输入 |

## 坑（全部实测踩过）
- 腾讯接口返回 GBK，必须按 GBK 解码
- 新浪 hq.sinajs.cn 无 Referer 会 403
- 东财部分接口对裸 urllib 反爬(RemoteDisconnected)，curl_cffi 伪装 Chrome TLS 可解；未装则自动回退 urllib
- 东财 push2ex 的 ut token 若失效，从东方财富行情页-涨停池网络请求里重新抓
- 东财 clist 连续分页有突发限流：编号子域轮换(1-92.push2)+代码表每日缓存(data/stock_list.json)
- PowerShell 5.1 下 python 输出 UTF-8：脚本内已 sys.stdout.reconfigure(encoding='utf-8')
- PowerShell 控制台显示中文乱码≠数据坏了，浏览器/python utf-8 解码验证为准
- Invoke-RestMethod 对 UTF-8 JSON 会按 Latin-1 解码导致乱码，落盘检查改用 python urllib
- 情绪指数权重与势力打分系数都是经验值，积累一个月存档后可回测校准
- **跌停池(DT)必须用 sort=fund:asc**：fbt(首次封板时间)字段跌停股没有，恒返回空pool——2026-08-25 曾因此误判"接口无历史数据"做成 LHB 兜底，被第三方复核打回（真实历史数据一直都在，响应的 tc 字段也带总数）
- **qdate 归档陷阱**：push2ex 对任何历史日期查询恒返回 qdate=查询当日，绝不能用作归档日期；归档日=回溯命中的请求参数日
- **盘中快照禁止写档**：当日15:00前的涨停数只增不减，写档会占死归档槽导致收盘真实数据被去重跳过（emotion 已内置守卫）
- **多拷贝同步以 SHA256 为准**："已复制过"不算同步——2026-08-25 评审包就因漏同步拿到旧版导致评审误判；四处拷贝（D:\股票看盘\scripts、skills、hermes-home\scripts、stock_review_pkg）改动后逐一哈希校验

## 扩展点（未实现，按需加）
- 自选股池监控（放量突破/公告雷提醒）
- 情绪指数历史曲线图导出PNG（旧 Jinja/ECharts 曲线已随旧 UI 删除，React 前端待补，数据仍在 `GET /api/emotion/history`）
- 可转债溢价率作为投机情绪先行指标
- 模拟器回测：用历史存档逐日跑 agents/sim，统计「合力>30次日上涨概率」等命中率校准权重

## 收口更新（2026-09-30 · Hermes）
- **情绪指数升级 v2（同日）**：广度/高度改平方根去饱和（广度饱和点 80→120 家、分辨率约 4 倍），封板质量 20→12，**新增"赚钱效应"项 25 分**（`0.6×昨日涨停今均溢价` 按 ±5% 缩尾归一 + `0.4×1进2晋级率`，数据复用竞价雷达、5 分钟缓存），跌停惩罚 15 不变。打分抽为纯函数 `_emotion_score_v1 / _emotion_score_v2 / _effect_metrics`（v1 保留对照；存档新增 `algo`/`score_v1`/`effect`/`diverge` 字段）。实测今日 **v1 59.6 → v2 53.6**，并自动输出「分数偏高但赚钱效应偏弱」背离行；`cycle_position` 的 MA3/MA7 只取同 algo 记录，避免新旧尺度混算。验证：`scratch/verify_step3.py`（13 项离线断言全过）
- **存档单点化（含一处认知更正）**：两条静态落点规则原来是"脚本上级 `data/` 存在 → 恒用它；否则 `STOCK_DATA_HOME > HERMES_HOME > ~/.hermes`"（`stock_dashboard.py:28-32`）。所以 **D:\股票看盘 本体从来不会写歪**（bat 也不是元凶）；当年分叉的是**没有同级 `data/` 的副本**（旧 Hermes 技能副本 / cron 里那份脚本），它们回落到 `HERMES_HOME\stock_data`。现存唯一副本已无该风险；为防"再拷一份出去跑"复发，`STOCK_DATA_HOME=D:\股票看盘\data` 已固化进两个启动器（GBK+CRLF）并写入 Hermes `.env` 作为**冗余保险**（回落分支实测有效，见 `scratch/verify_step2.py` 2b 段）
- **历史分叉已合并**：Hermes 侧旧档（29 条，缺 20260929）与项目侧（30 条）按日期并集合并，同日期冲突 0 条，已原子写回项目侧；旧档冻结为 `sentiment_history.jsonl.legacy-20260930`，快照备份在 `scratch/step2_backup_20260930/`
- **`sync_check.ps1` 重写为"单点校验"**：旧版治理的 `D:\hermes\...` 硬链副本随 2026-08-17 删除已不存在，旧哨兵只会输出 MISSING（防分叉机制已死）；新版校验①权威存档存在②Hermes 侧不再长出第二份存档③两个启动器均已固化变量，退出码=问题数
- **`data_feed.py` 两处修正**（验证脚本 `scratch/verify_step1.py`）：① 健康度阈值 `>=3 / elif >=5` 使 `offline` 永不可达 → 改为从高到低判断；② 东财资金流失败时的兜底不再按 55/45 编造"超大单/大单"（改 `null` + `estimated:true` + `source:tencent_inout`），前端显示"数据不可用"并附注"源降级"，不再把编造的数字画进资金结构图
- **P2-A 健壮性四件套**（同日，验证 `scratch/verify_step4.py` 23 项全过）：① `MemoryTTLCache` 改真 LRU（`OrderedDict` + 命中 `move_to_end`）+ 硬上限 4000 + 超限先清过期再淘汰到 90%，新增 `evictions` 统计；② `is_market_closed()` 拆出可单测的 `_closed_by_clock()` 并**补上午休 11:30–13:00 与节假日**——节假日靠上证实时行情的日期戳识别（不硬编码日历、300s 缓存、取不到时保守按交易日），长假里不会再用 6/15s TTL 白刷上游；③ 首页 pill 改显示**大盘页自己的**缓存口径（`/api/data_status` 新增 `market_cache`：hits/misses/ttl_s/age_s）+ 休市标记（原来读的是行情快照那套缓存，恒 0%，看着像坏了）；④ 涨停池 `_pool()` 响应缺 `data`（或 `data:null`）时打印 **ut token 失效告警**并给出重抓指引（以前被当成"该日无涨停池"静默吞掉 → 7 日回溯白跑、情绪分凭空少一块）。另 `.gitignore` 忽略 `scratch/*_backup_*/`
- **顺手抓到并修掉的真 bug（同日）**：`/api/market` 的缓存时间戳原来记"**请求开始时刻**"——只要单次请求耗时超过 TTL，下一次请求立刻判过期，**缓存等于从未命中**（实测 8.08s 的请求后，2s 后的请求仍 miss）；改记"产出完成时刻"后第 3 次请求 `from_cache=True, cache_age=2.2`。规则：缓存 TTL 一律以"**产出完成**"为基准计时
- **涨停质量分 `limit_up_quality()`（同日，P2-⑤）**：0~10 分 = `0.35×封板时间 + 0.35×封单强度(封单额/流通市值) + 0.30×连板结构`，缺项按剩余权重归一（缺流通市值不会误判成 0 分），炸板 3 次扣 1.5 / 2 次扣 0.7；分档依据涨停板因子实证（竞价封板 3 日超额 +5.7%、封单占流通 >5% +8.4%、第 2 板 alpha 最强、6 板以上转负）。**E/F/H 策略排序键改为 `(质量分, 原分)`**（同分才看旧打分），分数写回池子对象 `x['qlty']`，structured 输出加 `quality` 字段——CLI 与 Web 同源。验证 `scratch/verify_step5.py`（离线断言全过 + 线上 E 条目 quality 递减 `[7.5,7.5,6.45]`、mode=all 8 个策略适配器无异常）
- **改文件必守行尾**：本项目 `data_feed.py / web/main.py / .gitignore` 是 **LF**，`stock_dashboard.py / index.html` 是 **CRLF**，`.bat` 必须 **GBK+CRLF+无 BOM**。Python 文本模式 `write_text()` 在 Windows 会把 `\n` 写成 `\r\n` —— 改文件前先探测原行尾，按原样写回（已踩过一次，见 `fix_eol.py`）
- **当日消息面采集+整理 `scripts/news_events.py`（2026-09-30 新增 · 消息面→推演 第①②步）**：三源合并（东财7x24 `column=350` 翻页跨零点 / 东财快讯 fastNewsList 单次上限 200 / 新浪7x24 页大小固定 100、约 35 分钟一页、翻页很快），标题归一化 + shingle 倒排索引去重（判据：Jaccard≥0.72 **或** 重叠系数≥0.8 **或** 短标题被长标题包含）；整理为结构化事件（类型走“主体+动作”双命中，极性/强度全可解释；作用板块=当日涨停池 hybk + 板块资金名 + 题材词表；作用个股对照 `data/stock_names.json`，2 字名需邻近市场语境词防地名误判）。输出 `data/news/YYYY-MM-DD.jsonl`（去重后当日消息，幂等重跑）与 `data/news/events-YYYY-MM-DD.json`（事件表+板块榜）。**口径三坑**：① 强度必须以【标题】打分——摘要里常有无关键信息的大数字（曾把“韩国税收有望创新高”抬到 9.6 顶格）；② 去重不能用“前 N 字分桶”（“央行宣布降准” vs “央行降准” 会漏判）；③ 东财 hybk 是 4 字截断名（“房地产服”），板块词表须与更长名去重。验证 `scratch/verify_news_events.py`，其中「jsonl 行数 == 事件表条数」是可断言的不变量
- **LLM 消息面推演 `scripts/sim_llm.py`（2026-09-30 新增 · 消息面→推演 第③步）**：参考 MiroFish 的流水线（种子→人格→多轮→报告），但**不搬它的社交平台仿真**。种子=交付①事件表+市场微结构（sha 存档可对账）；人格=九方（名称/权重与 `_AGENT_W` 一致）；**LLM 只输出判断层（九方冲击矩阵/板块优先级/风险点/三档情景/叙事），数值聚合仍由确定性引擎算**（`_sim_pipeline(impact_override=...)` + `sim_world(llm_impact=...)`）。`/api/sim?engine=llm`；无密钥或调用失败 → `engine=rule(fallback)` 且规则层结果照常，**绝不把页面搞挂**。配置发现顺序：环境变量 > `config/llm.local.json` >（opt-in `fallback_hermes`）Hermes .env 的 DashScope 通道；`config/llm.local.json` 与 `data/llm/` 已 gitignore。**两个坑**：① `deduce_impact()` 返回的是整个响应体、冲击矩阵在 `resp['impact']`——首版直接把它当矩阵用，导致九方全 0、多轮全空（靠 `--dry-run` 抓出来）；② `impact_override` 里会混入 `theme_priority` 列表，注入前必须逐项 `try/float` 过滤，否则 float(list) 崩。验证 `scratch/verify_sim_llm.py`（27 项：配置/种子/JSON 容错/response_format 400 重试/多轮/落盘/无密钥回落/真实 `_sim_pipeline` 冲击注入）+ `python scripts/sim_llm.py --dry-run` 全链路
- **次日打脸账本 `scripts/sim_score.py`（2026-09-30 新增 · 消息面→推演 第④步）**：把当天推演（净合力符号 / 强度 / 板块优先级 / 三档情景 / 风险点）与**次一交易日真实结果**五段对账，输出 `data/llm/score-YYYY-MM-DD.json` 并追加 `data/llm/ledger.jsonl` 累计命中率。数据源：情绪存档里的次交易日记录 + 上证日K（kline_tx，历史可查）+ 次日涨停池行业分布；**记分核心 `score_one(pred, facts)` 是纯函数**（事实由 `gather_facts` 传入）→ 能用合成事实离线单测（23 项）。两处口径必须记住：① 模型没输出三档概率，所以情景只做「归位」不做「押中率」；② 风险点核对**优先采用可自动验证的规则** —— 「高位连板特停风险」同时含「特停」(不可验证)与「高位」(可验证)，按关键词顺序命中会把它判成「未发生」，**比「未验证」更危险**（把没排除的风险说成已排除）
- **模拟页前端（同日 · 交付③）**：加「推演引擎」单选（规则秒级 / LLM 读当日事件表 1-3 分钟）+ `llmBoard` 结构化面板（九方冲击矩阵条形 / 板块 chips / 多轮博弈 / 风险点 / 三档情景 / 未配密钥的回落提示）；`runSim()` 按引擎拼 `engine=llm`。验证手段：服务端 HTML 标记齐全 + **`node --check` 对整段 90KB 脚本做语法检查**（比数括号可靠）；预览面板的 ref 有重名（`btn-2`/`btn-3` 重复）时别指望点击可靠，改用浏览器直接跑 JS 断言
- **归档写入门禁 v2（2026-10-08）**：情绪档案的写入资格改为 `_archive_eligible()` 三层校验 —— ① 该日**必须在交易所日K里（含“今天”）**：收盘后日K必有当天行；**日K取不到/为空一律 fail-closed**（宁可今天不归档，也不写可能是假的数据）；② 四项数值（zt/zb/dt/max_lb）与最近一条存档**完全相同** → 判为“接口对休市日回吐最近交易日数据”并拒绝；③ `FORCE_ARCHIVE=1` 可绕过 ①（人工补录），② 始终生效。**旧版 bug 的教训：门禁写了 `ymd < today`，把“今天”排除在校验外 —— 而 20261001 那条假记录恰恰是“当天是假期”时写进去的（探针在休市日也能取到最近一个涨停池 → hit_day 停在假期日）。修门禁的第一原则：默认怀疑“今天”，而不是默认信任。**
- **打脸账本必须 upsert（同日）**：`sim_score.py` 原先对同一笔预测**盲目追加**，`--all` 跑两次就把 1 笔样本变成 4 笔、把陈旧样本（用假期日 20261001 当次日算出来的那条）也算进命中率（方向命中被算成 25%，实际只有 1 笔、方向 ❌）。现改为按 `pred_date` **upsert 覆盖**，并让 `already_scored(date, next_ymd)` 校验“记的次日就是当前算出的次日” → 口径变了会自动重算、陈旧样本自愈（实测 4 条 → 1 条，样本数与命中率恢复诚实）。**任何累计指标都不能靠“追加”维护。**
- **门禁救回硬指标必须看时间戳与成交额（2026-10-08 补漏）**：`_archive_eligible` 救回逻辑中，休市日腾讯行情仍返回昨日收盘价（`price > 0` 恒成立），若按 `price > 0` 会导致休市日傍晚全部被放行。必须严查腾讯实时时间戳与真实成交额：`sh_q[0]['trade_time'][:8] == ymd and raw_amount > 0`。休市日接口返回的是历史时间戳，绝不会伪装成今天。
- **三大工程铁律（同日复盘沉淀）**：
  1. **注释与代码必须同源**：注释写了“查百亿成交额”，代码绝不能偷懒写成 `price > 0`。杜绝写 A 查 B。
  2. **判今天交易日用时间戳与真实成交额硬判据**：日K切线延迟可以靠实时行情救回，但判定事实源必须是实时接口的行情生成时间戳 `trade_time[:8] == ymd` 和成交额 `raw_amount > 0`。
  3. **改完先跑验证再报数，用 Git 与实测说话**：所有改动必须在本地有完整的单测和实测覆盖，杜绝自说自话。
- **核心判定阈值真实统计依据与核验（同日 · 实事求是校准）**：
  - 杜绝修辞通胀与虚构概率，以本库历史存档真实样本（$N=32$）及 `scripts/threshold_evidence.py` 对账为准：
  - `42 分`：对应本库历史全样本下四分位经验线（$P25=41.5$）；当前 $v2$ 样本仅 2 条，暂承袭 $v1$ 经验分位，待 $v2$ 独立样本 $\ge 30$ 条后持续动态校准。
  - `68 分 / 65 分`：系统多头共振高分位经验线（全量 $P75=69.6$）；在 `stock_dashboard` 中为国家队逆周期降温调节线（情绪 $>68$ 分时国家队从托底转为逢高平抑 $-20$）。
  - `35.0% 炸板率`：对应本库样本上四分位（$P75=32.1\%$）之上高危抛压区；本库实测 $>35\%$ 样本仅 $N=7$（次日指数下跌 2 次、上涨 5 次、次日均幅 $-0.08\%$），严禁在样本不足时宣称“超 70% 必跌”之类虚假胜率。
  - `20.0% 炸板率`：对应本库样本中低抛压分位（$P25=18.6\%$），指示封单相对坚决、分歧较小。
  - `12.0% 1进2晋级率` / `0.3% 次日开盘溢价`：属于短线打板经典盈亏平衡经验线（本库带 $effect$ 样本仅 2 天，诚实标注为先验规则，杜绝伪称本库实证）。
- **推演引擎进阶迭代：跨节降权 + 日内消化过滤 + 账本双刻度（同日 · 推演迭代）**：
  - **跨期衰减**：`sim_llm.py` 计算距目标次一有效交易日的日历天数 `gap_days`；长假跨期（>3天，如国庆8天）自动计算衰减系数 `time_decay = max(0.25, 1.0 / (1.0 + 0.25 * (gap_days - 1)))`（约 0.36），周末衰减 0.75。Prompt 明确告诫长假避险与海外波动，最终输出折现合力 `decayed_net / decayed_net_pct`。
  - **CLI 可视化可见**：`stock_dashboard.py sim` 在 `time_decay < 1.0` 时打印 `⏱️ 跨期N天衰减 X折 → 折现合力 Y`，彻底告别“只能翻JSON”。（旧 Jinja 前端已删除；当前 React 前端尚未接管九方推演视图，Web 侧暂无这块展示，属待补功能。）
  - **日内消化过滤**：事件表甄别时效，15:00 收盘前的事件标注 `[日内已反映/警惕兑现]`，盘后标注 `[盘后增量]`；Prompt 注入博弈铁律“日内已反映多已 price in 甚至炸板，次日谨防借利好出逃”，严禁把日内已消化的利好当成次日推力。
  - **打脸账本双刻度并行（科学对账）**：`sim_score.py` 的 `ledger.jsonl` 与 `score-*.json` 同时独立记录 `raw`（原始未衰减）与 `decayed`（折现后）两套方向与强度判定（输出 `direction` 与 `direction_raw`），并在累计统计中汇报 `direction_hit_pct` 与 `raw_direction_hit_pct`，回答“跨期折现究竟能否提高长期胜率”。验证：`scratch/verify_sim_decay.py` 16 项全过。

## 收口更新（2026-10-25 · 结构梳理 + P0 假数据清理）
- **`ultraShort` 由后端真值提供**（此前前端读 `quote.ultraShort` 恒为空 → 「连板梯队最高 0 板」）：`web/quant_data_service.get_ultra_short_profile()` 用东财涨停池/炸板池 + L1 快照构建，字段含 `consecutiveBoards / yesterdayBoards / firstSealTime / dragonRole / sealOrderAmount / sealRatioPct / brokenTimes / isIntradayTouchedLimitUp / auctionPrice / auctionChangePercent / yesterdayPerformanceNote / poolDate / isCurrentSession`。挂载点：`/api/market/quote/{symbol}`、`/api/market/snapshot`、WS `INIT_SNAPSHOT`、`/api/quant/ladder` 的每只成分股。**取不到池子时返回 `None`（不塞字段），绝不返回 0 冒充"没连板"**。
- **口径日必须看 `poolDate`**：盘前/周末最新池仍是上一交易日，`isCurrentSession=false` 时 `consecutiveBoards` 描述的是那天，不是"此刻"。
- **前端禁止再合成 ultraShort**：工作台原来的 `auctionVolume=12000 / yesterdayAmount=1.5亿 / cumDeviation 按板数查表` 已删除。`types/market.ts` 里已用注释区分「真实可算」与「后端不给（显示—）」两组字段。
- **WS 快照必须合并而不是替换**：`applySnapshotBatch` 改成 `{...旧, ...新}`，否则每帧 L1 都会把 `ultraShort` 冲掉，页面 3 秒后回到 0 板。
- **题材共振的领涨股不再编造**：不在涨停池里的领涨股，`firstSealTime/consecutiveBoards/amount` 一律 `None`（旧版写死 `09:35:00`、`amount=turnover*0.15`）。
- **前端构建要跑类型检查**：`bun run build`（vite）不做 tsc，`bun run lint` 才是。此前 `OrderBookLevel` 缺 `level`、`asks: []` 长度不符都能静默进产物。
- **监管异动面板已接真实端点（2026-10-25 第三轮）**：`/api/quant/regulatory` 返回体新增 `history`（`stock_return_t1/t2`、`index_return_t1/t2/today`，取自该端点已拉的日K，零额外请求）。前端 `calculateRegulatoryDeviation(quote, indexPct?, history?)` 用它替换掉原来的 `?? 5.2 / ?? 4.8` 占位值，并在结果里带 `historySource: 'kline' | 'estimated'`；面板顶部新增「交易所法规口径（真实引擎）」区块（安全价/剩余空间/绑定窗口/9日内触发/建议），估算时打「估算 · 未接真实日K」标。
- **两处「连板梯队」必须共用一份数据**：主图页顶部六维条（`UltraShortStockDiagnosticStrip`）和作战室（`UltraShortQuantWorkbench`）原本各自 `calculateBoardLadderSummary(allQuotes)` —— 只扫自选股，自选里没涨停就恒显示「最高标 0板」。现统一走 `hooks/useRealQuantData.ts` 的 `useRealLadder()` / `useRealRegulatory()`（60s 模块级缓存）。**以后新增面板读梯队/监管，一律用这两个钩子，不要再本地算。**
- **竞价「抢筹」判定必须带方向门禁（2026-10-26 · 三峡新材 600293 实证）**：原 `auction_boom` 是一条纯量能表达式（`量比>=3 or 一字 or 封单>=0.3亿 or 占昨比>=5%`），**完全不看方向**，于是 600293 一字跌停（-9.98%、买盘全空、卖一压 31 万手）被判成「超预期抢筹」，理由还写着"竞价占昨比 513%"。现抽出纯函数 `is_auction_boom()` 加三道门禁：①非跌停 ②`pct>=0` ③`order_ratio>-40`。另修两处连带问题：①`big_loss` 排序只按 `drop_from_high`，一字跌停的 high==low 恒为 0 会被挤出前 12 → 改成「跌停优先→跌幅→回撤」复合键；②`main.py` 信号组装顺序原为 弱转强→抢筹→核按钮，先入先得导致"跌停放巨量"被抢筹标签占住 → 改为**核按钮优先**。
- **金额口径必须标明（同日）**：`amount` 在 9:30 之后是**当日累计成交额**，不是竞价额。`/api/quant/auction_radar` 新增 `amount_basis`（`pre`/`auction`/`intraday`），前端金额标签按口径切换「09:25竞价额 / 当日累计成交」；不在雷达里的个股（如茅台）竞价额是按系数估的，标「竞价额(估算)」。**看到"竞价额 3.56 亿 / 占昨 513%"先看口径，那多半是盘中累计。**
- **缠论图层曾经"整块消失"（2026-10-26 补回）**：React 迁移时只搬了 K线/五档/竞价，**缠论笔与中枢没搬**（旧 Jinja 的 `dashboard.js` 里有，`git log -S"缠论" -- frontend/src` 查不到任何提交）。后端 `core/chan.py` 与 `/api/stock/{code}.chan` 一直是好的。现补：`/api/quant/chan/{symbol}`（同源日K + 缓存 5 分钟）→ Canvas 画金色笔折线 + 中枢虚线框 + 买卖点箭头，工具栏「缠论」可开关。**教训：UI 迁移要按「后端已有能力清单」逐项核对，别只看页面上还剩下什么。**
- **「打脸账本」曾整体前视偏差（2026-10-26 实锤）**：`auction_audit.audit_auction_for_day` 在快照缺失时会**拿当前雷达现场补一份**，而 `auction_radar` 的快照又是用 `dt.date.today()` 归档的。结果：①快照全是**收盘后**抓的（`recorded_at` 全在 15:00 之后/深夜），里面 12 只"竞价爆量"推荐 `pct` 全是 +10、`is_zt=True` —— **用收盘已涨停的票去核验"9:25 的推荐"，封板率 100% 是自证**；②周六 20261025 也生成了一条"封板率33.3%/胜率33.3%"的假对账并进了账本。**这套账本过去不能用于阈值校准。**
- **现在的四条护栏**：①非交易日 `not_trading_day` 直接拒绝对账（`_is_trading_day`）；②快照缺失**不许**用当前雷达补录（除非显式 `allow_synthetic=True`）；③`save_auction_candidates_snapshot(phase=...)` 只有 9:15~9:35 抓的才是 `auction`，其余时点一律 `phase='post_close'` + `synthetic=True`；④账本统计只算 `synthetic=False` 的样本，并返回 `excluded_synthetic_days`。现有历史档案已全部标记为合成样本（备份在 `scratch/backup_audit_cleanup_20261026/`），**真实样本目前为 0，需从下一个交易日的 9:15~9:35 开始重新积累**。
- **归档日期必须用 t_date 不能用 today**：`auction_radar` 的快照归档原来用 `dt.date.today()`，休市日会把最近交易日的盘面存成"今天"。与情绪存档 20261001 假记录同源——**默认怀疑"今天"**。
