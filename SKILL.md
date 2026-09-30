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
4. **多主体模拟解读**：合力>30 修复反弹倾向 / <-40 恐慌加速风险 / 中间 磨底观望；情景注入是假设推演不写入记忆；存档<8条时定位置信度低要注明
5. **免责**：报告尾注"不构成投资建议"
6. 周末/节假日运行时注明数据为最近交易日收盘

## 情绪指数算法（脚本内置）
`基准10 + 涨停广度30(涨停数/80封顶) + 连板高度25(最高板/8封顶) + 封板质量20(1-炸板率) - 跌停惩罚15(跌停数/15封顶)`
> ⚠️ 上面是 **v1 公式**（`_emotion_score_v1`，2026-09-30 起仅作对照留档）。**主用 v2**：`基准10 + 广度18(平方根, 饱和点120家) + 高度17(平方根) + 封板质量12 + 赚钱效应25 + 跌停惩罚15`，详见文末「收口更新」。
历史自动存档：sentiment_history.jsonl（date/score/band/zt/zb/dt/max_lb），复盘周报可直接读。

## 周期定位规则（cycle_position）
亢奋(score≥85) / 冰点(score<30 或 涨停≤15且高度≤2) / 退潮(MA3<MA7 且 高度回落2板或涨停缩至7成或score<45) / 主升(MA3≥MA7 且 高度≥4板或5日均涨停≥55) / 其余=修复震荡。
存档不足8条时会输出置信度警告——此时不要把定位当确定性结论写进报告。

## 多主体模拟架构（agents/sim）
- 九方势力：国家队/机构/游资/团伙控盘/散户/北向/量化/产业资本/大散户，各有加权(国家1.2最高)
- 大盘模式输入：情绪分/连板高度/炸板率/两融环比/A50日内位置/大宗交易折溢价
- 世界模拟v2三机制：①势力记忆(昨日立场惯性0.3) ②交互传染(邻接矩阵3轮阻尼0.6) ③情景注入(_SCN表)
- 记忆存档 agents_state.json：仅无情景推演写入（情景是假设，防污染）

## 可视化仪表盘（D:\股票看盘\web，端口8013测试/8001正式）
FastAPI+ECharts。页面含：指数卡片/外盘卡/情绪仪表盘+历史曲线/板块资金/两融/快讯/
**多主体模拟面板(/api/sim)**：下拉选情景或填个股代码→终端风格输出推演全过程/形态选股面板。
后端直接 import stock_dashboard，依赖四个采集函数的返回值(global_markets/sector_flow/margin_total/news 已返回结构化数据)。
启动：桌面「启动股票看盘.bat」或 `$env:STOCK_DATA_HOME='D:\股票看盘\data'; python -m uvicorn main:app --port 8001`(workdir=D:\股票看盘\web)

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
- 情绪指数历史曲线图导出PNG（web 已有 ECharts 曲线）
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

