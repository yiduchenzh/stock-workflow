# Aurora AI 量化投资工作站 — 架构设计方案 v3.0

> 技术选型: Vue3 + Vite + Naive UI + FastAPI + SQLite→PostgreSQL + Redis
> 设计原则: 图形 > 数字 > 文字 · 清爽可交互 · 可水平扩展

---

## 一、架构总览（面向大规模并发）

```
┌─────────────────────────────────────────────────────────────┐
│                        用户层                                │
│  浏览器(PC)    浏览器(移动)    微信小程序    (未来)App       │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS
┌─────────────────────────▼───────────────────────────────────┐
│                    CDN / Nginx 反代层                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ 静态资源  │ │ 负载均衡  │ │ 限流     │                    │
│  │ (Vite构建)│ │ (轮询/IP) │ │ 1k/s IP │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI 应用层                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ API容器1 │ │ API容器2 │ │ API容器3 │ │ ...      │       │
│  │ (水平扩展)│ │ (水平扩展)│ │ (水平扩展)│ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
└─────────────┬───────────────────┬────────────────────────────┘
              │                   │
┌─────────────▼──────┐ ┌─────────▼──────────────────────────┐
│   缓存层(Redis)     │ │        数据层                       │
│  ┌──────────────┐  │ │ ┌──────────┐ ┌──────────────────┐  │
│  │ Signal Cache │  │ │ │ SQLite   │ │ PostgreSQL (未来) │  │
│  │ Market Cache │  │ │ │ (Phase1) │ │ (Phase2+ 迁移)   │  │
│  │ Session Cache│  │ │ └──────────┘ └──────────────────┘  │
│  │ Rate Limit   │  │ │ ┌────────────────────────────────┐ │
│  └──────────────┘  │ │ │ Aurora Engine (单进程/子进程)  │ │
│                    │ │ │ engine_state.json (共享文件)   │ │
└────────────────────┘ │ │ sim_state.json                  │ │
                       │ └────────────────────────────────┘ │
                       └────────────────────────────────────┘
```

### 1.1 分层扩展策略

| 瓶颈 | 当前方案 | 水平扩展方案 |
|:-----|:---------|:-------------|
| 静态资源 | 单服务器 | CDN分发(阿里OSS/腾讯COS) |
| API请求 | 单进程uvicorn | Nginx负载均衡→多容器 |
| 数据库读 | JSON文件 | 只读副本(PostgreSQL) |
| 实时推送 | SSE单进程 | Redis PubSub跨进程广播 |
| 用户会话 | 内存 | Redis Session Store |
| 限流 | 无 | Redis Token Bucket |

### 1.2 实时推送架构（关键：SSE跨进程）

当前问题：SSE在单进程内用`asyncio.Queue`工作，但多容器时无法跨进程推送。

```
Phase 1 (单机):
Aurora引擎 → publish() → asyncio.Queue → SSE → 用户

Phase 2 (多机):
Aurora引擎 → Redis PubSub → 
  ├── API容器1 → SSE → 用户群A
  ├── API容器2 → SSE → 用户群B  
  └── API容器3 → SSE → 用户群C
```

Phase 1完全可用（单机支撑500+并发），Phase 2只需替换`publish()`实现为Redis即可扩展。

---

## 二、前端架构（Vue3 + Vite + Naive UI）

### 2.1 目录结构

