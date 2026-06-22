
"""Aurora Trading Desktop — PySide6 GUI"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit, QTableWidget, QTableWidgetItem, QHBoxLayout, QHeaderView, QMessageBox, QGroupBox, QFrame, QSplitter)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

STYLE = """
QMainWindow { background-color: #1e1e2e; color: #cdd6f4; }
QTabWidget::pane { border: 1px solid #45475a; background: #181825; }
QTabBar::tab { background: #313244; color: #cdd6f4; padding: 8px 16px; margin: 2px; border-radius: 4px; }
QTabBar::tab:selected { background: #cba6f7; color: #1e1e2e; font-weight: bold; }
QTableWidget { background: #181825; color: #cdd6f4; gridline-color: #313244; border: 1px solid #45475a; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background: #313244; color: #cdd6f4; padding: 4px; border: none; }
QPushButton { background: #cba6f7; color: #1e1e2e; padding: 8px 16px; border-radius: 6px; font-weight: bold; }
QPushButton:hover { background: #f5c2e7; }
QPushButton:pressed { background: #b4befe; }
QGroupBox { color: #cba6f7; font-weight: bold; border: 2px solid #cba6f7; border-radius: 8px; margin-top: 12px; padding-top: 16px; background: #181825; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QTextEdit { background: #181825; color: #cdd6f4; border: 1px solid #45475a; border-radius: 4px; }
QLabel { color: #cdd6f4; }
"""

class DashboardPage(QWidget):
    def __init__(self): super().__init__(); self._build()
    def _build(self):
        l = QVBoxLayout(self)
        g = QGroupBox("市场体检"); gl = QVBoxLayout(g)
        self.info = QLabel("等待数据加载..."); self.info.setFont(QFont("Microsoft YaHei", 12))
        gl.addWidget(self.info)
        btn = QPushButton("刷新市场快照"); btn.clicked.connect(self._refresh); gl.addWidget(btn)
        l.addWidget(g); l.addStretch()

    def _refresh(self):
        try:
            from data.sources import get_index_snapshot, get_sector_ranking
            idx = get_index_snapshot(["000001","399001","399006"])
            sec = get_sector_ranking(5)
            lines = ["=== 指数快照 ==="]
            for k,v in idx.items():
                c = v.get("change_pct",0); arrow = "↑" if c>0 else "↓"
                lines.append(f"{v.get('name',k)}: {v.get('price',0):.2f} {arrow}{abs(c):.2f}%")
            lines.append("\n=== 热点板块 TOP5 ===")
            for s in sec[:5]:
                lines.append(f"  {s['name']}: {s['change_pct']:+.2f}% (涨{s['up']}/跌{s['down']})")
            self.info.setText("\n".join(lines))
        except Exception as e:
            self.info.setText(f"加载失败: {e}")

class ScreeningPage(QWidget):
    def __init__(self): super().__init__(); self._build()
    def _build(self):
        l = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["代码","名称","价格","涨跌%","PE","量比"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(QLabel("选股结果"))
        btn = QPushButton("执行选股"); btn.clicked.connect(self._screen); l.addWidget(btn)
        l.addWidget(self.table)

    def _screen(self):
        try:
            from screening.cascade import cascade_screen
            import yaml
            cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
            candidates = cascade_screen(cfg)
            self.table.setRowCount(len(candidates))
            for i, c in enumerate(candidates):
                for j, k in enumerate(["code","name","price","change_pct","pe","vol_ratio"]):
                    item = QTableWidgetItem(str(c.get(k,"")))
                    if k == "change_pct":
                        v = c.get(k,0)
                        item.setForeground(QColor("#f38ba8" if v>=0 else "#a6e3a1"))
                    self.table.setItem(i, j, item)
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

class TradingPage(QWidget):
    def __init__(self): super().__init__(); self._build()
    def _build(self):
        l = QVBoxLayout(self)
        g = QGroupBox("模拟账户"); gl = QVBoxLayout(g)
        self.acct_label = QLabel("未加载"); gl.addWidget(self.acct_label)
        btn = QPushButton("刷新账户"); btn.clicked.connect(self._refresh); gl.addWidget(btn)
        l.addWidget(g)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["代码","持仓","成本","现价","盈亏%"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addWidget(self.table)
        l.addStretch()

    def _refresh(self):
        try:
            import json
            d = json.loads(open("data/sim_state.json").read())
            self.acct_label.setText(f"现金: {d.get('cash',0):,.0f} | 总资产: {d.get('total',0):,.0f}")
            pos = d.get("positions", {})
            self.table.setRowCount(len(pos))
            for i, (code, p) in enumerate(pos.items()):
                self.table.setItem(i, 0, QTableWidgetItem(code))
                self.table.setItem(i, 1, QTableWidgetItem(str(p.get("shares",0))))
                self.table.setItem(i, 2, QTableWidgetItem(f"{p.get('avg_cost',0):.2f}"))
                cur = p.get("current_price", p.get("avg_cost", 0))
                self.table.setItem(i, 3, QTableWidgetItem(f"{cur:.2f}"))
                pnl = (cur - p.get("avg_cost",cur)) / p.get("avg_cost",cur) * 100 if p.get("avg_cost",0) > 0 else 0
                item = QTableWidgetItem(f"{pnl:+.2f}%")
                item.setForeground(QColor("#f38ba8" if pnl>=0 else "#a6e3a1"))
                self.table.setItem(i, 4, item)
        except Exception as e:
            self.acct_label.setText(f"加载失败: {e}")

class ReviewPage(QWidget):
    def __init__(self): super().__init__(); self._build()
    def _build(self):
        l = QVBoxLayout(self)
        self.text = QTextEdit(); self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 10))
        l.addWidget(QLabel("交易复盘"))
        btn = QPushButton("生成复盘报告"); btn.clicked.connect(self._review); l.addWidget(btn)
        l.addWidget(self.text)

    def _review(self):
        try:
            import json
            trades = json.loads(open("data/sim_trades.json").read()) if os.path.exists("data/sim_trades.json") else []
            buys = [t for t in trades if t.get("action")=="buy"]
            sells = [t for t in trades if t.get("action")=="sell"]
            wins = [t for t in sells if t.get("pnl",0) > 0]
            lines = [f"=== 交易复盘 ===", f"总交易: {len(sells)}笔", f"盈利: {len(wins)}笔",
                     f"胜率: {len(wins)/len(sells)*100:.1f}%" if sells else "胜率: N/A",
                     f"总PnL: {sum(t.get('pnl',0) for t in sells):+,.0f}"]
            self.text.setText("\n".join(lines))
        except Exception as e:
            self.text.setText(f"加载失败: {e}")

class SettingsPage(QWidget):
    def __init__(self): super().__init__(); self._build()
    def _build(self):
        l = QVBoxLayout(self)
        self.text = QTextEdit()
        try:
            self.text.setText(open("config.yaml", encoding="utf-8").read())
        except: pass
        l.addWidget(QLabel("配置文件 (config.yaml)"))
        l.addWidget(self.text)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aurora Trading v1.0")
        self.setGeometry(100, 100, 1280, 800)
        self.tabs = QTabWidget()
        self.tabs.addTab(DashboardPage(), "📊 市场体检")
        self.tabs.addTab(ScreeningPage(), "🔍 选股")
        self.tabs.addTab(TradingPage(), "💼 交易持仓")
        self.tabs.addTab(ReviewPage(), "📋 复盘")
        self.tabs.addTab(SettingsPage(), "⚙️ 设置")
        self.setCentralWidget(self.tabs)

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
