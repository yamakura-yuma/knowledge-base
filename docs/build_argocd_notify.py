#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "markdown"]
# ///
"""docs/src/argocd-notify/*.md から docs/site/argocd-notify/ 以下の HTML を組む。

landscape / dotfiles とは独立した系統で、build.py の PAGES やナビには載せない。
既存ページの出力を変えないため、CSS もここに自前で持つ（色の変数だけ build.py と揃える）。

md の中の ```diagram ブロック（YAML）は、ビルド時に SVG へ描き直す。
図を手書きの SVG にせず宣言にしておくのは、方式ごとに十数枚ある図の描き方を揃えるため。

使い方:  uv run docs/build_argocd_notify.py   （build.py とは別に流す）
"""

from __future__ import annotations

import html
import pathlib
import re
import sys
import unicodedata

import markdown as md_lib
import yaml

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src" / "argocd-notify"
OUT = HERE / "site" / "argocd-notify"

# (ファイル名の stem, ナビのラベル)。index が概要、残りが方式ごとのページ。
PAGES = [
    ("index",         "概要"),
    ("recommended",   "推奨構成の詳細"),
    ("criteria",      "評価軸"),
    ("report",        "実測の報告書"),
    ("notifications", "① Notifications"),
    ("hooks",         "② PostSync / PostDelete"),
    ("knative",       "③ Knative"),
    ("argo-events",   "④ Argo Events"),
    ("finalizer",     "⑤ 自前 finalizer"),
    ("api-stream",    "⑥ API stream"),
]

