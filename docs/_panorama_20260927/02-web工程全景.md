# 02 · web 工程全景 — hunter-v2

> 审计时间：2026-09-27 17:04–17:10（CST，周末休市）
> 工程路径：`D:\Hermes Agent CN Desktop\hunter-v2`
> 技术栈：React 19 + Vite（前端 `:5173`） / FastAPI（后端 `:8000`，实测在跑）
> 唯一权威路由来源：`curl http://127.0.0.1:8000/openapi.json` → **196 paths / 34 前缀**（python 解析，非目测）
> 证据约定：`file:line` = 代码证据；`curl:` = 真实 HTTP 返回片段

---

## 0. 一页速览

| 维度 | 数量 | 证据 |
|---|---|---|
| 后端路由（path 数） | **196** | `curl /openapi.json` → `len(paths)=196` |
| 后端 API 前缀（分组） | **34** | python `Counter` 按 `/api/v1/<seg>` 聚合 |
| 菜单分组 | **6 个业务组 + 1 个底部「系统设置」** | `src/layouts/Sidebar.tsx:22-71` |
| 菜单条目 | **16**（业务组 15 + 设置 1） | `Sidebar.tsx` NAV_GROUPS + SETTINGS_ENTRY |
| 前端页面文件 | **24** `.tsx` | `ls src/pages/*.tsx` |
| 前端路由 | **23**（含 `*` 兜底） | `src/App.tsx:74-109` |
| 菜单不可达（隐藏）路由 | **6** | `App.tsx` 路由集 − NAV_GROUPS |
| 全自动引擎 | **4**（3 运行 / 1 停用） | 引擎 status 接口实测 |
| 运行时状态文件 | **4 个引擎 state.json** + 5 个 DB + 4 个 cache | `ls data/ cache/` |
| Windows 计划任务 | **7** | `schtasks /query` 实测 |
| 前端零消费的后端前缀 | **10 个前缀 / 28 条路由** | 前端源码 `/api/v1/<prefix>` 反查 |

**最关键的三条结论**

1. **后端路由数（196）远超前端消费（26 前缀）**：有 10 个前缀 28 条路由前端完全没引用，其中 `hithink`（13 条，同花顺 L2 校验源）整个是"挂了但对用户不可见"。
2. **3 个全自动引擎同时 running 且各持 5 / 3 / 5 只仓位**，但 `last_tick` 全部停在 **2026-09-24 23:59**（`started_at` 却是 09-27 16:29）——即"进程重启过、tick 没推进"。
3. **实测发现一个真实缺陷**：`GET /api/v1/auto-trade/trades` 返回 **HTTP 500 Internal Server Error**，而另两个引擎的同名接口正常。

---

## 1. 功能总表（菜单 → 页面 → API → 引擎/状态 → 数据源）

分类列：`市`=市场分析 / `选`=选股 / `交`=交易 / `回`=回测 / `工`=工具

### 📊 行情（市场分析）

| 菜单项 | 路由 | 页面 file | 后端 API 前缀 | 引擎/状态文件 | 数据源 | 类 |
|---|---|---|---|---|---|---|
| 市场感知 | `/analysis` | `MarketAnalysisPage.tsx` | `market`（37 条，最大前缀） | `cache/market_snapshot.json` | 东财 push2delay + `em_node.py` 节点优选 | 市 |
| 个股分析 | `/kline` | `Kline.tsx`（74.9KB，最大页） | `kline`(11) + `stock`(3) | `cache/chan_disk/`、`cache/chan_mark.json` | mootdx / stock-sdk / 腾讯 | 市 |

> `market` 37 条覆盖：板块/概念/地域/资金流/北向南向/龙虎榜(billboard)/涨停(limitup)/阶梯(limit-ladder)/宏观(macro)/脉冲(pulse)/感知(perception)/日历/成分股/强弱(sector-strength)。
> `curl /api/v1/market/status` → `{"is_trading_day":false,"state":"bear","state_label":"下跌趋势","suggested_position_pct":0,"advance":1120,"decline":4305,"limit_up":66,"limit_down":26}`

### 🔍 选股（选股）

| 菜单项 | 路由 | 页面 file | 后端 API 前缀 | 引擎/状态文件 | 数据源 | 类 |
|---|---|---|---|---|---|---|
| 选股策略 | `/screener` | `ScreenerPage.tsx`（51.3KB） | `screener`(9) + `backtest`(7) + `factor-v4`(3) | `data/screener_daily/*.json`、`data/factor_panel.db`(244MB) | `factor_mainrise.py` → 腾讯 fqkline | 选 |
| 自选股 | `/watchlist` | `WatchlistPage.tsx` | `screener` + `quotes`(2) | — | stock-sdk 快照 | 选 |
| 选股记录 | `/screener-history` | `ScreenerHistoryPage.tsx` | `screener`/`market`/`auto-trade` | `data/screener_daily/`、`data/screener_perf_log.txt` | `screener_recorder.py` 守护线程 | 选 |
| 主力缩量信号 | `/vol-signal` | `VolSignalPage.tsx` | `vol-signal`(2) | `vol_signal_api.py` | 全市场量价（小龙女方法论 buy_A） | 选 |
| 大波机会 | `/wave-opportunity` | `WaveOpportunityPage.tsx` | `wave`(4) | `wave_api.py` | 312 万行全市场样本 | 选 |

> 实测：`curl /api/v1/vol-signal/stats` → `{"sample":{"rows":1766923,"codes":5544},"buy_a":{"f1":2.86,"w1":63.8},"oos":{"f1":1.79}}`
> 实测：`curl /api/v1/wave/stats` → `{"sample":{"rows":3123222,"codes":5634},"rule":{"wave":73.14,"lift":2.0},"coverage":{"days":96,"total_days":785}}`
> 实测：`curl /api/v1/factor-v4/meta` → `{"source":"tencent_fqkline(手→股×100)","codes_now":5545,"bars_now":1795111,"ok":true}`

