from datetime import datetime,date

BIASES = {
  "fomo":"FOMO追高:看到大涨后冲动买入,未等回调确认",
  "revenge":"报复交易:亏损后急于翻本,违反策略规则",
  "greed":"贪婪不止盈:达到目标位后幻想更多,利润回吐",
  "fear":"恐惧止损:提前卖出盈利仓位,害怕回调",
  "holding":"死扛亏损:不愿承认错误,不止损等解套",
  "overtrade":"频繁交易:过度交易,被手续费吞噬利润",
}

def detect_biases(trades,positions):
  """trades: list of dicts. Returns list of detected biases."""
  found=[]
  for t in (trades or []):
    if t.get('action')=='buy' and t.get('reason','').startswith('up'):
      found.append('fomo')
    if t.get('action')=='sell' and t.get('pnl',0)<0 and t.get('hold_days',99)<2:
      found.append('revenge')
  for p in (positions or []):
    if p.get('pnl_pct',0)<-8:
      found.append('holding')
  return list(set(found))

def generate_review(trades,positions,market_regime='range'):
  biases=detect_biases(trades,positions)
  total_trades=len(trades or [])
  wins=sum(1 for t in (trades or []) if t.get('pnl',0)>0)
  losses=sum(1 for t in (trades or []) if t.get('pnl',0)<=0)
  wr=wins/total_trades*100 if total_trades>0 else 0
  total_pnl=sum(t.get('pnl',0) for t in (trades or []))
  return {
    "date":date.today().isoformat(),
    "market_regime":market_regime,
    "summary":{"trades":total_trades,"wins":wins,"losses":losses,"win_rate":round(wr,1),"total_pnl":round(total_pnl,2)},
    "biases":[BIASES[b] for b in biases],
    "positions_health":len([p for p in (positions or []) if p.get("pnl_pct",0)<-5])
  }

SCENARIOS = {
  "up":"高开>0.5%:不追,等回踩确认。如直接破前高可轻仓试多",
  "flat":"平开:按计划正常操作,关注关键位突破情况",
  "down":"低开>0.5%:减少买入,检查持仓止损。急跌不抄底",
}

def next_day_prep(positions,market_regime='range'):
  return {
    "date":date.today().isoformat(),
    "scenarios":SCENARIOS,
    "checklist":["检查持仓止损位","确认今日候选股","查看外围市场","设定今日目标"],
    "positions_to_watch":[p.get("code","") for p in (positions or []) if p.get("pnl_pct",0)<-3]
  }