CSS = """
  :root {
    color-scheme: light dark;
    --bg:#fbfbfa; --surface:#fff; --surface-2:#f4f4f2; --ink:#1c1c1a; --ink-2:#57564f;
    --ink-3:#8a8880; --line:#e2e1dc;
    --l1:#2f5fa8; --l2:#8a5a12; --l3:#2f6e4f; --l0:#6b4f8a;
    --hot:#b4342a; --ok:#2f6e4f; --stale:#8a6a12; --dead:#9b9a94;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    --sans: ui-sans-serif, system-ui, -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#16161a; --surface:#1e1e23; --surface-2:#26262c; --ink:#eceae6; --ink-2:#b3b1ab;
      --ink-3:#807e78; --line:#33333a;
      --l1:#8fb3ea; --l2:#d8b25c; --l3:#7fc7a0; --l0:#b79ae0;
      --hot:#f2837a; --ok:#7fc7a0; --stale:#d8b25c; --dead:#5c5b57;
    }
  }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
         line-height:1.75; font-size:15px; }
  .wrap { max-width:1120px; margin:0 auto; padding:48px 20px 96px; }
  header { border-bottom:1px solid var(--line); padding-bottom:28px; margin-bottom:8px; }
  h1 { font-size:26px; line-height:1.4; margin:0 0 10px; letter-spacing:-.01em; }
  .sub { color:var(--ink-2); margin:0; font-size:14px; }
  h2 { font-size:19px; margin:56px 0 6px; padding-top:28px; border-top:1px solid var(--line); }
  h3 { font-size:15px; margin:28px 0 8px; }
  p { margin:10px 0; color:var(--ink-2); }
  p strong, li strong, td strong { color:var(--ink); font-weight:600; }
  a { color:var(--l1); }
  code { font-family:var(--mono); font-size:.88em; background:var(--surface-2);
         padding:1px 5px; border-radius:4px; }
  pre { font-family:var(--mono); font-size:12.5px; line-height:1.7; background:var(--surface);
        border:1px solid var(--line); border-radius:8px; padding:14px 16px; overflow-x:auto; }
  pre code { background:none; padding:0; }
  ul, ol { margin:10px 0; padding-left:22px; color:var(--ink-2); }
  li { margin:5px 0; }
  table { width:100%; border-collapse:collapse; margin:16px 0; font-size:13px; }
  th, td { text-align:left; padding:7px 9px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--ink-3); font-weight:600; font-size:11.5px; letter-spacing:.03em; }
  .tblwrap { overflow-x:auto; }
  .nav { display:flex; flex-wrap:wrap; gap:4px; margin:18px 0 8px;
         padding-bottom:14px; border-bottom:1px solid var(--line); }
  .nav a { font-family:var(--mono); font-size:11.5px; padding:4px 11px; border-radius:5px;
           border:1px solid var(--line); color:var(--ink-2); text-decoration:none;
           background:var(--surface); }
  .nav a:hover { border-color:var(--ink-3); }
  .nav a.on { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  .dgm { border:1px solid var(--line); border-radius:8px; background:var(--surface);
         padding:16px 18px; margin:18px 0; }
  .dgm > .cap { font-family:var(--mono); font-size:11px; color:var(--ink-3); margin:-4px 0 12px; }
  .pagegrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(235px,1fr)); gap:10px; margin:16px 0; }
  .pcard { display:block; padding:13px 15px; border:1px solid var(--line); border-radius:8px;
           background:var(--surface); text-decoration:none; }
  .pcard:hover { border-color:var(--ink-3); }
  .pcard b { display:block; color:var(--ink); font-size:14px; margin-bottom:3px; }
  .pcard span { color:var(--ink-3); font-size:12px; }
  footer { margin-top:64px; padding-top:24px; border-top:1px solid var(--line);
           color:var(--ink-3); font-size:12.5px; }

  /* SVG 図。色は CSS 変数から取るので、明暗どちらのテーマでも読める */
  .fig { display:block; width:100%; height:auto; margin:4px 0; font-family:var(--sans); }
  .fig text { fill:var(--ink-2); font-size:12px; }
  .fig .t-ink { fill:var(--ink); font-weight:600; }
  .fig .t-mono { font-family:var(--mono); font-size:10.5px; fill:var(--ink-3); }
  .fig .t-zone { font-family:var(--mono); font-size:11px; fill:var(--ink-3); font-weight:600; }
  .fig .zone { fill:none; stroke:var(--line); stroke-width:1.2; stroke-dasharray:5 4; }
  .fig .zone-platform { fill:color-mix(in srgb, var(--l1) 5%, transparent); stroke:var(--l1); }
  .fig .zone-app { fill:color-mix(in srgb, var(--l3) 6%, transparent); stroke:var(--l3); }
  .fig .zone-ext { fill:var(--surface-2); }
  .fig .nd { fill:var(--bg); stroke:var(--ink-3); stroke-width:1.2; }
  .fig .nd-crd { fill:var(--surface-2); stroke:var(--ink-3); stroke-dasharray:3 2; }
  .fig .nd-state { fill:color-mix(in srgb, var(--l2) 12%, var(--bg)); stroke:var(--l2); stroke-width:1.4; }
  .fig .nd-ext { fill:var(--bg); stroke:var(--l3); stroke-width:1.6; }
  .fig .nd-app { fill:var(--surface-2); stroke:var(--ink); stroke-width:1.4; }
  .fig .nd-bad { fill:var(--bg); stroke:var(--hot); stroke-width:1.6; }
  .fig .ln { stroke:var(--ink-3); stroke-width:1.4; fill:none; }
  .fig .ln-watch { stroke:var(--l1); stroke-dasharray:6 3; }
  .fig .ln-http { stroke:var(--ink-2); }
  .fig .ln-ce { stroke:var(--l3); stroke-width:2; }
  .fig .ln-patch { stroke:var(--l2); stroke-dasharray:2 3; stroke-width:1.8; }
  .fig .ln-bad { stroke:var(--hot); stroke-dasharray:4 3; }
  .fig .ln-rbac { stroke:var(--ink-3); stroke-dasharray:1 3; }
  .fig .ln-l1 { stroke:var(--l1); } .fig .ln-l3 { stroke:var(--l3); } .fig .ln-hot { stroke:var(--hot); }
  .fig .ln-dash { stroke-dasharray:4 3; }
  .fig .ar { fill:var(--ink-3); }
  .fig .ar-watch { fill:var(--l1); } .fig .ar-http { fill:var(--ink-2); } .fig .ar-ce { fill:var(--l3); }
  .fig .ar-patch { fill:var(--l2); } .fig .ar-bad { fill:var(--hot); } .fig .ar-rbac { fill:var(--ink-3); }
  .fig .lbl-bg { fill:var(--surface); }
  .fig .band { fill:var(--surface-2); }
  .fig .mk-ok { fill:var(--ok); } .fig .mk-bad { fill:var(--hot); } .fig .mk-mid { fill:var(--stale); }
  .fig .t-bad { fill:var(--hot); }
  .fig .divider { stroke:var(--ink); stroke-width:1.6; stroke-dasharray:8 5; }

  /* グラレコ。手描き風に、線を太く、色を蛍光ペン風にする */
  .gr .fig text { font-size:13px; fill:var(--ink); }
  .gr .gr-title { font-size:21px; font-weight:700; fill:var(--ink); }
  .gr .gr-h { font-size:16px; font-weight:700; fill:var(--ink); }
  .gr .gr-m { font-size:14px; fill:var(--ink); }
  .gr .gr-s { font-size:12.5px; fill:var(--ink-2); }
  .gr .gr-b { font-weight:700; }
  .gr .gr-big { font-size:64px; font-weight:800; }
  .gr .gr-red { fill:var(--hot); }
  .gr .gr-code { font-family:var(--mono); }
  .gr .gr-hl { fill:color-mix(in srgb, var(--stale) 30%, transparent); }
  .gr .gr-body { fill:color-mix(in srgb, var(--l1) 18%, var(--bg)); stroke:var(--ink); stroke-width:2.2; }
  .gr .gr-dot { fill:var(--ink); }
  .gr .gr-line { fill:none; stroke:var(--ink); stroke-width:2.2; stroke-linecap:round; }
  .gr .gr-line2 { fill:none; stroke:var(--ink); stroke-width:3; stroke-linecap:round; }
  .gr .gr-bubble { fill:var(--surface); stroke:var(--ink); stroke-width:2; }
  .gr .gr-warn { fill:color-mix(in srgb, var(--hot) 16%, var(--bg)); stroke:var(--hot); stroke-width:3; stroke-linejoin:round; }
  .gr .gr-sep { fill:none; stroke:var(--ink-3); stroke-width:1.5; stroke-dasharray:2 6; stroke-linecap:round; }
  .gr .gr-lock { fill:color-mix(in srgb, var(--l2) 25%, var(--bg)); stroke:var(--ink); stroke-width:2.4; }
  .gr .gr-note { fill:color-mix(in srgb, var(--stale) 28%, var(--bg)); stroke:var(--ink-3); stroke-width:1; }
  .gr .gr-note2 { fill:color-mix(in srgb, var(--l3) 22%, var(--bg)); stroke:var(--ink-3); stroke-width:1; }
  .gr .gr-pill { fill:color-mix(in srgb, var(--l1) 14%, var(--bg)); stroke:var(--ink); stroke-width:2.2; }
  .gr .gr-env { fill:var(--surface); stroke:var(--ink); stroke-width:2.2; }
  .gr .gr-arrow { fill:none; stroke:var(--ink); stroke-width:2.6; stroke-linecap:round; }
  .gr .gr-ink { fill:var(--ink); }
  .gr .gr-head { fill:color-mix(in srgb, var(--l1) 30%, var(--bg)); stroke:var(--ink); stroke-width:2; }
  .gr .gr-head2 { fill:color-mix(in srgb, var(--l3) 30%, var(--bg)); }

  .gr .gr-ok { fill:none; stroke:var(--ok); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; }
  .gr .gr-ng { fill:none; stroke:var(--hot); stroke-width:3; stroke-linecap:round; }
  .gr .gr-okc { fill:color-mix(in srgb, var(--ok) 18%, var(--bg)); stroke:var(--ok); stroke-width:2.2; }
  .gr .gr-ngc { fill:color-mix(in srgb, var(--hot) 16%, var(--bg)); stroke:var(--hot); stroke-width:2.2; }
  .gr .gr-panel { fill:var(--surface); stroke:var(--ink); stroke-width:1.8; }

  /* 評価マトリクス。◎○△× を背景色でも分ける */
  table.mx { font-size:12.5px; }
  table.mx td, table.mx th { text-align:center; }
  table.mx td:first-child, table.mx th:first-child { text-align:left; white-space:nowrap; }
  table.mx th { white-space:normal; min-width:4.5em; vertical-align:bottom; }
  table.mx td small { display:block; color:var(--ink-3); font-size:10.5px; line-height:1.35;
                      margin-top:2px; font-family:var(--mono); }
  .g3, .g2, .g1, .g0 { display:inline-block; min-width:2.2em; padding:1px 6px; border-radius:4px;
                       font-family:var(--mono); font-size:12px; font-weight:600; }
  .g3 { background:color-mix(in srgb, var(--ok) 22%, transparent); color:var(--ok); }
  .g2 { background:color-mix(in srgb, var(--l1) 16%, transparent); color:var(--l1); }
  .g1 { background:color-mix(in srgb, var(--stale) 20%, transparent); color:var(--stale); }
  .g0 { background:color-mix(in srgb, var(--hot) 18%, transparent); color:var(--hot); }
"""