### 🎯 决策

| 菜单项 | 路由 | 页面 file | 后端 API 前缀 | 引擎/状态文件 | 数据源 | 类 |
|---|---|---|---|---|---|---|
| 今日决策 | `/decision` | `BattlePlanPage.tsx`（33.4KB） | `battle-plan`(5) + `positions`(1) + `monitor`(4) | `trade.db` | 聚合 market + screener | 交 |

> 含 6 条：`battle-plan`(GET/confirm/execution/history/receipt)、`/api/v1/positions/management`、`monitor`(evaluate/events/rules CRUD)。

### 🤖 交易（交易）

| 菜单项 | 路由 | 页面 file | 后端 API 前缀 | 引擎文件 | 状态文件 | 类 |
|---|---|---|---|---|---|---|
| 昨收战法全自动交易 | `/auto-trade` | `AutoTradePage.tsx` | `auto-trade`(9) | `backend/auto_trader.py`(34.9KB) | `data/auto_trader_state.json`(8.5KB) | 交 |
| 昨收战法·15分K全自动 | `/prevclose15-auto` | `PrevClose15AutoPage.tsx` | `prevclose15`(9) | `backend/prevclose15_auto.py`(65.3KB) | `data/prevclose15_state.json`(225KB) | 交 |
| 缠论全自动交易 | `/chan-trade` | `ChanTradePage.tsx` | `chan-trade`(8) | `backend/chan_auto_trader.py`(57.4KB) | `data/chan_trade_state.json`(120KB) | 交 |

### 📐 回测（回测）

| 菜单项 | 路由 | 页面 file | 后端 API 前缀 | 引擎文件 | 数据源 | 类 |
|---|---|---|---|---|---|---|
| 昨收战法回测 | `/backtest-prevclose` | `PrevCloseBacktestPage.tsx` | `limitup`(4) + `backtest`(7) | `backend/limitup_backtest.py`(57.8KB) | 腾讯 fqkline | 回 |
| 缠论买卖点回测 | `/chan-backtest` | `ChanBacktestPage.tsx` | `chan-backtest`(1) | `backend/chan_theory.py`(47.7KB) / `chan_v2.py`(37.4KB) | 共享 K 线库 | 回 |

> 另有 `backtest_engine.py`(118KB，全工程最大后端文件)、`portfolio_backtest.py`、`hmj_backtest.py`、`chan_fx_backtest.py`、`chan_bi_backtest.py`、`chanlun_signal_backtest.py`、`dip_rolling_api.py`(33.5KB)、`auto_backtest.py`。

### ⚙️ 工具（工具）

| 菜单项 | 路由 | 页面 file | 后端 API 前缀 | 说明 | 类 |
|---|---|---|---|---|---|
| 策略中心 | `/strategies` | `StrategiesPage.tsx` | `strategies`(4) + `factor`(1) | 策略注册/热重载 | 工 |
| 数据源校验 | `/data-verify` | `DataVerifyPage.tsx` | `wsverify`(5) + `auto-trade` + `chan-trade` | 腾讯自选股 westock-data 交叉校验 | 工 |
| 系统设置（底部） | `/settings` | `SettingsPage.tsx` | `coach`(13) | LLM 配置 + 人格/心理学 | 工 |

> `curl /api/v1/wsverify/health` → `{"ok":true,"bin":"...\\westock-data-clawhub.cmd","latency_ms":737,"msg":"第三方源可用"}`

### 全局组件（无独立菜单，挂 App 外壳）

`AICoachPanel`（AI 教练浮窗，`coach` 前缀）、`AlertToast`（盘中异动 Toast，`coach`+`trade`）、底部 Status Bar（`App.tsx:119-149`，硬编码"🟢 风控正常 · 刷新间隔 0.8s"）。

### 隐藏路由（`App.tsx` 有 `Route` 但不在 NAV_GROUPS — 只能手工敲 URL）

| 路由 | 页面 | 说明 | 类 |
|---|---|---|---|
| `/` | `HomePage.tsx` | 首页（点侧边栏品牌区「猎·猎手工作台」可达，非菜单项） | 市 |
| `/overview` | `MarketIndexPage.tsx` | 已并入市场感知 Tab | 市 |
| `/ladder` | `LimitLadderPage.tsx` | 涨停阶梯，已并入 | 市 |
| `/funds` | `FundMonitorPage.tsx` | 资金监控，已并入 | 市 |
| `/sectors` | `SectorAnalysisPage.tsx` | 板块分析，已并入 | 市 |
| `/simulation` | `SimulationPanel.tsx` | 模拟盘，**有 Route 无菜单** | 回 |

> 代码自述：`Sidebar.tsx:6-7`「旧路由全部保留兼容（隐藏页: /overview /ladder /funds /sectors 已并入对应工作台 Tab, 直接访问旧 URL 仍可打开——过渡期双轨, Step3 迁移完成后再收口）」。
> 另有 3 个孤儿页面文件 `MarketPerceptionPage.tsx` / `MarketStatusTab.tsx` / `MarketStatusTab`无 `Route`（MarketStatusTab 被当作组件内嵌）。

---

## 2. 后端路由全景（按前缀统计）

python 解析 `openapi.json` → `Counter`。**总计 196 path / 34 前缀。**

