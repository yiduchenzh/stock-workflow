"""Aurora实时流引擎 — run_forever模式"""
import time, json, logging, signal, sys
from pathlib import Path
from datetime import datetime
from core.engine import AuroraEngine
from core.recovery import save_recovery_point, need_recovery, recover_engine, mark_crash

LIVE_STATE = Path(__file__).resolve().parent.parent / "data" / "live_state.json"

class EngineLiveWrapper:
    def __init__(self, interval=60):
        self.engine = AuroraEngine()
        # 崩溃恢复启动检测
        if need_recovery():
            self.log = logging.getLogger('aurora.live')
            self.log.warning('[Live] 检测到上次异常退出, 恢复引擎状态...')
            recover_engine(self.engine)
        self.interval = interval
        self.running = True
        self.fail_count = 0
        self._last_us_check = 0
        self.log = logging.getLogger("aurora.live")
        self._load_state()
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _save_state(self):
        state = {
            "last_run": datetime.now().isoformat(),
            "market_regime": self.engine.market_regime,
            "market_score": self.engine.market_score,
            "positions_count": len(self.engine.positions),
            "fail_count": self.fail_count,
        }
        LIVE_STATE.write_text(json.dumps(state))
    
    def _load_state(self):
        if LIVE_STATE.exists():
            try: return json.loads(LIVE_STATE.read_text())
            except: return {}
        return {}
    
    def _signal_handler(self, sig, frame):
        self.log.info("收到退出信号, 优雅关闭...")
        self._save_state()
        self.running = False
    
    def _check_health(self):
        """心跳检测"""
        # 检查腾讯API连通性
        try:
            import urllib.request
            r = urllib.request.urlopen("https://qt.gtimg.cn/q=sh000001", timeout=5)
            return r.status == 200
        except:
            return False
    
    def on_new_kline(self, code, kline_data):
        """新K线到达时的轻量级处理"""
        # 1. 如果是持仓股, 检查止损
        if code in self.engine.positions:
            pos = self.engine.positions[code]
            current_price = kline_data.get("close", 0)
            stop_loss = pos.get("stop_loss", 0)
            if stop_loss > 0 and current_price < stop_loss:
                self.engine.alerts.append({
                    "type": "live_stop", "code": code,
                    "price": current_price, "stop": stop_loss,
                    "time": datetime.now().isoformat()
                })
                self.log.warning(f"[LIVE] {code} 触发止损 {current_price:.2f}<{stop_loss:.2f}")
        
        # 2. 快速更新市场状态
        # (每5分钟做一次完整扫描)
    
    def _run_intraday_scan(self):
        try:
            from screening.intraday_scan import run_intraday_cycle
            result = run_intraday_cycle(self.engine)
            if result.get("new_signals",0) > 0:
                self.log.info(f"[Live] {result['session']}: 新{result['new_signals']}信号")
                from notify.pusher import push_trade_plan
                try: push_trade_plan(self.engine)
                except: pass
        except Exception as e:
            self.log.warning(f"[Live] intraday fail: {e}")

    def _check_us_crash(self):
        try:
            import urllib.request
            r = urllib.request.urlopen("https://qt.gtimg.cn/q=usSPY", timeout=5).read().decode("gbk","replace")
            if "~" in r:
                parts = r.split("~")
                if len(parts) > 32:
                    spy = float(parts[32] or 0)
                    if spy < -2:
                        self.engine.alerts.append({"type":"us_crash","spy_change":spy,"msg":f"usSPY跌{spy}%,A股可能承压"})
                        self.log.warning(f"[LIVE] usSPY跌{spy}%! A股开盘预警")
        except: pass

    def run_forever(self):
        """常驻运行主循环"""
        self.log.info(f"[Live] 启动实时流引擎, 轮询间隔={self.interval}s")
        last_market_update = 0
        last_heartbeat = time.time()
        
        while self.running:
            cycle_start = time.time()
            try:
                # 非交易日跳过
                from core.calendar import is_trading_day
                if not is_trading_day():
                    time.sleep(300)
                    continue
                # 非交易时段跳过
                _n = datetime.now()
                _m = _n.hour * 60 + _n.minute
                if _m < 570 or _m > 930:
                    time.sleep(60)
                    continue

                # 1. 检查市场数据
                api_ok = self._check_health()
                if not api_ok:
                    self.fail_count += 1
                    wait = min(300, self.fail_count * 60)
                    self.log.warning(f"[Live] API不可用({self.fail_count}), 等待{wait}s")
                    time.sleep(wait)
                    continue
                self.fail_count = 0
                
                # 2. 每5分钟做一次完整市场扫描
                if time.time() - last_market_update > 300:
                    self.engine.step_market()
                    last_market_update = time.time()
                    self.log.info(f"[Live] 市场更新: {self.engine.market_regime} ({self.engine.market_score:.0f})")
                    save_recovery_point(self.engine.market_regime, self.engine.market_score, len(self.engine.positions), 'market_scan')
                    self._run_intraday_scan()
                # 美股暴跌预警(每5分钟)
                if time.time() - getattr(self, '_last_us_check', 0) > 300:
                    self._check_us_crash()
                    self._last_us_check = time.time()
                
                # 3. 心跳日志
                if time.time() - last_heartbeat > 30:
                    self.log.info("[Live] 心跳正常 | {market} 持仓{pos} 告警{alerts}".format(market=self.engine.market_regime, pos=len(self.engine.positions), alerts=len(self.engine.alerts)))
                    last_heartbeat = time.time()
                
                # 4. 保存状态
                self._save_state()
                
            except Exception as e:
                self.log.error("[Live] 循环异常: {e}".format(e=e))
                mark_crash()
                self.fail_count += 1
            
            # 等待到下一个周期
            elapsed = time.time() - cycle_start
            sleep_time = max(1, self.interval - elapsed)
            time.sleep(sleep_time)
        
        self._save_state()
        self.log.info("[Live] 引擎已停止")
    
    def run_once(self):
        """单次运行模式(被定时任务调用)"""
        self.engine.run()
        self._save_state()

def start_live_engine(interval=60):
    """启动实时流引擎"""
    logging.basicConfig(level=logging.INFO, 
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    live = EngineLiveWrapper(interval)
    live.run_forever()