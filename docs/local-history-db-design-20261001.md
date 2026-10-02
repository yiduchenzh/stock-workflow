# 本地股票历史数据库 — 现状体检 + 设计方案（2026-10-01）

> 命题：本地细粒度历史库 + 持续更新 + 大盘/板块/个股多对多与一对多高度关联 + 定时更新。**是否可行、怎么做。**
> 结论：**可行，且主干已建成（约 60~70%）；真正缺的是「板块层」「基本面时点化」「指数同步」三块。**

---

## 一、现状体检（实测，非估算）

| 资产 | 位置 | 实测规模 | 判定 |
|---|---|---|---|
| 个股**前复权**日K | `hunter.db :: kline_daily_qfq` | **3,192,112 行 / 5,334 只 / 1997-07-03 ~ 2026-09-30** | ✅ 完整 |
| 个股日K（共享镜像） | `D:/MarketData/market.db :: kline_daily` | 3,842,690 行 / 5,638 只 / 2005-09-22 ~ **2026-09-30** | ✅ |
| **30 分钟K** | `market.db :: kline_30min` | **6,208,145 行 / 5,114 只** / 2024-01-11 ~ 09-30 | ✅ 分钟级主力 |
| 5 / 15 / 60 分钟K | `market.db` | 4.9万 / 36万 / 3.1万 行，**仅 21~119 只** | ⚠️ 只覆盖自选池 |
| 1 分钟K | `market.db :: kline_1min` | 1,934 行 / **2 只** | ❌ 几乎无 |
| **大盘宽度**（涨跌家数/涨停/跌停/均值） | `hunter.db :: market_trend` | 837 行 / **2023-04-20 ~ 2026-09-30** | ✅ 独有 |
| **除权除息事件** | `hunter.db :: stock_xdxr` | **177,210 行 / 5,222 只 / 1990 起** | ✅ 独有（一对多） |
| 指数日K | `market.db` | `sh000001` **最新 2026-09-24（滞后 4 个交易日）** | ❌ **缺陷** |
| 板块多对多映射 | `stock-workflow/data/fundamentals.db :: stock_sector` | **64 行 / 只有 3 只股票** | ❌ 空壳 |
| 基本面 | `同库 :: fundamentals` | **3 行（2026-08-14）** | ❌ 空壳 |
| 定时更新 | `MarketDB_Daily` 每交易日 19:00 / `MarketDB_Intraday` 每 30 分钟 | Intraday Rc=0 ✓；**Daily 今天 19:00 起仍在 Running（已 40+ 分钟）** | ⚠️ 需观测/加固 |

**已经解决的两大痛点**（沿用既有设计，勿重造）：
1. **海量** → 分层缓存 + 结果级回测缓存（同参回测 分钟→毫秒）
2. **多源口径** → 统一主键 `(code, ts)`、volume 统一「股」、脏 code 一律删（禁猜映射）
3. **接入安全** → 开关 `MARKETDB_READ` 默认关 + 未命中回落原链路；读可能被写的库**禁 `immutable=1`**

---

## 二、缺口 + 设计（按 ROI 排序）

> **实施记录（2026-10-01 当天落地，见 `sector_layer.py` / `marketdb.py` / `sync_assoc.bat`）**
> - 数据源实测变更：**东财 push2delay/push2his 对本机出口 IP 全线拒连**（`Remote end closed connection without response`，
>   带/不带 ut token、5 个主机全试）→ 板块链改用 **同花顺 CLI**（`index catalog/constituents/history`）
>   —— 好处：**官方板块指数真实历史**（320 行业 + 390 概念），**不需要自算**，因此没有成分漂移偏差
> - 指数链：**腾讯 fqkline**（`param=sh000001,day`），与 同花顺/新浪 **三方交叉验证一致**（09-30 收 3842.19）
> - 因此「板块指数自算」降级为**备选**（`basis='equal'` 列位已留），未实施


### P0-1 指数同步修复（半天）
- 现象：`sh000001` 停在 09-24，个股到 09-30（回测基准/大盘门控都会用到指数）
- 做法：同步脚本把指数与个股分开处理；指数走 `kline_daily` 同表但**单独做新鲜度校验**（`WHERE code=?` 取自身 max(ts) 比对交易日历）；补齐 `sh000001/sh000300/sh000905/sz399001/sz399006/sh000016`

### P0-2 板块层三表（1~2 天）★ 最大缺口
```sql
-- ① 维度表
CREATE TABLE sector (
  sector_id TEXT PRIMARY KEY,        -- 'BK0475' / 'THS:白酒' 等稳定 ID
  name TEXT NOT NULL,                -- 白酒Ⅱ / 光伏玻璃
  type TEXT NOT NULL,                -- industry | concept | style
  src  TEXT NOT NULL,                -- eastmoney | ths | derived
  updated_at TEXT
);
-- ② 桥表（多对多 + **时点化**）★ 无未来函数的关键
CREATE TABLE stock_sector (
  code TEXT NOT NULL, sector_id TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  valid_from TEXT NOT NULL,          -- 该归属生效日
  valid_to   TEXT,                   -- NULL=至今
  src TEXT,
  PRIMARY KEY (code, sector_id, valid_from)
);
CREATE INDEX idx_ss_code_ts ON stock_sector(code, valid_from);
CREATE INDEX idx_ss_sector  ON stock_sector(sector_id, valid_from);
-- ③ 板块行情事实表（等权 + 流通市值加权两口径都存）
CREATE TABLE sector_daily (
  sector_id TEXT NOT NULL, ts TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL,
  volume REAL, amount REAL,
  member_count INTEGER,
  basis TEXT NOT NULL,               -- equal | float_mcap
  PRIMARY KEY (sector_id, ts, basis)
);
```
- **板块归属会变**（成分调整、改名、概念新增）→ 只存"当前映射"会让回测产生未来函数 ⇒ **必须带 `valid_from/valid_to`**
- **板块指数自算**：用桥表 + 成分股前复权日K 聚合（等权 `mean(ret)` / 流通市值加权），**不依赖第三方板块行情接口**（接口不稳、口径不明、无历史）
- 查询范式：`as_of(stock_sector, date, mode='latest')` 取"当日可知的成分"→ 再聚合