| # | 前缀 | 路由数 | 归属模块（推定/已验证） | 前端消费 |
|---|---|---|---|---|
| 1 | `api/v1/market` | **37** | `data_service.py` / `concept_service.py` / `em_node.py` | ✅ |
| 2 | `api/v1/trade` | **20** | 交易/持仓/风控/止损（`trade_store.py`,`risk_engine.py`,`stop_loss_service.py`） | ✅ |
| 3 | `api/v1/coach` | **13** | AI 教练（`coach_chat.py`,`personality_service.py`,`daily_report.py`） | ✅ |
| 4 | `api/v1/hithink` | **13** | `hithink_api.py` ← `hithink_src.py`（同花顺 CLI） | ❌ **孤儿** |
| 5 | `api/v1/kline` | **11** | `kline_cache.py`(59.4KB) / `indicators.py` / `chan_theory.py` | ✅ |
| 6 | `api/v1/auto-trade` | 9 | `auto_trader.py` | ✅ |
| 7 | `api/v1/prevclose15` | 9 | `prevclose15_api.py` → `prevclose15_auto.py` | ✅ |
| 8 | `api/v1/screener` | 9 | `pick_engine.py`(46.8KB) / `screener_recorder.py` | ✅ |
| 9 | `api/v1/chan-trade` | 8 | `chan_auto_trader.py` | ✅ |
| 10 | `api/v1/backtest` | 7 | `backtest_engine.py` | ✅ |
| 11 | `api/v1/battle-plan` | 5 | `battle_plan.py`(42.7KB) | ✅ |
| 12 | `api/v1/wsverify` | 5 | `westock_check.py` → `westock_src.py` | ✅ |
| 13 | `api/v1/limitup` | 4 | `limitup_screener.py` / `limitup_backtest.py` | ✅ |
| 14 | `api/v1/monitor` | 4 | `monitor_rules.py` | ✅ |
| 15 | `api/v1/simulation` | 4 | `simulation_engine.py` | ✅(`/simulation`) |
| 16 | `api/v1/strategies` | 4 | `strategy_hub.py` / `strategy_registry.py` | ✅ |
| 17 | `api/v1/wave` | 4 | `wave_api.py` | ✅ |
| 18 | `api/v1/dip-rolling` | 3 | `dip_rolling_api.py` + `dip_rolling/` | ❌ **孤儿** |
| 19 | `api/v1/dip-trade` | 3 | `dip_trader_pro.py`（已停用） | ❌ **孤儿** |
| 20 | `api/v1/factor-v4` | 3 | `factor_api.py` → `factor_mainrise.py` | ✅ |
| 21 | `api/v1/stock` | 3 | 基本面/盘口（`fundamental_service.py`） | ✅ |
| 22 | `api/v1/analysis` | 2 | `analysis_service.py` | ✅ |
| 23 | `api/v1/content` | 2 | `content_service.py` | ❌ **孤儿** |
| 24 | `api/v1/quotes` | 2 | 快照/计数 | ❌ **孤儿** |
| 25 | `api/v1/vol-signal` | 2 | `vol_signal_api.py` | ✅ |
| 26 | `api/v1/attribution` | 1 | `attribution.py` | ❌ **孤儿** |
| 27 | `api/v1/auto-backtest` | 1 | `auto_backtest.py` | ❌ **孤儿** |
| 28 | `api/v1/chan-backtest` | 1 | `chan_backtest.py` | ✅ |
| 29 | `api/v1/diag` | 1 | `diag_api.py` | ❌ **孤儿** |
| 30 | `api/v1/discipline` | 1 | `discipline.py` | ❌ **孤儿** |
| 31 | `api/v1/factor` | 1 | `factor_ic.py` | ✅ |
| 32 | `api/v1/health` | 1 | 健康检查 | ❌(被 bat 用) |
| 33 | `api/v1/overview` | 1 | 首页聚合（60s 缓存） | ✅ |
| 34 | `api/v1/positions` | 1 | `position_management.py` | ✅ |
| — | `api/v1/rps` | 1 | `rps_service.py` | ✅ |

**前端零消费的孤儿前缀 = 10 个 / 28 条路由**：`hithink`(13) `dip-rolling`(3) `dip-trade`(3) `content`(2) `quotes`(2) `health`(1) `attribution`(1) `discipline`(1) `auto-backtest`(1) `diag`(1)。

**WebSocket**（不进 openapi）：`/api/v1/ws/quotes`，证据 `backend/main_restored.py:4495 @app.websocket("/api/v1/ws/quotes")` + `src/hooks/useWebSocket.ts` 引用 `ws` 前缀。

### ⚠️ `main.py` 的特殊架构（必读，影响任何改动）

`backend/main.py` 只有 236 行，**它不是真源码**：

- `main.py:45-47`：`marshal.loads(_data[16:])` → 从 `__pycache__/main.cpython-312.pyc`（273KB，≈4698 行源码）加载字节码后 `exec`。
- `main.py:26-43`：**pyc 完整性守卫** —— 若 pyc < 100000 字节就 `SystemExit`。原因见 `main.py:27-32`：对 `backend/main.py` 跑 `py_compile` 会无条件重写该 pyc → 变成 runner 自身编译产物 → `exec` 自己 → 无限自递归（RecursionError 998 层）→ 后端完全起不来。
- **铁律：永远不要对 `backend/main.py` 跑 py_compile。**
- `main.py:60-72`：拦截 `uvicorn.run` 拿到 `app`，先注册扩展路由再真启动。
- `main.py:74-95`：注入 `_DisabledTs2Engine` 桩 + 摘除 `/api/v1/ts2-trade/*` 路由（趋势回踩 v2 已删，但 pyc 里还有）。
- `main.py:105-154`：patch `httpx.Client.get`/`AsyncClient.get`，`push2*` 走 `em_node.py` 优选 IP 直连。
- `main.py:177-229`：**扩展路由注册区**（本次审计的注册清单）：

