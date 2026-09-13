# Aurora AI 量化投资平台 — 功能详细设计方案

## 一、当前状态（已完成33个API）

```
Phase 0: 直播MVP      8 API ✅
Phase 1a/b/c: 解说+WS+付费  9 API ✅
Phase 2: 画像+复盘      4 API ✅
Phase 3: 策略工坊+回测+进化  7 API ✅
Phase 4: 周报+大赛      5 API ✅
合计: 33个API端点
```

## 二、未实现的具体功能（需前端集成）

### 1. 策略参数热保存
- 现有: GET /api/strategies/config/{key} (只读)
- 缺失: POST /api/strategies/config/{key}
- 功能: 保存策略参数 → 写config.yaml → engine.reload_config()
- 前端: 滑块拖拽→保存按钮→POST请求→提示热加载成功

### 2. 会员升级面板
- 现有: GET /api/user/status, GET /api/user/upgrade, GET /api/tiers
- 缺失: 前端UI
- 功能: 显示4级定价卡，点击升级调用 /api/user/upgrade
- 触发: 免费额度用完自动弹出，或导航栏[升级]按钮

### 3. 邀请裂变面板
- 现有: GET /api/user/invite, GET /api/user/redeem
- 缺失: 前端UI
- 功能: 显示邀请码→复制→分享→双方获VIP天数

### 4. 使用量配额追踪
- 现有: GET /api/user/use
- 缺失: 前端UI
- 功能: 进度条显示今日用量 x/50次

### 5. SSE实时推送增强
- 现有: SSE端点存在但无数据推送
- 缺失: asyncio.create_task轮询器
- 功能: 每30秒推送指数/板块/涨跌比到前端
- 影响: 前端指数和板块数据实时更新

### 6. 战绩卡图形化
- 现有: GET /api/card/generate (纯文本HTML)
- 缺失: 前端分享按钮+SVG卡片渲染

## 三、下一步实施顺序

按前端影响度排序：

| 优先级 | 功能 | 工作量 | 用户可见度 |
|:-----:|:-----|:-----:|:---------:|
| P0 | SSE实时推送 | 5行代码 | ⭐⭐⭐ 数据实时更新 |
| P1 | 会员升级面板 | ~80行HTML | ⭐⭐⭐ 核心商业转化 |
| P2 | 策略参数保存 | 20行后端+30行前端 | ⭐⭐ 策略工坊完善 |
| P3 | 使用量配额 | ~30行HTML | ⭐⭐ 用户体验 |
| P4 | 邀请裂变面板 | ~40行HTML | ⭐ 增长功能 |
| P5 | 战绩卡图形化 | ~50行 | ⭐ 社交分享 |
