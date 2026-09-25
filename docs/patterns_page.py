"""話題③ ハーネスのパターン・カタログを描く。build.py から呼ぶ。

既存の話題（landscape / tool-research）とは完全に別系統にしてある。PAGES にもナビにも
入れず、既存ページが埋め込む CSS の文字列も変えない。CSS は build.CSS を読むだけで、
このページ固有の分は後ろに足す。

正本:  docs/src/patterns/catalog.yaml（パターンと出典）
       docs/src/data/candidates.json（collect_candidates.py が集めた出典候補）
"""

from __future__ import annotations

import html
import json
import pathlib

import markdown as md_lib
import yaml

LAYERS = ["prompt", "harness", "loop", "graph"]
LAYER_JA = {"prompt": "プロンプト", "harness": "ハーネス", "loop": "ループ", "graph": "グラフ"}
LAYER_NOTE = {
    "prompt": "モデルに渡す文面",
    "harness": "モデルを囲む環境",
    "loop": "反復と停止条件",
    "graph": "作業フローの形",
}
STATES = ["adopted", "partial", "missing", "watch"]
STATE_JA = {"adopted": "採用済", "partial": "部分的", "missing": "未採用", "watch": "観察"}
# 図に出す 3 状態。観察は採否を決めていないので、棒の外に数だけ出す。
BAR_STATES = ["adopted", "partial", "missing"]

