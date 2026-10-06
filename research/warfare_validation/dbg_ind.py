# -*- coding: utf-8 -*-
"""诊断行业面板 + 快速检验"""
import numpy as np
from ev import load
P = load()
ilc, ipct = P["ind_lim_count"], P["ind_pct"]
ind = P["code_ind_idx"]
print("code_ind_idx: 有行业代码数", (ind >= 0).sum(), "/", len(ind))
print("ind_lim_count 非NaN比例", np.mean(np.isfinite(ilc)), " 最大", np.nanmax(ilc))
print("ind_pct 非NaN比例", np.mean(np.isfinite(ipct)))
print("行样例 (最后一日) ilc[:10]", ilc[-1][:10])
print("行样例 (最后一日) ipct[:10]", ipct[-1][:10])
print("行业名前10:", list(P["ind_names"][:10]))
print("映射样例:", [(c, P["industry"][i], ind[i]) for i, c in enumerate(P["codes"][:5])])
# 单日 行业涨停数分布
import collections
v = ilc[-1]
print("最后一日 行业涨停数>=1 的行业数:", np.nansum(np.nan_to_num(v) >= 1), " >3:", np.nansum(np.nan_to_num(v) > 3))
print("最后一日 行业涨幅>1% 的行业数:", np.nansum(np.nan_to_num(ipct[-1]) > 1))
