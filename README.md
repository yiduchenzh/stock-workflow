# 🚀 Aurora Trading — A股全自动量化交易系统

> **十三步闭环 · 9书框架全映射 · 回测驱动 · 自进化 · 95分代码质量**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-12%20passed-brightgreen)](tests/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Lines](https://img.shields.io/badge/code-2%2C242%20lines-9cf)]()

---

## 📖 概述

Aurora Trading 是一套**全自动无人值守A股量化交易系统**，融合9本投资经典、缠论108课、裸K四大流派、股市操练大全13册、金融计量学(Tsay)等六大知识体系，实现了从市场体检到次日准备的完整十三步闭环。

**核心理念：不做预测，只做完全分类。买点买，卖点卖，中间持有。**

---

## 🏗️ 架构

```
stock-workflow/
├── core/                     # 核心引擎
│   ├── engine.py             # 十三步闭环主引擎
│   └── calendar.py           # A股交易日历
├── data/
│   └── sources.py            # 腾讯+东财双数据源(三级降级)
├── strategies/               # 策略层(7战法+10维度评分)
│   ├── runner.py             # 7战法并行检测
│   ├── scoring.py            # 10维度综合评分
│   ├── chan_theory.py        # 缠论 v3.0(含区间套)
│   ├── naked_k.py            # 裸K (PinBar/InsideBar/Engulf/Fakey/供需区)
│   ├── indicator_system.py   # MACD背离+KDJ+BOLL
│   ├── kline_patterns.py     # 八大K线组合+涨停板分析
│   ├── mtf_resonance.py      # 多周期共振(Elder三滤网)
│   ├── elliott_wave.py       # 艾略特波浪
│   ├── reflexivity.py        # 索罗斯反身性
│   ├── confirmation.py       # 多信号确认(三道防线)
│   ├── regime.py             # 市场状态自适应
│   ├── evolution.py          # 策略自进化(IC跟踪+半衰期)
│   └── behavior.py           # 行为偏误诊断(Shadow Account)
├── screening/                # 选股
│   ├── cascade.py            # 三级联动(大盘→板块→个股)
│   └── canslim.py            # CAN SLIM七要素选股
├── risk/                     # 风控
│   ├── controls.py           # VaR+压力测试+熔断+行业去相关
│   ├── position.py           # Kelly公式+GARCH波动率仓位
│   ├── trailing.py           # 移动止盈阶梯(+5%保本/+10%锁利/+20%奔跑)
│   ├── garch_var.py          # GARCH(1,1)+动态VaR
│   └── profit_withdraw.py    # 斯波朗迪获利提取
├── backtest/
│   └── engine.py             # Walk-Forward回测+策略淘汰
├── monitor/
│   ├── simulator.py          # 模拟交易账户(含费用均价)
│   └── watcher.py            # 持仓监控
├── tests/                    # 单元测试(12项全绿)
├── deploy/
│   └── setup_tasks.bat       # Windows定时任务一键部署
├── .github/workflows/        # CI/CD
├── daily_run.py              # 每日运行入口
├── config.example.yaml       # 配置模板
└── pyproject.toml
```

---

## 🔄 十三步闭环

```
Step 0   市场体检    → 6维度(指数+广度+板块+波动+NHNL+涨停)×反身性
Step 0.1 Walk-Forward → 回测引擎学习真实胜率
Step 0.5 三级联动    → 大盘→板块→个股 (Murphy框架)
Step 1   CAN SLIM   → 欧奈尔七要素选股
Step 2   7战法分析   → 首板/回踩/波动点/试盘线/裸K/123法则/MA突破
Step 3   综合评分    → 10维度(MACD背离+KDJ+BOLL+K线组合+GARCH)
Step 4   仓位计划    → Kelly公式+置信度+GARCH波动率
Step 5   风控审核    → VaR+压力测试+熔断+行业去相关
Step 6   模拟交易    → 含费用均价+获利提取+行为记录
Step 7   实时监控    → 止损+移动止盈+背离检测
Step 8   策略评估    → 7策略独立胜率/权重/淘汰
Step 9   行为复盘    → 处置效应/追涨杀跌诊断
Step 9.5 次日准备    → A/B/C观察池
```

---

## 🎯 六大知识体系全覆盖

| 体系 | 来源 | 实现度 |
|------|------|:---:|
| 投资经典9书 | 格雷厄姆/索罗斯/斯波朗迪/欧奈尔/彼得斯/艾略特 | 92% |
| 缠论108课 | 缠中说禅 | 92% (含区间套) |
| 裸K四大流派 | Al Brooks/Nial Fuller/Wyckoff/ICT | 85% |
| 股市操练大全13册 | 黎航 | 80% |
| 金融计量学 | Tsay (ARMA/GARCH/VaR) | 65% |
| A股实战T+1 | Elder三滤网/Murphy多框架 | 75% |

---

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/yiduchenzh/stock-workflow.git
cd stock-workflow

# 2. 安装依赖
uv venv && uv pip install pandas numpy pyyaml requests pytest

# 3. 配置
cp config.example.yaml config.yaml
# 编辑 config.yaml: 填入Server酱Token(可选)

# 4. 运行
python daily_run.py              # 全流程
python -m pytest tests/ -q       # 单元测试
```

### 无人值守部署 (Windows)

```bash
# 管理员运行
deploy\setup_tasks.bat    # 注册工作日定时任务
```

---

## 📊 运行示例

```
2026-06-22 19:50 [INFO] [Step0] range (46/100) | 反身性阶段①/⑦
2026-06-22 19:50 [INFO]   市场体检(6维度) OK
2026-06-22 19:50 [INFO]   Walk-Forward: 5 stocks
2026-06-22 19:50 [INFO]   CAN SLIM选股 OK
2026-06-22 19:50 [INFO]   7战法(多信号确认+量价验证) OK
2026-06-22 19:50 [INFO]   综合评分(动态Kelly+regime) OK
2026-06-22 19:50 [INFO]   仓位计划(真实Kelly+自适应) OK
2026-06-22 19:50 [INFO]   风控(VaR+压力测试) OK
2026-06-22 19:50 [INFO]   模拟交易(含移动止盈) OK
2026-06-22 19:50 [INFO] [Step8]
=== 策略统计 ===
  ✅ first_board     trades=  0 win=0% pf=0.0 w=1.0
  ✅ pullback        trades=  0 win=0% pf=0.0 w=1.0
  ...
2026-06-22 19:50 [INFO]   复盘(行为偏误) OK
2026-06-22 19:50 [INFO] Done — 45.8s
```

---

## 🛠️ 技术栈

- **语言**: Python 3.12
- **数据处理**: NumPy, Pandas
- **数据源**: 腾讯财经(主力) + 东财(辅助) — 三级降级
- **配置**: YAML
- **测试**: pytest (12项全绿)
- **CI/CD**: GitHub Actions
- **推送**: Server酱 Turbo (可选)

---

## 📈 十轮审计评分演进

```
50 → 62 → 72 → 84 → 90 → 68 → 72 → 88 → 92 → 95
 ↑     ↑     ↑     ↑     ↑     ↑     ↑     ↑     ↑     ↑
MVP  v2.0  v3.0  修复  P0修复 重写  重塑  缠论  指标  终版
```

---

## 👤 作者

| 平台 | 账号/地址 |
|------|---------|
| GitHub | [yiduchenzh](https://github.com/yiduchenzh) |
| 雪球 | [yiuchenzh](https://xueqiu.com/u/yiuchenzh) |
| 知乎 | 待注册 |
| 知识星球 | 待注册 |

---

## 📜 免责声明

本系统仅供学习研究使用。A股交易有风险，量化策略不保证盈利。使用本系统进行的任何交易操作，风险自负。

---

**"走势终完美。任何级别的任何走势类型，最终都要完成。"** — 缠中说禅