PAGE_CSS = """
  .pt-fig { margin:20px 0 8px; }
  .pt-fig svg { width:100%; height:auto; display:block; }
  .pt-fig figcaption { font-size:12.5px; color:var(--ink-3); margin-top:6px; }
  .pt { --adopted:#2f6e4f; --partial:#b07a12; --missing:#b4342a; --watch:#8a8880;
        --paper:#fffdf6; --pen:#2b2a26; --hl:#ffe98a; }
  @media (prefers-color-scheme: dark) {
    .pt { --adopted:#7fc7a0; --partial:#d8b25c; --missing:#f2837a; --watch:#807e78;
          --paper:#23221e; --pen:#eceae6; --hl:#6b5a12; }
  }
  .pt svg text { font-family:var(--sans); fill:var(--ink); }
  .pt svg .mut { fill:var(--ink-3); }
  .pt svg .ink2 { fill:var(--ink-2); }
  .pt svg .pen { stroke:var(--pen); fill:none; stroke-linecap:round; stroke-linejoin:round; }
  .st { display:inline-block; font-size:11.5px; padding:1px 8px; border-radius:10px;
        border:1px solid currentColor; white-space:nowrap; }
  .st-adopted { color:var(--adopted); } .st-partial { color:var(--partial); }
  .st-missing { color:var(--missing); } .st-watch { color:var(--watch); }
  .ly { font-family:var(--mono); font-size:11.5px; color:var(--ink-2); white-space:nowrap; }
  .pt td ul { margin:0; padding-left:1em; }
  .pt td small { color:var(--ink-3); }
  .pt-filters { position:absolute; opacity:0; pointer-events:none; }
  .pt-fbar { display:flex; flex-wrap:wrap; gap:6px; margin:12px 0 4px; }
  .pt-fbar label { font-family:var(--mono); font-size:11.5px; padding:3px 10px; border-radius:5px;
                   border:1px solid var(--line); background:var(--surface); cursor:pointer; color:var(--ink-2); }
  #pf-all:checked ~ .pt-fbar label[for=pf-all],
  #pf-missing:checked ~ .pt-fbar label[for=pf-missing] { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  #pf-missing:checked ~ .tablewrap tr.r:not(.s-missing) { display:none; }
  .pt .finding { color:var(--ink); margin:4px 0 12px; }
  .wb { --wb-ink:#1f1f1f; --wb-blue:#1d5fd0; --wb-red:#d7372b; }
  .wb .wb-board { fill:#fdfdfb; stroke:#c9c8c2; stroke-width:6; }
  .wb .wb-line { fill:none; stroke:var(--wb-ink); stroke-linecap:round; stroke-linejoin:round; }
  .wb .wb-red { fill:none; stroke:var(--wb-red); stroke-linecap:round; stroke-linejoin:round; }
  .wb .wb-blue { fill:none; stroke:var(--wb-blue); }
  .wb .wb-fill-blue { fill:var(--wb-blue); }
  .wb .wb-dot { fill:#fdfdfb; stroke:var(--wb-ink); stroke-width:2; }
  .wb .wb-note { fill:#fff; stroke:var(--wb-blue); stroke-width:2.2; }
  .pt svg.wb text.wb-t { fill:var(--wb-ink);
    font-family:'Klee','Klee One','Yomogi','Zen Kurenaido','UD Digi Kyokasho NK-R','UD デジタル 教科書体 NK-R',
                'Segoe Print','Comic Sans MS',cursive,var(--sans); font-weight:600; }
  .pt svg.wb text.wb-tr { fill:var(--wb-red); }
  .pt h2.first { border-top:none; padding-top:4px; }
  .picks { margin:8px 0 6px; padding-left:1.4em; }
  .picks li { margin:0 0 10px; }
  .picks .why { color:var(--ink-2); font-size:13.5px; }
  .pick-crit { font-size:12px; color:var(--ink-3); }
  .gc { font-family:var(--mono); font-size:11px; color:var(--ink-3); white-space:nowrap; }
  .opinion { font-size:11.5px; font-weight:600; color:var(--missing); border:1px solid currentColor;
             border-radius:10px; padding:1px 8px; margin-left:6px; vertical-align:middle; }
  .legend-crit { display:grid; grid-template-columns:auto 1fr; gap:4px 12px; font-size:13px;
                 color:var(--ink-2); margin:8px 0 0; }
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def load(src: pathlib.Path) -> tuple[dict, dict]:
    cat = yaml.safe_load((src / "patterns" / "catalog.yaml").read_text(encoding="utf-8"))
    cp = src / "data" / "candidates.json"
    cand = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
    return cat, cand


def check(cat: dict, warnings: list[str]) -> None:
    for l in LAYERS:
        if not (cat.get("layer_findings") or {}).get(l):
            warnings.append(f"層の要約（layer_findings）が無い: {l}")
    srcs = {s["id"] for s in cat.get("sources", [])}
    seen = set()
    for p in cat.get("patterns", []):
        pid = p.get("id")
        if pid in seen:
            warnings.append(f"パターン id が重複: {pid}")
        seen.add(pid)
        if p.get("layer") not in LAYERS:
            warnings.append(f"パターンの層が不正: {pid} {p.get('layer')}")
        if p.get("state") not in STATES:
            warnings.append(f"パターンの状態が不正: {pid} {p.get('state')}")
        refs = p.get("sources") or []
        if not refs:
            warnings.append(f"パターンに出典が無い: {pid}")
        for r in refs:
            if r.get("source") not in srcs:
                warnings.append(f"パターンが未知の出典を参照: {pid} → {r.get('source')}")
            if not str(r.get("url", "")).startswith("https://"):
                warnings.append(f"出典リンクが無い: {pid} ({r.get('source')})")
        if p.get("state") in ("missing", "partial"):
            if p.get("impact") not in IMPACT_JA or p.get("effort") not in EFFORT_JA or not (p.get("gain") and p.get("cost")):
                warnings.append(f"未採用・部分的なのに効果と手間（impact/effort/gain/cost）が無い: {pid}")
        if p.get("state") in ("adopted", "partial") and not p.get("self"):
            warnings.append(f"採用済・部分的なのに自作側の根拠が無い: {pid}")


def counts(pats: list[dict]) -> dict[str, dict[str, int]]:
    c = {l: {s: 0 for s in STATES} for l in LAYERS}
    for p in pats:
        if p.get("layer") in c and p.get("state") in STATES:
            c[p["layer"]][p["state"]] += 1
    return c


# ---------------------------------------------------------------- 図 1: 層 × 状態

def fig_counts(c: dict) -> str:
    """層ごとの横積み棒。どの層が薄いかを見る図なので、軸は件数ではなく割合にしない。"""
    W, left, right, top, rowh, barh = 760, 150, 200, 46, 52, 26
    mx = max(sum(c[l][s] for s in BAR_STATES) for l in LAYERS) or 1
    unit = (W - left - right) / mx
    out = [f'<svg viewBox="0 0 {W} {top + rowh * 4 + 16}" role="img" '
           f'aria-label="層ごとの採用状況の件数">']
    # 凡例は上に 1 行。色だけに頼らないよう、棒の中にも件数を書く。
    x = left
    for s in BAR_STATES + ["watch"]:
        out.append(f'<rect x="{x}" y="10" width="12" height="12" rx="2" fill="var(--{s})"/>'
                   f'<text x="{x + 17}" y="21" font-size="12.5" class="ink2">{STATE_JA[s]}'
                   f'{"（棒の外）" if s == "watch" else ""}</text>')
        x += 92 if s != "missing" else 92
    for i, l in enumerate(LAYERS):
        y = top + i * rowh
        out.append(f'<text x="{left - 12}" y="{y + 18}" text-anchor="end" font-size="14" '
                   f'font-weight="600">{LAYER_JA[l]}</text>'
                   f'<text x="{left - 12}" y="{y + 34}" text-anchor="end" font-size="11" '
                   f'class="mut">{LAYER_NOTE[l]}</text>')
        x = left
        for s in BAR_STATES:
            n = c[l][s]
            if not n:
                continue
            w = n * unit
            out.append(f'<rect x="{x:.1f}" y="{y + 4}" width="{w - 2:.1f}" height="{barh}" '
                       f'rx="3" fill="var(--{s})"><title>{LAYER_JA[l]} {STATE_JA[s]} {n}</title></rect>')
            if w > 22:
                out.append(f'<text x="{x + w / 2 - 1:.1f}" y="{y + 22}" text-anchor="middle" '
                           f'font-size="12.5" font-weight="600" style="fill:var(--bg)">{n}</text>')
            x += w
        tot = sum(c[l][s] for s in BAR_STATES)
        miss = c[l]["missing"] / tot if tot else 0
        tail = f'計 {tot}　未採用 {miss:.0%}'
        if c[l]["watch"]:
            tail += f'　観察 {c[l]["watch"]}'
        out.append(f'<text x="{x + 8:.1f}" y="{y + 22}" font-size="12" class="ink2">{tail}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- 図 2: 4 層の入れ子（グラレコ風）

def wobble_rect(x, y, w, h, seed) -> str:
    """手描き風の角丸四角。辺の中点を少しずらした 2 次ベジェでつなぐ。乱数は使わず seed で決める。"""
    j = [((seed * 7 + k * 13) % 7 - 3) * 0.9 for k in range(8)]
    r = 18
    return (f"M{x + r},{y + j[0]} Q{x + w / 2},{y - 3 + j[1]} {x + w - r},{y + j[2]} "
            f"Q{x + w + j[3]},{y} {x + w + j[3]},{y + r} "
            f"Q{x + w + 3 + j[4]},{y + h / 2} {x + w + j[4]},{y + h - r} "
            f"Q{x + w},{y + h + j[5]} {x + w - r},{y + h + j[5]} "
            f"Q{x + w / 2},{y + h + 3 + j[6]} {x + r},{y + h + j[6]} "
            f"Q{x + j[7]},{y + h} {x + j[7]},{y + h - r} "
            f"Q{x - 3},{y + h / 2} {x},{y + r} Q{x},{y + j[0]} {x + r},{y + j[0]}")


# ---------------------------------------------------------------- 図 3: 収集 → 抽出 → 採否 → 取り込み

def fig_flow(cat: dict, cand: dict, c: dict) -> str:
    pats = cat.get("patterns", [])
    n_src = len(cat.get("sources", []))
    pool = cand.get("pool_size", "—")
    top = len(cand.get("candidates", []))
    used = sum(1 for s in cat.get("sources", []) if s.get("kind") == "candidate")
    miss = sum(c[l]["missing"] for l in LAYERS)
    part = sum(c[l]["partial"] for l in LAYERS)
    W, H = 760, 320
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="候補収集から自作ハーネスへの取り込みまでの流れ">',
           f'<defs><marker id="pt-ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
           f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="var(--pen)"/></marker></defs>',
           f'<rect x="0" y="0" width="{W}" height="{H}" rx="10" fill="var(--paper)"/>']
    steps = [
        ("① 候補収集", f"{pool} 件", "topic 検索＋awesome",
         "collect_candidates.py", "LLM なし・star/日で上位"),
        ("② 抽出", f"{len(pats)} パターン", f"出典 {n_src}（候補から {used}）",
         "catalog.yaml", "公式 docs / README の一文が根拠"),
        ("③ 採否", f"未採用 {miss}", f"部分的 {part}",
         "state 列", "自作側のファイルで判定"),
        ("④ 取り込み", "dotfiles へ", "core-principal",
         "core-harness スキル", "check / rule / skill に振り分け"),
    ]
    bw, gap, y0 = 150, 40, 60
    for i, (t, big, sub, file, note) in enumerate(steps):
        x = 20 + i * (bw + gap)
        rot = (-1.2, 0.8, -0.6, 1.0)[i]
        out.append(f'<g transform="rotate({rot} {x + bw / 2} {y0 + 70})">'
                   f'<path d="{wobble_rect(x, y0, bw, 140, i + 3)}" fill="var(--surface)" '
                   f'stroke="var(--pen)" stroke-width="2"/>'
                   f'<rect x="{x + 12}" y="{y0 + 16}" width="{len(t) * 14}" height="11" fill="var(--hl)" opacity=".85"/>'
                   f'<text x="{x + 14}" y="{y0 + 27}" font-size="15" font-weight="700">{esc(t)}</text>'
                   f'<text x="{x + bw / 2}" y="{y0 + 70}" text-anchor="middle" font-size="22" '
                   f'font-weight="700"{" style=&quot;fill:var(--missing)&quot;" if i == 2 else ""}>{esc(big)}</text>'
                   f'<text x="{x + bw / 2}" y="{y0 + 94}" text-anchor="middle" font-size="12" class="ink2">{esc(sub)}</text>'
                   f'<text x="{x + bw / 2}" y="{y0 + 122}" text-anchor="middle" font-size="11" '
                   f'style="font-family:var(--mono)" class="mut">{esc(file)}</text></g>'
                   f'<text x="{x + bw / 2}" y="{y0 + 172}" text-anchor="middle" font-size="12" class="ink2">'
                   f'{esc(note)}</text>')
        if i < 3:
            ax = x + bw + 4
            out.append(f'<path class="pen" d="M{ax},{y0 + 72} Q{ax + gap / 2},{y0 + 62} {ax + gap - 8},{y0 + 72}" '
                       f'stroke-width="2.2" marker-end="url(#pt-ah)"/>')
    # 戻りの矢印: 取り込んだら次の周回で状態が変わる。
    out.append(f'<path class="pen" d="M{20 + 3 * (bw + gap) + bw / 2},{y0 + 190} '
               f'C{600},{H - 40} {140},{H - 40} {20 + bw / 2 + 20},{y0 + 190}" stroke-width="1.6" '
               f'stroke-dasharray="5 4" marker-end="url(#pt-ah)"/>'
               f'<text x="{W / 2}" y="{H - 16}" text-anchor="middle" font-size="12.5" class="ink2">'
               f'取り込んだら state を更新し、次の収集で出典の顔ぶれを見直す（/update-landscape の最後）</text>'
               f'<text x="20" y="34" font-size="13" class="mut">候補は出典としてだけ使う。ランドスケープの母集団（registry.yaml）には入れない。</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- 次に取り込む候補

IMPACT_JA = {3: "高", 2: "中", 1: "低"}
EFFORT_JA = {1: "小", 2: "中", 3: "大"}


def next_picks(pats: list[dict], n: int = 5) -> list[dict]:
    """未採用・部分的の行を 効果 − 手間 → 効果 → 出典数 の順に並べる（基準は catalog.yaml の priority_criteria）。"""
    rated = [p for p in pats if p.get("state") in ("missing", "partial") and p.get("impact") and p.get("effort")]
    rated.sort(key=lambda p: (-(p["impact"] - p["effort"]), -p["impact"], -len(p.get("sources") or []), p["id"]))
    return rated[:n]


def picks_list(picks: list[dict], crit: dict) -> str:
    items = "".join(
        f'<li><strong>{esc(p["name"])}</strong> <span class="ly">{LAYER_JA[p["layer"]]}・{STATE_JA[p["state"]]}'
        f'・効果 {IMPACT_JA[p["impact"]]}／手間 {EFFORT_JA[p["effort"]]}</span><br>'
        f'<span class="why">{esc(p["gain"])}。手間は、{esc(p["cost"])}。</span></li>'
        for p in picks)
    ic, ec = crit.get("impact", {}), crit.get("effort", {})
    legend = (f'効果 高＝{esc(ic.get(3))}、中＝{esc(ic.get(2))}、低＝{esc(ic.get(1))}。'
              f'手間 小＝{esc(ec.get(1))}、中＝{esc(ec.get(2))}、大＝{esc(ec.get(3))}。'
              f'並べ方は {esc(crit.get("order"))}。')
    return f'<ol class="picks">{items}</ol><p class="pick-crit">{legend}</p>'


# ---------------------------------------------------------------- 図 0: 白板のグラレコ

def _wrap(t: str, n: int) -> list[str]:
    """n 文字で 2 行に折る。句読点が行頭に来るなら前の行に寄せる。"""
    a, b = t[:n], t[n:]
    while b and b[0] in "、。）」":
        a, b = a + b[0], b[1:]
    return [a, b] if b else [a]


def _icon(layer: str, x: float, y: float) -> str:
    """層の小さな絵。吹き出し（言う）・盾（守る）・回る矢印（繰り返す）・つながる点（流れ）。"""
    k = 'class="wb-line" stroke-width="2.4"'
    if layer == "prompt":
        return (f'<path {k} d="M{x-14},{y-10} h28 a4,4 0 0 1 4,4 v12 a4,4 0 0 1 -4,4 h-16 l-8,7 v-7 '
                f'h-4 a4,4 0 0 1 -4,-4 v-12 a4,4 0 0 1 4,-4 z"/>'
                f'<path {k} d="M{x-8},{y-3} h16 M{x-8},{y+3} h10"/>')
    if layer == "harness":
        return (f'<path {k} d="M{x},{y-14} L{x+13},{y-9} Q{x+13},{y+7} {x},{y+15} Q{x-13},{y+7} {x-13},{y-9} Z"/>'
                f'<path {k} d="M{x-6},{y} l4,5 l8,-9"/>')
    if layer == "loop":
        return (f'<path {k} d="M{x+12},{y-4} A13,13 0 1 0 {x+9},{y+9}"/>'
                f'<path {k} d="M{x+6},{y-9} l6,5 l5,-7"/>')
    return (f'<path {k} d="M{x-11},{y+9} L{x},{y-9} L{x+12},{y+9} M{x-11},{y+9} H{x+12}"/>'
            f'<circle cx="{x-11}" cy="{y+9}" r="4.5" class="wb-dot"/><circle cx="{x}" cy="{y-9}" r="4.5" class="wb-dot"/>'
            f'<circle cx="{x+12}" cy="{y+9}" r="4.5" class="wb-dot"/>')


def _pip(state: str, x: float, y: float) -> str:
    if state == "adopted":
        return f'<circle cx="{x}" cy="{y}" r="6.5" class="wb-fill-blue"/>'
    if state == "partial":
        return (f'<circle cx="{x}" cy="{y}" r="6.5" class="wb-blue" stroke-width="2"/>'
                f'<path d="M{x},{y-6.5} A6.5,6.5 0 0 0 {x},{y+6.5} Z" class="wb-fill-blue"/>')
    return f'<circle cx="{x}" cy="{y}" r="6.5" class="wb-red" stroke-width="2.2"/>'


def fig_whiteboard(c: dict, picks: list[dict]) -> str:
    """4 層の入れ子に、層ごとの採否を丸（塗り＝採用済・半分＝部分的・白抜き赤＝未採用）で描き、
    次に取り込む 5 つを付箋にして、差し込む層まで線でつなぐ。文字は層名と付箋だけにする。"""
    W, H = 1000, 630
    rings = {  # 外側から。(x, y, w, h)
        "graph": (40, 78, 520, 486), "loop": (68, 158, 464, 392),
        "harness": (96, 238, 408, 298), "prompt": (124, 318, 352, 204),
    }
    out = [f'<svg class="wb" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="4 層の採否と、次に取り込む 5 つのパターン（白板の手描き図）">',
           '<defs><filter id="wb-rough" x="-3%" y="-3%" width="106%" height="106%">'
           '<feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="5" result="n"/>'
           '<feDisplacementMap in="SourceGraphic" in2="n" scale="3.4" xChannelSelector="R" yChannelSelector="G"/></filter>'
           '<filter id="wb-rough-t"><feTurbulence type="fractalNoise" baseFrequency="0.08" numOctaves="1" seed="2" result="n"/>'
           '<feDisplacementMap in="SourceGraphic" in2="n" scale="1.4" xChannelSelector="R" yChannelSelector="G"/></filter>'
           '<marker id="wb-ah" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="9" markerHeight="9" orient="auto">'
           '<path d="M1,1 L10,6 L1,11" class="wb-red" stroke-width="2.2"/></marker></defs>',
           f'<rect x="4" y="4" width="{W-8}" height="{H-8}" rx="14" class="wb-board"/>']
    g = ['<g filter="url(#wb-rough)">']
    t = ['<g filter="url(#wb-rough-t)">']
    # タイトル
    t.append('<text x="40" y="52" class="wb-t" font-size="26">自作ハーネスの いま</text>')
    g.append('<path class="wb-line" stroke-width="2.4" d="M40,62 q60,6 120,0 t120,2"/>')
    thin = max(LAYERS, key=lambda l: c[l]["missing"] / max(1, sum(c[l][s] for s in BAR_STATES)))
    anchor = {}
    for i, l in enumerate(LAYERS[::-1]):  # graph → prompt の順に外から描く
        x, y, w, h = rings[l]
        g.append(f'<path d="{wobble_rect(x, y, w, h, i + 2)}" class="wb-line" stroke-width="2.6"/>')
        g.append(f'<path d="{wobble_rect(x + 2, y + 1, w - 3, h - 2, i + 5)}" class="wb-line" stroke-width="1" opacity=".45"/>')
        g.append(_icon(l, x + 30, y + 30))
        t.append(f'<text x="{x + 54}" y="{y + 38}" class="wb-t" font-size="21">{LAYER_JA[l]}</text>')
        px, py = x + 58, y + 62  # 丸は層名の下に 1 列で並べる
        k = 0
        for st in BAR_STATES:
            for _ in range(c[l][st]):
                g.append(_pip(st, px + k * 16, py))
                k += 1
        anchor[l] = (x + w, y + 31)
        if l == thin:  # いちばん穴の多い層に赤で丸をつける
            cx, cy, rx = px + (k - 1) * 16 / 2, py, (k - 1) * 16 / 2 + 13
            g.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="14" class="wb-red" stroke-width="2.4" '
                     f'transform="rotate(-1.5 {cx} {cy})"/>')
            tx = x + 58 + len(LAYER_JA[l]) * 21 + 34
            t.append(f'<text x="{tx}" y="{y + 36}" class="wb-t wb-tr" font-size="19">穴が多い!</text>')
            g.append(f'<path class="wb-red" stroke-width="2" marker-end="url(#wb-ah)" '
                     f'd="M{tx + 100},{y + 30} q24,6 8,{py - y - 44}"/>')
    # 中心: モデル
    g.append('<ellipse cx="300" cy="455" rx="62" ry="30" class="wb-line" stroke-width="2.2"/>')
    t.append('<text x="300" y="462" text-anchor="middle" class="wb-t" font-size="18">モデル</text>')
    # 右: 次に取り込む 5 つ。電球の絵と赤いマーカー
    g.append('<path class="wb-red" stroke-width="12" opacity=".22" d="M636,44 h262"/>')
    t.append('<text x="640" y="52" class="wb-t" font-size="24">つぎに入れる 5 つ</text>')
    g.append('<path class="wb-line" stroke-width="2.2" d="M610,34 a13,13 0 1 1 18,0 v9 h-18 z M612,49 h14 M614,54 h10"/>'
             '<path class="wb-line" stroke-width="1.6" d="M598,22 l-6,-5 M619,12 v-7 M640,22 l6,-5"/>')
    for i, p in enumerate(picks):
        x, y = 612, 78 + i * 100
        rot = (-1.5, 1.2, -0.8, 1.6, -1.1)[i % 5]
        g.append(f'<g transform="rotate({rot} {x + 170} {y + 42})">'
                 f'<path d="{wobble_rect(x, y, 350, 84, i + 7)}" class="wb-note"/></g>')
        g.append(f'<circle cx="{x + 30}" cy="{y + 42}" r="19" class="wb-red" stroke-width="2.6"/>')
        t.append(f'<text x="{x + 30}" y="{y + 50}" text-anchor="middle" class="wb-t wb-tr" font-size="22">{i + 1}</text>')
        g.append(_icon(p["layer"], x + 318, y + 42))
        for j, line in enumerate(_wrap(p["name"], 12)):
            t.append(f'<text x="{x + 60}" y="{y + 36 + j * 26}" class="wb-t" font-size="19">{esc(line)}</text>')
        # 付箋から、差し込む層の右端へ赤い矢印
        ax, ay = anchor[p["layer"]]
        g.append(f'<path class="wb-red" stroke-width="2" stroke-dasharray="7 6" marker-end="url(#wb-ah)" '
                 f'd="M{x - 4},{y + 42} C{x - 30},{y + 42} {ax + 40},{ay + (i - 2) * 6} {ax + 6},{ay + (i - 2) * 4}"/>')
    # 凡例は丸 3 つだけ
    ly = H - 22
    for i, (st, lab) in enumerate([("adopted", "ある"), ("partial", "一部"), ("missing", "ない")]):
        g.append(_pip(st, 44 + i * 86, ly - 6))
        t.append(f'<text x="{58 + i * 86}" y="{ly}" class="wb-t" font-size="16">{lab}</text>')
    g.append("</g>")
    t.append("</g>")
    out += g + t + ["</svg>"]
    return "".join(out)


# ---------------------------------------------------------------- 表

def catalog_table(cat: dict, layer: str) -> str:
    """1 つの層の行だけを描く。層は節見出しに出すので列には持たない。"""
    srcs = {s["id"]: s for s in cat.get("sources", [])}
    sorder = {"missing": 0, "partial": 1, "watch": 2, "adopted": 3}
    rows = []
    pats = sorted((p for p in cat.get("patterns", []) if p.get("layer") == layer),
                  key=lambda p: (sorder.get(p.get("state"), 9), p.get("name", "")))
    for p in pats:
        refs = "".join(
            f'<li><a href="{esc(r["url"])}">{esc(srcs.get(r["source"], {}).get("name", r["source"]))}</a></li>'
            for r in p.get("sources") or [])
        mat = "".join(
            f'<li>{esc(srcs.get(r["source"], {}).get("version") or "—")}'
            f'{"・日常利用を明記" if srcs.get(r["source"], {}).get("dogfood") else ""}</li>'
            for r in p.get("sources") or [])
        selfs = "".join(f"<li><code>{esc(s)}</code></li>" for s in p.get("self") or [])
        note = f'<br><small>{esc(p["note"])}</small>' if p.get("note") else ""
        gc = (f'<span class="gc">効果 {IMPACT_JA[p["impact"]]}</span> {esc(p["gain"])}<br>'
              f'<span class="gc">手間 {EFFORT_JA[p["effort"]]}</span> {esc(p["cost"])}') if p.get("gain") else "—"
        rows.append(
            f'<tr class="r s-{esc(p.get("state"))}">'
            f'<td><strong>{esc(p.get("name"))}</strong></td>'
            f'<td><ul>{refs}</ul></td>'
            f'<td>{esc(p.get("problem"))}</td>'
            f'<td>{gc}</td>'
            f'<td><span class="st st-{esc(p.get("state"))}">{esc(STATE_JA.get(p.get("state"), p.get("state")))}</span></td>'
            f'<td>{("<ul>" + selfs + "</ul>") if selfs else "—"}{note}</td>'
            f'<td><ul>{mat}</ul></td></tr>')
    return "".join(rows)


def source_table(cat: dict) -> str:
    kind_ja = {"official": "公式", "candidate": "候補", "self": "自作"}
    rows = []
    for s in cat.get("sources", []):
        n = sum(1 for p in cat.get("patterns", []) for r in p.get("sources") or [] if r.get("source") == s["id"])
        dog = s.get("dogfood")
        rows.append(f'<tr><td><a href="{esc(s["url"])}">{esc(s["name"])}</a></td>'
                    f'<td>{kind_ja.get(s.get("kind"), "")}</td><td>{esc(s.get("version") or "—")}</td>'
                    f'<td>{("<a href=" + chr(34) + esc(dog["url"]) + chr(34) + ">明記あり</a>") if dog else "記載なし"}</td>'
                    f'<td style="text-align:right">{n}</td></tr>')
    return "".join(rows)


def candidate_table(cand: dict, cat: dict) -> str:
    used = {s.get("repo", "").lower() for s in cat.get("sources", []) if s.get("repo")}
    rows = []
    for c in cand.get("candidates", []):
        mark = "抽出済" if c["repo"].lower() in used else ""
        ls = "ランドスケープにもある" if c.get("in_landscape") else ""
        rows.append(f'<tr><td style="text-align:right">{c["rank"]}</td>'
                    f'<td><a href="https://github.com/{esc(c["repo"])}">{esc(c["repo"])}</a></td>'
                    f'<td style="text-align:right">{c["stars_per_day"]:,}</td>'
                    f'<td style="text-align:right">{c["stars"]:,}</td><td>{esc(c["pushed_at"])}</td>'
                    f'<td>{mark}</td><td><small>{esc(ls)}</small></td></tr>')
    return "".join(rows)


# ---------------------------------------------------------------- 見立てのページ（harness-form.md）

FORM_SRC = "harness-form.md"


def _md(text: str) -> str:
    return md_lib.Markdown(extensions=["tables", "attr_list"]).convert(text)


def _form_sections(src: pathlib.Path, cat: dict) -> tuple[str, str, dict[str, str]]:
    """harness-form.md を読み、数を catalog.yaml から埋めて (題, 副題, {節見出し: 本文}) を返す。"""
    raw = (src / "patterns" / FORM_SRC).read_text(encoding="utf-8")
    gap = [p for p in cat.get("patterns", []) if p.get("state") in ("missing", "partial")]
    n = {e: [p for p in gap if p.get("effort") == e] for e in (1, 2, 3)}
    fill = {"gap_total": len(gap), "effort_1": len(n[1]), "effort_2": len(n[2]), "effort_3": len(n[3]),
            "effort_3_names": "、".join(f"「{p['name']}」" for p in n[3])}
    for k, v in fill.items():
        raw = raw.replace("{{" + k + "}}", str(v))
    head, _, rest = raw.partition("\n")
    title = head.lstrip("# ").strip()
    sub, _, rest = rest.lstrip().partition("\n")
    secs, cur = {"": []}, ""
    for line in rest.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            secs[cur] = []
        else:
            secs[cur].append(line)
    return title, sub.lstrip("> ").strip(), {k: "\n".join(v).strip() for k, v in secs.items()}


def fig_form() -> str:
    """見立ての構図: 各社のループ（借りる）の上に、薄い自作の層（検証・境界・知識）を載せる。
    自作ループには×。乗り換えても層は持ち運べる。"""
    W, H = 1000, 380
    out = [f'<svg class="wb" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="ループは借り、検証・境界・知識の薄い層だけを自分で持つ（手描き図）">',
           '<defs><filter id="wb-rough" x="-3%" y="-3%" width="106%" height="106%">'
           '<feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="7" result="n"/>'
           '<feDisplacementMap in="SourceGraphic" in2="n" scale="3.4" xChannelSelector="R" yChannelSelector="G"/></filter>'
           '<marker id="wb-ah" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="9" markerHeight="9" orient="auto">'
           '<path d="M1,1 L10,6 L1,11" class="wb-red" stroke-width="2.2"/></marker></defs>',
           f'<rect x="4" y="4" width="{W-8}" height="{H-8}" rx="14" class="wb-board"/>']
    g, t = ['<g filter="url(#wb-rough)">'], []
    # 下: 各社のループ（借りる）を 2 つ並べる
    for i, (x, name) in enumerate([(60, "Claude Code"), (330, "Codex CLI")]):
        g.append(f'<path d="{wobble_rect(x, 220, 230, 110, i + 3)}" class="wb-line" stroke-width="2.4"/>')
        g.append(_icon("loop", x + 34, 262))
        t.append(f'<text x="{x + 60}" y="{270}" class="wb-t" font-size="20">{name}</text>')
        t.append(f'<text x="{x + 60}" y="{300}" class="wb-t" font-size="15">のループ＝借りる</text>')
    # 上: 薄い自作の層。3 本柱
    g.append(f'<path d="{wobble_rect(60, 70, 500, 120, 9)}" class="wb-note"/>')
    t.append('<text x="80" y="58" class="wb-t" font-size="22">Thin Harness, <tspan class="wb-tr">Fat Skills</tspan></text>')
    for i, (lab, ic) in enumerate([("検証", "loop"), ("境界", "harness"), ("知識", "prompt")]):
        x = 110 + i * 160
        g.append(_icon(ic, x, 118))
        t.append(f'<text x="{x + 22}" y="{126}" class="wb-t" font-size="24">{lab}</text>')
    t.append('<text x="90" y="170" class="wb-t" font-size="15">SKILL.md ・ hook ・ MCP の形で書く</text>')
    # 層から下の 2 つへ矢印（乗せ替えられる）
    for x in (175, 445):
        g.append(f'<path class="wb-red" stroke-width="2.2" marker-end="url(#wb-ah)" d="M{x},{192} q10,12 0,{24}"/>')
    t.append('<text x="585" y="232" class="wb-t wb-tr" font-size="19">乗り換えても 残る!</text>')
    g.append('<path class="wb-red" stroke-width="2" d="M580,240 q-10,6 -14,14"/>')
    # 右: 自作ループに ×
    g.append(f'<path d="{wobble_rect(700, 90, 240, 110, 4)}" class="wb-line" stroke-width="2.2" stroke-dasharray="8 7"/>')
    g.append(_icon("loop", 740, 130))
    t.append('<text x="768" y="138" class="wb-t" font-size="20">自作のループ</text>')
    t.append('<text x="720" y="178" class="wb-t" font-size="15">モデルの版で 古びる</text>')
    g.append('<path class="wb-red" stroke-width="5" d="M712,100 L928,192 M928,100 L712,192"/>')
    # 右下: 信じる ＞ 書く
    t.append('<text x="700" y="290" class="wb-t" font-size="22">書く → <tspan class="wb-tr">信じる</tspan></text>')
    t.append('<text x="700" y="320" class="wb-t" font-size="15">ボトルネックの移動</text>')
    g.append('<path class="wb-red" stroke-width="10" opacity=".22" d="M770,292 h80"/>')
    g.append("</g>")
    out += g + ['<g>'] + t + ['</g>', "</svg>"]
    return "".join(out)


def form_summary(src: pathlib.Path, cat: dict, warnings: list[str]) -> str:
    """カタログのページ冒頭に置く要約。結論の 1 段落と形式の比較表だけを、見立てのページから抜く。"""
    if not (src / "patterns" / FORM_SRC).exists():
        warnings.append(f"見立ての原稿が無い: docs/src/patterns/{FORM_SRC}")
        return ""
    _, _, secs = _form_sections(src, cat)
    concl = next((v for k, v in secs.items() if k.startswith("結論")), "").split("\n\n")[0]
    comp = next((v for k, v in secs.items() if k.startswith("形式の比較")), "")
    table = "\n".join(l for l in comp.splitlines() if l.startswith("|"))
    return (f'<h2>Thin Harness, Fat Skills — どういう形式のハーネスがよいか <span class="opinion">意見</span></h2>'
            f'<div class="finding">{_md(concl)}</div>'
            f'<div class="tablewrap">{_md(table)}</div>'
            f'<p><small>言葉は Garry Tan「<a href="https://github.com/garrytan/gbrain/blob/master/docs/ethos/THIN_HARNESS_FAT_SKILLS.md">Thin Harness, Fat Skills</a>」から'
            f'（紹介記事は <a href="https://fyve.co.jp/claude-code/articles/thin-harness-fat-skills-guide">Fyve</a>）。</small></p>'
            f'<p><a href="harness-form.html">理由・原典との対応・自作ハーネスへの当てはめ・図を読む →</a></p>')


def render_form(src: pathlib.Path, base_css: str, warnings: list[str]) -> str:
    cat, _ = load(src)
    if not (src / "patterns" / FORM_SRC).exists():
        return ""
    title, sub, secs = _form_sections(src, cat)
    body = _md(secs.pop("", "")).replace("<p>{{figure}}</p>", f'<figure class="pt-fig">{fig_form()}</figure>')
    for k, v in secs.items():
        head = esc(k).replace("（意見）", '<span class="opinion">意見</span>')
        body += f"<h2>{head}</h2>{_md(v)}"
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{base_css}{PAGE_CSS}</style></head>
<body><div class="wrap pt">
<header><h1>{esc(title)}</h1><p class="sub">{_md(sub)[3:-4]}</p>
<p class="sub"><a href="index.html">← ハーネスのパターン・カタログ</a></p></header>
{body}
<footer><p>正本は <code>docs/src/patterns/{FORM_SRC}</code>。件数は <code>catalog.yaml</code> から生成時に数える。</p></footer>
</div></body></html>
"""


