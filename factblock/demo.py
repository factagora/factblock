"""An animated walkthrough of a bundle in the terminal: the README GIF and talks. Every number and
statement on screen comes from the reads the plain CLI makes (scan, why, recall) or from a bench's
results file; nothing is typed in by hand. Needs Rich: pip install --pre 'factblock[demo]'.

    factblock demo title
    factblock demo timeline samples/cramer --as-of 2024-09-30 2025-09-30 2026-09-10
    factblock demo why samples/cramer f8c739a204944e7f --as-of 2026-09-10
    factblock demo replaced samples/rates c1 --as-of 2024-10-01 2024-08-01
    factblock demo verdict samples/cramer 66027d5985bf9605 --as-of 2024-09-01 2024-10-15 2024-12-31
    factblock demo leak bench/streamingqa/results.json
    factblock demo end

FACTBLOCK_DEMO_FAST=1 skips the pauses (tests)."""
import argparse
import json
import os
import time

from .bundle import Bundle, parse_instant
from .scan import _as_of, scan, visible
from .validate import CORE_FAMILY
from .why import why

try:
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.tree import Tree
except ImportError:  # pragma: no cover
    raise SystemExit("factblock demo needs Rich: pip install --pre 'factblock[demo]'") from None

ACCENT, GREEN, YELLOW, RED, GRAY = "#1C90F7", "#3FB950", "#D29922", "#F85149", "grey50"
WIDTH = 86
FAST = bool(os.environ.get("FACTBLOCK_DEMO_FAST"))
console = Console(width=WIDTH, highlight=False)

LOGO = """\
         ▄▄▄▄
   ▄▄  ▄ ▀▀▀▀ ▄  ▄
▄▄▄ ▀▀▀▀      ▀▀▀▀ ▄▄
█████▄▄  ▀██▀  ▄▄█████
█████████▄▄▄▄█████████
██████████████████████
▀██████████████████▀▀▀
   ▀▀█████████████▄  ▄▄
     ▄▄▀▀████     ▀▀▀▀ ▄▄▄
    █████▄▄  ▀███▀ ▄▄█████
    █████████▄▄▄▄█████████
    ██████████████████████
    ▀████████████████████▀
       ▀▀████████████▀▀▀
           ▀▀████▀▀"""


def pause(s):
    if not FAST:
        time.sleep(s)


def day(v):
    return parse_instant(v).date().isoformat() if not hasattr(v, "date") else v.date().isoformat()