GRADE = {"◎": "g3", "○": "g2", "△": "g1", "×": "g0"}


# ---------------------------------------------------------------- 図

def _w(text: str, size: float) -> float:
    """文字列の描画幅の概算。全角はフォントサイズ、半角はその 0.6 倍で数える。"""
    return sum(size if unicodedata.east_asian_width(c) in "WF" else size * 0.6 for c in text)


def _clip(cx, cy, tx, ty, box):
    """(cx,cy) から (tx,ty) へ向かう線が、box の縁と交わる点。"""
    x, y, w, h = box
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    ts = []
    if dx:
        ts += [((x + (w if dx > 0 else 0)) - cx) / dx]
    if dy:
        ts += [((y + (h if dy > 0 else 0)) - cy) / dy]
    t = min(t for t in ts if t > 0)
    return cx + dx * t, cy + dy * t


def diagram(spec: dict, warnings: list[str], where: str) -> str:
    """宣言（zones / nodes / edges / notes）を SVG にする。

    zones: 枠（namespace や Platform / App の区画）。kind は platform / app / ext / plain
    nodes: 箱。kind は comp（Pod・コントローラ）/ crd / state（状態を持つ場所）/ ext / app / bad
    edges: 矢印。kind は watch / http / ce / patch / bad / rbac。via で折れ点を指定できる
    """
    W = spec.get("width", 1000)
    H = spec["height"]
    esc = html.escape
    boxes = {}
    out = [f'<svg class="fig" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(spec.get("title", ""))}">']
    out.append("<defs>" + "".join(
        f'<marker id="a-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="ar-{k}"/></marker>'
        for k in ("watch", "http", "ce", "patch", "bad", "rbac")) + "</defs>")

    for z in spec.get("zones", []):
        x, y, w, h = z["box"]
        out.append(f'<rect class="zone zone-{z.get("kind", "plain")}" x="{x}" y="{y}" width="{w}" '
                   f'height="{h}" rx="8"/>')
        out.append(f'<text class="t-zone" x="{x + 10}" y="{y + 16}">{esc(z["label"])}</text>')
        if _w(z["label"], 11) > w - 14:
            warnings.append(f"{where}: 枠の見出しがはみ出す: {z['label']}")

    for d in spec.get("dividers", []):
        x1, y1, x2, y2 = d["line"]
        out.append(f'<line class="divider" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')
        for t in d.get("labels", []):
            out.append(f'<text class="t-ink" x="{t[0]}" y="{t[1]}">{esc(t[2])}</text>')

    for n in spec.get("nodes", []):
        x, y, w, h = n["box"]
        boxes[n["id"]] = (x, y, w, h)
        out.append(f'<rect class="nd nd-{n.get("kind", "comp")}" x="{x}" y="{y}" width="{w}" '
                   f'height="{h}" rx="6"/>')
        lines = [("t-ink", 12, n["label"])] + [("", 11.5, s) for s in n.get("lines", [])] \
            + [("t-mono", 10.5, s) for s in n.get("mono", [])]
        ty = y + 19
        for cls, size, text in lines:
            out.append(f'<text class="{cls}" x="{x + 10}" y="{ty}">{esc(text)}</text>')
            if _w(text, size) > w - 16:
                warnings.append(f"{where}: 箱の文字がはみ出す: {text}")
            ty += 16
        if ty - 16 + 6 > y + h:
            warnings.append(f"{where}: 箱の行が収まらない: {n['label']}")

    for e in spec.get("edges", []):
        a, b = boxes[e["from"]], boxes[e["to"]]
        kind = e.get("kind", "http")
        via = [tuple(p) for p in e.get("via", [])]
        ac = (a[0] + a[2] / 2, a[1] + a[3] / 2)
        bc = (b[0] + b[2] / 2, b[1] + b[3] / 2)
        first = via[0] if via else bc
        last = via[-1] if via else ac
        p0 = _clip(*ac, *first, a)
        p1 = _clip(*bc, *last, b)
        pts = [p0, *via, p1]
        d = "M" + " L".join(f"{px:.0f},{py:.0f}" for px, py in pts)
        both = ' marker-start="url(#a-%s)"' % kind if e.get("both") else ""
        out.append(f'<path class="ln ln-{kind}" d="{d}" marker-end="url(#a-{kind})"{both}/>')
        if e.get("label"):
            i = len(pts) // 2
            if len(pts) % 2 == 0:
                mx, my = (pts[i - 1][0] + pts[i][0]) / 2, (pts[i - 1][1] + pts[i][1]) / 2
            else:
                mx, my = pts[i]
            dx, dy = e.get("dx", 0), e.get("dy", 0)
            lw = _w(e["label"], 10.5) + 8
            out.append(f'<rect class="lbl-bg" x="{mx + dx - lw / 2:.0f}" y="{my + dy - 11:.0f}" '
                       f'width="{lw:.0f}" height="15" rx="3"/>')
            out.append(f'<text class="t-mono" x="{mx + dx:.0f}" y="{my + dy:.0f}" '
                       f'text-anchor="middle">{esc(e["label"])}</text>')

    for t in spec.get("notes", []):
        out.append(f'<text class="t-mono" x="{t[0]}" y="{t[1]}">{esc(t[2])}</text>')

    if spec.get("legend", True):
        items = [("watch", "watch"), ("http", "HTTP"), ("ce", "CloudEvent"),
                 ("patch", "書き込み（annotation・finalizer）"), ("rbac", "権限付与")]
        items = [i for i in items if any(e.get("kind", "http") == i[0] for e in spec.get("edges", []))]
        lx = 20
        for k, lab in items:
            out.append(f'<path class="ln ln-{k}" d="M{lx},{H - 10} L{lx + 28},{H - 10}" '
                       f'marker-end="url(#a-{k})"/>')
            out.append(f'<text class="t-mono" x="{lx + 34}" y="{H - 6}">{esc(lab)}</text>')
            lx += 34 + _w(lab, 10.5) + 22
        if any(n.get("kind") == "state" for n in spec.get("nodes", [])):
            out.append(f'<rect class="nd nd-state" x="{lx}" y="{H - 18}" width="16" height="12" rx="2"/>')
            out.append(f'<text class="t-mono" x="{lx + 22}" y="{H - 6}">状態を持つ場所</text>')
    out.append("</svg>")
    cap = spec.get("caption")
    cap_html = f'<div class="cap">{esc(cap)}</div>' if cap else ""
    return f'<div class="dgm">{cap_html}{"".join(out)}</div>'


