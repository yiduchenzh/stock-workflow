import json
import urllib.request
import subprocess

# 用 hermes CLI 拿真实技能清单（若可用）
out = subprocess.run(["powershell", "-NoProfile", "-Command",
                      "Get-ChildItem -Path 'C:\\Users\\User871619\\AppData\\Roaming\\cn.org.hermesagent.desktop\\runtime\\hermes-home\\skills' -Recurse -Filter SKILL.md | Measure-Object | Select-Object -ExpandProperty Count"],
                     capture_output=True, text=True, encoding="utf-8", errors="ignore")
print("磁盘 SKILL.md 总数 =", (out.stdout or "").strip())

# 逐个技能 frontmatter 解析（yaml），确认没有解析失败
import yaml
from pathlib import Path
SK = Path(r"C:\Users\User871619\AppData\Roaming\cn.org.hermesagent.desktop\runtime\hermes-home\skills")
bad = []
names = []
for f in SK.rglob("SKILL.md"):
    if ".bak-" in str(f) or ".archive" in str(f):
        continue
    t = f.read_text(encoding="utf-8", errors="ignore")
    if not t.startswith("---"):
        bad.append((f, "无 frontmatter"))
        continue
    fm = t.split("---", 2)[1]
    try:
        m = yaml.safe_load(fm) or {}
        names.append(m.get("name") or f.parent.name)
    except Exception as e:
        bad.append((f, "YAML错误: %s" % str(e)[:90]))
print("可解析技能数 =", len(names))
print("解析失败 =", len(bad))
for f, why in bad[:10]:
    print("   ❌", str(f).replace(str(SK), ""), "|", why)

edited = ["a-share-backtest", "a-share-trading-system-design", "a-share-web-data-architecture",
          "limitup-prevclose-system", "limitup-prevclose-trading", "mainrise-factor-signature",
          "real-time-financial-dashboard", "hikyuu-reference"]
print("\n本次改过的 8 个技能是否仍在清单里:")
for e in edited:
    print("   %-34s %s" % (e, "OK" if e in names else "❌ 丢失"))
