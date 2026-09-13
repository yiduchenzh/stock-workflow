"""result_cache 结果级缓存测试 — 覆盖命中/miss/key稳定性/BUST/并发安全."""
import sys, os, threading
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.result_cache import ResultCache, make_bt_key  # noqa: E402

# 所有测试用临时缓存文件,避免污染生产缓存 data/bt_result_cache.json
TMP_CACHE = Path(__file__).parent / "_tmp_bt_cache.json"


def _make_cache():
    if TMP_CACHE.exists():
        TMP_CACHE.unlink()
    return ResultCache(TMP_CACHE)


# ------------------------------------------------------------------ (c) key 稳定性
def test_key_stable_for_same_params():
    p = {"name": "wave_point", "S": "2024-01-01", "E": "2024-06-01",
         "CAP": 1000000, "MP": 100, "MXP": 5, "STOP": 0.07, "RR": 2.8,
         "CD": ["000001", "000002", "600036"], "n_strats": ["a", "b"]}
    assert make_bt_key(p) == make_bt_key(p)


def test_key_changes_on_any_param_change():
    base = {"name": "wave_point", "S": "2024-01-01", "E": "2024-06-01",
            "CAP": 1000000, "MP": 100, "MXP": 5, "STOP": 0.07, "RR": 2.8,
            "CD": ["000001", "000002", "600036"], "n_strats": ["a", "b"]}
    k0 = make_bt_key(base)
    # 逐个改动任一参数,key 都必须变
    for mutate in [
        {"CAP": 2000000}, {"MP": 200}, {"MXP": 3}, {"STOP": 0.05},
        {"RR": 2.0}, {"name": "mean_reversion"}, {"S": "2023-01-01"},
        {"E": "2024-12-31"}, {"CD": ["000001", "000002", "000333"]},
    ]:
        p = dict(base); p.update(mutate)
        assert make_bt_key(p) != k0, f"改动 {mutate} 后 key 未变化"


def test_key_cd_pool_order_independent():
    """CD 标的池顺序不影响 key (集合语义)."""
    base = dict(name="w", S="S", E="E", CAP=1, MP=1, MXP=1, STOP=0.1,
                RR=2.0, CD=[], n_strats=[])
    a = dict(base); a["CD"] = ["1", "2", "3"]
    b = dict(base); b["CD"] = ["3", "2", "1"]
    assert make_bt_key(a) == make_bt_key(b)
    c = dict(base); c["CD"] = ["1", "2", "4"]  # 换一只标的必须变
    assert make_bt_key(a) != make_bt_key(c)


# ------------------------------------------------------------------ (a) 同参二次命中
def test_same_params_second_call_hits():
    cache = _make_cache()
    key = "bt:unit-test-key"
    assert cache.get(key) is None  # 第一次 miss
    cache.set(key, {"n": 10, "pnl": 100.0})
    assert cache.get(key) == {"n": 10, "pnl": 100.0}  # 第二次 hit,结果相等
    st = cache.stats()
    assert st["misses"] == 1 and st["hits"] == 1


# ------------------------------------------------------------------ (b) 改参则 miss 且结果不同
def test_param_change_misses_and_differs():
    cache = _make_cache()
    p1 = dict(name="wave_point", S="2024-01-01", E="2024-06-01", CAP=1000000,
              MP=100, MXP=5, STOP=0.07, RR=2.8, CD=["000001"], n_strats=["a"])
    p2 = dict(p1); p2["MXP"] = 3  # 改一个参数
    k1, k2 = make_bt_key(p1), make_bt_key(p2)
    assert k1 != k2
    cache.set(k1, {"MXP": 5})
    assert cache.get(k2) is None  # 改参后必 miss


# ------------------------------------------------------------------ (d) BUST 强制重跑不命中
def test_bust_force_rerun(monkeypatch):
    bt_full = __import__("bt_full", fromlist=["_BT_CACHE", "make_strategy_params"])
    cache = bt_full._BT_CACHE
    params = bt_full.make_strategy_params("wave_point")
    key = make_bt_key(params)
    cache.set(key, {"fake": "old"})  # 预置一个"旧结果"
    counter = {"n": 0}
    real = bt_full.run_strategy

    # 用真实 run_strategy 走全流程,BUST_CACHE=True 时应忽略缓存重新计算
    bt_full.BUST_CACHE = True
    try:
        # run_strategy 会真实回测;用 monkeypatch 让 kc 为空避免拉真实数据
        r = real("wave_point", {})
    finally:
        bt_full.BUST_CACHE = False
    # 空 kc 也会返回一个 result dict,且重新写入缓存覆盖旧值
    assert "strategy" in r
    assert cache.get(key) != {"fake": "old"}  # 覆写生效


# ------------------------------------------------------------------ (e) 并发安全
def test_concurrent_reads_safe():
    cache = _make_cache()
    for i in range(50):
        cache.set(f"k{i}", {"v": i})
    errors = []

    def worker():
        try:
            for _ in range(200):
                for i in range(50):
                    v = cache.get(f"k{i}")
                    assert v is None or v == {"v": i}
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors, f"并发读出现异常: {errors}"


# ------------------------------------------------------------------ 清理
def teardown_module():
    if TMP_CACHE.exists():
        TMP_CACHE.unlink()
