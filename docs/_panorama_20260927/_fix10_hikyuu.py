import io
import re
from pathlib import Path

P = Path(r"C:\Users\User871619\AppData\Roaming\cn.org.hermesagent.desktop\runtime\hermes-home\skills\stock-trading\hikyuu-reference\SKILL.md")
txt = P.read_text(encoding="utf-8")
lines = txt.splitlines(keepends=True)

NEW_DESC = ("description: hikyuu 开源量化平台(fasiondog, C++核心+Python绑定)架构参考。"
            "2026-09-27 实测——本机没有 hikyuu 源码克隆(D:\\hikyuu_research 不存在, D 盘无任何 hikyuu 目录), "
            "现存唯一产物是 hunter-v2\\docs\\hikyuu-调研报告.md, 结论=方法论富矿但不建议移植本体(仅借鉴 4 模块 + IC 加权); "
            "因此本文的目录结构仅作架构对照, 不要当成可 ls 的本地路径, 需要源码请先 clone。"
            "触发场景 — 用户要求研究 hikyuu 任意模块、对比架构、借鉴数据层/驱动/复权/板块设计, 或回答 hikyuu 如何做某功能。\n")

hit_desc = False
if "description:" in lines[2]:
    lines[2] = NEW_DESC
    hit_desc = True

txt = "".join(lines)

WARN = """> ⚠️ **2026-09-27 实测更正**：本机**不存在** `D:\\\\hikyuu_research`（`ls -d` → No such file；D 盘全盘无 hikyuu 目录）。
> 现存唯一 hikyuu 产物 = `D:\\Hermes Agent CN Desktop\\hunter-v2\\docs\\hikyuu-调研报告.md`，
> 调研结论是 **「方法论富矿，不建议移植本体」**（只借鉴 4 个模块 + IC 加权）。
> 下文目录结构来自该调研（上游 `github.com/fasiondog/hikyuu`），**仅作架构对照**，不要当本地路径直接用；需要源码请先 clone。

"""

txt = re.sub(r"(# hikyuu 代码库参考\r?\n)", lambda m: m.group(1) + "\n" + WARN, txt, count=1)
txt = re.sub(r"## 仓库布局 \([^)]*\)", "## 仓库布局（上游源码结构；⚠️ 本机未克隆）", txt, count=1)

P.write_text(txt, encoding="utf-8")

# 验证 frontmatter 能被 YAML 解析
import yaml
fm = txt.split("---")[1]
meta = yaml.safe_load(fm)
print("frontmatter 解析 OK:", {k: (str(v)[:70] + "...") for k, v in meta.items()})
print("description 里还有旧断言吗:", "代码在" in meta["description"])
print("行数:", len(txt.splitlines()), "| 描述改动:", hit_desc)
