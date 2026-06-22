# Aurora Trading v1.0

A股全自动交易系统 — 十三步闭环无人值守

## 架构

```
aurora-trading/
├── core/engine.py       # 十三步闭环主引擎
├── data/sources.py      # 腾讯+东财双数据源
├── strategies/          # 5战法并行检测
├── screening/           # 三级联动选股
├── risk/                # 风控+仓位
├── monitor/             # 模拟交易+监控
├── desktop/             # PySide6桌面应用
├── deploy/              # Windows定时任务
└── .github/workflows/   # CI/CD
```

## 快速开始

```bash
pip install -r requirements.txt  # 或 uv pip install numpy pandas pyyaml requests PySide6
python daily_run.py              # 执行全流程
python desktop/main.py           # 启动桌面
```

## 无人值守

1. 管理员运行 `deploy/setup_tasks.bat`
2. 配置 GitHub Secrets `SCT_TOKEN`
3. 修改 `config.yaml` 中的 `mode: live`
