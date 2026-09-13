#!/usr/bin/env python3
"""Generate clean frontend HTML for Aurora AI Trading Terminal"
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
def main():
  HTML = """''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Aurora AI Trading Terminal</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#0d1117;color:#c9d1d9;overflow:hidden}
.hdr{display:flex;align-items:center;justify-content:space-between;padding:8px 20px;background:#161b22;border-bottom:1px solid #30363d}
.logo{font-size:18px;font-weight:700;background:linear-gradient(135deg,#58a6ff,#f0883e);background-clip:text}
.st{display:flex;gap:16px;font-size:12px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:4px}
.dot.g{background:#3fb950}.dot.r{background:#f85149}
.gd{display:grid;grid-template-columns:280px 1fr 300px;gap:10px;padding:10px;height:calc(100vh-44px)}
.pn{background:#161b22;border:1px solid #30363d;border-radius:8px;display:flex;flex-direction:column}
.ph{padding:8px 12px;font-size:11px;font-weight:600;color:#8b949e;border-bottom:1px solid #21262d}
.pb{padding:8px 12px;flex:1;overflow-y:auto}
.gv{text-align:center;padding:10px}
.gv-n{font-size:48px;font-weight:700}
.gv-b{margin:8px auto;height:6px;width:80%;background:#21262d;border-radius:3px}
.gv-f{height:100%;border-radius:3px;transition:width 1s}
.ix{font-size:12px}
.ixr{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1c2128}
.sg{background:#1c2128;border-radius:6px;padding:8px;margin-bottom:5px;font-size:12px}
.sgt{display:flex;justify-content:space-between;margin-bottom:3px}
.tgn{display:inline-block;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600}
.tg-g{background:#0d4429;color:#3fb950}.tg-r{background:#44200d;color:#f85149}.tg-b{background:#1f3a5f;color:#58a6ff}
.cb{height:130px;overflow-y:auto;margin-bottom:5px}
.msg{margin:4px 0;padding:5px 8px;border-radius:6px;font-size:12px}
.msg.u{background:#1f2a3f;margin-left:20px}.msg.a{background:#1c2128}
.ml{font-size:10px;color:#484f58}
.ir{display:flex;gap:4px}
.ir input{flex:1;background:#0d1117;border:1px solid #30363d;border-radius:4px;padding:5px 8px;color:#c9d1d9;font-size:12px;outline:none}
.ir input:focus{border-color:#58a6ff}
.ir button{background:#238636;border:none;border-radius:4px;padding:5px 10px;color:#fff;font-size:11px;cursor:pointer}
.qs{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:5px}
.qs button{background:#21262d;border:1px solid #30363d;border-radius:4px;padding:2px 6px;color:#c9d1d9;font-size:10px;cursor:pointer}
.stb{display:flex;justify-content:space-between;padding:3px 0;font-size:11px}
.g2{color:#3fb950}.r2{color:#f85149}.y2{color:#d29922}
</style></head><body>
<div class=hdr><div class=logo>Aurora AI</div><div class=st><span><span id=sd class=dot></span><span id=st>Connecting</span></span></div></div>
<div class=gd>
<div class=pn><div class=ph>Market</div><div class=pb>
<div class=gv><div id=mn class=gv-n style=color:#8b949e>--</div><div id=mr style=font-size:12px;color:#8b949e>--</div><div class=gv-b><div id=mf class=gv-f style=width:0%></div></div></div>
<div id=ix class=ix></div><div id=pl style=margin-top:8px></div></div></div>
<div class=pn><div class=ph>Live</div><div class=pb id=lf><div style=text-align:center;padding:30px;color:#484f58>Loading</div></div></div>
<div class=pn><div class=ph>AI Coach</div><div class=pb>
<div class=cb id=cm><div class="msg a"><div class=ml>AI</div>Welcome</div></div>
<div class=qs><button onclick=q("wave_point")>wave</button><button onclick=q("缠论")>chan</button><button onclick=q("止损")>stop</button><button onclick=q("仓位")>pos</button><button onclick=q("大盘")>mkt</button></div>
<div class=ir><input id=inp placeholder=Ask><button onclick=s()>Send</button></div>
<div id=pr style=margin-top:6px></div><div id=rv style=margin-top:6px></div></div></div></div>
<script>
var mn=document.getElementById("mn"),mr=document.getElementById("mr"),mf=document.getElementById("mf")
var ix=document.getElementById("ix"),lf=document.getElementById("lf"),cm=document.getElementById("cm")
function sv(v){v=v||0;var c=v>=70?"#3fb950":v>=40?"#d29922":"#f85149";mn.textContent=v;mn.style.color=c;mf.style.background=c;mf.style.width=Math.min(v,100)+"%";mr.textContent=""}
async function init(){try{var r=await(await fetch("/api/market/overview")).json();sv(r.market_score);mr.textContent=(r.market_regime||"-").toUpperCase();ix.innerHTML="";if(r.indices){for(var k in r.indices){ix.innerHTML+="<div class=ixr><span>"+k+"</span><span style=color:"+(r.indices[k].indexOf("+")>=0?"#3fb950":"#f85149")+">"+r.indices[k]+"</span></div>"}}if(r.plans&&r.plans.length){ix.innerHTML+="<div style=color:#8b949e;font-size:11px;margin:6px 0 3px>Plans</div>";r.plans.forEach(function(p){ix.innerHTML+="<div style=font-size:11px;padding:2px 0>"+p.target+": "+p.reason+"</div>"})}}catch(e){console.error(e)}}
async function ls(){try{var s=await(await fetch("/api/signals/latest")).json();lf.innerHTML="";if(s.signals&&s.signals.length){s.signals.slice(-15).reverse().forEach(function(sg){var a=sg.action||"enter";var c=sg.score||50;var tc=a==="buy"?"tg-g":a==="sell"?"tg-r":"tg-b";var cc=c>=70?"g2":c>=40?"y2":"r2";lf.innerHTML+="<div class=sg><div class=sgt><span><span class=tgn "+tc+">"+(a||"").toUpperCase()+"</span><span style=font-weight:600> "+(sg.name||"")+"</span><span style=color:#484f58;font-size:10px> "+(sg.code||"")+"</span></span><span style=font-size:13px;font-weight:700;class="+cc+">"+c+"</span></div><div style=color:#8b949e;font-size:11px>"+(sg.strategy||"")+"</div></div>"})}else{lf.innerHTML="<div style=text-align:center;padding:30px;color:#484f58>No signals</div>"}}catch(e){console.error(e)}}
function am(r,t){var d=document.createElement("div");d.className="msg "+(r==="user"?"u":"a");d.innerHTML="<div class=ml>"+(r==="user"?"You":"AI")+"</div>"+t;cm.appendChild(d);d.scrollIntoView({behavior:"smooth"})}
function s(){var i=document.getElementById("inp");var m=i.value.trim();if(!m)return;i.value="";am("user",m);if(window.ws&&window.ws.readyState===1){ws.send(JSON.stringify({question:m}))}else{am("ai","WS not connected")}}
function q(t){document.getElementById("inp").value=t;s()}
function cws(){try{ws=new WebSocket("ws://"+location.host+"/api/ws/chat");ws.onopen=function(){document.getElementById("sd").className="dot g";document.getElementById("st").textContent="Connected"};ws.onmessage=function(e){try{var d=JSON.parse(e.data);if(d.type==="connected"||d.type==="answer"){am("ai",d.answer||d.msg||"")}}catch(e){}};ws.onclose=function(){document.getElementById("sd").className="dot r";document.getElementById("st").textContent="Reconnecting";setTimeout(cws,3000)}}catch(e){console.error(e)}}
async function lp(){try{var d=await(await fetch("/api/profile/quiz")).json();var h="<div style=color:#3fb950;font-size:11px;margin-bottom:4px>Trader Quiz</div>";d.questions.forEach(function(q,i){h+="<div style=font-size:10px;margin:2px 0>"+q.q+"</div>";q.opts.forEach(function(o,j){h+="<label style=font-size:9px;cursor:pointer;margin-right:3px><input type=radio name=p"+i+" value="+j+(j==1?" checked":"")+"> "+o+"</label>"})});h+="<button onclick=sp() style=background:#238636;border:none;border-radius:4px;padding:3px 8px;color:#fff;font-size:10px;margin:4px 0;cursor:pointer>Profile</button><div id=prr></div>";document.getElementById("pr").innerHTML=h}catch(e){}}
async function sp(){var a=[];for(var i=0;i<5;i++){var e=document.querySelector("input[name=p"+i+"]:checked");a.push(e?parseInt(e.value):1)}try{var r=await(await fetch("/api/profile/result?a0="+a[0]+"&a1="+a[1]+"&a2="+a[2]+"&a3="+a[3]+"&a4="+a[4])).json();document.getElementById("prr").innerHTML="<b>"+r.name+"</b>: "+r.desc}catch(e){}}
async function lr(){try{var r=await(await fetch("/api/review/today")).json();var s=r.review.summary;var h="<div style=color:#d29922;font-size:11px;margin-bottom:4px>Review</div>";h+="<div class=stb><span>Trades</span><span>"+s.trades+"</span></div><div class=stb><span>WR</span><span>"+s.win_rate+"%</span></div><div class=stb><span>PnL</span><span class="+(s.total_pnl>=0?"g2":"r2")+">"+(s.total_pnl>=0?"+":"")+s.total_pnl+"</span></div>";document.getElementById("rv").innerHTML=h}catch(e){}}
init();ls();cws();setTimeout(function(){lp();lr()},2000)
</script></body></html>
"""''
  path = os.path.join(HERE, "static", "live_page.html")
  with open(path, "w", encoding="utf-8") as f:
    f.write(HTML)
  print(f"Generated {path} ({len(HTML)} bytes)")
if __name__ == "__main__":
  main()