def cut(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def frame(body, title, cmd, caption=None):
    """Every scene sits in one panel: what it shows on top, the plain command that gives the same numbers below."""
    if caption:
        body = Group(body, Text(""), Text(caption, style="italic white"))
    return Panel(body, title=f"[bold {ACCENT}]{title}[/]", title_align="left", subtitle=f"[{GRAY}]same data: {cmd}[/]",
                 subtitle_align="left", border_style=ACCENT, box=box.ROUNDED, width=WIDTH, padding=(1, 2))


def logo():
    return Text(LOGO, style=ACCENT)


# --- scenes --------------------------------------------------------------------------------------

def title(_):
    words = Group(Text("FactBlock", style=f"bold {ACCENT}"), Text("Agent memory with a track record.", style="bold"), Text(""),
                  Text("1  Every read is as of a date", style="white"),
                  Text("2  Claims are linked by cause", style="white"),
                  Text("3  Nothing is overwritten", style="white"),
                  Text(""), Text("Real data: 2 years of a TV", style=GRAY), Text("stock picker's calls", style=GRAY))
    grid = Table.grid(padding=(0, 4))
    grid.add_row(logo(), Align(words, vertical="middle"))
    console.print(Panel(Align(grid, align="center"), border_style=ACCENT, box=box.ROUNDED, width=WIDTH, padding=(1, 2)))


def timeline(a):
    b = Bundle(a.bundle)
    said = sorted(n["asserted_at"] for n in b.nodes)
    lo, hi = said[0], said[-1]
    reads = []
    for d in a.as_of:
        s = scan(b, d)
        reads.append({"date": day(_as_of(d)), "t": _as_of(d), "known": s.nodes.num_rows,
                      "later": s.certificate.get("masked", {}).get("node", 0), "verdicts": s.resolutions.num_rows})
    bar_w = WIDTH - 14

    def pos(t):
        return round((min(max(t, lo), hi) - lo) / (hi - lo) * (bar_w - 1))

    def render(p, r, k):
        marker = Text(" " * p + "▼", style=f"bold {ACCENT}")
        label = Text(" " * max(0, min(p - 5, bar_w - 10)) + r["date"], style=f"bold {ACCENT}")
        line = Text("━" * p, style=ACCENT) + Text("━" * (bar_w - p), style=GRAY)
        ends = Text(f"{lo.date().isoformat()[:7]}" + " " * (bar_w - 14) + f"{hi.date().isoformat()[:7]}", style=GRAY)
        stats = Table.grid(expand=True)
        for _ in range(3):
            stats.add_column(justify="center")
        n = lambda v: f"{round(v * k):,}"  # noqa: E731
        stats.add_row(Text(n(r["known"]), style=f"bold {ACCENT}"), Text(n(r["later"]), style="bold white"),
                      Text(n(r["verdicts"]), style=f"bold {GREEN}"))
        stats.add_row(Text("blocks known", style=GRAY), Text("learned later: hidden", style=GRAY),
                      Text("verdicts known", style=GRAY))
        body = Group(label, marker, line, ends, Text(""), stats)
        return frame(body, "1 · Every read is as of a date", f"factblock scan {a.bundle} --as-of {r['date']}",
                     "The same files, read on different dates. What was learned later is hidden, not deleted.")

    with Live(render(0, reads[0], 0), console=console, refresh_per_second=24) as live:
        prev = 0
        for r in reads:
            target = pos(r["t"])
            for i in range(1, 13):
                live.update(render(prev + (target - prev) * i // 12, r, i / 12))
                pause(0.05)
            prev = target
            if r is not reads[-1]:
                pause(1.1)


FAMILY_STYLE = {"causal": f"bold {ACCENT}", "argumentative": "bold white", "temporal": f"bold {YELLOW}"}


def why_scene(a):
    b = Bundle(a.bundle)
    w = why(b, a.node_id, a.as_of[0], depth=2)
    fam = {**CORE_FAMILY, **b.edge_types}
    rows = sorted(w["chain"], key=lambda r: (r["depth"], r["asserted_at"]))

    def label(r):
        t = Text()
        if r["via"]:
            f = fam.get(r["via"]["edge_type"], "")
            t.append(f"{r['role'].replace('_', ' ')} ", style=FAMILY_STYLE.get(f, "bold"))
        t.append(f"{day(r['asserted_at'])}  ", style=GRAY)
        t.append(" ".join(r["statement"].split()), style="white" if r["depth"] else "bold white")   # wraps; the screen has the rows
        return t

    def render(k):
        tree, nodes = None, {}
        for r in rows[:k]:
            if r["depth"] == 0:
                tree = nodes[r["id"]] = Tree(label(r), guide_style=GRAY)
            else:
                nodes[r["id"]] = nodes[r["path"][-2]].add(label(r))
        legend = Text("causal", style=FAMILY_STYLE["causal"]) + Text("  ·  ", style=GRAY) + \
            Text("argumentative", style=FAMILY_STYLE["argumentative"]) + Text("  ·  ", style=GRAY) + \
            Text("temporal (replaced by)", style=FAMILY_STYLE["temporal"])
        cert = w["certificate"]
        hid = sum(cert.get("masked", {}).values())
        foot = Text(f"as of {day(cert['as_of'])}: {len(rows)} blocks in the chain, {hid} hidden on this walk", style=GRAY)
        return frame(Group(tree or Text(""), Text(""), legend, foot), "2 · Claims are linked by cause",
                     f"factblock why {a.bundle} {a.node_id} --as-of {day(cert['as_of'])}",
                     "Why did he say it, what supports it, and what replaced it later.")

    with Live(render(0), console=console, refresh_per_second=24) as live:
        for k in range(1, len(rows) + 1):
            live.update(render(k))
            if k < len(rows):
                pause(0.4)


def card(n, state, note, style):
    body = Group(Text(n["statement"], style="bold white" if style != "dim" else GRAY),
                 Text(f"said {day(n['asserted_at'])}", style=GRAY), Text(""), Text(note, style=style if style != "dim" else GRAY))
    return Panel(body, title=f"[{'bold ' + ACCENT if style != 'dim' else GRAY}]{n['id']} · {state}[/]", title_align="left",
                 border_style=ACCENT if style not in ("dim",) else GRAY, box=box.ROUNDED, width=34, padding=(0, 1))


def replaced(a):
    b = Bundle(a.bundle)
    old = next(n for n in b.nodes if n["id"] == a.node_id)
    succ_id = next(e["source_id"] for e in b.edges if e["edge_type"] == "SUPERSEDES" and e["target_id"] == a.node_id)
    new = next(n for n in b.nodes if n["id"] == succ_id)

    def render(d):
        s = scan(b, d)
        vis = {r["id"]: r for r in s.nodes.select(["id", "superseded_by"]).to_pylist()}
        verdicts = sorted((r for r in s.resolutions.to_pylist() if r["target_id"] == old["id"]), key=lambda r: r["decided_at"])
        v = f"verdict {verdicts[-1]['outcome']} · {day(verdicts[-1]['decided_at'])}" if verdicts else "no verdict yet"
        if vis.get(old["id"], {}).get("superseded_by") == new["id"]:
            left = card(old, "replaced", f"kept, superseded_by {new['id']}\n{v}", "dim")
            mid = Text("\n\nSUPERSEDES\n◀────────", style=f"bold {YELLOW}")
            right = card(new, "current", "the claim that stands", ACCENT)
        else:
            left = card(old, "current", v, ACCENT)
            mid = Text("\n\n\n", style=GRAY)
            right = card(new, "not known yet", "said after this date", "dim")
        row = Table.grid(padding=(0, 1))
        row.add_row(left, Align(mid, align="center"), right)
        head = Text(f"as of {day(_as_of(d))}", style=f"bold {ACCENT}")
        return frame(Group(head, Text(""), row), "3 · Replaced, not overwritten", f"factblock scan {a.bundle} --as-of {day(_as_of(d))}",
                     f"{old['id']} is never edited. {new['id']} replaces it; read an earlier date and {old['id']} stands again.")

    with Live(render(a.as_of[0]), console=console, refresh_per_second=24) as live:
        for d in a.as_of:
            live.update(render(d))
            if d != a.as_of[-1]:
                pause(2.0)


def verdict(a):
    b = Bundle(a.bundle)
    n = next(x for x in b.nodes if x["id"] == a.node_id)
    p = n.get("payload") or {}
    src = p.get("source") or {}
    if not a.as_of:   # the day before it was said, halfway to its verdict, the day after the verdict
        from datetime import timedelta
        said = n["known_at"]
        decided = min((r["known_at"] for r in b.resolutions if r["target_id"] == a.node_id), default=said + timedelta(days=60))
        a.as_of = [d.date().isoformat() for d in (said - timedelta(days=1), said + (decided - said) / 2, decided + timedelta(days=1))]

    def badge(d):
        nodes, _, res, _ = visible(b, d)
        if a.node_id not in {x["id"] for x in nodes}:
            said_later = n["asserted_at"] > _as_of(d)
            return (Text(" NOT SAID YET " if said_later else " NOT KNOWN YET ", style=f"bold black on {GRAY}"),
                    "the block does not exist as of this date" if said_later else f"said {day(n['asserted_at'])}, learned {day(n['known_at'])}")
        rs = sorted((r for r in res if r["target_id"] == a.node_id), key=lambda r: r["decided_at"])
        if not rs:
            return Text(" OPEN ", style=f"bold black on {YELLOW}"), "said, not settled yet"
        r = rs[-1]
        val = r["value"]
        ret = f"  {p.get('asset', '')} {val['return']:+.1%}" if isinstance(val, dict) and "return" in val else ""
        color = GREEN if r["outcome"] == "came_true" else RED
        return Text(f" {r['outcome'].replace('_', ' ').upper()}{ret} ", style=f"bold black on {color}"), f"decided {day(r['decided_at'])} · {cut((r.get('criteria') or '').split(':')[0], 64)}"

    def render(i):
        ticks = Text()
        for j, d in enumerate(a.as_of):
            ticks.append(f"  {day(_as_of(d))}  ", style=f"bold black on {ACCENT}" if j == i else GRAY)
            if j < len(a.as_of) - 1:
                ticks.append("──────", style=GRAY)
        bdg, why_ = badge(a.as_of[i])
        claim = Group(Text(f"“{n['statement']}”", style="bold white"),
                      Text(f"{p.get('speaker', '')}, {cut(src.get('channel', ''), 30)}, said {day(n['asserted_at'])}", style=GRAY))
        body = Group(Text("as of", style=GRAY), ticks, Text(""), claim, Text(""), bdg, Text(why_, style=GRAY))
        return frame(body, "4 · The verdict arrives later, with its own date", f"factblock recall {a.bundle} Nvidia --as-of {day(_as_of(a.as_of[i]))}",
                     "The verdict is its own row, known from the day it was decided. Before that: open.")

    with Live(render(0), console=console, refresh_per_second=24) as live:
        for i in range(len(a.as_of)):
            live.update(render(i))
            if i < len(a.as_of) - 1:
                pause(1.5)


def leak(a):
    r = json.loads(open(a.results).read())
    q, lq = r["questions"], r["leaked_questions"]

    def bar(frac, k, color):
        full = 40
        filled = round(full * frac * k)
        return Text("█" * filled, style=color) + Text("░" * (full - filled), style=GRAY)

    def render(k):
        t = Table.grid(padding=(0, 2))
        t.add_column(width=24)
        t.add_column()
        t.add_row(Text("recall ignoring time", style="bold white"), bar(lq / q, k, RED) + Text(f"  {lq / q * k:.1%}", style=f"bold {RED}"))
        t.add_row(Text(""), Text(f"{round(lq * k):,} of {q:,} answers rested on something learned later", style=GRAY))
        t.add_row(Text(""), Text(""))
        t.add_row(Text("recall as of the date", style="bold white"), bar(0, k, GREEN) + Text("  0.0%", style=f"bold {GREEN}"))
        t.add_row(Text(""), Text(f"0 of {q:,}: what it had not learned yet stays hidden", style=GRAY))
        src = Text(f"{r['corpus']}, top-{r['k']} recall, {q:,} questions", style=GRAY)
        return frame(Group(t, Text(""), src), "5 · Without a clock, memory leaks the future", f"factblock leak <bundle> <questions>  ({a.results})",
                     "A backtest or an audit that ignores when things were learned grades the agent on hindsight.")

    with Live(render(0), console=console, refresh_per_second=24) as live:
        for i in range(1, 21):
            live.update(render(i / 20))
            pause(0.06)


def end(_):
    words = Group(Text("FactBlock", style=f"bold {ACCENT}"), Text("Agent memory with a track record.", style="bold"), Text(""),
                  Text("pip install --pre factblock", style=f"bold white on grey15"), Text(""),
                  Text("github.com/factagora/factblock", style=f"bold {ACCENT}"),
                  Text("An open format: plain files, Apache-2.0.", style=GRAY))
    grid = Table.grid(padding=(0, 4))
    grid.add_row(logo(), Align(words, vertical="middle"))
    console.print(Panel(Align(grid, align="center"), border_style=ACCENT, box=box.ROUNDED, width=WIDTH, padding=(1, 2)))


SCENES = {"title": title, "timeline": timeline, "why": why_scene, "replaced": replaced, "verdict": verdict, "leak": leak, "end": end}


def main(argv=None):
    p = argparse.ArgumentParser(prog="factblock demo", description="an animated walkthrough of a bundle, for screens and recordings")
    p.add_argument("scene", choices=list(SCENES))
    p.add_argument("bundle", nargs="?", help="bundle folder (results file for leak)")
    p.add_argument("node_id", nargs="?")
    p.add_argument("--as-of", nargs="+", default=[])
    a = p.parse_args(argv)
    a.results = a.bundle
    SCENES[a.scene](a)


if __name__ == "__main__":
    main()