```
stock-workflow/frontend/
├── index.html
├── package.json
├── vite.config.js
├── src/
│   ├── main.js                    # 入口
│   ├── App.vue                    # 根组件(布局+导航)
│   ├── router/
│   │   └── index.js               # 路由: 7个页面
│   ├── stores/
│   │   ├── market.js              # 市场数据(Pinia)
│   │   ├── signals.js             # 信号数据
│   │   ├── portfolio.js           # 持仓数据
│   │   ├── user.js                # 用户状态
│   │   └── sse.js                 # SSE连接管理
│   ├── components/
│   │   ├── layout/
│   │   │   ├── TopBar.vue         # 顶部导航栏
│   │   │   ├── NavTabs.vue        # Tab导航
│   │   │   ├── FooterDisclaimer.vue # 底部免责
│   │   │   └── MobileNav.vue      # 移动端底部导航
│   │   ├── gauge/
│   │   │   └── MarketScore.vue    # 评分仪表盘(CSS圆环+进度条)
│   │   ├── cards/
│   │   │   ├── IndexCard.vue      # 指数卡片
│   │   │   ├── SignalCard.vue     # 信号卡片(可展开)
│   │   │   ├── StrategyCard.vue   # 策略卡片(可开关)
│   │   │   └── StatCard.vue       # 统计卡片(大号数字)
│   │   ├── charts/
│   │   │   ├── SectorBar.vue      # 板块轮动图(ECharts)
│   │   │   ├── EquityCurve.vue    # 权益曲线(ECharts)
│   │   │   └── MiniSparkline.vue  # 迷你走势(Canvas)
│   │   ├── trading/
│   │   │   ├── PositionTable.vue  # 持仓表格
│   │   │   ├── RiskStatus.vue     # 风控状态
│   │   │   └── TradeHistory.vue   # 交易记录
│   │   ├── academy/
│   │   │   ├── AiChat.vue         # AI问答组件
│   │   │   └── KnowledgeCard.vue  # 知识库卡片
│   │   ├── training/
│   │   │   ├── BlindKLine.vue     # 盲K训练(Canvas)
│   │   │   ├── RecognizeChallenge.vue # 识图挑战
│   │   │   └── TrainingScore.vue  # 训练得分
│   │   └── common/
│   │       ├── LoadingSkeleton.vue # 骨架屏
│   │       └── ErrorState.vue     # 错误状态
│   ├── views/
│   │   ├── MarketView.vue         # 市场全景
│   │   ├── SignalsView.vue        # 量化信号
│   │   ├── PortfolioView.vue      # 组合透视
│   │   ├── StrategiesView.vue     # 策略工坊
│   │   ├── BacktestView.vue       # 回测分析
│   │   ├── AcademyView.vue        # AI学院
│   │   └── TrainingView.vue       # 盘感训练
│   ├── composables/
│   │   ├── useSSE.js              # SSE连接管理
│   │   ├── useApi.js              # API请求封装
│   │   └── useAuth.js             # 用户认证
│   ├── utils/
│   │   ├── format.js              # 格式化(数字/日期/涨跌幅)
│   │   ├── colors.js              # 颜色映射
│   │   └── klinePatterns.js       # K线形态识别
│   └── styles/
│       ├── variables.css          # 设计系统变量
│       ├── global.css             # 全局样式
│       └── dark-theme.css         # Naive UI暗色覆盖
├── public/
│   └── favicon.ico
└── dist/                          # 构建产物, Nginx托管
```

### 2.2 组件树（市场全景示例）

```
MarketView.vue
├── TopBar (全局)
├── MarketScore.vue          ← 评分仪表盘 (图形仪表盘, 大字+进度)
├── IndexCard.vue × 4        ← 上证/深证/创业板/科创 (图形箭头+数字+迷你走势)
├── SectorBar.vue            ← 板块轮动 (横向条形图 ECharts)
├── MarketDiagnosis.vue      ← 市场环境诊断 (4个小卡片: 量/涨跌比/涨停/北向)
├── TodayPlan.vue            ← 今日计划 (系统建议卡片)
└── FooterDisclaimer (全局)
```

### 2.3 路由设计

