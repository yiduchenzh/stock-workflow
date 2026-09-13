"""users module"""
import json,os,time,hashlib
from pathlib import Path
DATA=Path(__file__).parent/"data"/"users"
TIERS={"free":{"name":"free","price":0,"qpd":3,"ws_qpd":3,"delay":600,"signals":False},"live":{"name":"live","price":29,"qpd":50,"ws_qpd":50,"delay":0,"signals":True},"vip":{"name":"vip","price":99,"qpd":-1,"ws_qpd":-1,"delay":0,"signals":True},"annual":{"name":"annual","price":399,"qpd":-1,"ws_qpd":-1,"delay":0,"signals":True}}
INVITE_REWARD={"days":3,"tier":"live"}
class User:
 def __init__(s,uid="",tier="free",expires=0,invited_by=""):
  s.uid=uid or hashlib.md5(os.urandom(16)).hexdigest()[:12]
  s.tier=tier;s.expires=expires;s.invited_by=invited_by
  s.usage={"api":0,"ws":0,"date":""};s.invite_code=s.uid[:8];s.invites_used=0
 def can_use(s,ws=False):
  s._reset_daily()
  if s.expires>0 and time.time()>s.expires:s.tier="free"
  t=TIERS.get(s.tier,TIERS["free"])
  if s.tier=="free":return False
  k="ws" if ws else "api";l=t["ws_qpd" if ws else "qpd"]
  return True if l==-1 else s.usage[k]<l
 def use(s,ws=False):
  s._reset_daily()
  if s.can_use(ws):k="ws" if ws else "api";s.usage[k]+=1;_save(s);return True
  return False
 def _reset_daily(s):
  t=time.strftime("%Y-%m-%d")
  if s.usage["date"]!=t:s.usage={"api":0,"ws":0,"date":t}
 def to_dict(s):
  return {"uid":s.uid,"tier":s.tier,"expires":s.expires,"invited_by":s.invited_by,"usage":s.usage,"invite_code":s.invite_code,"invites_used":s.invites_used}
def _path_uid(uid):return DATA/f"{uid}.json"
def _save(u):
 DATA.mkdir(parents=True,exist_ok=True)
 _path_uid(u.uid).write_text(json.dumps(u.to_dict(),ensure_ascii=False))
 return u
def load(uid):
 p=_path_uid(uid)
 if p.exists():
  d=json.loads(p.read_text());u=User(d["uid"],d["tier"],d["expires"],d.get("invited_by",""))
  u.usage=d.get("usage",{"api":0,"ws":0,"date":""});u.invite_code=d.get("invite_code",uid[:8]);u.invites_used=d.get("invites_used",0)
  return u
 return None
def get_or_create(uid=""):
 u=load(uid) if uid else None
 return u if u else _save(User(uid))
def upgrade(uid,tier,days=30):
 u=get_or_create(uid);u.tier=tier;u.expires=time.time()+days*86400;_save(u);return u
