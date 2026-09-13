"""结果级缓存 v1.0 — 同参回测磁盘持久化缓存,避免全量重跑.

设计要点:
- 磁盘持久化: JSON 文件保存 python dict 语义 (str -> any JSON 可序列化对象)。
- 线程安全: 所有读写均加 RLock,支持多线程并发读/写。
- 命中统计: hits / misses / 命中率可查询,便于监控缓存效率。
- 可失效: 由调用方在 bt_full.py 中通过 BUST_CACHE 常量显式强制重跑并覆写。

用法:
    cache = ResultCache(Path("data/bt_result_cache.json"))
    cache.set(some_key, result_dict)
    cached = cache.get(some_key)          # None 表示未命中
    cache.stats() -> {"hits":..., "misses":..., "hit_rate":...}
"""
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("aurora.result_cache")

DEFAULT_CACHE_FILE = Path(__file__).resolve().parent / "bt_result_cache.json"


def _canonicalize(key: str, value: Any) -> str:
    """把参数字段规范化为稳定可哈希的表现形式.

    禁止使用 list 的默认 str()(如 ['a','b'] 在旧版本是 '['a', 'b']' 会因内存地址
    变化而漂移),统一按全局确定性排序序列化。list/tuple/set 视为无序集合排序后
    以 JSON 序列化,嵌套 dict/list 递归归一化。
    """
    if isinstance(value, (list, tuple, set)):
        # 集合语义: 排序后统一 JSON 序列化,避免 list 默认 str 的内存地址漂移;
        # 依次_canonicalize 每个元素,保证嵌套结构也稳定。
        ordered = sorted(value, key=str)
        items = [f"{type(v).__name__}:{_canonicalize(key, v)}" for v in ordered]
        return json.dumps(items, sort_keys=True, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(
            {str(k): _canonicalize(str(k), v) for k, v in sorted(value.items(), key=str)},
            sort_keys=True, ensure_ascii=False,
        )
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str, type(None))):
        return f"{key}={value}"
    # 兜底: 其余类型按其类型名+确定性字符串
    try:
        return f"{key}={json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)}"
    except Exception:
        return f"{key}={type(value).__name__}:{str(value)}"


def make_bt_key(params: dict) -> str:
    """从回测全部确定性参数生成稳定唯一的缓存 key.

    特点:
    1. 确定性: 参数名=值 排序后拼接再 md5,参数不变 => key 固定。
    2. 敏感: 任一参数值变动(含 CD 标的池换一只) => key 变化,保证不会误用旧结果。
    3. 禁止对象 hash / list 默认 str,统一走 _canonicalize 规范化。

    返回: 32 位十六进制 md5 摘要,实际落盘 key 为 "bt:" + 摘要。
    """
    # 强制 key 名稳定排序,确保字段顺序不影响结果
    fields = []
    for key in sorted(params.keys()):
        fields.append(_canonicalize(str(key), params[key]))
    canonical = "|".join(fields)
    digest = hashlib.md5(canonical.encode("utf-8")).hexdigest()
    logger.debug(f"[make_bt_key] canonical={canonical[:120]}... md5={digest}")
    return f"bt:{digest}"


class ResultCache:
    """线程安全的 JSON 磁盘持久化结果缓存 (str -> JSON 值)."""

    def __init__(self, path: Path = DEFAULT_CACHE_FILE, autosave: bool = True):
        self.path = Path(path)
        self.autosave = autosave
        # _lock 保护内存 dict 与磁盘持久化一致性
        self._lock = threading.RLock()
        self._data: dict = {}
        self._hits = 0
        self._misses = 0
        self._load()

    # ---------------------------------------------------------------- 持久化
    def _load(self):
        """启动时从磁盘加载已有缓存;文件缺失或损坏时退化为空缓存."""
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            # 兼容最外层包裹 {"data": {...}} 与直接 dict 两种格式
            self._data = raw.get("data", raw) if isinstance(raw, dict) else {}
            if not isinstance(self._data, dict):
                self._data = {}
        except Exception as e:
            logger.warning(f"[ResultCache] 加载缓存失败({self.path.name}): {e}; 使用空缓存")
            self._data = {}

    def save(self):
        """将内存缓存写回磁盘 (JSON)."""
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                payload = {"data": self._data, "hits": self._hits, "misses": self._misses}
                self.path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"[ResultCache] 保存缓存失败({self.path.name}): {e}")

    # ------------------------------------------------------------------ 核心
    def get(self, key: str) -> Optional[Any]:
        """取缓存值;命中返回值,未命中返回 None. key 必须为确定性字符串."""
        with self._lock:
            if key in self._data:
                self._hits += 1
                return self._data[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any):
        """写入缓存并可选立即持久化."""
        with self._lock:
            self._data[key] = value
            if self.autosave:
                self.save()

    # ---------------------------------------------------------------- 统计
    def contains(self, key: str) -> bool:
        with self._lock:
            return key in self._data

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            rate = (self._hits / total * 100) if total > 0 else 0.0
            return {"hits": self._hits, "misses": self._misses,
                    "total": total, "hit_rate": round(rate, 2)}

    def size(self) -> int:
        with self._lock:
            return len(self._data)

    def clear(self):
        """清空内存缓存 (不影响磁盘除非调用 save)."""
        with self._lock:
            self._data.clear()
            self._hits = 0
            self._misses = 0