def _icon(kind: str, x: float, y: float) -> str:
    """パネル右上の小さな手描き風アイコン。"""
    if kind == "ok":
        return (f'<circle class="gr-okc" cx="{x}" cy="{y}" r="16"/>'
                f'<path class="gr-ok" d="M{x-8},{y} L{x-2},{y+7} L{x+9},{y-7}"/>')
    if kind == "bad":
        return (f'<circle class="gr-ngc" cx="{x}" cy="{y}" r="16"/>'
                f'<path class="gr-ng" d="M{x-7},{y-7} L{x+7},{y+7} M{x+7},{y-7} L{x-7},{y+7}"/>')
    if kind == "warn":
        return (f'<path class="gr-warn" d="M{x},{y-17} L{x+18},{y+14} L{x-18},{y+14} Z"/>'
                f'<text class="gr-h gr-red" x="{x}" y="{y+10}" text-anchor="middle">!</text>')
    if kind == "key":
        return (f'<rect class="gr-lock" x="{x-14}" y="{y-4}" width="28" height="22" rx="4"/>'
                f'<path class="gr-line2" d="M{x-8},{y-4} v-6 a8,8 0 0 1 16,0 v6"/>')
    if kind == "eye":
        return (f'<path class="gr-line2" d="M{x-18},{y} Q{x},{y-16} {x+18},{y} Q{x},{y+16} {x-18},{y} Z"/>'
                f'<circle class="gr-dot" cx="{x}" cy="{y}" r="5"/>')
    if kind == "people":
        return (f'<circle class="gr-head" cx="{x-9}" cy="{y-6}" r="7"/><circle class="gr-head gr-head2" cx="{x+9}" cy="{y-6}" r="7"/>'
                f'<path class="gr-line2" d="M{x-19},{y+14} q10,-12 20,0 M{x-1},{y+14} q10,-12 20,0"/>')
    return (f'<circle class="gr-okc" cx="{x}" cy="{y}" r="16"/>'
            f'<path class="gr-arrow" d="M{x-8},{y} L{x+8},{y} M{x+2},{y-6} L{x+8},{y} L{x+2},{y+6}"/>')


