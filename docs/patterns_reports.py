"""パターン・カタログのうち、技術記事の使用報告にかかわる部分を描く。patterns_page.py から呼ぶ。

公式ドキュメント・README の出典（sources）と、記事の使用報告（reports）は別の種類の証拠なので、
表の列も節も分けて描く。記事の一覧は catalog.yaml の articles、名前を挙げたハーネスの評判は
docs/src/data/articles.json の reputation（collect_articles.py が集めた数）と catalog.yaml の
reputation（読んで拾った引用）を合わせて描く。
"""

from __future__ import annotations

import html
import json
import pathlib

SITE_JA = {"zenn": "Zenn", "qiita": "Qiita", "hn": "Hacker News", "devto": "dev.to", "reddit": "Reddit"}
UNIT_JA = {"zenn": "いいね", "qiita": "いいね", "hn": "pt", "devto": "反応", "reddit": "pt"}
THEME_JA = {"harness": "ハーネス", "slop": "AI slop"}
STATE_JA = {"adopted": "採用済", "partial": "部分的", "missing": "未採用", "watch": "観察"}
POL = {"positive": ("+", "効いた"), "negative": ("−", "効かなかった"), "mixed": ("±", "条件付き")}
VERDICT_JA = {"reflected": "反映", "irrelevant": "該当なし", "unreadable": "読めず"}

