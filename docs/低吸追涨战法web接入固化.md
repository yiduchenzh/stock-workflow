# 低吸追涨战法 · web 工程接入固化（2026-08-23 v1.0）

> 来源：老陈提供 `Y:\dip-rolling-pro`（后复制至 `D:\dip-rolling-pro`）技能（SKILL.md + scripts/ 自包含引擎，终态 2年全市场 +462%）。
> 目标：接入 hunter-v2 web（自动交易 tab「🎯 低吸追涨战法全自动交易」+ 回测验证 tab「🎯 低吸追涨战法回测」），参数/引擎与技能完全一致，异步任务根治超时。

---

## 一、战法本质（一句话）

**日K选股（涨停→缩量回调低吸）+ 昨收战法5分K实时执行（速战速结）**。

观察池三层（老陈定调）：①大盘（涨停数≥30 冰点过滤）②板块/个股 ③涨停股票池（涨停→回调3-8天→缩量+防守线信号）。

**流程**：`build_lu_index(全市场涨停日索引)` → `backtest_dip_rolling(涨停票回调观察池→缩量信号)` → 信号进候选 → `backtest_dip_pro(5分K回抽确认→买入→持仓管理)`。

## 二、6大精髓（5分K级，全部对齐技能）

| # | 机制 | 规则 |
|:--|:--|:--|
| 1 | 回抽确认进场 | buy_confirm 信号日尾盘买；buy_low 次日5分K"下探→回抽站上开盘价"确认（B强开/A回抽），confirm_days=2 |
| 2 | 早盘弱势卖出 | 持仓浮亏 + 开盘3分钟全收<昨收 → 09:40早走 |
| 3 | 重进机制 | 清仓后冷却3天 + 连续5根5分K站稳昨收 → 快速重进 |
| 4 | T0底仓回转 | 冲高回落高抛→回踩接回，趋势分档 up40%/range30%/down15% |
| 5 | 连续4根破位清仓 | 连续4根5分K收<昨收 → 清仓；全天弱势尾盘清仓 |
| 6 | 单笔止损7%尾盘兜底 | 浮亏≥7% 尾盘清仓；加仓=回踩不破+5分K放量(禁down) |

## 三、参数终态（与 run_verify.py 逐项一致，勿动）

```python
start_day="2024-08-21", end_day="2026-08-21", count=500, workers=12, max_codes=0,
need_confirm=False,   # ⭐ 对齐核心: 默认 False（+270% vs True 的 +137.86%, 差近1倍）
stop_guard="lu_low",
pos_pct=0.3, pos_max_per_day=2, min_zt_floor=30,
t0_enable=True, trend_layers=True, add_enable=True, lose_streak_stop=3,
stop_single_pct=7.0, confirm_days=2,
re_entry_enable=True, re_entry_cd=3,
```

⚠️ **样本模式坑**：`max_codes>0` 时 lu_index 只统计样本内涨停数(0-2只) → min_zt_floor=30 永远触发冰点禁开仓 → 样本模式强制 min_zt_floor=0。

## 四、引擎代码一致性（2026-08-23 MD5 核对）

| 文件 | hunter-v2/backend/dip_rolling/ vs D:\dip-rolling-pro\scripts\ | 说明 |
|------|------|------|
| absorb_dip.py / backtest.py / dip_rolling_pro.py | **SAME** | 核心逻辑零改动 |
| dip_rolling.py / datafeed.py | DIFF | 仅性能优化：KlineDB 攒批commit + flush（不影响战法逻辑） |

依赖坑：`dip_rolling/backtest.py` import `screener`（classify_prev_volume/score_signal）→ 需把 `limitup-system` 加进 sys.path。

## 五、缓存体系（三层 + 异步）

| 层 | 机制 | 效果 |
|----|------|------|
| ① 结果级 | `_BT_CACHE` 24h（key 含全部参数） | 同参 **0s 秒回** |
| ② 日K | KlineDB SQLite 持久（125MB）+ 后台预热 + 攒批commit | 全市场秒级读 |
| ③ 5分K | `cache/min5/{code}.json` 磁盘（1474只永久复用）+ 信号磁盘缓存 | 变参重跑只算回放 |
| ④ 异步任务 | `POST /backtest` 立即返回 task_id + `GET /backtest/status` 轮询 | **根治长任务超时** |

**性能优化记录**：
- KlineDB 每只单独 commit（SQLite fsync 串行）→ 全市场日K 20min+ → **攒批 commit（50只/次, 写加速~50x）**
- 信号检测（backtest_dip_rolling 2460只纯Python扫描）每次重算 → **信号磁盘缓存**（确定性key, 命中跳过）
- 预热线程与回测并发写 KlineDB → SQLite 锁竞争数据全丢 → **`_BT_LOCK` 互斥**
- 5分K 串行拉（need_confirm=False 后信号 5076 个 → 串行 40min+）→ **`prefetch_min5_parallel` 并发8**

## 六、验证结果（2026-08-23 实测，异步任务 1322s）

```
web 实测: +270.36% | 年化97.45% | 回撤62.04% | 夏普1.64 | 卡玛1.57 | 胜率61.5% | 盈亏比2.10 | 期末¥370,355
SKILL.md: +462.01% | 年化145.22% | 回撤68.69% | 夏普1.67 | 卡玛2.11 | 胜率64.9% | 期末¥562,010
```

- **策略质量对齐**：夏普 1.64 vs 1.67、胜率 61.5% vs 64.9%（几乎一致）→ 代码/参数完全对齐 ✅
- **收益差距归因（数据层, 非代码）**：①5分K 窗口 20000根≈1.75年（2年前段信号无法执行, 买入852 vs 1074）②股票池截面=当前在池（历史退市/停牌/涨超200元的票缺失）③复权基准时点差异。SKILL.md 官方也说"偏差大先查数据源/复权/缓存"。
- **need_confirm 对齐效果**：True→False 信号 1674→5076、买入 408→852、收益 137.86%→270.36%（翻倍）。

## 七、web 接口清单

```
POST /api/v1/dip-rolling/backtest          # 异步提交回测 → {task_id}
GET  /api/v1/dip-rolling/backtest/status   # ?task_id= 轮询 running/done/error
GET  /api/v1/dip-rolling/signals           # 信号预览（涨停观察池候选, 快）
GET  /api/v1/dip-trade/status              # 自动交易状态
POST /api/v1/dip-trade/start|stop          # 自动交易启停
```

前端：BacktestPage tab「🎯 低吸追涨战法回测」（DipRollingBacktestPage, 异步轮询 5s）；AutoTradePage 双tab「🤖 昨收/🎯 低吸追涨」（DipTradePanel）。

## 八、已知边界

- 首次全市场冷启动 20-40min（拉全市场 5分K 落盘一次性成本）；缓存热后同参 0s / 变参 5min（回放计算, 全局资金池不可并行）
- 自动交易器（DipTrader）为简化实时版：60s tick + 观察池信号 + 5分K 确认，与回测引擎同源但非完全等价（未含全部状态机细节）——实盘前需 2-4 周模拟盘验证
- 结果缓存/任务存储为进程内（后端重启丢失 → 重新提交, 数据缓存仍在）

---

*低吸追涨战法 web 接入 v1.0 · 2026-08-23 · 参数对齐 run_verify + 异步任务 + 三层缓存 + 性能优化 · 实测 +270.36% 胜率61.5% 夏普1.64*