| 顺序 | 模块 | 挂载前缀 | 行号 |
|---|---|---|---|
| 1 | `factor_api` | `/api/v1/factor-v4` | `main.py:181-182` |
| 2 | `prevclose15_api` | `/api/v1/prevclose15` | `main.py:184-185` |
| 3 | `westock_check` | `/api/v1/wsverify` | `main.py:189-191` |
| 4 | `hithink_api` | `/api/v1/hithink` | `main.py:195-197` |
| 5 | `vol_signal_api` | `/api/v1/vol-signal` | `main.py:201-202` |
| 6 | `wave_api` | `/api/v1/wave` | `main.py:206-207` |

模式统一为 `def register(app, ctx=None)`。另有 `main.py:214-226` 后台预热线程（sleep 20s 后跑一次全市场因子）。

---

## 3. 各引擎实测状态（curl 真实返回）

### 3.1 汇总

| 引擎 | 状态接口 | `running` | 持仓数 | 交易记录数 | `cash` | `last_tick` | `started_at` |
|---|---|---|---|---|---|---|---|
| 昨收战法 | `/api/v1/auto-trade/status` | **true** | 5 | `trades len=13` | 52904.52 | **2026-09-24 23:59:26** | 2026-09-27 16:29:15 |
| 昨收·15分K | `/api/v1/prevclose15/status` | **true** | 3 | `trades len=13` | 11836.29 | **2026-09-24 21:51:57** | (无字段) |
| 缠论 | `/api/v1/chan-trade/status` | **true** | 5 | `trades len=218` | 67275.21 | **2026-09-24 23:59:05** | 2026-09-27 16:29:15 |
| 低吸追涨 | `/api/v1/dip-trade/status` | **false** | — | — | — | — | — |
| 模拟盘 | `/api/v1/simulation/status` | `active:1` | 0 | `trades`（14 条样例） | 14919.86 | `last_date: 2026-08-10` | `start_date: 2026-05-12` |

> **关键异常**：三个 running 引擎的 `last_tick` 全部停在 **09-24**，而 `started_at` 是 **09-27 16:29:15**。说明进程 09-27 重启过、`started_at` 被刷新，但 tick 未推进（09-25 之后的 `data/chanlun_scan_20260925.json` 存在，但引擎 tick 无记录）。周末休市下"不 tick"属合理，但 `started_at` 与 `last_tick` 的 3 天差需要确认是否是 tick 计时器未恢复。

### 3.2 逐条 curl 证据

**`/api/v1/auto-trade/status`**（截断至 900 字符）
```json
{"running":true,"cash":52904.52,"positions":5,"total_asset":92045.52,
 "positions_detail":[{"name":"平潭发展","shares":1200,"cost":7.95,"price":8.78,
 "buy_day":"2026-09-08","prev_close":7.98,"type":"A","code":"000592",
 "anchor_prev_close":6.81,"breakeven":7.975,"market_value":10536.0,
 "pnl":996.0,"pnl_pct":10.44}, ...]}
```
`data/auto_trader_state.json` 关键字段：`keys=['running','cash','day','started_at','last_tick','positions','trades','signals','alarms','pool','pool_updated','market_guard','notes','_pending_sell']`；`positions` 5 只（`000592 300179 301071 300285 301176`）、`trades len=13`、`signals len=9`、`pool len=0`。

**`/api/v1/prevclose15/status`**
```json
{"running":true,
 "cfg":{"codes":["300850","002093","300690","300727","002134"],"capital":100000.0,
 "auto_resume":true,"tick_sec":60,"pos_up":0.8,"high_ban_b":80.0,"stop_pct":-9.0,
 "gap_stop_pct":-8.0,"max_positions":3,"max_total_pos":0.8,"max_per_stock_pct":0.35,
 "dd_stop_pct":-15.0,"market_guard":true,"guard_index_drop":-1.0,
 "min_amount":80000000.0,"auto_select":true,"pool_size":5,"reselect_days":1,
 "auto_tick":true,"auto_select_time":"09:25","select_method":"trend_sector_leader"},
 "cash":11836.29,"net":96851.29,
 "positions":{"301015":{...},"001389":{...},"600256":{...}}}
```
`prevclose15_state.json`：`keys=['running','cfg','cash','positions','trades','signals','last_tick','last_bar_key','stats','universe','universe_meta','last_select_day','peak_net','cur_dd']`；`stats={'trades':13,'wins':..,'realized':..,'started':..}`。

**`/api/v1/chan-trade/status`**
```json
{"running":true,"cash":67275.21,"positions":5,"total_asset":96216.21,
 "pnl":-3783.79,"pnl_pct":-3.78,
 "market_guard":"大盘弱势(收盘<MA20)·半仓运行",
 "started_at":"2026-09-27 16:29:15","last_tick":"2026-09-24 23:59:05",
 "pool_mode":"缠论·走势类型状态机","fx_mode":true,
 "positions_detail":[{"name":"博云新材","shares":400,"cost":22.99,"price":22.47,
 "buy_day":"2026-09-11","signal":"加仓","stop_loss":20.31,
 "sub_level":{"lv":"60min","note":"次级别60min无数据(≤2026-09-08)"},
 "code":"002297","pnl":-208.0,"pnl_pct":-2.26}, ...]}
```
`chan_trade_state.json`：`trades len=218`、`signals len=201`、`consumed_signals`、`last_intraday_scan`。
> 注意 `sub_level.note = "次级别60min无数据(≤2026-09-08)"` —— 次级别数据缺口，多周期联立降级。