def grareco(spec: dict, warnings: list[str], where: str) -> str:
    """ページ冒頭のグラレコ。人物と吹き出し（問い）→ 3 枚のパネル → 結論の帯。"""
    esc = html.escape
    W, H = 1000, 430
    o = [f'<svg class="fig" viewBox="0 0 {W} {H}" role="img" aria-label="グラレコ: {esc(spec["title"])}">',
         '<defs><marker id="grm-ar" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" '
         'orient="auto"><path d="M0,0 L10,5 L0,10 z" class="gr-ink"/></marker></defs>',
         '<path class="gr-hl" d="M40,22 C260,12 620,30 960,18 L962,52 C640,62 300,46 38,58 Z"/>',
         f'<text class="gr-title" x="500" y="46" text-anchor="middle">{esc(spec["title"])}</text>']
    if _w(spec["title"], 21) > 900:
        warnings.append(f"{where}: グラレコの題がはみ出す")
    # 人物と吹き出し
    o.append('<rect class="gr-body" x="50" y="92" width="80" height="70" rx="12"/>'
             '<circle class="gr-dot" cx="75" cy="118" r="4"/><circle class="gr-dot" cx="105" cy="118" r="4"/>'
             '<path class="gr-line" d="M76,140 Q90,132 104,140"/>')
    o.append('<path class="gr-bubble" d="M170,78 h560 a12,12 0 0 1 12,12 v58 a12,12 0 0 1 -12,12 h-530 '
             'l-34,16 l10,-16 h-6 a12,12 0 0 1 -12,-12 v-58 a12,12 0 0 1 12,-12 z"/>')
    for i, line in enumerate(spec["say"]):
        o.append(f'<text class="gr-m" x="190" y="{110 + i * 24}">{esc(line)}</text>')
        if _w(line, 14) > 540:
            warnings.append(f"{where}: 吹き出しがはみ出す: {line}")
    # 3 枚のパネル
    for i, pnl in enumerate(spec["panels"]):
        x = 30 + i * 325
        o.append(f'<rect class="gr-panel" x="{x}" y="190" width="290" height="150" rx="10" '
                 f'transform="rotate({(-1, 0.8, -0.6)[i % 3]} {x + 145} 265)"/>')
        o.append(_icon(pnl.get("icon", "flow"), x + 258, 218))
        o.append(f'<text class="gr-h" x="{x + 16}" y="222">{esc(pnl["head"])}</text>')
        if _w(pnl["head"], 16) > 220:
            warnings.append(f"{where}: パネルの見出しがはみ出す: {pnl['head']}")
        for j, line in enumerate(pnl.get("lines", [])):
            o.append(f'<text class="gr-s" x="{x + 16}" y="{254 + j * 22}">{esc(line)}</text>')
            if _w(line, 12.5) > 262:
                warnings.append(f"{where}: パネルの文がはみ出す: {line}")
        if i < len(spec["panels"]) - 1:
            o.append(f'<path class="gr-arrow" d="M{x + 294},265 C{x + 305},255 {x + 312},255 {x + 322},265" '
                     'marker-end="url(#grm-ar)"/>')
    # 結論の帯
    o.append('<ellipse class="gr-pill" cx="500" cy="388" rx="470" ry="30"/>')
    o.append(f'<text class="gr-m gr-b" x="500" y="393" text-anchor="middle">{esc(spec["bottom"])}</text>')
    if _w(spec["bottom"], 14) > 880:
        warnings.append(f"{where}: 結論の帯がはみ出す")
    o.append("</svg>")
    return f'<div class="dgm gr"><div class="cap">グラレコ: このページを 1 枚で</div>{"".join(o)}</div>'


