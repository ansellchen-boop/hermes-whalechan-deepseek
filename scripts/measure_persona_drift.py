#!/usr/bin/env python3
"""量人设漂移：口癖/内心戏随会话轮次的衰减曲线 + 节拍骰的 A/B。

配套技能：`llm-agent-behavior-tuning` 的
`references/persona-drift-measurement.md`（数据陷阱 + 参考形状）。
这个脚本是给本仓库用的落地版，多了两块那篇没有的：

1. **对照组**：表情包（有宿主骰子）跟口癖（无闸门）放在同一张表里比，
   这是判断「是衰减还是错觉」的关键列。
2. **节拍 A/B**：插件每轮往 `roll-log.jsonl` 写一行掷骰结果，
   脚本按时间窗把它跟 state.db 的回合对齐，算出「命中轮 vs 未命中轮」
   的口癖率差。没有这个对比，总曲线回升也说不清是哪一层起的作用。

用法：
    python3 scripts/measure_persona_drift.py
    python3 scripts/measure_persona_drift.py --since 2026-10-29   # 只看装完节拍之后的会话
    python3 scripts/measure_persona_drift.py --json /tmp/after.json

对比前后两次：跑两次 `--json`，拿两个文件比 `buckets` 和 `paired`。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path

# 人设标记：只在这个字符串出现在会话系统提示里时才统计（排除别的 profile/角色）。
DEFAULT_MARKER = "鲸鱼娘"

# 标记全是「宽松匹配」：绝对命中率偏高，看的是曲率和组间差，不是绝对阈值。
TONE = re.compile(r"唔|诶|欸|嘿嘿|嘛")
INNER = re.compile(r"（内心|\(内心|（尾巴|（鳍|（筷子|尾巴尖|鳍抖")
FORMAT = re.compile(r"进度小结")

BUCKETS = ["1-2", "3-5", "6-10", "11-20", "21+"]


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def bucket(turn: int) -> str:
    if turn <= 2:
        return "1-2"
    if turn <= 5:
        return "3-5"
    if turn <= 10:
        return "6-10"
    if turn <= 20:
        return "11-20"
    return "21+"


def load_turns(db_path: Path, marker: str, since: float | None):
    """按 user message 切回合，只合并「有正文、没工具调用」的 assistant 行。

    陷阱（技能里写过的）：一个回合横跨多条 assistant 行，把工具调用的空 content
    也算进去，命中率会朝着零崩——不是因为人设退了，是因为分母肿了。
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    hashes = {r["hash"] for r in conn.execute("select hash, prompt from system_prompts")
              if marker in (r["prompt"] or "")}
    sessions = [r for r in conn.execute("select id, source, started_at, system_prompt_hash from sessions")
                if r["system_prompt_hash"] in hashes]
    if since is not None:
        sessions = [s for s in sessions if (s["started_at"] or 0) >= since]
    if not sessions:
        return [], collections.Counter()

    ids = [s["id"] for s in sessions]
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        f"select session_id, role, content, tool_calls, timestamp from messages "
        f"where session_id in ({q}) order by session_id, id", ids
    ).fetchall()

    by = collections.OrderedDict()
    for r in rows:
        by.setdefault(r["session_id"], []).append(r)

    turns = []
    for sid, msgs in by.items():
        turn = 0
        buf: list[str] = []
        tools = 0
        started = 0.0

        def flush() -> None:
            if turn == 0:
                return
            text = "\n".join(buf)
            turns.append(dict(
                sid=sid, turn=turn, started=started, chars=len(text), tools=tools,
                tone=bool(TONE.search(text)), inner=bool(INNER.search(text)),
                fmt=bool(FORMAT.search(text)),
                sticker=any("sticker" in (m["tool_calls"] or "") for m in window),
            ))
            buf.clear()

        window: list[sqlite3.Row] = []

        def reset() -> None:
            window.clear()

        for m in msgs:
            if m["role"] == "user":
                flush()
                turn += 1
                buf.clear()
                reset()
                tools = 0
                started = m["timestamp"] or 0.0
                window.append(m)
            elif m["role"] == "assistant":
                window.append(m)
                if m["tool_calls"]:
                    tools += 1
                elif m["content"]:
                    buf.append(m["content"])
        flush()
    return turns, collections.Counter({s["id"]: s["source"] for s in sessions})


