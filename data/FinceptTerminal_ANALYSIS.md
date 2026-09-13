# FinceptTerminal 分析报告 — 可提取到 Aurora 的内容

> 分析来源: README.md (19KB) + README截图描述
> 技术栈: C++20 + Qt6 原生桌面应用 (非Web)

---

## 一、技术栈对比

| 维度 | FinceptTerminal | Aurora (我们) | 结论 |
|:-----|:----------------|:--------------|:------|
| UI框架 | Qt6 C++ | Vue3+NaiveUI | ✓ 差异化，趋势相仿 |
| 后端 | C++嵌入Python | FastAPI Python | ✓ 几乎相同架构 |
| 桌面壳 | Qt原生窗口 | Electron | ✓ Electron更轻量 |
| AI Agent | 37个C++代理 | 6个Python Agent | ⚠️ 我们可以扩展 |
| 数据连接器 | 100+ C++连接器 | WZ+Tencent+Sina | ⚠️ 需扩展 |
| **代码复用** | ❌ C++代码不能直接复用 | — | 提取设计模式 |

---

## 二、可提取的核心设计

### 1. 多面板专业布局 (直接影响界面)

FinceptTerminal的Qt6界面特征:
```
┌──────────────┬────────────────────────────────┬──────────────┐
│  左侧导航栏(Qt Dock) │    主内容区域(Qt Central)     │  右侧工具栏  │
│  - Equity     │    Market Overview           │  - News Feed │
│  - Portfolio  │    Charts + Data             │  - Alerts    │
│  - News       │                              │  - AI Agent  │
│  - Screener   │                              │   Chat       │
│  - Settings   │                              │              │
├──────────────┴────────────────────────────────┴──────────────┤
│  底栏: 状态栏 + 实时行情小部件                                 │
└──────────────────────────────────────────────────────────────┘
```

**到Aurora的映射**:
```
Vue3目前:  顶栏Tab + 左右布局 (65%/35%)
Fincept式: 左侧图标导航栏 + 主内容 + 右侧AI面板 + 底部状态栏

改造方案: 从Tab式导航改为左侧Dock式导航
- 左侧: 紧凑图标栏 (市场/信号/组合/策略/回测/学院/训练) - 60px宽
- 中间: 主内容区 (当前页面) - 弹性
- 右侧: AI助手面板 (可折叠) - 300px
- 底部: 实时行情滚动条 - 32px高
```

### 2. 37个AI Agent体系

Fincept的Agent架构:
```
37 Agents = 
  Trader/Investor: Buffett, Graham, Lynch, Munger, Klarman, Marks, ...
  + Economic: 宏观经济分析
  + Geopolitics: 地缘政治分析
  所有Agent通过LLM API运行 (OpenAI, Anthropic, DeepSeek等)
```

**Aurora现有6个Agent**: 上班族中短线、趋势跟踪者、价值投资者、波段交易者、量化对冲、长线持有

**可扩展方向**: 
- 增加知名投资人画像Agent (如巴菲特、彼得·林奇、索罗斯、达利欧)
- 增加宏观经济Agent (利率/汇率/大宗商品分析)
- 每个Agent可视化为独立面板

### 3. 多数据连接器架构

Fincept的连接器模式:
```
Data Connector Interface (抽象基类)
  ├── YahooFinanceConnector
  ├── PolygonConnector  
  ├── AkShareConnector
  ├── FREDConnector (宏观经济)
  ├── DBnomicsConnector
  └── CustomConnector (用户自定义)
```

**Aurora当前**: WZ + Tencent + Sina (硬编码)

**可提取模式**: 插件式数据源注册
```python
class DataConnector(ABC):
    @abstractmethod
    def get_quote(self, code): ...
    @abstractmethod
    def get_klines(self, code, days): ...
    @abstractmethod
    def get_market_breadth(self): ...

# 注册机制
connectors = [WZConnector(), TencentConnector(), SinaConnector()]
for c in connectors:
    if c.available:
        data = c.get_quote(code)
        if data: break  # 优先级链
```

### 4. 组合优化与风险指标

Fincept提供的分析 (嵌入Python):
```
Portfolio Optimization: 均值方差 / Black-Litterman / 风险平价
Risk Metrics: VaR(95%/99%), CVaR, Sharpe, Sortino, Max Drawdown, Beta
Derivatives Pricing: 期权定价(Black-Scholes/Monte Carlo)
```

**Aurora当前**: 基础仓位管理 + 止损

**可提取**: 添加风险指标API端点
```
/api/portfolio/risk → {VaR, CVaR, Sharpe, MaxDD}
/api/portfolio/optimize → {weights, expected_return, volatility}
```

### 5. Node Editor — 可视化策略构建器

Fincept的Node Editor是Qt6的图形化节点编辑器:
```
[节点] → [条件] → [操作] → [仓位管理]
  条件节点: 价格>MA20, RSI<30, MACD金叉
  操作节点: 买入, 卖出, 加仓, 减仓
  逻辑节点: AND, OR, NOT
```

**Aurora当前**: 通过config.yaml手动编辑策略参数

**可提取**: 简单的可视化策略配置 (Vue3版)
- 用卡片拖拽代替节点编辑器
- 条件选择器: 下拉选条件 → 设阈值
- 策略预览: 实时显示回测效果

---

## 三、优先级实施计划

| 优先级 | 功能 | 工作量 | 影响 |
|:------:|:-----|:------:|:----:|
| **P0** | 左侧导航栏改造 (Tab→Dock) | 2天 | 立即提升产品感 |
| **P0** | AI助手右侧面板 (LLM问答) | 1天 | 已有, 需强化 |
| **P1** | 扩展Agent至12个+画像 | 1天 | 差异化卖点 |
| **P1** | 插件式数据连接器 | 1天 | 可扩展性 |
| **P2** | 风险指标API (VaR/Sharpe) | 1天 | 专业性 |
| **P2** | 底部实时行情滚动条 | 0.5天 | 看盘体验 |
| **P3** | 可视化策略配置器 | 3天 | 高级功能 |

---

## 四、关键区别 (无需复制)

| Fincept有但不需要 | 原因 |
|:-------------------|:-----|
| 16家券商交易接口 | Aurora是分析工具 + 半自动交易 |
| QuantLib全套衍生品定价 | A股散户用不到期权定价 |
| 100+数据连接器 | A股数据源已够用 (WZ+Tencent+Sina) |
| C++ Qt6编译链 | Electron更轻量, 更新更方便 |
