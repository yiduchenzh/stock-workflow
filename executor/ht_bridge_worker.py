"""华泰桥接Worker — 32位Python操控xiadan.exe (subprocess JSON通信)"""
import json, sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [HT] %(message)s")
logger = logging.getLogger("ht_worker")

def main():
    """接收JSON指令, 操控华泰客户端, 返回JSON结果"""
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No command"}))
        return
    
    try:
        cmd = json.loads(sys.argv[1])
    except:
        print(json.dumps({"success": False, "error": "Invalid JSON"}))
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
            result = _do_cancel(cmd)
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}
    except Exception as e:
        result = {"success": False, "error": str(e)}
    
    print(json.dumps(result, ensure_ascii=False, default=str))

def _connect():
    """连接华泰客户端窗口"""
    try:
        from pywinauto import Application
        # 尝试连接已运行的xiadan.exe
        app = Application(backend="win32").connect(path=r"C:\htzqzyb3\xiadan.exe")
        dlg = app.window(class_name="#32770")  # 华泰对话框
        if not dlg.exists():
            # 尝试连接主窗口
            dlg = app.top_window()
        return app, dlg
    except Exception as e:
        logger.error(f"连接失败: {e}")
        # 尝试启动客户端
        try:
            import subprocess
            subprocess.Popen([r"C:\htzqzyb3\xiadan.exe"])
            time.sleep(5)
            from pywinauto import Application
            app = Application(backend="win32").connect(path=r"C:\htzqzyb3\xiadan.exe")
            dlg = app.top_window()
            return app, dlg
        except Exception as e2:
            raise RuntimeError(f"无法连接华泰客户端: {e2}")

def _do_buy(cmd):
    """执行买入"""
    code = cmd.get("code", "")
    price = cmd.get("price", 0)
    shares = cmd.get("shares", 0)
    
    try:
        app, dlg = _connect()
        # 点击"买入"按钮
        dlg.child_window(title="买入", control_type="Button").click()
        time.sleep(0.5)
        
        # 输入股票代码
        buy_dlg = app.window(title_re=".*买入.*")
        buy_dlg.child_window(auto_id="stockCode").set_text(code)
        time.sleep(0.3)
        
        # 输入价格
        buy_dlg.child_window(auto_id="price").set_text(str(price))
        
        # 输入数量
        buy_dlg.child_window(auto_id="amount").set_text(str(shares))
        
        # 点击"买入"确认
        buy_dlg.child_window(title="买入", control_type="Button").click()
        time.sleep(0.5)
        
        # 确认弹窗
        confirm = app.window(title="提示")
        if confirm.exists():
            confirm.child_window(title="确定", control_type="Button").click()
        
        return {"success": True, "code": code, "price": price, "shares": shares,
                "message": "买入委托已提交"}
    except Exception as e:
        return {"success": False, "error": f"买入失败: {e}"}

def _do_sell(cmd):
    """执行卖出"""
    code = cmd.get("code", "")
    price = cmd.get("price", 0)
    shares = cmd.get("shares", 0)
    
    try:
        app, dlg = _connect()
        dlg.child_window(title="卖出", control_type="Button").click()
        time.sleep(0.5)
        
        sell_dlg = app.window(title_re=".*卖出.*")
        sell_dlg.child_window(auto_id="stockCode").set_text(code)
        time.sleep(0.3)
        sell_dlg.child_window(auto_id="price").set_text(str(price))
        sell_dlg.child_window(auto_id="amount").set_text(str(shares))
        sell_dlg.child_window(title="卖出", control_type="Button").click()
        time.sleep(0.5)
        
        confirm = app.window(title="提示")
        if confirm.exists():
            confirm.child_window(title="确定", control_type="Button").click()
        
        return {"success": True, "code": code, "price": price, "shares": shares,
                "message": "卖出委托已提交"}
    except Exception as e:
        return {"success": False, "error": f"卖出失败: {e}"}

def _get_positions():
    """获取持仓列表"""
    try:
        app, dlg = _connect()
        # 点击"持仓"标签
        dlg.child_window(title="持仓", control_type="TabItem").click() if dlg.child_window(title="持仓", control_type="TabItem").exists() else None
        time.sleep(1)
        
        # 读取持仓表格 (华泰客户端用SysListView32)
        grid = dlg.child_window(class_name="SysListView32")
        rows = grid.item_count()
        positions = {}
        for i in range(rows):
            row_text = grid.get_item(i).get("text", "")
            if not row_text: continue
            # 尝试解析持仓数据
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
        # pywinauto不可用时返回空
        return {"success": True, "positions": {}, "note": f"pywinauto不可用: {e}"}

def _get_balance():
    """获取账户资金"""
    try:
        app, dlg = _connect()
        # 尝试读取余额标签
        balance_text = dlg.child_window(title_re=".*可用.*").window_text()
        return {"success": True, "available": 0, "raw": balance_text}
    except:
        return {"success": True, "available": 0, "note": "需手动配置资金读取"}

def _get_today_trades():
    """获取当日成交"""
    try:
        app, dlg = _connect()
        dlg.child_window(title="当日成交", control_type="TabItem").click() if dlg.child_window(title="当日成交", control_type="TabItem").exists() else None
        time.sleep(1)
        grid = dlg.child_window(class_name="SysListView32")
        rows = grid.item_count()
        trades = []
        for i in range(rows):
            row_text = grid.get_item(i).get("text", "")
            if row_text: trades.append({"raw": row_text})
        return {"success": True, "trades": trades}
    except:
        return {"success": True, "trades": [], "note": "需pywinauto"}

def _do_cancel(cmd):
    """撤单"""
    return {"success": False, "error": "撤单功能待实现"}

if __name__ == "__main__":
    main()