def render_diagrams(text: str, warnings: list[str], where: str) -> str:
    def sub(m):
        return diagram(yaml.safe_load(m.group(1)), warnings, where)

    def sub_gr(m):
        return grareco(yaml.safe_load(m.group(1)), warnings, where)
    text = re.sub(r"^```grareco\n(.*?)^```\n", sub_gr, text, flags=re.S | re.M)
    return re.sub(r"^```diagram\n(.*?)^```\n", sub, text, flags=re.S | re.M)


def grade_cells(fragment: str) -> str:
    """マトリクス表の先頭の ◎○△× を色付きのバッジにする。table.mx の中だけが対象。"""
    def cell(m):
        body = m.group(1)
        g = body[:1]
        if g in GRADE:
            rest = body[1:].strip()
            note = f"<small>{rest}</small>" if rest else ""
            return f'<td><span class="{GRADE[g]}">{g}</span>{note}</td>'
        return m.group(0)

    def table(m):
        return re.sub(r"<td>(.*?)</td>", cell, m.group(0), flags=re.S)
    return re.sub(r'<table class="mx">.*?</table>', table, fragment, flags=re.S)


# ---------------------------------------------------------------- ページ

def nav(active: str) -> str:
    items = "".join(f'<a href="{s}.html" class="{"on" if s == active else ""}">{html.escape(l)}</a>'
                    for s, l in PAGES)
    return f'<nav class="nav">{items}</nav>'


