# -*- coding: utf-8 -*-
"""共用评估函数: 逐日横截面去均值(控大盘beta) + 分组统计"""
import pickle
from pathlib import Path
import numpy as np
import pandas as pd

_DIR = Path(__file__).parent
_P = None


def load():
    global _P
    if _P is None:
        with open(_DIR / "panel.pkl", "rb") as f:
            _P = pickle.load(f)
    return _P


def hold_from_open(P, off, h):
    """买入=第 off 日开盘 (off=1 → 次日), 持有到第 off+h-1 日收盘. 返回 % 收益矩阵"""
    O = np.vstack([P["open"][off:], np.full((off, P["open"].shape[1]), np.nan)])
    C = np.vstack([P["close"][off + h - 1:], np.full((off + h - 1, P["close"].shape[1]), np.nan)])
    with np.errstate(invalid="ignore", divide="ignore"):
        return (C / O - 1.0) * 100.0


def daymean(F):
    """逐日横截面等权均值 (作为基准, 扣除大盘beta)"""
    with np.errstate(invalid="ignore"):
        return np.nanmean(np.where(np.isfinite(F), F, np.nan), axis=1)


def fwd_at(F, off):
    """out[t] = F[t+off]  (把未来第off日的值对齐到观察日t)"""
    out = np.full_like(F, np.nan)
    out[:-off] = F[off:]
    return out


def fwd_roll(F, h, off=1, how="min"):
    """out[t] = 未来 [t+off, t+off+h-1] 区间的 min/max/mean/sum, 对齐到观察日 t"""
    S = pd.DataFrame(F)
    r = getattr(S.rolling(h, min_periods=1), how)().to_numpy()
    k = off + h - 1
    out = np.full_like(F, np.nan)
    out[:-k] = r[k:]
    return out


def stat(F, mask, P, demean=True):
    """F=收益矩阵, mask=信号矩阵(bool). 返回 n/均值/中位/胜率/超额均值"""
    if F is None:
        return None
    finite = np.isfinite(F)
    m = mask & finite
    if m.sum() == 0:
        return dict(n=0)
    v = F[m]
    ex = (F - daymean(F)[:, None])[m] if demean else v
    return dict(n=int(m.sum()), mean=float(np.mean(v)), med=float(np.median(v)),
                win=float(np.mean(v > 0) * 100), exc=float(np.mean(ex)))


def table(rows, headers=("条件", "样本", "均值%", "中位%", "胜率%", "超额%")):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for name, s in rows:
        if not s or s.get("n", 0) == 0:
            out.append(f"| {name} | 0 | - | - | - | - |")
        else:
            out.append(f"| {name} | {s['n']:,} | {s['mean']:+.2f} | {s['med']:+.2f} | {s['win']:.1f} | {s['exc']:+.2f} |")
    return "\n".join(out)


def yearly(F, mask, P):
    """分年度稳健性: 返回 {year: (n, mean, win, exc)}"""
    yrs = pd.DatetimeIndex(P["days"]).year.to_numpy()
    res = {}
    for y in sorted(set(yrs)):
        mm = mask & (yrs[:, None] == y)
        s = stat(F, mm, P)
        if s and s.get("n", 0) > 30:
            res[int(y)] = s
    return res
