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


def fig_nest(c: dict) -> str:
    W, H = 760, 400
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="プロンプト ⊂ ハーネス ⊂ ループ ⊂ グラフ の入れ子">',
           f'<rect x="0" y="0" width="{W}" height="{H}" rx="10" fill="var(--paper)"/>']
    boxes = [("graph", 20, 20, 470, 360), ("loop", 50, 76, 410, 280),
             ("harness", 80, 132, 350, 200), ("prompt", 110, 188, 290, 120)]
    tint = {"graph": "var(--l0)", "loop": "var(--l2)", "harness": "var(--l1)", "prompt": "var(--l3)"}
    for i, (l, x, y, w, h) in enumerate(boxes):
        out.append(f'<path d="{wobble_rect(x, y, w, h, i + 1)}" fill="{tint[l]}" fill-opacity=".07" '
                   f'stroke="{tint[l]}" stroke-width="2.4" stroke-linecap="round"/>')
        tot = sum(c[l][s] for s in BAR_STATES)
        # 見出しにマーカーを引く。未採用の件数を横に丸で囲む。
        out.append(f'<rect x="{x + 14}" y="{y + 12}" width="{len(LAYER_JA[l]) * 17 + 8}" height="12" '
                   f'fill="var(--hl)" opacity=".85" transform="rotate(-1.2 {x + 14} {y + 18})"/>'
                   f'<text x="{x + 18}" y="{y + 24}" font-size="16" font-weight="700">{LAYER_JA[l]}</text>'
                   f'<text x="{x + 22 + len(LAYER_JA[l]) * 17}" y="{y + 24}" font-size="12" class="ink2">'
                   f'{LAYER_NOTE[l]}</text>')
        miss = c[l]["missing"]
        cx = x + w - 34
        out.append(f'<ellipse cx="{cx}" cy="{y + 20}" rx="26" ry="14" fill="none" stroke="var(--missing)" '
                   f'stroke-width="1.8" transform="rotate(-4 {cx} {y + 20})"/>'
                   f'<text x="{cx}" y="{y + 24}" text-anchor="middle" font-size="11.5" '
                   f'style="fill:var(--missing)" font-weight="700">未{miss}/{tot}</text>')
    # 中心の例と、右側の吹き出し。
    out.append('<text x="255" y="262" text-anchor="middle" font-size="12.5" class="ink2">'
               'CLAUDE.md・スキル本文・出力の型</text>')
    notes = [
        (515, 40, "グラフ", "誰がどの順で動くか", "worktree・並列・CI"),
        (515, 130, "ループ", "いつ止め、やり直すか", "検証・Stop フック・振り返り"),
        (515, 220, "ハーネス", "何が見え、何ができるか", "ツール・権限・フック・索引"),
        (515, 310, "プロンプト", "何を言うか", "規範・スキル・メモリ"),
    ]
    for i, (x, y, t, a, b) in enumerate(notes):
        rot = (-1.5, 1.2, -0.8, 1.4)[i]
        out.append(f'<g transform="rotate({rot} {x + 110} {y + 30})">'
                   f'<rect x="{x}" y="{y}" width="232" height="62" rx="4" fill="var(--surface)" '
                   f'stroke="var(--line)"/>'
                   f'<text x="{x + 12}" y="{y + 22}" font-size="12.5" font-weight="700">{t}：{a}</text>'
                   f'<text x="{x + 12}" y="{y + 44}" font-size="12" class="ink2">例）{b}</text></g>')
    # 吹き出しから箱への矢印（手描き風の曲線）。
    tips = [(490, 70), (460, 150), (430, 240), (400, 290)]
    for (x, y, *_), (tx, ty) in zip(notes, tips):
        out.append(f'<path class="pen" d="M{x - 2},{y + 31} Q{(x + tx) / 2},{y + 40} {tx + 6},{ty}" '
                   f'stroke-width="1.4" stroke-dasharray="4 3"/>'
                   f'<circle cx="{tx + 6}" cy="{ty}" r="2.6" fill="var(--pen)"/>')
    out.append("</svg>")
    return "".join(out)


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
        rows.append(
            f'<tr class="r s-{esc(p.get("state"))}">'
            f'<td><strong>{esc(p.get("name"))}</strong></td>'
            f'<td><ul>{refs}</ul></td>'
            f'<td>{esc(p.get("problem"))}</td>'
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
<thead><tr><th>パターン</th><th>出典</th><th>解く問題</th><th>自作での状態</th>
<th>自作側の根拠（~/dotfiles）</th><th>出典の成熟度</th></tr></thead>
<tbody>{catalog_table(cat, l)}</tbody></table></div>""")
    body = f"""
<figure class="pt-fig">{fig_counts(c)}
<figcaption>{len(pats)} パターンを層 × 自作ハーネスでの状態で数えたもの。未採用の割合がいちばん高いのは
<strong>{LAYER_JA[thinnest]}</strong>。</figcaption></figure>
<div class="legend-crit">{crit}</div>

<h2>4 層の捉え方</h2>
<figure class="pt-fig">{fig_nest(c)}
<figcaption>内側ほどモデルに近い。丸囲みは各層の「未採用 / 計」（観察を除く）。</figcaption></figure>

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
