from datetime import datetime
def gen(t):
 bp=float(t.get('buy_price',0));sp=float(t.get('sell_price',0));q=float(t.get('shares',0))
 pnl=(sp-bp)*q;pct=round((sp/bp-1)*100,1)if bp else 0
 clr='green'if pnl>=0 else 'red';sg='+'if pnl>=0 else ''
 n=t.get('name','');c=t.get('code','')
 tm=datetime.now().strftime('%Y-%m-%d %H:%M')
 return '<html><body>'+n+' '+c+' '+sg+str(pct)+'%<br>P&L:'+sg+str(pnl)+'</body></html>'