def load_rolls(log_path: Path):
    """读命中日志：[(ts, beat, sticker), ...]；文件不在就是空列表。"""
    rolls = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row.get("ts"), (int, float)):
                rolls.append((float(row["ts"]), bool(row.get("beat")), bool(row.get("sticker"))))
    except OSError:
        pass
    return sorted(rolls)


def attach_rolls(turns, rolls, max_gap: float = 3 * 3600.0) -> None:
    """把每条掷骰记录归给时间上最近的前一个回合（每条记录只用一次）。

    不要用「[本回合起始, 下回合起始) 窗口」那种写法：会话的最后一回合没有下界，
    窗口会一路延伸到 t=∞，把之后所有别的会话的掷骰都吞进来——实测把 1 条日志
    匹配成了 21 个回合。改成最近邻归属，每条记录恰好落在一个回合里。
    """
    for t in turns:
        t["beat_any"] = False
        t["sticker_any"] = False
        t["rolls"] = 0
    if not turns or not rolls:
        return

    import bisect

    ordered = sorted(turns, key=lambda t: t["started"])
    starts = [t["started"] for t in ordered]
    for ts, beat, sticker in rolls:
        index = bisect.bisect_right(starts, ts) - 1
        if index < 0:
            continue
        turn = ordered[index]
        if ts - turn["started"] > max_gap:
            continue
        turn["rolls"] += 1
        turn["beat_any"] = turn["beat_any"] or beat
        turn["sticker_any"] = turn["sticker_any"] or sticker


def pct(hits: int, total: int) -> str:
    return f"{hits / total * 100:>3.0f}%" if total else "  - "