CSS = """
.rp { font-family:var(--mono); font-size:11.5px; white-space:nowrap; }
.rp-positive { color:var(--adopted); } .rp-negative { color:var(--missing); } .rp-mixed { color:var(--partial); }
.pt details summary { cursor:pointer; }
.pt details li { margin-bottom:6px; }
.pt q { color:var(--ink-2); }
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def load(src: pathlib.Path) -> dict:
    p = src / "data" / "articles.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def check(cat: dict, warnings: list[str]) -> None:
    arts = {a["id"] for a in cat.get("articles", [])}
    for a in cat.get("articles", []):
        if a.get("kind") != "article":
            warnings.append(f"記事の kind が article でない: {a.get('id')}")
        if a.get("verdict") not in VERDICT_JA:
            warnings.append(f"記事の判定（verdict）が不正: {a.get('id')}")
    used = set()
    for p in all_patterns(cat):
        for r in p.get("reports") or []:
            used.add(r.get("article"))
            if r.get("article") not in arts:
                warnings.append(f"使用報告が未知の記事を参照: {p.get('id')} → {r.get('article')}")
            if r.get("polarity") not in POL:
                warnings.append(f"使用報告の肯定・否定が不正: {p.get('id')} → {r.get('article')}")
            if not r.get("quote"):
                warnings.append(f"使用報告に引用が無い: {p.get('id')} → {r.get('article')}")
    srcs = {x["id"] for x in cat.get("sources", [])}
    for p in cat.get("slop_patterns") or []:
        if p.get("state") not in STATE_JA:
            warnings.append(f"slop パターンの状態が不正: {p.get('id')}")
        if not p.get("sources") and not p.get("reports"):
            warnings.append(f"slop パターンに出典も使用報告も無い: {p.get('id')}")
        for r in p.get("sources") or []:
            if r.get("source") not in srcs:
                warnings.append(f"slop パターンが未知の出典を参照: {p.get('id')} → {r.get('source')}")
    for a in cat.get("articles", []):
        if (a.get("verdict") == "reflected") != (a["id"] in used):
            warnings.append(f"記事の判定と使用報告が食い違う: {a['id']}")


def all_patterns(cat: dict) -> list[dict]:
    return (cat.get("patterns") or []) + (cat.get("slop_patterns") or [])


def tally(p: dict) -> dict[str, int]:
    t = {k: 0 for k in POL}
    for r in p.get("reports") or []:
        if r.get("polarity") in t:
            t[r["polarity"]] += 1
    return t


def net(p: dict) -> int:
    """上位 5 の並べ方に使う、肯定 − 否定。条件付きは数えない。"""
    t = tally(p)
    return t["positive"] - t["negative"]


def cell(p: dict, arts: dict) -> str:
    """パターンの行の「使用報告」列。件数を先に出し、引用は畳んでおく。"""
    reps = p.get("reports") or []
    if not reps:
        return "—"
    t = tally(p)
    head = " ".join(f'<span class="rp rp-{k}">{POL[k][0]}{t[k]}</span>' for k in POL if t[k])
    items = "".join(
        f'<li><span class="rp rp-{esc(r["polarity"])}">{POL[r["polarity"]][0]}</span> '
        f'<a href="{esc(arts.get(r["article"], {}).get("url"))}">{esc(label(arts.get(r["article"], {})))}</a> '
        f'<q>{esc(r["quote"])}</q></li>'
        for r in reps)
    return f'<details><summary>{head}</summary><ul>{items}</ul></details>'


def label(a: dict) -> str:
    return f'{SITE_JA.get(a.get("site"), a.get("site"))} {a.get("reactions", "—")}{UNIT_JA.get(a.get("site"), "")}'


def article_table(cat: dict) -> str:
    names = {}
    for p in all_patterns(cat):
        for r in p.get("reports") or []:
            hits = names.setdefault(r["article"], [])
            if (p["name"], r.get("polarity")) not in hits:
                hits.append((p["name"], r.get("polarity")))
    rows = []
    for a in sorted(cat.get("articles", []), key=lambda a: (list(SITE_JA).index(a["site"]), -a["reactions"])):
        hit = "".join(f'<li><span class="rp rp-{esc(pol)}">{POL.get(pol, ("",))[0]}</span> {esc(n)}</li>'
                      for n, pol in names.get(a["id"], []))
        rows.append(f'<tr><td>{SITE_JA[a["site"]]}<br><small>{THEME_JA.get(a.get("theme", "harness"))}</small></td>'
                    f'<td><a href="{esc(a["url"])}">{esc(a["title"])}</a>'
                    f'<br><small>{esc(a.get("published"))}</small></td>'
                    f'<td style="text-align:right">{a["reactions"]:,}</td>'
                    f'<td>{VERDICT_JA.get(a.get("verdict"), "")}</td>'
                    f'<td>{("<ul>" + hit + "</ul>") if hit else "<small>" + esc(a.get("why")) + "</small>"}</td></tr>')
    return "".join(rows)


def reputation_table(cat: dict, data: dict) -> str:
    notes = cat.get("reputation") or {}
    rows = []
    for name, r in (data.get("reputation") or {}).items():
        n = notes.get(name) or {}
        counts = "<br>".join(f'{SITE_JA[s]} {r["count"][s]} 本・計 {r["reactions"][s]:,}{UNIT_JA[s]}'
                             for s in r["count"])
        top = "".join(f'<li><a href="{esc(a["url"])}">{esc(a["title"])}</a> '
                      f'<small>{SITE_JA[a["site"]]} {a["reactions"]:,}{UNIT_JA[a["site"]]}・{esc(a["published"])}</small></li>'
                      for a in r.get("top", [])[:3])
        quotes = "".join(f'<li><a href="{esc(q["url"])}">{esc(q["where"])}</a> <q>{esc(q["quote"])}</q></li>'
                         for q in n.get("quotes") or [])
        rows.append(f'<tr><td><strong>{esc(name)}</strong></td><td>{counts}</td><td><ul>{top}</ul></td>'
                    f'<td>{("<ul>" + quotes + "</ul>") if quotes else "—"}'
                    f'</td></tr>')
    return "".join(rows)


def section(cat: dict, data: dict) -> str:
    arts = cat.get("articles", [])
    reflected = sum(1 for a in arts if a.get("verdict") == "reflected")
    n_rep = sum(len(p.get("reports") or []) for p in all_patterns(cat))
    top = data.get("top") or {}
    mins = data.get("min_reactions") or {}
    crit = "、".join(f'{SITE_JA[s]} 上位 {top[s]}（{mins.get(s)}{UNIT_JA[s]}以上）' for s in top)
    return f"""
