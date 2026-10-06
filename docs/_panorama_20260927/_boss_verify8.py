import os
import stat
import subprocess

p = r"D:\Aurora"
st = os.stat(p, follow_symlinks=False)
print("st_file_attributes =", st.st_file_attributes)
print("FILE_ATTRIBUTE_REPARSE_POINT =", stat.FILE_ATTRIBUTE_REPARSE_POINT,
      "| 是重解析点:", bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT))
out = subprocess.run(["cmd", "/c", "dir", "D:\\", "/AL"], capture_output=True, text=True,
                     encoding="gbk", errors="ignore").stdout
print("\n=== dir /AL (重解析点清单) ===")
for l in out.splitlines():
    if "Aurora" in l or "<" in l and "JUNCTION" in l.upper():
        print("  ", l.strip()[:160])
print("\n=== cmd dir 里 Aurora 行 ===")
out2 = subprocess.run(["cmd", "/c", "dir", "D:\\"], capture_output=True, text=True,
                      encoding="gbk", errors="ignore").stdout
for l in out2.splitlines():
    if "Aurora" in l:
        print("  ", l.strip()[:160])
print("\n=== 实际内容抽样 ===")
for name in ("weekly_evolution.py", "core", "strategies"):
    q = os.path.join(p, name)
    print("  %-22s exists=%s" % (name, os.path.exists(q)))
