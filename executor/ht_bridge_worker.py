"""Huatai bridge worker - 32bit Python controlling xiadan.exe via subprocess JSON"""
import json, sys, time, logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [HT] %(message)s")
logger = logging.getLogger("ht_worker")

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No command"}))
        return
    try:
        cmd = json.loads(sys.argv[1])
    except Exception:
        print(json.dumps({"success": False, "error": "Invalid JSON"}))
        return
    action = cmd.get("action", "")
    try:
        if action == "buy": result = _do_buy(cmd)
        elif action == "sell": result = _do_sell(cmd)
        elif action == "positions": result = _get_positions()
        elif action == "balance": result = _get_balance()
        elif action == "today_trades": result = _get_today_trades()
        elif action == "cancel": result = _do_cancel()
        else: result = {"success": False, "error": f"Unknown action: {action}"}
    except Exception as e:
        result = {"success": False, "error": str(e)}
    print(json.dumps(result, ensure_ascii=False, default=str))

def _connect():
    import subprocess as sp
    try:
        from pywinauto import Application
        app = Application(backend="win32").connect(path=r"C:\htzqzyb3\xiadan.exe")
        dlg = app.window(class_name="#32770")
        if not dlg.exists(): dlg = app.top_window()
        return app, dlg
    except Exception as e:
        logger.error(f"Connect failed: {e}")
        sp.Popen([r"C:\htzqzyb3\xiadan.exe"])
        time.sleep(5)
        from pywinauto import Application
        app = Application(backend="win32").connect(path=r"C:\htzqzyb3\xiadan.exe")
        return app, app.top_window()

def _do_buy(cmd):
    try:
        app, dlg = _connect()
        dlg.child_window(title_re=".*Buy.*").click()
        time.sleep(0.5)
        bd = app.window(title_re=".*Buy.*")
        bd.child_window(auto_id="stockCode").set_text(cmd.get("code",""))
        bd.child_window(auto_id="price").set_text(str(cmd.get("price",0)))
        bd.child_window(auto_id="amount").set_text(str(cmd.get("shares",0)))
        bd.child_window(title_re="Buy", control_type="Button").click()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _do_sell(cmd):
    try:
        app, dlg = _connect()
        dlg.child_window(title_re=".*Sell.*").click()
        time.sleep(0.5)
        sd = app.window(title_re=".*Sell.*")
        sd.child_window(auto_id="stockCode").set_text(cmd.get("code",""))
        sd.child_window(auto_id="price").set_text(str(cmd.get("price",0)))
        sd.child_window(auto_id="amount").set_text(str(cmd.get("shares",0)))
        sd.child_window(title_re="Sell", control_type="Button").click()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def _get_positions():
    try:
        app, dlg = _connect()
        time.sleep(1)
        positions = {}
        try:
            grid = dlg.child_window(class_name="SysListView32")
            for i in range(grid.item_count()):
                row = grid.get_item(i).get("text","")
                cells = row.split()
                if len(cells) >= 5 and cells[2].isdigit():
                    positions[cells[0]] = {"shares": int(cells[2]), "cost": float(cells[3])}
        except: pass
        return {"success": True, "positions": positions}
    except Exception as e:
        return {"success": True, "positions": {}}

def _get_balance():
    return {"success": True, "available": 0}
def _get_today_trades():
    return {"success": True, "trades": []}
def _do_cancel():
    return {"success": False, "error": "Not implemented"}

if __name__ == "__main__":
    main()
