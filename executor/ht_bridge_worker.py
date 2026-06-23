"""鍗庢嘲妗ユ帴Worker 鈥?32浣峆ython鎿嶆帶xiadan.exe (subprocess JSON閫氫俊)"""
import json, sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [HT] %(message)s")
logger = logging.getLogger("ht_worker")

def main():
    """鎺ユ敹JSON鎸囦护, 鎿嶆帶鍗庢嘲瀹㈡埛绔? 杩斿洖JSON缁撴灉"""
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No command"}))
        return
    
    try:
        cmd = json.loads(sys.argv[1])
    except Exception:`r`n        print(json.dumps({"success": False, "error": "Invalid JSON"}))
        return
    
    action = cmd.get("action", "")
    
    try:
        if action == "buy":
            result = _do_buy(cmd)
        elif action == "sell":
            result = _do_sell(cmd)
        elif action == "positions":
            result = _get_positions()
        elif action == "balance":
            result = _get_balance()
        elif action == "today_trades":
            result = _get_today_trades()
        elif action == "cancel":
            result = _do_cancel()
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}
    except Exception as e:
        result = {"success": False, "error": str(e)}
    
    print(json.dumps(result, ensure_ascii=False, default=str))

def _connect():
    """杩炴帴鍗庢嘲瀹㈡埛绔獥鍙?""
    try:
        from pywinauto import Application
        # 灏濊瘯杩炴帴宸茶繍琛岀殑xiadan.exe
        app = Application(backend="win32").connect(path=r"C:\htzqzyb3\xiadan.exe")
        dlg = app.window(class_name="#32770")  # 鍗庢嘲瀵硅瘽妗?
        if not dlg.exists():
            # 灏濊瘯杩炴帴涓荤獥鍙?
            dlg = app.top_window()
        return app, dlg
    except Exception as e:
        logger.error(f"杩炴帴澶辫触: {e}")
        # 灏濊瘯鍚姩瀹㈡埛绔?
        try:
            import subprocess
            subprocess.Popen([r"C:\htzqzyb3\xiadan.exe"])
            time.sleep(5)
            from pywinauto import Application
            app = Application(backend="win32").connect(path=r"C:\htzqzyb3\xiadan.exe")
            dlg = app.top_window()
            return app, dlg
        except Exception as e2:
            raise RuntimeError(f"鏃犳硶杩炴帴鍗庢嘲瀹㈡埛绔? {e2}")

def _do_buy(cmd):
    """鎵ц涔板叆"""
    code = cmd.get("code", "")
    price = cmd.get("price", 0)
    shares = cmd.get("shares", 0)
    
    try:
        app, dlg = _connect()
        # 鐐瑰嚮"涔板叆"鎸夐挳
        dlg.child_window(title="涔板叆", control_type="Button").click()
        time.sleep(0.5)
        
        # 杈撳叆鑲＄エ浠ｇ爜
        buy_dlg = app.window(title_re=".*涔板叆.*")
        buy_dlg.child_window(auto_id="stockCode").set_text(code)
        time.sleep(0.3)
        
        # 杈撳叆浠锋牸
        buy_dlg.child_window(auto_id="price").set_text(str(price))
        
        # 杈撳叆鏁伴噺
        buy_dlg.child_window(auto_id="amount").set_text(str(shares))
        
        # 鐐瑰嚮"涔板叆"纭
        buy_dlg.child_window(title="涔板叆", control_type="Button").click()
        time.sleep(0.5)
        
        # 纭寮圭獥
        confirm = app.window(title="鎻愮ず")
        if confirm.exists():
            confirm.child_window(title="纭畾", control_type="Button").click()
        
        return {"success": True, "code": code, "price": price, "shares": shares,
                "message": "涔板叆濮旀墭宸叉彁浜?}
    except Exception as e:
        return {"success": False, "error": f"涔板叆澶辫触: {e}"}

def _do_sell(cmd):
    """鎵ц鍗栧嚭"""
    code = cmd.get("code", "")
    price = cmd.get("price", 0)
    shares = cmd.get("shares", 0)
    
    try:
        app, dlg = _connect()
        dlg.child_window(title="鍗栧嚭", control_type="Button").click()
        time.sleep(0.5)
        
        sell_dlg = app.window(title_re=".*鍗栧嚭.*")
        sell_dlg.child_window(auto_id="stockCode").set_text(code)
        time.sleep(0.3)
        sell_dlg.child_window(auto_id="price").set_text(str(price))
        sell_dlg.child_window(auto_id="amount").set_text(str(shares))
        sell_dlg.child_window(title="鍗栧嚭", control_type="Button").click()
        time.sleep(0.5)
        
        confirm = app.window(title="鎻愮ず")
        if confirm.exists():
            confirm.child_window(title="纭畾", control_type="Button").click()
        
        return {"success": True, "code": code, "price": price, "shares": shares,
                "message": "鍗栧嚭濮旀墭宸叉彁浜?}
    except Exception as e:
        return {"success": False, "error": f"鍗栧嚭澶辫触: {e}"}

def _get_positions():
    """鑾峰彇鎸佷粨鍒楄〃"""
    try:
        app, dlg = _connect()
        # 鐐瑰嚮"鎸佷粨"鏍囩
        dlg.child_window(title="鎸佷粨", control_type="TabItem").click() if dlg.child_window(title="鎸佷粨", control_type="TabItem").exists() else None
        time.sleep(1)
        
        # 璇诲彇鎸佷粨琛ㄦ牸 (鍗庢嘲瀹㈡埛绔敤SysListView32)
        grid = dlg.child_window(class_name="SysListView32")
        rows = grid.item_count()
        positions = {}
        for i in range(rows):
            row_text = grid.get_item(i).get("text", "")
            if not row_text: continue
            # 灏濊瘯瑙ｆ瀽鎸佷粨鏁版嵁
            cells = row_text.split() if isinstance(row_text, str) else []
            if len(cells) >= 5:
                code = cells[0] if len(cells) > 0 else ""
                name = cells[1] if len(cells) > 1 else ""
                shares = int(cells[2]) if len(cells) > 2 and cells[2].isdigit() else 0
                cost = float(cells[3]) if len(cells) > 3 else 0
                cur = float(cells[4]) if len(cells) > 4 else 0
                if code and shares > 0:
                    positions[code] = {"name": name, "shares": shares, "cost": cost, "current_price": cur}
        
        return {"success": True, "positions": positions}
    except Exception as e:
        # pywinauto涓嶅彲鐢ㄦ椂杩斿洖绌?
        return {"success": True, "positions": {}, "note": f"pywinauto涓嶅彲鐢? {e}"}

def _get_balance():
    """鑾峰彇璐︽埛璧勯噾"""
    try:
        app, dlg = _connect()
        # 灏濊瘯璇诲彇浣欓鏍囩
        balance_text = dlg.child_window(title_re=".*鍙敤.*").window_text()
        return {"success": True, "available": 0, "raw": balance_text}
    except Exception:`r`n        return {"success": True, "available": 0, "note": "闇€鎵嬪姩閰嶇疆璧勯噾璇诲彇"}

def _get_today_trades():
    """鑾峰彇褰撴棩鎴愪氦"""
    try:
        app, dlg = _connect()
        dlg.child_window(title="褰撴棩鎴愪氦", control_type="TabItem").click() if dlg.child_window(title="褰撴棩鎴愪氦", control_type="TabItem").exists() else None
        time.sleep(1)
        grid = dlg.child_window(class_name="SysListView32")
        rows = grid.item_count()
        trades = []
        for i in range(rows):
            row_text = grid.get_item(i).get("text", "")
            if row_text: trades.append({"raw": row_text})
        return {"success": True, "trades": trades}
    except Exception:`r`n        return {"success": True, "trades": [], "note": "闇€pywinauto"}

def _do_cancel():
    """鎾ゅ崟"""
    return {"success": False, "error": "鎾ゅ崟鍔熻兘寰呭疄鐜?}

if __name__ == "__main__":
    main()