```javascript
const routes = [
  { path: '/',          redirect: '/market' },
  { path: '/market',    name: 'Market',     component: () => import('@/views/MarketView.vue'),     meta: { title: '市场全景', icon: 'chart' } },
  { path: '/signals',   name: 'Signals',    component: () => import('@/views/SignalsView.vue'),    meta: { title: '量化信号', icon: 'flash' } },
  { path: '/portfolio', name: 'Portfolio',  component: () => import('@/views/PortfolioView.vue'),  meta: { title: '组合透视', icon: 'wallet' } },
  { path: '/strategies',name: 'Strategies', component: () => import('@/views/StrategiesView.vue'), meta: { title: '策略工坊', icon: 'settings' } },
  { path: '/backtest',  name: 'Backtest',   component: () => import('@/views/BacktestView.vue'),   meta: { title: '回测分析', icon: 'trending' } },
  { path: '/academy',   name: 'Academy',    component: () => import('@/views/AcademyView.vue'),    meta: { title: 'AI学院',   icon: 'book' } },
  { path: '/training',  name: 'Training',   component: () => import('@/views/TrainingView.vue'),   meta: { title: '盘感训练', icon: 'game' } },
]
// 按需加载, 首包只含 market+signals
```

### 2.4 状态管理(Pinia)

```javascript
// stores/sse.js — SSE连接管理(单例, 全局唯一)
export const useSSEStore = defineStore('sse', () => {
  const eventSource = ref(null)
  const connected = ref(false)
  const reconnectAttempts = ref(0)
  
  function connect() {
    // 创建SSE连接, 自动重连(3s/10s/30s退避)
    // 接收事件 → 分派到对应store
  }
  function disconnect() { /* ... */ }
  return { connected, connect, disconnect }
})

// stores/signals.js — 信号数据
export const useSignalsStore = defineStore('signals', () => {
  const signals = ref([])
  const filter = ref('all') // all | bull | bear | neutral
  const unreadCount = ref(0)
  
  function addSignal(signal) { /* 插入顶部 + unreadCount++ */ }
  function markRead() { unreadCount.value = 0 }
  function setFilter(f) { /* 过滤 */ }
  return { signals, filter, unreadCount, addSignal, setFilter }
})
```

SSE事件→Store分发映射:
```
market  → marketStore.update()
signal  → signalsStore.addSignal()
trade   → portfolioStore.updateTrade()
regime_change → marketStore.updateRegime()
```

---

## 三、设计原则落地：图形 > 数字 > 文字

### 3.1 每条数据的三层呈现

以"市场评分68"为例:

```
第一层: 图形 (立即感知)
  ┌──────────────────────┐
  │   ╭───╮             │
  │   │ 68│   ← 圆形仪表盘 + 进度条弧
  │   ╰───╯             │
  │   ▓▓▓▓▓▓▓░░░░░░░    │
  │   弱───────●──强     │
  └──────────────────────┘

第二层: 数字 (精确数值)
  68 分

第三层: 文字 (补充说明)
  市场评分 · 偏强
```

### 3.2 每种数据的视觉编码优先级

| 数据类型 | 图形 | 数字 | 文字 | 示例 |
|:---------|:----:|:----:|:----:|:-----|
| 市场评分 | 圆形仪表盘 | 大号数字 | 强度标签 | 仪表盘中心68+弧线 |
| 指数涨跌 | 迷你走势线 | 涨跌幅% | 指数名 | 绿色/红色走势+↑↓ |
| 板块轮动 | 横向Bar | 涨跌幅% | 板块名 | 条形图长度=涨幅 |
| 信号评分 | 颜色左边框 | 评分数字 | 信号标签 | 蓝色边框+85+评分偏多 |
| 信号强度 | 星级(★) | — | 策略名 | ★★★★★ |
| 持仓盈亏 | 迷你图表 | 盈亏金额 | 股票名 | 绿色/红色数字 |
| 风控状态 | 警告图标 | — | 告警文字 | ⚠️ 熔断+红色 |
| 对比数据 | 柱状图/折线 | 百分比值 | 指标名 | 权益曲线+基准对比 |
| 训练得分 | 进度环 | 得分数字 | 评级文字 | 环形85+优秀 |
| 涨跌 | 三角箭头↑↓ | 涨跌幅% | — | ↑ +0.65% (红色) |

### 3.3 交互设计原则

