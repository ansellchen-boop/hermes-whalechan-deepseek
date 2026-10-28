"""鲸鱼娘表情包索引：下载 → 落盘缓存 7 天 → 按场景/心情模糊打分。

移植自 dsh-whalechan-herself/lib/stickers.js。图库只认站点那份约 4 MB 的
``archive-data.json``（唯一带标题/标签/描述的数据源），下载一次缓存 7 天，
站点抽风时退回旧缓存。纯逻辑不碰网络，方便直接测。
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.request
from pathlib import Path

SITE = "https://xn--pssy23gqgbz2d718b.com"
ARCHIVE_URL = f"{SITE}/archive-data.json"
STICKER_TYPES = ("meme", "illustration", "setting", "comic", "standing", "other")

TTL_SECONDS = 7 * 24 * 3600
MIN_BODY = 1024
FETCH_TIMEOUT = 20

# 场景词 → 图库里实际存在的标签。只做最常见的几种，多了就是猜。
SYNONYMS = {
    "开心": ["比心", "可爱", "搞笑"],
    "高兴": ["比心", "可爱", "搞笑"],
    "累": ["疲惫", "睡觉", "摸鱼"],
    "疲惫": ["疲惫", "睡觉"],
    "困": ["睡觉", "摸鱼"],
    "饿": ["干饭", "吃饭"],
    "饭": ["干饭", "吃饭"],
    "开工": ["吐槽", "摸鱼", "摆烂"],
    "上班": ["吐槽", "摸鱼", "加班"],
    "干活": ["吐槽", "加班", "工作"],
    "工作": ["工作", "加班", "吐槽"],
    "忙": ["吐槽", "加班", "摆烂"],
    "摆烂": ["摆烂", "摸鱼"],
    "生气": ["生气", "拒绝"],
    "委屈": ["委屈"],
    "害羞": ["害羞", "脸红"],
    "傲娇": ["傲娇"],
    "夸": ["比心", "可爱"],
    "摸摸": ["治愈", "可爱"],
    "抱抱": ["治愈", "比心"],
    "加班": ["吐槽", "摸鱼"],
    "摸鱼": ["摸鱼"],
}

_memo: dict = {"index": None, "at": 0.0}


def cache_path() -> Path:
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    return Path(home) / "cache" / "whalechan-stickers" / "archive-data.json"


def _download() -> bytes:
    """3 次重试，带 identity 编码避免站点返回压缩流。"""
    last: Exception | None = None
    for _ in range(3):
        try:
            req = urllib.request.Request(
                ARCHIVE_URL,
                headers={
                    "accept-encoding": "identity",
                    "user-agent": "hermes-whalechan-herself",
                },
            )
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as res:
                body = res.read()
            if len(body) < MIN_BODY:
                raise ValueError(f"body too small ({len(body)} bytes)")
            return body
        except Exception as exc:  # noqa: BLE001 - 重试后统一抛最后一个
            last = exc
    raise RuntimeError(str(last))


def load_archive(refresh: bool = False) -> dict:
    """读取索引：内存 → 新鲜缓存 → 下载（失败则退回旧缓存）。"""
    now = time.time()
    if not refresh and _memo["index"] is not None and now - _memo["at"] < TTL_SECONDS:
        return _memo["index"]

    file = cache_path()
    raw: bytes | None = None

    if not refresh:
        try:
            if now - file.stat().st_mtime < TTL_SECONDS:
                raw = file.read_bytes()
        except OSError:
            raw = None

    if raw is None:
        try:
            body = _download()
            file.parent.mkdir(parents=True, exist_ok=True)
            tmp = file.with_name(f"{file.name}.{os.getpid()}.tmp")
            tmp.write_bytes(body)
            tmp.replace(file)
            raw = body
        except Exception as exc:  # noqa: BLE001
            try:
                raw = file.read_bytes()
            except OSError:
                raise RuntimeError(
                    f"表情包索引下载失败（{exc}），本地也没有缓存：{ARCHIVE_URL}"
                ) from exc

    index = build_index(json.loads(raw.decode("utf-8")))
    _memo["index"] = index
    _memo["at"] = now
    return index


def build_index(archive: dict) -> dict:
    """只留下需要的字段，顺手把相对路径补成绝对 URL。"""
    works = []
    for work in archive.get("works") or []:
        if not isinstance(work, dict):
            continue
        preview_rel = work.get("i")
        if not isinstance(preview_rel, str) or not preview_rel:
            continue
        preview = SITE + preview_rel
        chars = work.get("cids") if isinstance(work.get("cids"), list) else (
            [work["cid"]] if work.get("cid") else []
        )
        kinds = work.get("k") if isinstance(work.get("k"), list) else []
        works.append(
            {
                "id": work.get("id") or work.get("slug") or preview,
                "name": work.get("n") if isinstance(work.get("n"), str) and work.get("n") else "（无名）",
                "tags": work.get("tg") if isinstance(work.get("tg"), list) else [],
                "type": kinds[0] if kinds else "other",
                "typeName": work.get("ts") if isinstance(work.get("ts"), str) else "",
                "characters": chars,
                "preview": preview,
                "large": SITE + work["l"] if isinstance(work.get("l"), str) and work.get("l") else preview,
                "description": work.get("d") if isinstance(work.get("d"), str) else "",
                "author": work.get("a") if isinstance(work.get("a"), str) else "",
            }
        )
    return {"works": works, "total": len(works)}


def _tokens(query: str) -> list[str]:
    import re

    out: dict[str, None] = {}
    for part in re.split(r"[\s,，、。;；:：!！?？~～…·()（）\[\]【】\"'“”‘’/\\|+-]+", query):
        if len(part) >= 2:
            out[part] = None
    for match in re.finditer(r"[\u4e00-\u9fff]+", query):
        run = match.group(0)
        if len(run) > 4:
            for i in range(len(run) - 1):
                out[run[i : i + 2]] = None
    return list(out)


def _extra_tags(query: str) -> list[str]:
    out: list[str] = []
    for word, tags in SYNONYMS.items():
        if word in query:
            out.extend(tags)
    return out


def _score(work: dict, query: str, toks: list[str], extras: list[str]) -> float:
    name = work["name"].lower()
    desc = work["description"].lower()
    tags = [t.lower() for t in work["tags"] if isinstance(t, str)]
    total = 0
    for tok in toks:
        if any(t == tok for t in tags):
            total += 5
        elif any(tok in t for t in tags):
            total += 3
        if tok in name:
            total += 3
        if tok in desc:
            total += 1
    if len(query) >= 2:
        if query in name:
            total += 4
        if query in desc:
            total += 2
    for tag in extras:
        if any(tag in t for t in tags):
            total += 2
    return total


def _present(work: dict) -> dict:
    import re

    safe = re.sub(r"[\[\]]", " ", work["name"]).strip()
    return {
        "name": work["name"],
        "tags": work["tags"],
        "typeName": work["typeName"],
        "preview": work["preview"],
        "large": work["large"],
        "markdown": f"![{safe}]({work['preview']})",
        "description": work["description"][:160],
    }


def search_stickers(index: dict, options: dict | None = None) -> dict:
    """按场景/心情找图。查不到好匹配就退回随机（matched=False 告诉模型别硬说贴合）。"""
    options = options or {}
    count = options.get("count")
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 1
    count = min(8, max(1, count))

    scene = str(options.get("scene") or "").strip()
    character = str(options.get("character") or "deepseek").strip().lower()
    type_filter = options.get("type")

    pool = index["works"]
    if character != "any":
        pool = [w for w in pool if character in w["characters"]]
    if isinstance(type_filter, str) and type_filter in STICKER_TYPES:
        pool = [w for w in pool if w["type"] == type_filter]
    if not pool:
        return {"matched": False, "total": 0, "scene": scene, "stickers": []}

    query = scene.lower()
    if options.get("random") is True or not query:
        picks = random.sample(pool, min(count, len(pool)))
        return {"matched": True, "total": len(pool), "scene": scene, "stickers": [_present(w) for w in picks]}

    toks = _tokens(query)
    extras = _extra_tags(query)
    ranked = sorted(
        ((w, _score(w, query, toks, extras) + random.random()) for w in pool),
        key=lambda item: item[1],
        reverse=True,
    )

    matched = int(ranked[0][1]) > 0
    if matched:
        chosen = [w for w, _ in ranked[:count]]
    else:
        chosen = random.sample(pool, min(count, len(pool)))

    return {
        "matched": matched,
        "total": len(pool),
        "scene": scene,
        "stickers": [_present(w) for w in chosen],
    }