# ---------------------------------------------------------------- ページ

def render(src: pathlib.Path, base_css: str, warnings: list[str]) -> str:
    cat, cand = load(src)
    check(cat, warnings)
    pats = cat.get("patterns", [])
    c = counts(pats)
    crit = "".join(f'<span class="st st-{s}">{STATE_JA[s]}</span><span>{esc(cat["state_criteria"][s])}</span>'
                   for s in STATES)
    thinnest = max(LAYERS, key=lambda l: (c[l]["missing"] / max(1, sum(c[l][s] for s in BAR_STATES))))
    fbar = "".join(f'<label for="pf-{k}">{v}</label>' for k, v in [("all", "すべて"), ("missing", "未採用だけ")])
    radios = "".join(f'<input type="radio" name="pf" id="pf-{k}" class="pt-filters"{" checked" if k == "all" else ""}>'
                     for k in ["all", "missing"])
    findings = cat.get("layer_findings") or {}
    sections = []
    for l in LAYERS:
        n = sum(c[l].values())
        tally = "・".join(f"{STATE_JA[s]} {c[l][s]}" for s in STATES if c[l][s])
        sections.append(f"""
<h2>{LAYER_JA[l]}層 — {LAYER_NOTE[l]}（{n} 件）</h2>
<p class="finding"><strong>{esc(findings.get(l, ""))}</strong></p>
<p><small>{tally}</small></p>
<div class="tablewrap"><table>
<thead><tr><th>パターン</th><th>出典</th><th>解く問題</th><th>取り込んだ場合（効果 / 手間）</th><th>自作での状態</th>
<th>自作側の根拠（~/dotfiles）</th><th>出典の成熟度</th></tr></thead>
<tbody>{catalog_table(cat, l)}</tbody></table></div>""")
    picks = next_picks(pats)
    body = f"""
<figure class="pt-fig">{fig_whiteboard(c, picks)}</figure>
<h2 class="first">次に取り込む候補 上位 5</h2>
{picks_list(picks, cat.get("priority_criteria") or {})}

{form_summary(src, cat, warnings)}

<h2>層 × 採否の件数</h2>
<figure class="pt-fig">{fig_counts(c)}
<figcaption>{len(pats)} パターンを層 × 自作ハーネスでの状態で数えたもの。未採用の割合がいちばん高いのは
<strong>{LAYER_JA[thinnest]}</strong>。</figcaption></figure>
<div class="legend-crit">{crit}</div>

<h2>カタログの作り方</h2>
<figure class="pt-fig">{fig_flow(cat, cand, c)}</figure>

<p>以下、層ごとに節を分けて並べる。行はパターンで、ツールではない。同じ働きを複数の出典が持つときは
1 行にまとめ、出典を並べた。各表は未採用 → 部分的 → 観察 → 採用済の順。</p>
{radios}<div class="pt-fbar">{fbar}</div>
{"".join(sections)}

<h2>出典（{len(cat.get("sources", []))}）</h2>
<p>公式ドキュメントか README に書かれていることだけを根拠にした。版は GitHub のリリース、
「日常利用」は作者自身が毎日使っていると README や公式ドキュメントに書いてあるかどうか。</p>
<div class="tablewrap"><table><thead><tr><th>出典</th><th>種別</th><th>版</th><th>作者の日常利用</th>
<th style="text-align:right">パターン</th></tr></thead><tbody>{source_table(cat)}</tbody></table></div>

<h2>出典候補（上位 {len(cand.get("candidates", []))}）</h2>
<p><code>docs/collect_candidates.py</code> が {esc(cand.get("fetched_at", "—"))} に集めたもの。
直近 {esc(cand.get("push_days", "—"))} 日に push があり、アーカイブされていないリポジトリ
{esc(cand.get("pool_size", "—"))} 件を、作成以来の star/日 で並べた。star の総数では並べていない。</p>
<div class="tablewrap"><table><thead><tr><th style="text-align:right">#</th><th>リポジトリ</th>
<th style="text-align:right">star/日</th><th style="text-align:right">star</th><th>直近 push</th><th>カタログ</th><th></th>
</tr></thead><tbody>{candidate_table(cand, cat)}</tbody></table></div>
"""
    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ハーネスのパターン・カタログ</title>
<style>{base_css}{PAGE_CSS}</style></head>
<body><div class="wrap pt">
<header><h1>ハーネスのパターン・カタログ</h1>
<p class="sub">各ハーネス・スキル集から学べる型と、自作ハーネス（~/dotfiles の core-principal）に何が入っていて何が無いか。
確認日 {esc(cat.get("verified", "—"))}。</p></header>
{body}
<footer><p>正本は <code>docs/src/patterns/catalog.yaml</code> と <code>docs/src/data/candidates.json</code>。
HTML は <code>docs/build.py</code> が生成する。更新手順は <code>docs/src/landscape/UPDATE_PROMPT.md</code> の
「パターン・カタログ」節。</p></footer>
</div></body></html>
"""