| 场景 | 交互 | 原因 |
|:-----|:-----|:------|
| 信号卡片 | 点击展开/收起, 平滑动画 | 信息渐进呈现, 不一次性堆砌 |
| 导航Tab | 切换时内容渐变过渡 | 不给用户"跳页"生硬感 |
| 策略参数 | 滑块实时调整, 即时预览 | 所见即所得 |
| 股市指数 | 悬停显示当日OHLC | 细节按需展示 |
| 表格 | 点击列头排序 | 用户按需组织 |
| SSE推送 | 新数据淡入+高亮闪烁 | 让用户感知"有变化" |
| 加载 | 骨架屏(非spinner) | 减少等待焦虑 |
| 空状态 | 插图+引导文字 | 不白屏, 有方向 |
| 错误 | 重试按钮+缓存降级显示 | 不死在错误页 |

---

## 四、后端扩展方案（大规模并发）

### 4.1 数据库迁移路径

```
Phase 1 (单机, ≤500并发):
  数据: JSON文件 + SQLite
  缓存: Python dict (local memory)
  实时: asyncio.Queue (单进程)
  
Phase 2 (多机, ≤5000并发):
  数据: PostgreSQL (只读副本)
  缓存: Redis (跨进程共享)
  实时: Redis PubSub → SSE
  限流: Redis Token Bucket
  
Phase 3 (弹性, ≤50000并发):
  数据: PostgreSQL + 读写分离
  缓存: Redis Cluster
  实时: 独立SSE服务 (Go/Node.js)
  限流: API Gateway层
```

### 4.2 读写分离设计

```
写入密集型 (低频):
  Aurora引擎 → write engine_state.json → Redis通知
  用户注册/升级 → SQLite/PostgreSQL
  模拟交易 → write sim_state.json

读取密集型 (高频, 需缓存):
  市场全景 → Redis Cache (TTL=30s) → 降级→JSON文件
  信号列表 → Redis Cache (TTL=5s) → 降级→内存
  指数行情 → 腾讯API直连 (不落盘)
  用户信息 → Redis Cache (TTL=300s)
  
  缓存未命中规则:
  Redis miss → 读JSON文件/数据库 → 写回Redis
  JSON文件不存在 → 返回降级数据(最近有效值)
```

### 4.3 SSE跨进程方案

```python
# Phase 1: 单进程asyncio.Queue (当前方案)
async def publish(channel, event, data):
    for q in subscribers.get(channel, []):
        await q.put(data)
        
# Phase 2: Redis PubSub (多进程)
import aioredis
async def publish(channel, event, data):
    redis = await aioredis.from_url("redis://localhost")
    await redis.publish(f"aurora:{channel}", json.dumps({"event": event, "data": data}))

# 每台API服务器:
async def sse_listener():
    redis = await aioredis.from_url("redis://localhost")
    async with redis.pubsub() as ps:
        await ps.subscribe("aurora:live")
        async for msg in ps.listen():
            # 转发到本机SSE连接的客户端
            await broadcast(msg["data"])
```

### 4.4 Nginx配置（生产）

```nginx
upstream aurora_api {
    least_conn;  # 最少连接分发
    server 127.0.0.1:7878 weight=5;
    server 127.0.0.1:7879 weight=5;
    server 127.0.0.1:7880 weight=5;
}

server {
    listen 443 ssl http2;
    server_name aurora.example.com;
    
    # 静态资源 (CDN)
    location /assets/ {
        root /var/www/aurora/dist;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    # API (负载均衡)
    location /api/ {
        proxy_pass http://aurora_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # SSE的支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
        
        # 限流 (每IP 60请求/分钟)
        limit_req zone=api burst=20 nodelay;
    }
    
    # SSE (走单独连接池, 避免被普通API请求饿死)
    location /api/sse/ {
        proxy_pass http://aurora_api;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }
}
```

### 4.5 限流策略

| 层级 | 限制 | 超限处理 |
|:-----|:-----|:---------|
| 单IP | 60请求/分钟 | 429 + 重试等待X秒 |
| 免费用户 | 30请求/分钟 | 429 + 升级提示 |
| 会员用户 | 120请求/分钟 | 429 |
| SSE连接 | 每用户3连接 | 拒绝新连接 |
| 全站 | 1000请求/秒 | 降级+告警 |