<h2>記事の使用報告（{len(arts)} 本を読み、{reflected} 本から {n_rep} 件）</h2>
<p>公式ドキュメントや README は「何ができるか」の証拠で、記事は「使った人に効いたか」の証拠になる。
種類が違うので、パターンの表では出典と使用報告を別の列に分けた。
<code>docs/collect_articles.py</code> が {esc(data.get("fetched_at", "—"))} に、直近
{esc(data.get("window_days", "—"))} 日の記事から {crit} を反応数だけで機械的に選んだ。
AI slop の軸の記事は別の検索語で同じように選び、題の下に軸を書いた。
Reddit の 1 本は last30days-skill を試したときに拾ったもので、スクリプトの対象外。
反応数は媒体ごとに尺度が違うので、媒体をまたいで比べない。反映の欄は、筆者自身の使用結果が
書かれていてカタログの型に当てはまったものを「反映」、ハーネスの型の話でないものを「該当なし」とした。</p>
<div class="tablewrap"><table><thead><tr><th>媒体</th><th>題</th><th style="text-align:right">反応数</th>
<th>判定</th><th>効いたパターン（+ 効いた / − 効かなかった / ± 条件付き）</th></tr></thead>
<tbody>{article_table(cat)}</tbody></table></div>

<h2>名前の挙がったハーネスの評判</h2>
<p>題名にその名前を含む記事を媒体ごとに数えた（期間で切らない）。本数と反応数の合計は
<code>articles.json</code> の <code>reputation</code>、引用は記事を読んで拾ったもの。</p>
<p class="finding"><strong>{esc(cat.get("reputation_finding") or "")}</strong></p>
<div class="tablewrap"><table><thead><tr><th>ハーネス</th><th>記事の本数と反応数</th><th>反応の多い記事</th>
<th>使用報告の引用</th></tr></thead><tbody>{reputation_table(cat, data)}</tbody></table></div>
"""


def slop_section(cat: dict, stage_label) -> str:
    """AI slop の軸。4 層とは別の表にし、層の件数や上位 5 には数えない。段階の表記は呼び出し側から受け取る。"""
    srcs = {s["id"]: s for s in cat.get("sources", [])}
    arts = {a["id"]: a for a in cat.get("articles", [])}
    rows = []
    for p in cat.get("slop_patterns") or []:
        refs = "".join(f'<li><a href="{esc(r["url"])}">{esc(srcs.get(r["source"], {}).get("name", r["source"]))}</a></li>'
                       for r in p.get("sources") or [])
        selfs = "".join(f"<li><code>{esc(x)}</code></li>" for x in p.get("self") or [])
        note = f'<br><small>{esc(p["note"])}</small>' if p.get("note") else ""
        rows.append(f'<tr id="p-{esc(p["id"])}"><td><strong>{esc(p["name"])}</strong>'
                    f'<br><span class="ly">{stage_label(p)}</span></td><td>{esc(p.get("target"))}</td>'
                    f'<td>{("<ul>" + refs + "</ul>") if refs else "<small>記事のみ</small>"}</td>'
                    f'<td>{esc(p.get("problem"))}</td>'
                    f'<td><span class="st st-{esc(p["state"])}">{STATE_JA[p["state"]]}</span></td>'
                    f'<td>{("<ul>" + selfs + "</ul>") if selfs else "—"}{note}</td>'
                    f'<td>{cell(p, arts)}</td></tr>')
    return f"""
<h2>AI slop 対策（{len(cat.get("slop_patterns") or [])} 件）</h2>
<p>AI が書いた文章・コード・UI の質の低さを防ぐ・消す型。ハーネスの 4 層とは別の軸なので、上の件数と上位 5 には数えていない。</p>
<p class="finding"><strong>{esc(cat.get("slop_findings") or "")}</strong></p>
<div class="tablewrap"><table><thead><tr><th>パターン</th><th>対象</th><th>出典</th><th>解く問題</th><th>自作での状態</th>
<th>自作側の根拠（~/dotfiles）</th><th>記事の使用報告</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
"""