### P1-1 基本面时点化（半天）
```sql
CREATE TABLE fundamentals_hist (
  code TEXT NOT NULL, as_of TEXT NOT NULL,   -- 数据可知日(如财报发布日)
  report_date TEXT,                          -- 报告期
  pe_ttm REAL, pb REAL, market_cap REAL, roe REAL, float_mcap REAL,
  src TEXT, updated_at TEXT,
  PRIMARY KEY (code, as_of)
);
```
- 现状只存"最新快照"（且只有 3 行）→ 无法做"当时估值"回测；改为**追加式(append-only)**，配 `as_of()` 复用
- 红线：拉不到写 NULL，**禁模拟值**（用户已点名过的 P0）

### P1-2 同步任务加固（半天）
- `MarketDB_Daily` 跑到 40+ 分钟未结束 → 加：① 分阶段进度日志 ② 单阶段超时+续跑（水位线幂等）③ 完成写 `sync_heartbeat(table, last_ts, rows, ok, finished_at)` ④ 失败告警
- 沿用既有铁律：**本地源增量同步**（50s，不走网络），网络路径只作冷启动/补缺

### P2 分钟级按需扩展（视需求）
- 全市场 1min 一年 ≈ 5,000×240×250 = **3 亿行/年** ⇒ 不建议全量落
- 建议策略：**30min 全市场（已有）+ 5min 按池（自选/持仓/候选池）+ 1min 仅当日**（当日用完即归档）

---

## 三、可行性判断

| 维度 | 结论 |
|---|---|
| 技术 | ✅ 可行 —— 现有 1.35GB/6 表/4 千万行 SQLite+WAL 单机跑得动 |
| 数据量 | 日K全历史 ≈ 2,800 万行；30min 每年 ≈ 1,000 万行 ≈ 1GB → 5 年 5GB，**单机 SQLite 够** |
| 何时升级 | **到 1 亿行或需要列式扫描（全市场因子计算）再上 DuckDB/Parquet**，现在上属过度设计 |
| 真正难点 | 不是存储，而是 ① **关联的时点化**（板块/基本面会变）② **多源口径归一**（volume 股/手，已踩过）③ **更新幂等** ④ **新鲜度门控按票而非全表** |
| 定时更新 | ✅ 机制已在跑（19:00 全量 + 盘后每 30 分钟增量），需加固超时/心跳 |

---

## 四、建议落地顺序与工作量

> **落地状态（2026-10-01 当天完成 D1~D4）**

| 序 | 任务 | 工作量 | 状态 |
|---|---|---|---|
| 1 | 指数同步修复 + 按票新鲜度门控 | 半天 | ✅ **完成**（6 大指数补齐到 09-30；两工程经开关实测读到） |
| 2 | 板块三表 + 时点化桥表 + 板块指数 | 1~2 天 | ✅ **完成**（710 板块 / **799,437 行板块指数 / 2021-10-29~2026-09-30** / SCD2 时点化 80,750 条） |
| 3 | 基本面 append-only 时点化 | 半天 | ✅ **完成**（fundamentals_hist，拉不到写 NULL） |
| 4 | 同步任务心跳/超时/告警 | 半天 | ✅ **完成**（sync_heartbeat 每板块一行；19:00 随 sync_daily.bat） |
| 5 | 分钟级按池/当日策略 | 按需 | ⏳ 未做（30min 全市场已覆盖） |

**交付物**：`D:/MarketData/sector_layer.py`（库+CLI）、`marketdb.py`（只读接入器）、`sync_assoc.bat`（定时）、
`test_sector_layer.py`（11 项契约）、`verify_assoc.py`（11 项端到端）、`assoc_demo.py`（用法实证）；
本地 git 仓库已建立（脚本版控，DB/日志/大样本已 gitignore）。


| 序 | 任务 | 工作量 | 收益 |
|---|---|---|---|
| 1 | 指数同步修复 + 按票新鲜度门控 | 半天 | 修基准/门控失真 |
| 2 | 板块三表 + 时点化桥表 + 自算板块指数 | 1~2 天 | **补最大缺口**，支撑板块轮动/热度 |
| 3 | 基本面 append-only 时点化 | 半天 | 支撑"当时估值"回测 |
| 4 | 同步任务心跳/超时/告警 | 半天 | 无人值守可靠性 |
| 5 | 分钟级按池/当日策略 | 按需 | 高频回测 |

> 完成 1~4 后，库即具备「大盘(指数+宽度) / 板块(行业+概念, 时点化) / 个股(日K+复权+分钟) / 事件(除权) / 基本面(as_of)」五层全关联，且**全部可 as_of 对齐**（无未来函数）。