**`/api/v1/dip-trade/status`**
```json
{"running":false,"stopped":true,
 "msg":"低吸追涨全自动交易已停用(2026-09-01 老陈), 前端入口已删除; 转向趋势×强度×回踩新战法研究"}
```
> ⚠️ 页面入口确实删了，但 3 条 `/api/v1/dip-trade/*` 路由 + `data/dip_trader_state.json`（`running:true`，与接口返回矛盾）**仍然存在**——状态文件里的 `running` 是 true，接口走的是硬编码停用分支。

**`/api/v1/simulation/status`**
```json
{"id":1,"active":1,"strategy":"ma_cross",
 "params":{"portfolio_size":5,"total_cap_pct":80,"risk_per_trade":2,"atr_stop_mult":2,"tactics_enabled":1},
 "codes":["600519","000063","000001","601398","000333"],
 "initial_capital":100000.0,"cash":14919.86,"equity":99465.76,"pnl":-534.24,
 "positions":[],"last_date":"2026-08-10","start_date":"2026-05-12"}
```
> 模拟盘数据 **停在 2026-08-10**，已陈旧 48 天；且 `/simulation` 路由无菜单入口。

### 3.3 交易记录接口

| 接口 | 结果 |
|---|---|
| `/api/v1/prevclose15/trades` | ✅ 正常。样例：`{"ts":"2026-09-14 10:37","code":"300408","action":"建仓","price":131.0,"shares":200,"reason":"挖坑转强(开盘<昨收+盘中破位+连续3根收回) 趋势up","cash_after":73793.19}` |
| `/api/v1/chan-trade/trades` | ✅ 正常。样例：`{"day":"2026-09-10","ts":"2026-09-10 11:06:33","action":"SELL","code":"601949","name":"中国出版","price":6.99,"reason":"顶分型减仓级(MA60上未创新高(趋势内回调顶))","pnl_pct":-0.18}` |
| `/api/v1/auto-trade/signals` | ✅ 正常。样例：`{"day":"2026-09-08","ts":"2026-09-08 09:30:35","code":"000592","name":"平潭发展","type":"BUY_A","detail":"开盘确认买入","price":7.95}` |
| **`/api/v1/auto-trade/trades`** | ❌ **HTTP 500 `Internal Server Error`**（`curl -w "HTTP=%{http_code}"` 实测）。state 文件里 `trades len=13` 数据是有的，说明是**读接口的代码 bug，非无数据**。 |

### 3.4 风控/资金实况

`curl /api/v1/trade/risk-check`
```json
{"passed":true,"checks":[
 {"type":"total_position","current":0.0,"limit":20,"passed":true},
 {"type":"daily_stop","current":0.0,"limit":3,"passed":true},
 {"type":"monthly_stop","current":0.0,"limit":6,"passed":true},
 {"type":"market_state","state":"bear","suggested_position":0,"passed":true}],
 "warnings":["当前熊市，建议仓位不超过0%"],"summary":"⚠️ 风控通过但有1项警告"}
```
`curl /api/v1/positions/management` → `{"cards":[],"total_pnl":0.0,"positions_count":0,"alerts":[]}` ← **空**，与 3 引擎实持 13 只仓位矛盾（该接口读的是另一套手动持仓表 `trade.db`，与引擎 state.json 不互通）。

---

## 4. 数据源清单（代码落点 + 实际用途）