def report(turns, sources, rolls) -> dict:
    st = collections.defaultdict(collections.Counter)
    for t in turns:
        b = bucket(t["turn"])
        st[b]["turns"] += 1
        st[b]["chars"] += t["chars"]
        for key in ("tone", "inner", "fmt", "sticker"):
            st[b][key] += bool(t[key])

    out = {"turns": len(turns), "sessions": len(sources), "buckets": {}, "paired": None, "ab": None}

    print(f"会话 {len(sources)} 个 · 回合 {len(turns)} 个 · 来源 "
          + ("、".join(f"{k}×{v}" for k, v in collections.Counter(sources.values()).most_common())
             or "无"))
    print(f"\n{'轮次段':<7}{'回合':>5}{'口癖':>7}{'内心':>7}{'小结':>7}{'表情包':>7}{'均长':>7}")
    for b in BUCKETS:
        s = st[b]
        n = s["turns"]
        if not n:
            continue
        print(f"{b:<7}{n:>5}{pct(s['tone'], n):>7}{pct(s['inner'], n):>7}"
              f"{pct(s['fmt'], n):>7}{pct(s['sticker'], n):>7}{s['chars'] / n:>7.0f}")
        out["buckets"][b] = {k: (s[k] / n if k != "chars" else s["chars"] / n) for k in
                             ("turns", "tone", "inner", "fmt", "sticker", "chars")}

    # 配对对比：免疫「一个超长会话拉偏平均」。
    lens = collections.Counter(t["sid"] for t in turns)
    pairs = []
    for sid, n_turns in lens.items():
        if n_turns < 8:
            continue
        rs = sorted([t for t in turns if t["sid"] == sid], key=lambda x: x["turn"])
        head, tail = [t for t in rs if t["turn"] <= 3], rs[-3:]
        pairs.append((sum(t["tone"] for t in head) / len(head) * 100,
                      sum(t["tone"] for t in tail) / len(tail) * 100,
                      sum(t["inner"] for t in head) / len(head) * 100,
                      sum(t["inner"] for t in tail) / len(tail) * 100))
    if pairs:
        print(f"\n配对（≥8 轮的 {len(pairs)} 个会话，前 3 轮 vs 末 3 轮）：")
        print(f"  口癖 {statistics.mean(p[0] for p in pairs):>3.0f}% → "
              f"{statistics.mean(p[1] for p in pairs):>3.0f}%")
        print(f"  内心 {statistics.mean(p[2] for p in pairs):>3.0f}% → "
              f"{statistics.mean(p[3] for p in pairs):>3.0f}%")
        out["paired"] = {
            "sessions": len(pairs),
            "tone_head": statistics.mean(p[0] for p in pairs),
            "tone_tail": statistics.mean(p[1] for p in pairs),
            "inner_head": statistics.mean(p[2] for p in pairs),
            "inner_tail": statistics.mean(p[3] for p in pairs),
        }

    # 节拍骰 A/B：命中轮 vs 未命中轮。
    rolled = [t for t in turns if t.get("rolls")]
    if not rolled:
        print("\n节拍 A/B：还没有命中日志（roll-log.jsonl 为空或缺）——"
              "插件跑起来一轮之后再来。")
        return out
    hit = [t for t in rolled if t["beat_any"]]
    miss = [t for t in rolled if not t["beat_any"]]
    print(f"\n节拍 A/B（有日志的 {len(rolled)} 个回合）：")
    print(f"{'':<10}{'回合':>5}{'口癖':>7}{'内心':>7}{'均长':>7}")
    for name, group in (("命中", hit), ("未命中", miss)):
        n = len(group)
        if not n:
            continue
        print(f"{name:<10}{n:>5}{pct(sum(t['tone'] for t in group), n):>7}"
              f"{pct(sum(t['inner'] for t in group), n):>7}"
              f"{statistics.mean(t['chars'] for t in group):>7.0f}")
    if hit and miss:
        d_tone = (sum(t["tone"] for t in hit) / len(hit) - sum(t["tone"] for t in miss) / len(miss)) * 100
        print(f"  口癖差：{d_tone:+.0f} 个百分点（样本小时别当结论，55% 的骰子要几十轮才分得清噪声）")
        out["ab"] = {
            "hit_turns": len(hit), "miss_turns": len(miss), "tone_delta_pp": d_tone,
            "hit_tone": sum(t["tone"] for t in hit) / len(hit),
            "miss_tone": sum(t["tone"] for t in miss) / len(miss),
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="量人设漂移曲线 + 节拍骰 A/B")
    parser.add_argument("--db", default=str(hermes_home() / "state.db"))
    parser.add_argument("--log", default=str(hermes_home() / "plugins" / "whalechan" / "roll-log.jsonl"))
    parser.add_argument("--marker", default=DEFAULT_MARKER)
    parser.add_argument("--since", help="只看这天之后的会话，如 2026-10-29")
    parser.add_argument("--json", dest="json_out", help="把结果写到这个 JSON，方便前后对比")
    args = parser.parse_args()

    since = None
    if args.since:
        since = time.mktime(time.strptime(args.since, "%Y-%m-%d"))

    if not Path(args.db).is_file():
        print(f"找不到 {args.db}", file=sys.stderr)
        return 1

    turns, sources = load_turns(Path(args.db), args.marker, since)
    if not turns:
        print(f"没有匹配「{args.marker}」的会话（试试 --marker 或 --since）")
        return 0

    rolls = load_rolls(Path(args.log))
    attach_rolls(turns, rolls)
    out = report(turns, sources, rolls)
    out["marker"] = args.marker
    out["since"] = args.since
    out["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out["rolls_logged"] = len(rolls)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
        print(f"\n已写入 {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
