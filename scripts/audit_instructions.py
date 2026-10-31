#!/usr/bin/env python3
"""审计指令文件有没有膨胀、有没有该退休的规矩。

把 AGENTS.md 当技术债看待，查四件事：

  1. 尺寸    入口行数 / 字符数，跟上次比长了没有
  2. 三件    硬约束段里每条是否带齐 来源 / 适用 / 过期
  3. 死链    入口里 `docs/xxx.md` 这类引用指向的文件还在不在
  4. 陈旧    文件多久没复审了（超过 STALE_DAYS 天提示）

退出码：0 = 全绿；1 = 有硬失败；2 = 只有警告。

用法：
    python3 scripts/audit_instructions.py              # 审默认的三个位置
    python3 scripts/audit_instructions.py --json       # 机器可读
    python3 scripts/audit_instructions.py --targets /path/to/AGENTS.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

STALE_DAYS = 90
MAX_ENTRY_LINES = 200
MAX_CONSTRAINTS = 15

DEFAULT_TARGETS = [
    "/home/ubuntu/AGENTS.md",
    "/home/ubuntu/qq-bridge/AGENTS.md",
    "/home/ubuntu/hermes-whalechan/AGENTS.md",
]

HISTORY = os.path.expanduser("~/.hermes/cache/audit/history.jsonl")

CONSTRAINT_HEAD = re.compile(r"^#{1,3}\s.*硬约束")
HEADING = re.compile(r"^#{1,6}\s")
LIST_ITEM = re.compile(r"^(?:\d+\.|[-*+])\s+")
DOC_LINK = re.compile(r"`(docs/[\w./-]+\.md)`")

# 每篇专题文档开头必须声明的三件（文件级，不是逐条）
DOC_DECL_KEYS = ("适用", "过期条件", "来源")
DOC_HEAD_LINES = 12


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def constraint_section(lines: list[str]) -> tuple[int, int]:
    """返回硬约束段的 [start, end) 行号；找不到返回 (-1, -1)。"""
    start = -1
    for i, ln in enumerate(lines):
        if CONSTRAINT_HEAD.match(ln):
            start = i
            break
    if start < 0:
        return -1, -1
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    for j in range(start + 1, len(lines)):
        m = HEADING.match(lines[j])
        if m and (len(lines[j]) - len(lines[j].lstrip("#"))) <= level:
            return start, j
    return start, len(lines)


def audit_constraints(lines: list[str]) -> list[dict]:
    """逐个硬约束条目检查三件是否齐。"""
    start, end = constraint_section(lines)
    if start < 0:
        return []
    body = lines[start + 1 : end]
    items = []
    for i, ln in enumerate(body):
        if not LIST_ITEM.match(ln):
            continue
        # 条目正文到下一个条目为止
        chunk = [ln]
        for nxt in body[i + 1 :]:
            if LIST_ITEM.match(nxt):
                break
            chunk.append(nxt)
        text = "\n".join(chunk)
        title = re.sub(r"^[\d.\-*+]\s*", "", ln).replace("**", "").strip()
        items.append(
            {
                "line": start + 1 + i + 1,
                "title": title[:36],
                "has_source": "来源" in text,
                "has_scope": "适用" in text,
                "has_expiry": "过期" in text,
            }
        )
    return items


def audit_links(path: str, text: str) -> list[str]:
    """入口里 `docs/xxx.md` 形式的引用，文件必须存在。"""
    base = os.path.dirname(path)
    missing = []
    for rel in sorted(set(DOC_LINK.findall(text))):
        if not os.path.exists(os.path.join(base, rel)):
            missing.append(rel)
    return missing


def audit_docs(base: str) -> list[str]:
    """同目录 docs/*.md 每篇顶部要有时效声明，缺的返回文件名。"""
    docs = os.path.join(base, "docs")
    if not os.path.isdir(docs):
        return []
    missing = []
    for name in sorted(os.listdir(docs)):
        if not name.endswith(".md"):
            continue
        head = "\n".join(read(os.path.join(docs, name)).splitlines()[:DOC_HEAD_LINES])
        if not all(k in head for k in DOC_DECL_KEYS):
            missing.append(name)
    return missing


def last_touched(path: str) -> int:
    """文件多久没动了（天）。git 仓库看最后一次提交，否则看 mtime。"""
    try:
        out = subprocess.run(
            ["git", "-C", os.path.dirname(path), "log", "-1", "--format=%ct", "--", os.path.basename(path)],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            return int((time.time() - int(out.stdout.strip())) // 86400)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return int((time.time() - os.path.getmtime(path)) // 86400)


def previous_size(path: str) -> int | None:
    if not os.path.exists(HISTORY):
        return None
    last = None
    with open(HISTORY, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("path") == path:
                last = rec.get("chars")
    return last


def audit_one(path: str) -> dict:
    text = read(path)
    lines = text.splitlines()
    items = audit_constraints(lines)
    missing = [it for it in items if not (it["has_source"] and it["has_scope"] and it["has_expiry"])]
    chars = len(text)

    fails, warns = [], []
    if len(lines) > MAX_ENTRY_LINES:
        fails.append(f"入口 {len(lines)} 行，超过 {MAX_ENTRY_LINES} 行上限")
    if len(items) > MAX_CONSTRAINTS:
        warns.append(f"硬约束 {len(items)} 条，超过 {MAX_CONSTRAINTS} 条建议值")
    for it in missing:
        fails.append(f"第 {it['line']} 行「{it['title']}」缺 {missing_parts(it)}")
    for rel in audit_links(path, text):
        fails.append(f"死链：`{rel}` 不存在")
    doc_missing = audit_docs(os.path.dirname(path))
    for name in doc_missing:
        fails.append(f"docs/{name} 顶部缺时效声明（要 适用 / 过期条件 / 来源 三件）")
    days = last_touched(path)
    if days > STALE_DAYS:
        warns.append(f"{days} 天没复审（阈值 {STALE_DAYS}）")

    prev = previous_size(path)
    delta = None if prev is None else chars - prev

    return {
        "path": path,
        "lines": len(lines),
        "chars": chars,
        "delta": delta,
        "constraints": len(items),
        "missing": len(missing),
        "days_since_touch": days,
        "docs_missing": len(doc_missing),
        "fails": fails,
        "warns": warns,
    }


def missing_parts(it: dict) -> str:
    parts = []
    if not it["has_source"]:
        parts.append("来源")
    if not it["has_scope"]:
        parts.append("适用")
    if not it["has_expiry"]:
        parts.append("过期")
    return "+".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", nargs="*", default=DEFAULT_TARGETS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-history", action="store_true", help="不写历史（演示时用）")
    args = ap.parse_args()

    results = []
    for path in args.targets:
        if not os.path.exists(path):
            results.append({"path": path, "fails": [f"文件不存在"], "warns": [],
                            "lines": 0, "chars": 0, "delta": None,
                            "constraints": 0, "missing": 0, "days_since_touch": 0})
            continue
        results.append(audit_one(path))

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("指令审计 —— 把 AGENTS.md 当技术债看\n")
        for r in results:
            d = f"（较上次 {r['delta']:+d}）" if r["delta"] not in (None, 0) else ""
            status = "✗" if r["fails"] else ("!" if r["warns"] else "✓")
            print(f"{status} {r['path']}")
            print(f"    {r['lines']} 行 / {r['chars']} 字符{d}   硬约束 {r['constraints']} 条，"
                  f"缺三件 {r['missing']} 条   文档缺声明 {r.get('docs_missing', 0)} 篇   "
                  f"{r['days_since_touch']} 天未动")
            for f in r["fails"]:
                print(f"    ✗ {f}")
            for w in r["warns"]:
                print(f"    ! {w}")
            print()

    if not args.no_history:
        os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
        with open(HISTORY, "a", encoding="utf-8") as fh:
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            for r in results:
                fh.write(json.dumps({"ts": now, "path": r["path"], "lines": r["lines"],
                                     "chars": r["chars"], "missing": r["missing"]},
                                    ensure_ascii=False) + "\n")

    if any(r["fails"] for r in results):
        print("结论：有硬失败，先修再干活。")
        return 1
    if any(r["warns"] for r in results):
        print("结论：通过，但有警告。")
        return 2
    print("结论：全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