| 数据源 | 落点（file:line） | 实际用途 | 角色 |
|---|---|---|---|
| **通达信 mootdx** | `backend/auto_trader.py:233` `from mootdx.quotes import Quotes`<br>`backend/auto_trader.py:405`（当日 5 分K）<br>`backend/chan_auto_trader.py:565`<br>`backend/chase_screener.py:62` | 日K 补数（共享库未命中时）、当日 5 分K | 冷备/补数。`auto_trader.py:254` 自述"共享库未覆盖的票回落 mootdx(≈1.8s/只)" |
| **共享通达信 K 线库** | `backend/auto_trader.py:212` "读共享通达信日K库(limitup-system/cache/kline.db)" | 主日K 读取（跨工程共享） | 主源 |
| **stock-sdk (TS)** | `backend/data_service.py:606` "主源: stock-sdk 全市场快照 (2026-09-08 老陈拍板: stock-sdk 转正主源, 东财降备胎)"<br>`data_service.py:610` `import stock_sdk_bridge`<br>`data_service.py:617` `stock_sdk_bridge.get_all_quotes(ttl=0)` | **全市场实时快照主源**（0.6s 全市场） | **主源** |
| ↳ 桥接实现 | `backend/stock_sdk_bridge.py`（3.9KB）+ `backend/stock_bridge.mjs`（2.6KB） | Python ↔ Node TS SDK 桥 | — |
| **腾讯 qt.gtimg / fqkline** | `backend/data_service.py:189` `url = "https://qt.gtimg.cn/q="`<br>`backend/auto_trader.py:301`<br>`backend/chan_auto_trader.py:598`<br>`backend/dip_rolling/datafeed.py:35` `TENCENT_QUOTE`、`:240` `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 批量实时行情（昨收 `parts[4]`，GBK，不封 IP）+ 前复权日K | 主源（K线） |
| **腾讯 fqkline → 因子面板** | `scripts/factor_panel_build.py:11` "数据源: 腾讯 fqkline(qfq, 手→股 ×100) ← TDX(mootdx/pytdx) 本机不可达(实测 0 根)" | `data/factor_panel.db`（244MB）主升因子 v4 面板 | 主源 |
| **东方财富 push2 / push2delay** | `backend/em_node.py`（9.4KB，IP 直连优选）<br>`backend/auto_trader.py:338`、`:381`<br>`backend/chan_auto_trader.py:629`<br>`backend/coach_service.py:89`<br>`backend/concept_service.py:4-7`（概念/北向/北向历史） | 全市场快照（降级备胎）、板块/概念/地域/资金流/北向 | 备胎 + 板块主源 |
| **东财节点优选补丁** | `backend/main.py:103-154` patch `httpx.Client.get`/`AsyncClient.get`，命中 `_EM_HOSTS` 走 `em_node.get_json` | 绕过 GTM 把 DNS 调度到"不发响应直接断连"的坏节点 | 运行时补丁 |
| **同花顺 hithink-finance** | `backend/hithink_src.py:2`（封装层）、`:18` 官方 CLI `%APPDATA%\npm\hithink-finance.cmd`<br>`backend/hithink_api.py:3`（HTTP 层，13 条路由） | L2 权威校验源 + 特色榜单主源 | **校验源（前端不可见）** |
| **腾讯自选股 westock-data** | `backend/westock_src.py`（9.2KB）、`backend/westock_check.py`（19.8KB，5 条 `/wsverify` 路由）<br>`main.py:190` 注册 | 第三方交叉校验（K线/指标/筹码/批量） | 校验源 |
| **新浪** | `backend/backfill_minute_sina.py:36` `quotes.sina.cn/cn/api/jsonp_v2.php/.../getKLineData` | 30 分K 回填（1023 根 ≈ 6 个月）<br>`backfill_minute_sina.py:4` 自述"TDX 能连上但所有数据请求返回空" | 备胎/回填 |
| **腾讯（screener_perf）** | `scripts/screener_perf.py:5` "+ 腾讯日K（入选股表现）" | 选股成效追踪 | 单点 |
| **本地 SQLite（落库）** | `data/hunter.db`(1.05GB + 124MB WAL)、`data/factor_panel.db`(244MB)、`data/trade.db`、`data/trade_calendar.db`、`data/macro_cache.db`、`data/fundamental_cache.db` | 主数据仓 | — |
| **本地文件缓存** | `cache/market_snapshot.json`(2.3MB)、`cache/chan_mark.json`(115KB)、`cache/sector_map.json`(144KB)、`cache/boards/`、`cache/chan_disk/`、`cache/em_node.json` | 快照/缠论磁盘缓存/节点记忆 | — |

> 数据源优先级（代码注释佐证）：**stock-sdk（全市场快照）→ 东财**（`data_service.py:545,606`）；**共享 TDX 库 → mootdx**（`auto_trader.py:212`）；**K线/因子面板：腾讯 fqkline 优先，TDX 不可达时降级**（`scripts/factor_panel_build.py:11`）。

---

## 5. 运行时状态文件与数据库

### 5.1 引擎状态 JSON（`data/`）

| 文件 | 大小 | 关键字段（python 实测） |
|---|---|---|
| `auto_trader_state.json` | 8.5KB | `running` `cash` `day` `started_at` `last_tick` `positions`(5) `trades`(13) `signals`(9) `alarms` `pool`(0) `market_guard` `notes` `_pending_sell` |
| `prevclose15_state.json` | **225KB** | `running` `cfg`(30+ 参数) `cash` `positions`(3) `trades`(13) `signals` `last_tick` `last_bar_key` `stats` `universe` `universe_meta` `last_select_day` `peak_net` `cur_dd` |
| `chan_trade_state.json` | **120KB** | `running` `cash` `day` `started_at` `last_tick` `positions`(5) `trades`(**218**) `signals`(**201**) `alarms` `pool`(0) `consumed_signals` `fx_mode` `last_intraday_scan` |
| `dip_trader_state.json` | 6.2KB | `running`(**true**, 与接口 `running:false` 矛盾) `cash` `positions` `trades` `today_buys` `watchpool` `lose_streak` `last_clear_day` |

### 5.2 数据库（`data/`）

| 文件 | 大小 | 用途 |
|---|---|---|
| `hunter.db` (+`-wal` 124MB) | **1.05GB** | 主数据仓（K线/行情），17:04 仍在写 |
| `factor_panel.db` | 244MB | 主升因子 v4 归一面板（`kline_daily` + `meta`） |
| `trade.db` | 242KB | 手动交易/持仓/日志（`daily_report.py:14` 引用） |
| `trade_calendar.db` | 516KB | 交易日历（`trading_calendar.py`） |
| `macro_cache.db` | 12KB | 宏观缓存 |
| `fundamental_cache.db` | 246KB | 基本面缓存 |
| `_audit_test_trade.db` | 28KB | 审计残留 |

### 5.3 缓存与中间产物

`cache/`：`market_snapshot.json`(2.3MB) `chan_mark.json`(115KB) `sector_map.json`(144KB) `em_node.json` `boards/` `chan_disk/`
`data/` 中间产物：`auto_bt_kline_1y.json`(55.8MB) `auto_bt_kline_2y.json`(114.5MB) `chanlun_scan_2026MMDD.json`×10 `rust_signal_forward_log.json` `factor_lhb_daily.json` `screener_daily/` `screener_perf/` `reports/` `logs/` `_fv4.json` `push_dedup.json` `best_params.json`
日志：`data/screener_daily_log.txt`(68.7KB) `data/screener_perf_log.txt`(25.8KB) `data/factor_panel_build.log`(34.7KB) `data/chanlun_nightly_log.md`(7.4KB) `backend/startup.log`(21.8KB)

### 5.4 运行时进程文件

`backend.pid`（内容 5 字节，`backend/launcher.py` 末尾写入）、`backend/startup.log`。

---

## 6. 定时任务与守护进程

### 6.1 Windows 计划任务（`schtasks /query /fo CSV` 实测，7 条）

| 任务名 | 下次触发 | 状态 | 对应脚本（bat 自述） |
|---|---|---|---|
| `\HunterV2_Daily_0830` | 2026/9/28 8:30 | 就绪 | `start_unattended.bat`（起后端 8000 + 前端 5173，幂等） |
| `\HunterV2_Autostart` | N/A（登录触发） | 就绪 | 同上（`start_unattended.bat` 自述"login + 08:30 daily"） |
| `\HunterKline_Daily_1545` | 2026/9/28 15:45 | 就绪 | K线日更（无对应根目录 bat 文件） |
| `\HunterScreener_Daily_1545` | 2026/9/28 15:45 | 就绪 | `run_screener_daily.bat` → `scripts/screener_daily.py` |
| `\HunterFactorPanel_1550` | 2026/9/28 15:50 | 就绪 | `run_factor_panel_daily.bat` → `scripts/factor_panel_build.py`（两趟：全量 + `--missing`） |
| `\HunterScreenerPerf_Daily_1600` | 2026/9/28 16:00 | 就绪 | `run_screener_perf.bat` → `scripts/screener_perf.py` |
| `\HunterChanlunNightly_1615` | 2026/9/28 16:15 | 就绪 | `run_chanlun_nightly.bat` → `backend/chanlun_nightly.py --threads 6 --workers 8` |

### 6.2 脚本职责

| 脚本 | 频率/触发 | 职责（源码自述） |
|---|---|---|
| `scripts/screener_daily.py` | 15:45 计划任务 | 8 大选股方法 ×≤10 只 → `data/screener_daily/YYYY-MM-DD.json`；主升因子走 `/api/v1/factor-v4`；`BASE = "http://127.0.0.1:8000"`（**依赖后端在跑**） |
| `scripts/screener_perf.py` | 16:00 计划任务 | 追踪入选股 +5/+10/+20 交易日收益 → `data/screener_perf/analysis.json`；数据源腾讯日K |
| `scripts/factor_panel_build.py` | 15:50 计划任务 | 因子面板构建（`--pages 60 --workers 16 --days 320`）→ `data/factor_panel.db` |
| `backend/chanlun_nightly.py` | 16:15 计划任务 | 三步：①新浪 30min 增量（缺口补 1023 根）②因果确认扫描 → `data/chanlun_scan_YYYYMMDD.json` ③前向验证日志回填 8/16/40 根收益 |
| `backend/screener_recorder.py` | **后端内常驻守护线程** | 开市日 **9:20–9:30** 一次性跑 5 方向（auction/limitup/trend/reversal/range）各 Top10 → `data/screener_daily/` + `_summary.json` |
| `backend/backfill_minute.py` / `backfill_minute_sina.py` | 手工 | 分钟级回填（TDX 源 / 新浪源） |
| `backend/launcher.py` | 被 `start_unattended.bat` 调 | DETACHED_PROCESS 起 `backend/main.py`，写 `backend.pid` + `startup.log` |
| `start.bat` | 手工 | 交互式启动 |
| `backend/*.bat` | 手工 | `check_all.bat` `check_main.bat` `check_recorder.bat` `check_zsl_import.bat` 自检 |

### 6.3 测试（`tests/`，16 个）

`test_attribution` `test_backtest_rstats` `test_battle_plan` `test_chan_theory` `test_chanlun_engine` `test_concept_service_fallback` `test_discipline` `test_hikyuu_deep` `test_hikyuu_p2` `test_hikyuu_p3` `test_ic_weights` `test_indicators` `test_position_management` `test_pulse` `test_sector_pool` `test_tdx_qfq`

### 6.4 `scripts/`（120+ 文件，绝大多数是一次性诊断残留）

含 `verify_p0a.py`…`verify_p0e_tick.py`（P0 修复验证链）、`phase_fix_p0a`…`p0e`（同批修复脚本）、`ab_*.py`（A/B 实验）、`check_*.py`/`diag_*.py`/`analyze_*.py`、大量 `*_err.txt`/`*_out.txt` 空/短输出残留。**建议归档，勿删**（其中 `verify_*`/`phase_fix_*` 是 2026-09-24 P0 修复的证据链）。

---

## 7. 缺口分析

### 7.1 菜单里没有但对交易系统重要的功能

| 缺口 | 现状证据 | 严重度 |
|---|---|---|
| **无独立风控页面** | `trade` 前缀 20 条里有 `risk-check` / `risk-check-trade` / `stop-loss/*`(4) / `capital-calc`，但**没有对应菜单项**；风控只在 `App.tsx:130` 状态栏硬编码一行 `"🟢 风控正常"`（**假的，无数据绑定**）。`curl /api/v1/trade/risk-check` 返回 `passed:true` 带 `warnings:["当前熊市，建议仓位不超过0%"]` 却无人展示 | **高** |
| **无独立资金管理页面** | `backend/capital_manager.py`(6.7KB) 存在，`/api/v1/trade/capital-calc` 存在，前端零引用 | **高** |
| **无独立复盘页面** | `backend/daily_report.py`(17.1KB，"AI自动复盘报告服务") + `/api/v1/coach/daily-report(s)` 存在，只作为 AI 教练浮窗的一部分，无独立复盘工作台 | 中 |
| **持仓视图三套互不相通** | 引擎持仓在 `*_state.json`（13 只实仓）；`/api/v1/positions/management` 返回 `{"cards":[],"positions_count":0}`；手动持仓在 `trade.db`。**没有页面能一屏看全 3 引擎合并持仓+总敞口** | **高** |
| **hithink 13 条路由前端零消费** | `main.py:195-197` 挂载成功，`curl /api/v1/hithink/health` → `{"ok":true,"cli_version":"0.1.12","auth_configured":true}`，但前端无一页引用。这个"L2 权威校验源"目前只能 curl 用 | 中 |
| **模拟盘 `/simulation` 有路由无菜单，数据停在 2026-08-10** | `App.tsx:103` 有 Route；`Sidebar.tsx` 无该 path；`curl /api/v1/simulation/status` → `"last_date":"2026-08-10"`，陈旧 48 天 | 中 |
| **`auto-trade/trades` 接口 500** | `curl -w HTTP=%{http_code}` → `500`；state 文件 `trades len=13` 数据完好 | **高（功能缺陷）** |
| **dip 系列残留** | `dip_trader_state.json` 的 `running:true` 与 `/api/v1/dip-trade/status` 的 `running:false` + `"已停用"` 矛盾；6 条 `/api/v1/dip-*` 路由 + `dip_rolling/` 目录 + `dip_trader_pro.py`(35.3KB) 都在 | 中 |
| **盘后无"一键复盘/日报"菜单入口** | `docs/作战系统开发计划.md` 等 10 份设计文档齐备，但菜单无落点 | 中 |
| **10 个孤儿 API 前缀 / 28 条路由** | 见 §2 表 | 中 |
| **`data/_audit_test_trade.db` 残留** | 28KB，审计污染残留 | 低 |

### 7.2 其他工程卫生问题

| 问题 | 证据 |
|---|---|
| `backend/main.py` 是 pyc runner，**真源码只能从 pyc 反编译** | `main.py:5-16`。存在 `main_restored.py`(211KB) / `main_restored2.py`(211KB) 两个候选恢复版但未被使用 |
| 大量 `.bak0924*` 备份文件 | `auto_trader.py.bak0924` `~b/c/d`、`chan_auto_trader.py.bak0924` `~c/d`、`prevclose15_auto.py.bak0924d/e`、`prevclose15_api.py.bak0924f` —— 共 8 个 |
| `src/pages/` 24 个文件但只有 23 条路由 | `MarketPerceptionPage.tsx` 完全无 Route（死文件） |
| `MarketAnalysisPage.tsx`(3.3KB)/`MarketIndexPage.tsx`(2.4KB)/`MarketPerceptionPage.tsx`(1.3KB) 极小 | 说明市场感知已重构成"壳 + 组件"，逻辑在 `src/components/` |
| `index.html` 时间戳 09-12，`dist/` 时间戳 09-11 | 生产构建**已 16 天未更新**，与 `src/`（09-27）严重脱节 |
| `frontend-check.png` / `trend-check.png` 遗留在根目录 | 调试截图未清理 |
| 根目录 2 份重复的 README（`README-Hermes迁移.md` / `README-交付版.md`）+ 3 份缺失分析 md | 文档碎片化 |

---

## 8. 页面数 / 菜单数 复核（供全景索引引用）

- **菜单分组数 = 6 业务组**（📊行情 / 🔍选股 / 🎯决策 / 🤖交易 / 📐回测 / ⚙️工具）+ **1 底部独立入口**（⚙️系统设置）= `Sidebar.tsx:22-71`
- **菜单条目数 = 16**
  - 📊 行情 2：`/analysis` `/kline`
  - 🔍 选股 5：`/screener` `/watchlist` `/screener-history` `/vol-signal` `/wave-opportunity`
  - 🎯 决策 1：`/decision`
  - 🤖 交易 3：`/auto-trade` `/prevclose15-auto` `/chan-trade`
  - 📐 回测 2：`/backtest-prevclose` `/chan-backtest`
  - ⚙️ 工具 2：`/strategies` `/data-verify`
  - 底部 1：`/settings`
- **页面文件数 = 24**（`ls src/pages/*.tsx`）
- **前端路由数 = 23**（含 `*` 兜底 → 22 个真实路由）；其中 **6 个菜单不可达**：`/` `/overview` `/ladder` `/funds` `/sectors` `/simulation`
- **后端路由数 = 196 / 34 前缀**；前端消费 26 前缀（含 `ws`），**孤儿 10 前缀 / 28 条**

---

## 附：本次审计的取证命令（可复现）

```bash
# 1. 全量真实路由（唯一权威）
curl -s http://127.0.0.1:8000/openapi.json -o /tmp/hv2_openapi.json
python -c "import json,collections;d=json.load(open('/tmp/hv2_openapi.json',encoding='utf-8'));print(len(d['paths']))"

# 2. 引擎实测
curl -s http://127.0.0.1:8000/api/v1/auto-trade/status
curl -s http://127.0.0.1:8000/api/v1/prevclose15/status
curl -s http://127.0.0.1:8000/api/v1/chan-trade/status
curl -s http://127.0.0.1:8000/api/v1/dip-trade/status
curl -s http://127.0.0.1:8000/api/v1/simulation/status
curl -s -w '\nHTTP=%{http_code}\n' http://127.0.0.1:8000/api/v1/auto-trade/trades   # → 500

# 3. 状态文件关键字段
python -c "import json;d=json.load(open('data/auto_trader_state.json',encoding='utf-8'));print(list(d.keys()))"

# 4. 计划任务（GBK → UTF-8）
schtasks /query /fo CSV /nh 2>/dev/null | iconv -f GBK -t UTF-8 | grep -i hunter
```

**禁止事项（本工程特有）**：不要对 `backend/main.py` 执行 `py_compile`（`main.py:26-43` 守卫会拒绝启动，需从 `main_22h42.cpython-312.pyc` 恢复）。