---

## 五、前端性能目标

| 指标 | 目标 | 实现方式 |
|:-----|:----:|:---------|
| LCP (首屏渲染) | <1.5s | Vite按需加载+骨架屏 |
| FCP (首次内容) | <0.8s | 关键CSS内联 |
| TTI (可交互) | <2s | 组件懒加载 |
| 信号推送延迟 | <500ms | SSE长连接 |
| 页面切换 | <300ms | keep-alive缓存 |
| 交互响应 | <100ms | 本地状态优先 |
| 离线可用 | 缓存数据 | IndexedDB缓存行情 |
| 首包大小 | <200KB | 路由级code split |

---

## 六、实施路线（Phase 1）

### 第一步：搭建Vue3框架（2天）

| 任务 | 产出 |
|:-----|:------|
| 安装Vite+Vue3+Naive UI | package.json + vite.config.js |
| 设计系统CSS变量 | variables.css (颜色/间距/字号/圆角) |
| 全局样式+暗色覆盖 | global.css + dark-theme.css |
| 布局组件 | TopBar/NavTabs/Footer/MobileNav |
| 路由配置 | 7个页面按需加载 |
| SSE Store | 连接/重连/分发 |
| API封装 | fetch + 错误处理 + 缓存 |

### 第二步：市场全景页面（2天）

| 组件 | 数据 | 交互 |
|:-----|:-----|:------|
| MarketScore.vue | /api/market/overview | 环形进度+动画 |
| IndexCard.vue ×4 | 腾讯API直连 | 迷你走势(Sparkline) |
| SectorBar.vue | 板块数据 | ECharts横向条形 |
| MarketDiagnosis.vue | 环境数据 | 4小卡片 |
| TodayPlan.vue | 今日计划 | 行动入口→信号Tab |

### 第三步：量化信号页面（1.5天）

| 组件 | 数据源 | 交互 |
|:-----|:-------|:------|
| SignalCard.vue | SSE+API | 展开/收起+新信号动画 |
| FilterBar.vue | 本地状态 | 筛选+搜索 |
| SignalList.vue | signalsStore | 无限滚动 |

### 后续页面按优先级推进

---

## 七、关键决策记录

| 决策 | 选择 | 原因 |
|:-----|:-----|:------|
| 前端框架 | Vue3 + Vite | 用户选择, 长期维护 |
| UI组件库 | Naive UI | 暗色原生支持, 中文友好 |
| 状态管理 | Pinia | Vue3官方推荐 |
| 实时通信 | SSE (非WebSocket) | 单向推送+跨进程易扩展 |
| 图表 | ECharts (非D3) | 金融图表原生支持 |
| 数据库起步 | SQLite | 数据量<100MB, 零运维 |
| 缓存 | Redis (Phase2) | 通用, 支持PubSub |
| 构建输出 | `dist/` → Nginx托管 | 性能最优 |
| 图形成分 | CSS Canvas ECharts | 按复杂度分层选型 |

---

## 八、后端API改造清单

当前后端33端点基本可用, 需新增/改造:

| 端点 | 方法 | 当前 | 改造 |
|:-----|:----:|:----:|:-----|
| /api/market/overview | GET | ✅ | 加Redis缓存30s |
| /api/signals/latest | GET | ✅ | 加分页+SSE兼容 |
| /api/sse/live | GET | ✅ | Phase2→Redis PubSub |
| /api/config/strategy | GET/POST | ❌ | 新增, 策略配置CRUD |
| /api/backtest/summary | GET | ❌ | 新增, 回测汇总 |
| /api/user/register | POST | ❌ | 新增, 邮箱注册 |
| /api/user/login | POST | ❌ | 新增, JWT登录 |
| /api/user/profile | GET | ❌ | 新增, 用户画像 |
| /api/payment/create | POST | ❌ | 新增, 创建订单 |
| /api/payment/callback | POST | ❌ | 新增, 支付回调 |
