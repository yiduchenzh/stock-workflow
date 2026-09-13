from datetime import datetime
QUESTIONS=[
  {"q":"Your holding period?","opts":["1-3d","3-10d","10-30d","30d+"]},
  {"q":"Risk tolerance?","opts":["Low","Med","High","Agg"]},
  {"q":"Screen time?","opts":["Close","AMPM","4h","All"]},
  {"q":"Capital?","opts":["<10k","10-100k","100-500k","500k+"]},
  {"q":"Strategy?","opts":["Trend","Swing","Momentum","Value"]},
]
TYPES={
  "swing":{"name":"Swing","desc":"3-10d","strategies":["wave_point"]},
  "momentum":{"name":"Momentum","desc":"1-3d","strategies":["momentum_breakout"]},
  "trend":{"name":"Trend","desc":"10-30d","strategies":["wave_point","sector_rotation"]},
  "newbie":{"name":"Newbie","desc":"3-10d","strategies":["mean_reversion"]},
  "news":{"name":"News","desc":"1-3d","strategies":["momentum_breakout","naked_k"]},
  "value":{"name":"Value","desc":"30d+","strategies":["mean_reversion"]},
}
def classify(answers):
  scores={t:0 for t in TYPES}
  if len(answers)<4: return "newbie"
  if answers[0]==0:scores["momentum"]+=2;scores["news"]+=2
  elif answers[0]==1:scores["swing"]+=2;scores["newbie"]+=2
  elif answers[0]==2:scores["trend"]+=3
  else:scores["value"]+=3
  if answers[1]==0:scores["value"]+=2;scores["newbie"]+=2
  elif answers[1]==1:scores["swing"]+=2;scores["trend"]+=2
  elif answers[1]==2:scores["momentum"]+=3
  else:scores["news"]+=3
  if answers[2]==0:scores["value"]+=2
  elif answers[2]==1:scores["swing"]+=3
  elif answers[2]==2:scores["momentum"]+=2;scores["news"]+=2
  else:scores["momentum"]+=3;scores["news"]+=2
  if answers[3]==0:scores["newbie"]+=3
  elif answers[3]==1:scores["swing"]+=2
  elif answers[3]==2:scores["trend"]+=2;scores["momentum"]+=1
  else:scores["value"]+=2;scores["trend"]+=2
  if len(answers)>=5:
    if answers[4]==0:scores["trend"]+=3
    elif answers[4]==1:scores["swing"]+=3
    elif answers[4]==2:scores["momentum"]+=3;scores["news"]+=2
    else:scores["value"]+=3
  return max(scores,key=scores.get)
def get_profile(answers):
  tk=classify(answers);t=TYPES[tk]
  return {"type_key":tk,"name":t["name"],"desc":t["desc"],"strategies":t["strategies"]}