def page(stem: str, label: str, warnings: list[str]) -> str:
    src = SRC / f"{stem}.md"
    if not src.exists():
        warnings.append(f"原稿が無い: docs/src/argocd-notify/{src.name}")
        return ""
    raw = src.read_text(encoding="utf-8")
    title, sub, body_md = label, "", raw
    if raw.startswith("# "):
        head, _, rest = raw.partition("\n")
        title = head[2:].strip()
        rest = rest.lstrip()
        if rest.startswith("> "):
            line, _, body_md = rest.partition("\n")
            sub = line[2:].strip()
        else:
            body_md = rest
    body_md = render_diagrams(body_md, warnings, src.name)
    conv = md_lib.Markdown(extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
    body = grade_cells(conv.convert(body_md))
    sub_html = md_lib.markdown(sub).removeprefix("<p>").removesuffix("</p>")
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{html.escape(title)}</h1>
  <p class="sub">{sub_html}</p>
</header>
{nav(stem)}
{body}
<footer>
  正本は <code>docs/src/argocd-notify/*.md</code>。この HTML は <code>docs/build_argocd_notify.py</code>
  の生成物なので直接編集しないこと。実測は kind 上の Argo CD v3.5.3 で行い、条件は概要ページの末尾に書いた。
  GitHub の数字は 2026-09-25 に <code>gh api</code> で取った値。
</footer>
</div>
</body>
</html>
"""


def main() -> int:
    warnings: list[str] = []
    written, unchanged = [], []
    OUT.mkdir(parents=True, exist_ok=True)
    expected = set()
    for stem, label in PAGES:
        text = page(stem, label, warnings)
        if not text:
            continue
        f = OUT / f"{stem}.html"
        expected.add(f.name)
        if f.exists() and f.read_text(encoding="utf-8") == text:
            unchanged.append(f.name)
        else:
            f.write_text(text, encoding="utf-8")
            written.append(f.name)
    for f in OUT.glob("*.html"):
        if f.name not in expected:
            f.unlink()
            written.append(f"{f.name}（削除）")
    if written:
        print("argocd-notify 生成: " + "、".join(written))
    if unchanged:
        print(f"argocd-notify 変更なし: {len(unchanged)} ページ")
    if warnings:
        print(f"\n== argocd-notify 警告 {len(warnings)} 件 ==")
        for w in sorted(set(warnings)):
            print("  " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
