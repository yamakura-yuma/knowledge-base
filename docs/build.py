#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "markdown"]
# ///
"""registry.yaml + metrics.json + tools/*.md から docs/site/ 以下の HTML を組む。

設計方針:
  - 出力は自己完結。外部 CDN・Web フォント・JS を一切使わない。
    （既存の ~/show-me-*.html が両方とも JS ゼロなので、それに合わせる。
      絞り込みは CSS の :checked セレクタだけで実装する。）
  - 状態とティアは実測値から機械的に決める。手で上書きしたものは画面上で「手動」と明示する。
  - 値が無いところは空欄にする。埋めない。

使い方:  uv run docs/build.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import sys

import markdown as md_lib
import yaml

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src"            # 正本。手で書く markdown と registry
OUT = HERE / "site"           # 生成物。話題ごとのディレクトリに出す
TL_START = (2021, 1)          # タイムラインの左端
STAR_THRESHOLD = 25_000       # 詳細ティアの自動昇格ライン
ACTIVE_DAYS = 90
STALE_DAYS = 180
VERIFY_STALE_DAYS = 180      # 出典を読み直すべき目安

LAYER_LABEL = {
    "L0": "モデル提供元",
    "L1": "エージェント本体",
    "L2": "モデルアクセス層",
    "L3": "共通基盤",
}
PLACEMENT_LABEL = {"terminal": "ターミナル", "ide": "IDE", "cloud": "クラウド"}
STATUS_LABEL = {
    "hot": "勢いあり",
    "active": "現役",
    "stale": "停滞",
    "ended": "終了",
    "unknown": "指標なし",
}


# ---------------------------------------------------------------- 日付ユーティリティ

def ym(value) -> tuple[int, int] | None:
    """'2025-08' / '2025-08-06' / date を (年, 月) に。"""
    if not value:
        return None
    s = str(value)
    try:
        if len(s) == 4:           # 年しか裏が取れていないものは 1 月に寄せる
            return int(s), 1
        return int(s[0:4]), int(s[5:7])
    except (ValueError, IndexError):
        return None


def qcol(t: tuple[int, int]) -> int:
    """(年, 月) を四半期カラム番号 (1 始まり) に。"""
    q = (t[1] - 1) // 3
    base_q = (TL_START[1] - 1) // 3
    return (t[0] - TL_START[0]) * 4 + (q - base_q) + 1


def days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (dt.date.today() - dt.date.fromisoformat(iso)).days
    except ValueError:
        return None


# ---------------------------------------------------------------- 判定ロジック

def releases_in_window(m: dict, days: int = ACTIVE_DAYS) -> int:
    """直近 N 日のリリース数を、取得済みの日付一覧から数える。
    集計を fetch 側でやると、上流に何も起きていなくても日付の経過だけで
    metrics.json が書き換わるので、窓の計算はこちら側に置いてある。"""
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    return sum(1 for d in (m.get("release_dates") or []) if d >= cutoff)


def decide_status(tool: dict, m: dict) -> str:
    """状態を実測値から決める。基準はページ上に明記してあるものと同一。"""
    if tool.get("ended"):
        return "ended"
    if m.get("archived"):
        return "ended"
    pushed = days_since(m.get("pushed_at"))
    if pushed is None:
        return "unknown"
    if pushed > STALE_DAYS:
        return "stale"
    if pushed <= ACTIVE_DAYS:
        return "hot" if releases_in_window(m) >= 10 else "active"
    return "active"


def decide_tier(tool: dict, m: dict, status: str) -> tuple[str, bool]:
    """(ティア, 手動指定か) を返す。registry の tier 指定が最優先。"""
    if tool.get("tier"):
        return tool["tier"], True
    stars = m.get("stars")
    if status in ("hot", "active") and stars is not None and stars >= STAR_THRESHOLD:
        return "detail", False
    return "history", False


# ---------------------------------------------------------------- HTML 部品

def esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def num(n) -> str:
    return f"{n:,}" if isinstance(n, int) else "—"


def load() -> tuple[dict, dict]:
    reg = yaml.safe_load((SRC / "landscape" / "registry.yaml").read_text(encoding="utf-8"))
    mp = SRC / "data" / "metrics.json"
    metrics = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {"repos": {}}
    return reg, metrics


def build_rows(reg: dict, metrics: dict) -> list[dict]:
    repos = metrics.get("repos", {})
    rows = []
    for t in reg["tools"]:
        m = repos.get(t["slug"], {})
        status = decide_status(t, m)
        tier, manual = decide_tier(t, m, status)
        # タイムラインの起点: 裏取り済みの公表日を優先し、無ければリポジトリ作成日で代用する。
        origin, origin_kind = ym(t.get("released")), "announced"
        if origin is None:
            origin, origin_kind = ym(m.get("created_at")), "repo"
        rows.append({
            **t, "m": m, "status": status, "tier": tier, "manual_tier": manual,
            "origin": origin, "origin_kind": origin_kind, "end": ym(t.get("ended")),
        })
    return rows


def timeline(rows: list[dict], today: tuple[int, int]) -> str:
    cols = qcol(today)
    drawable = [r for r in rows if r["origin"] and r["layer"] != "L0"]
    drawable.sort(key=lambda r: (qcol(r["origin"]), r["name"]))

    # 年の目盛り
    ticks = []
    for y in range(TL_START[0], today[0] + 1):
        c = qcol((y, 1))
        if 1 <= c <= cols:
            ticks.append(f'<div class="tick" style="grid-column:{c}/span 4">{y}</div>')

    bars = []
    for r in drawable:
        raw_s = qcol(r["origin"])
        s = max(1, raw_s)
        clipped = " clipped" if raw_s < 1 else ""
        e = qcol(r["end"]) if r["end"] else cols + 1
        e = max(s + 1, min(e, cols + 1))
        cls = f'bar l-{r["layer"]} s-{r["status"]}{clipped}'
        tip = f'{r["name"]}：{r["origin"][0]}-{r["origin"][1]:02d} 〜 ' + (
            f'{r["end"][0]}-{r["end"][1]:02d} 終了' if r["end"] else "現在")
        dot = "" if r["origin_kind"] == "announced" else " approx"
        bars.append(
            f'<div class="tl-name{dot}">{esc(r["name"])}</div>'
            f'<div class="tl-track">'
            f'<span class="{cls}" style="grid-column:{s}/{e}" title="{esc(tip)}"></span></div>'
        )
    return (
        f'<div class="tl" style="--cols:{cols}">'
        f'<div class="tl-name"></div><div class="tl-axis">'
        + "".join(ticks) + "</div>" + "".join(bars) + "</div>"
    )


def table(rows: list[dict], compact: bool = False) -> str:
    out = []
    for r in rows:
        m = r["m"]
        origin = f'{r["origin"][0]}-{r["origin"][1]:02d}' if r["origin"] else "—"
        if r["origin_kind"] == "repo" and r["origin"]:
            origin = f'<span class="approx" title="公表日が裏取りできていないため、リポジトリ作成日で代用">{origin}</span>'
        end = f'{r["end"][0]}-{r["end"][1]:02d}' if r["end"] else ""
        name = esc(r["name"])
        if r.get("url"):
            name = f'<a href="{esc(r["url"])}">{name}</a>'
        place = PLACEMENT_LABEL.get(r.get("placement") or "", "")
        layer = r["layer"] + (f" / {place}" if place else "")
        succ = ""
        if r.get("succeeded_by"):
            succ = f'<span class="succ">→ {esc(r["succeeded_by"])}</span>'
        out.append(
            f'<tr data-layer="{r["layer"]}" data-status="{r["status"]}">'
            f'<td class="c-name">{name}{succ}</td>'
            f'<td class="c-layer">{layer}</td>'
            f'<td class="c-date">{origin}</td>'
            f'<td class="c-date">{end}</td>'
            f'<td class="c-stat"><span class="pill p-{r["status"]}">{STATUS_LABEL[r["status"]]}</span></td>'
            f'<td class="c-num">{num(m.get("stars"))}</td>'
            f'<td class="c-date">{esc(m.get("last_release") or "")}</td>'
            f'<td class="c-sum">{esc(r.get("summary") or "")}'
            + (f'<span class="unsure">未確定: {esc(r["status_note"])}</span>'
               if r.get("status_note") else "")
            + '</td></tr>'
        )
    return "".join(out)


def demote_headings(fragment: str) -> str:
    """カード本文の見出しをページの階層に合わせて下げる。
    tools/*.md 側は ## で自然に書けるまま保つための処理。"""
    def sub(m):
        lvl = int(m.group(2))
        new = 4 if lvl <= 2 else 5
        return f"<{m.group(1)}h{new}>"
    return re.sub(r"<(/?)h([1-6])>", lambda m: sub(m), fragment)


def cards(rows: list[dict], warnings: list[str]) -> str:
    rows = [x for x in rows if x['tier'] == 'detail']
    conv = md_lib.Markdown(extensions=["tables", "fenced_code"])
    out = []
    for r in rows:
        body_path = SRC / "landscape" / "tools" / f'{r["slug"]}.md'
        if body_path.exists():
            conv.reset()
            body = demote_headings(conv.convert(body_path.read_text(encoding="utf-8")))
        else:
            warnings.append(f'詳細ティアだが本文が無い: docs/src/landscape/tools/{r["slug"]}.md')
            body = f'<p class="todo">本文未着手。{esc(r.get("summary") or "")}</p>'
        m = r["m"]
        meta = [f'<span class="k">層</span>{r["layer"]}・{LAYER_LABEL[r["layer"]]}']
        if r.get("vendor"):
            meta.append(f'<span class="k">提供</span>{esc(r["vendor"])}')
        if r.get("license"):
            meta.append(f'<span class="k">ライセンス</span>{esc(r["license"])}')
        if m.get("stars") is not None:
            meta.append(f'<span class="k">star</span>{num(m["stars"])}')
        if m.get("last_release"):
            meta.append(f'<span class="k">直近リリース</span>{m["last_release"]}')
        if r.get("pricing"):
            meta.append(f'<span class="k">課金</span>{esc(r["pricing"])}')
        if r.get("status_note"):
            meta.append(f'<span class="k">未確定</span>{esc(r["status_note"])}')
        src = "".join(
            f'<a href="{esc(u)}">{esc(u.replace("https://", "").rstrip("/"))}</a>'
            for u in (r.get("sources") or [])
        )
        tag = ""
        if r["manual_tier"] and r["tier"] == "detail":
            why = esc(r.get("tier_reason") or "理由の記載なし")
            tag = f'<span class="pill p-manual" title="{why}">手動で詳細に指定</span>'
            meta.append(f'<span class="k">手動昇格の理由</span>{why}')
        out.append(
            f'<article class="card" id="t-{esc(r["slug"])}">'
            f'<h3>{esc(r["name"])} <span class="pill p-{r["status"]}">{STATUS_LABEL[r["status"]]}</span>{tag}</h3>'
            f'<div class="meta">{"".join(f"<span>{x}</span>" for x in meta)}</div>'
            f"{body}"
            f'<div class="src">出典 {src}｜確認 {esc(r.get("verified") or "未確認")}</div>'
            "</article>"
        )
    return "".join(out)


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
  h2 { font-size:19px; margin:56px 0 6px; padding-top:28px; border-top:1px solid var(--line);
       letter-spacing:-.01em; }
  h3 { font-size:15px; margin:28px 0 8px; }
  p { margin:10px 0; color:var(--ink-2); }
  p strong, li strong, td strong { color:var(--ink); font-weight:600; }
  a { color:var(--l1); }
  code { font-family:var(--mono); font-size:.88em; background:var(--surface-2);
         padding:1px 5px; border-radius:4px; }
  pre { font-family:var(--mono); font-size:12.5px; line-height:1.7; background:var(--surface);
        border:1px solid var(--line); border-radius:8px; padding:14px 16px; overflow-x:auto;
        margin:14px 0; color:var(--ink); }
  pre code { background:none; padding:0; }
  ul { margin:10px 0; padding-left:20px; color:var(--ink-2); }
  li { margin:5px 0; }
  table { width:100%; border-collapse:collapse; margin:16px 0; font-size:13px; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line);
           vertical-align:top; }
  th { color:var(--ink-3); font-weight:600; font-size:11.5px; letter-spacing:.03em;
       text-transform:uppercase; white-space:nowrap; }
  .note { background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--l1);
          border-radius:8px; padding:14px 18px; margin:20px 0; font-size:13.5px; color:var(--ink-2); }
  .note strong { color:var(--ink); }

  /* ---- 凡例・ピル ---- */
  .pill { display:inline-block; font-family:var(--mono); font-size:10.5px; padding:1px 7px;
          border-radius:4px; vertical-align:2px; margin-left:6px; white-space:nowrap;
          border:1px solid currentColor; }
  .p-hot{color:var(--hot)} .p-active{color:var(--ok)} .p-stale{color:var(--stale)}
  .p-ended{color:var(--dead)} .p-unknown{color:var(--ink-3)} .p-manual{color:var(--l0)}

  /* ---- 層の図 ---- */
  .layers { display:grid; gap:8px; margin:18px 0; }
  .lay { display:grid; grid-template-columns:130px 1fr; gap:14px; align-items:start;
         background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:12px 14px; }
  .lay b { font-family:var(--mono); font-size:12px; }
  .lay.L1 b{color:var(--l1)} .lay.L2 b{color:var(--l2)}
  .lay.L3 b{color:var(--l3)} .lay.L0 b{color:var(--l0)}
  .lay div { font-size:13.5px; color:var(--ink-2); }

  /* ---- タイムライン ---- */
  .tl { display:grid; grid-template-columns:150px 1fr; gap:2px 10px; margin:18px 0 8px;
        font-size:12px; }
  .tl-axis, .tl-track { display:grid; grid-template-columns:repeat(var(--cols),1fr);
                        grid-column:2 !important; }
  .tl-axis { border-bottom:1px solid var(--line); padding-bottom:3px; margin-bottom:5px; }
  .tick { font-family:var(--mono); font-size:10.5px; color:var(--ink-3);
          border-left:1px solid var(--line); padding-left:4px; }
  .tl-name { font-size:11.5px; color:var(--ink-2); text-align:right; white-space:nowrap;
             overflow:hidden; text-overflow:ellipsis; line-height:16px; }
  .tl-name.approx { color:var(--ink-3); font-style:italic; }
  .tl-track { height:16px; align-items:center; }
  .bar { height:8px; border-radius:2px; display:block; }
  .bar.l-L1{background:var(--l1)} .bar.l-L2{background:var(--l2)} .bar.l-L3{background:var(--l3)}
  .bar.s-ended { background:var(--dead) !important; }
  .bar.s-stale { opacity:.42; }
  .bar.s-hot { box-shadow:0 0 0 2px color-mix(in srgb, var(--hot) 45%, transparent); }
  /* 表示範囲より前に始まっているバーは、左端を斜めに切って「ここが起点ではない」ことを示す */
  .bar.clipped { border-radius:0 2px 2px 0;
                 clip-path:polygon(4px 0, 100% 0, 100% 100%, 0 100%); }
  .legend { font-size:12px; color:var(--ink-3); margin:6px 0 0; }
  .legend span { margin-right:14px; white-space:nowrap; }
  .sw { display:inline-block; width:14px; height:8px; border-radius:2px; vertical-align:1px;
        margin-right:5px; }

  /* ---- CSS だけの絞り込み（JS を使わない） ---- */
  .filters { position:absolute; opacity:0; pointer-events:none; }
  .fbar { display:flex; flex-wrap:wrap; gap:6px; margin:16px 0 4px; }
  .fbar label { font-family:var(--mono); font-size:11.5px; padding:3px 10px; border-radius:5px;
                border:1px solid var(--line); color:var(--ink-2); cursor:pointer;
                background:var(--surface); user-select:none; }
  #f-all:checked  ~ .fbar label[for=f-all],
  #f-L1:checked   ~ .fbar label[for=f-L1],
  #f-L2:checked   ~ .fbar label[for=f-L2],
  #f-L3:checked   ~ .fbar label[for=f-L3],
  #f-L0:checked   ~ .fbar label[for=f-L0],
  #f-live:checked ~ .fbar label[for=f-live],
  #f-dead:checked ~ .fbar label[for=f-dead]
    { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  #f-L1:checked ~ .tblwrap tr:not([data-layer=L1]),
  #f-L2:checked ~ .tblwrap tr:not([data-layer=L2]),
  #f-L3:checked ~ .tblwrap tr:not([data-layer=L3]),
  #f-L0:checked ~ .tblwrap tr:not([data-layer=L0]),
  #f-live:checked ~ .tblwrap tr[data-status=ended],
  #f-live:checked ~ .tblwrap tr[data-status=stale],
  #f-dead:checked ~ .tblwrap tr[data-status=hot],
  #f-dead:checked ~ .tblwrap tr[data-status=active],
  #f-dead:checked ~ .tblwrap tr[data-status=unknown]
    { display:none; }

  /* ラジオは見えないが focus は残す。キーボードでも絞り込みを操作できるようにする。 */
  #f-all:focus-visible ~ .fbar label[for=f-all],
  #f-L1:focus-visible ~ .fbar label[for=f-L1],
  #f-L2:focus-visible ~ .fbar label[for=f-L2],
  #f-L3:focus-visible ~ .fbar label[for=f-L3],
  #f-L0:focus-visible ~ .fbar label[for=f-L0],
  #f-live:focus-visible ~ .fbar label[for=f-live],
  #f-dead:focus-visible ~ .fbar label[for=f-dead]
    { outline:2px solid var(--l1); outline-offset:2px; }

  /* ---- ページ間ナビ ---- */
  .nav { display:flex; flex-wrap:wrap; gap:4px; margin:18px 0 8px;
         padding-bottom:14px; border-bottom:1px solid var(--line); }
  .nav a { font-family:var(--mono); font-size:11.5px; padding:4px 11px; border-radius:5px;
           border:1px solid var(--line); color:var(--ink-2); text-decoration:none;
           background:var(--surface); }
  .nav a:hover { border-color:var(--ink-3); }
  .nav a.on { background:var(--ink); color:var(--bg); border-color:var(--ink); }
  .sub2 { color:var(--ink-2); font-size:13.5px; margin:14px 0 0; }

  .pagegrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(235px,1fr));
              gap:10px; margin:16px 0; }
  .pcard { display:block; padding:13px 15px; border:1px solid var(--line); border-radius:8px;
           background:var(--surface); text-decoration:none; }
  .pcard:hover { border-color:var(--ink-3); }
  .pcard b { display:block; color:var(--ink); font-size:14px; margin-bottom:3px; }
  .pcard span { color:var(--ink-3); font-size:12px; font-family:var(--mono); }

  .tblwrap { overflow-x:auto; }
  .c-name { font-weight:600; color:var(--ink); white-space:nowrap; }
  .c-name a { color:var(--ink); text-decoration:none; border-bottom:1px solid var(--line); }
  .c-layer, .c-date, .c-num { font-family:var(--mono); font-size:11.5px; color:var(--ink-3);
                              white-space:nowrap; }
  .c-num { text-align:right; }
  .c-sum { color:var(--ink-2); min-width:22em; }
  .succ { font-family:var(--mono); font-size:10.5px; color:var(--ink-3); margin-left:6px; }
  .unsure { display:block; margin-top:3px; font-size:11.5px; color:var(--stale); }
  .approx { border-bottom:1px dotted var(--ink-3); }

  /* ---- 詳細カード ---- */
  .card { background:var(--surface); border:1px solid var(--line); border-radius:8px;
          padding:18px 22px; margin:18px 0; }
  .card h3 { margin:0 0 8px; font-size:16px; }
  .card .meta { display:flex; flex-wrap:wrap; gap:4px 16px; font-family:var(--mono);
                font-size:11px; color:var(--ink-3); margin-bottom:12px;
                padding-bottom:10px; border-bottom:1px solid var(--line); }
  .card .meta .k { color:var(--ink-3); opacity:.7; margin-right:5px; }
  .card h4 { font-size:13px; margin:16px 0 4px; color:var(--ink);
              letter-spacing:.02em; }
  .card h5 { font-size:12.5px; margin:12px 0 4px; color:var(--ink-2); font-weight:600; }
  .card p { font-size:14px; }
  .card .todo { color:var(--ink-3); font-style:italic; }
  .src { margin-top:14px; padding-top:10px; border-top:1px solid var(--line);
         font-family:var(--mono); font-size:10.5px; color:var(--ink-3); }
  .src a { color:var(--ink-3); margin-right:10px; }
  footer { margin-top:64px; padding-top:24px; border-top:1px solid var(--line);
           color:var(--ink-3); font-size:12.5px; }

  @media (max-width:760px) {
    .wrap { padding:32px 14px 64px; }
    .lay { grid-template-columns:1fr; gap:4px; }
    .tl { grid-template-columns:104px 1fr; }
    .tl-name { font-size:10.5px; }
    .c-sum { display:none; }
  }
"""


AXIS_TABLE = """
| 軸の候補 | 採否 | 理由 |
|---|---|---|
| **経路上の位置**（アーキテクチャ層） | **主軸** | 役割が一意に決まり、層の違うもの同士を無理に比較せずに済む |
| 実行場所（ターミナル / IDE / クラウド） | 副軸 | L1 の中だけで使う。L2・L3 には効かないので主軸にできない |
| ビジネスモデル（OSS / 商用） | 不採用 | 分類ではなく表の列にした。同じ層に両方が混在するのが普通 |
| 用途（コーディング / 汎用 / 画像） | 不採用 | コーディング支援に範囲を絞ったので、軸として機能しない |
"""

LAYER_DIAGRAM = """L0  モデル提供元      Anthropic / OpenAI / Google / DeepSeek …     参考。ツールではない
      ↑
L2  モデルアクセス層  OpenRouter / LiteLLM / Headroom …            ルーティング・課金・圧縮・観測
      ↑
L1  エージェント本体  Claude Code / OpenCode / Cursor / Devin …    計画とツール実行のループ
      ↑              └ 副軸: ターミナル / IDE / クラウド
L3  共通基盤          MCP / AGENTS.md / Agent Skills / apm …       全層の下敷き"""


STATIC_ROWS: list[dict] = []   # main() が組み立てた rows を静的ページから参照するため

# (ファイル名, ラベル, 層の選択, 話題)。話題は site/<話題>/ の出力先と、
# ページ間リンクの `../<話題>/<ファイル名>` の両方に使う。
PAGES = [
    ("index.html",               "全体",            None,               "landscape"),
    ("l1-terminal.html",         "ターミナル",      ("L1", "terminal"), "landscape"),
    ("l1-ide.html",              "IDE",             ("L1", "ide"),      "landscape"),
    ("l1-cloud.html",            "クラウド",        ("L1", "cloud"),    "landscape"),
    ("l2.html",                  "モデルアクセス",  ("L2", None),       "landscape"),
    ("l3.html",                  "共通基盤",        ("L3", None),       "landscape"),
    ("l0.html",                  "モデル提供元",    ("L0", None),       "landscape"),
    ("context-optimization.html","文脈の最適化",    "static",           "tool-research"),
]


def href(fname: str) -> str:
    """ページ間リンク。どのページも site/<話題>/ の 1 階層下に出るので一律 ../<話題>/<file>。"""
    topic = next(t for f, _, _, t in PAGES if f == fname)
    return f"../{topic}/{fname}"


def nav(active: str) -> str:
    items = "".join(
        f'<a href="{href(f)}" class="{"on" if f == active else ""}">{esc(l)}</a>'
        for f, l, _, _ in PAGES)
    return f'<nav class="nav">{items}</nav>'


def shell(active: str, title: str, sub: str, body: str, fetched: str) -> str:
    """全ページ共通の外枠。CSS は 1 本、JS は無し、外部参照も無し。"""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{esc(title)}</h1>
  <p class="sub">{sub}</p>
</header>
{nav(active)}
{body}
<footer>
  分類は「リクエストが通る経路上の位置」を主軸、実行場所を副軸に取った。
  星の数・push 日時・リリース数・アーカイブ状態は GitHub API の実測値（取得日 {esc(fetched)}、
  <code>docs/fetch_metrics.py</code>）。それ以外の事実は各カードの出典と確認日のとおり。
  裏が取れなかった値は空欄にしてあり、推測では埋めていない。<br>
  正本は <code>docs/src/landscape/registry.yaml</code>・<code>docs/src/landscape/tools/*.md</code>・<code>docs/src/&lt;話題&gt;/*.md</code>。
  この HTML は <code>docs/build.py</code> の生成物なので直接編集しないこと。
  更新手順は <code>docs/src/landscape/UPDATE_PROMPT.md</code>。
</footer>
</div>
</body>
</html>
"""


def layer_page(fname, label, sel, rows, metrics, warnings) -> str:
    layer, place = sel
    sub_rows = [r for r in rows if r["layer"] == layer
                and (place is None or r.get("placement") == place)]
    detail = [r for r in sub_rows if r["tier"] == "detail"]
    hist = [r for r in sub_rows if r["tier"] == "history"]
    fetched = metrics.get("fetched_at", "—")
    place_txt = f"（{PLACEMENT_LABEL[place]}）" if place else ""
    body = f"""
<p class="sub2">
  {esc(LAYER_LABEL[layer])}{place_txt} の {len(sub_rows)} 項目。
  うち詳細を書いたのは {len(detail)} 項目、残り {len(hist)} 項目は表の 1 行のみ。
  <a href="{href('index.html')}">分類軸と全体のタイムラインは「全体」ページ</a>。
</p>
<h2>一覧</h2>
<div class="tblwrap"><table>
<thead><tr><th>名前</th><th>層</th><th>登場</th><th>終了</th><th>状態</th>
<th style="text-align:right">star</th><th>直近リリース</th><th>一言</th></tr></thead>
<tbody>{table(sub_rows)}</tbody>
</table></div>
"""
    if detail:
        body += f"<h2>詳細（{len(detail)} 項目）</h2>" + cards(detail, warnings)
    if hist:
        names = "、".join(esc(r["name"]) for r in hist)
        body += (f'<h2>行だけ残した {len(hist)} 項目</h2><p>{names}。'
                 "終了・停滞、あるいは自動昇格ラインに届かなかったもの。"
                 "<strong>人気を理由に落としたものは無い。</strong>詳細を書いていないだけで、"
                 "上の表には出ている。</p>")
    return shell(fname, f"{LAYER_LABEL[layer]}{place_txt}", 
                 f"AI コーディングツール・ランドスケープ ／ {esc(layer)}"
                 f"　実測値の取得日 {esc(fetched)}", body, fetched)


def fill_placeholders(text: str, rows: list[dict], warnings: list[str]) -> str:
    """静的ページの中の {{star:slug}} / {{status:slug}} / {{push:slug}} を実測値に差し替える。
    数字を原稿に直書きすると必ず腐るので、参照だけ書いて値はビルド時に入れる。"""
    by = {r["slug"]: r for r in rows}

    def sub(m):
        kind, slug = m.group(1), m.group(2)
        r = by.get(slug)
        if r is None:
            warnings.append(f"静的ページが未知のスラグを参照している: {slug}")
            return f"??{slug}??"
        if kind == "star":
            return num(r["m"].get("stars"))
        if kind == "status":
            return STATUS_LABEL[r["status"]]
        if kind == "push":
            return r["m"].get("pushed_at") or "—"
        if kind == "name":
            return esc(r["name"])
        warnings.append(f"静的ページの未知の参照種別: {kind}")
        return m.group(0)

    return re.sub(r"\{\{(star|status|push|name):([a-z0-9-]+)\}\}", sub, text)


def static_page(fname, label, topic, metrics, warnings) -> str:
    """docs/src/<話題>/<name>.md を同じ外枠で描く。図は md の中に生 HTML で書く。"""
    src = SRC / topic / fname.replace(".html", ".md")
    if not src.exists():
        warnings.append(f"静的ページの原稿が無い: docs/src/{topic}/{src.name}")
        return ""
    raw = fill_placeholders(src.read_text(encoding="utf-8"), STATIC_ROWS, warnings)
    title, sub, body_md = label, "", raw
    if raw.startswith("# "):
        head, _, rest = raw.partition("\n")
        title = head[2:].strip()
        if rest.lstrip().startswith("> "):
            line, _, rest2 = rest.lstrip().partition("\n")
            sub, body_md = line[2:].strip(), rest2
        else:
            body_md = rest
    conv = md_lib.Markdown(extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
    return shell(fname, title, esc(sub), conv.convert(body_md),
                 metrics.get("fetched_at", "—"))


# 話題③ アイデア。実測値を使わない構想置き場なので、PAGES・ナビ・外枠を既存の話題と
# 共有しない（共有すると既存ページの HTML に差分が出る）。CSS だけ同じものを埋め込む。
IDEA_MARKS = {
    "[確認済み]": '<span class="pill p-active">確認済み</span>',
    "[未確認]": '<span class="pill p-stale">未確認</span>',
}


def idea_pages(warnings: list[str]) -> dict[str, str]:
    """docs/src/ideas/*.md を 1 本 1 ページに描く。index.md が入口で、ナビの先頭に来る。"""
    srcs = sorted((SRC / "ideas").glob("*.md"), key=lambda p: (p.name != "index.md", p.name))
    if srcs and srcs[0].name != "index.md":
        warnings.append("ideas/ に index.md が無い")
    parsed = []
    for src in srcs:
        raw = src.read_text(encoding="utf-8")
        for mark, pill in IDEA_MARKS.items():
            raw = raw.replace(mark, pill)
        head, _, rest = raw.partition("\n")
        title = head[2:].strip() if head.startswith("# ") else src.stem
        sub = ""
        if rest.lstrip().startswith("> "):
            sub, _, rest = rest.lstrip().partition("\n")
            sub = sub[2:].strip()
        parsed.append((src.stem + ".html", title, sub, rest))

    def label(fname, title):
        return "一覧" if fname == "index.html" else title.split(" — ")[0]

    out = {}
    for fname, title, sub, body_md in parsed:
        items = "".join(
            f'<a href="{f}" class="{"on" if f == fname else ""}">{esc(label(f, t))}</a>'
            for f, t, _, _ in parsed)
        conv = md_lib.Markdown(extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
        out[fname] = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{esc(title)}</h1>
  <p class="sub">{esc(sub)}</p>
</header>
<nav class="nav">{items}</nav>
{conv.convert(body_md)}
<footer>
  ここは構想置き場で、未検証の主張を含む。各主張の <b>確認済み</b> / <b>未確認</b> は本文の印のとおり。
  確認済みは末尾の出典で裏を取ったもの、未確認はまだ試していないもの。<br>
  正本は <code>docs/src/ideas/*.md</code>。この HTML は <code>docs/build.py</code> の生成物なので直接編集しないこと。
</footer>
</div>
</body>
</html>
"""
    return out


def page(reg, metrics, rows, warnings) -> str:
    today = dt.date.today()
    tl_target = [r for r in rows if r["layer"] != "L0"]
    tl_missing = [r for r in tl_target if not r["origin"]]
    tnow = (today.year, today.month)
    conv = md_lib.Markdown(extensions=["tables"])
    n_detail = sum(1 for r in rows if r["tier"] == "detail")
    fetched = metrics.get("fetched_at", "—")
    links = []
    for fname, label, sel, _topic in PAGES:
        if sel is None:
            continue
        if sel == "static":
            desc = {"context-optimization.html":
                    "いま手元で使っている Headroom / CodeGraph / graphify を、対抗馬と並べて比較する"}[fname]
            links.append(f'<a class="pcard" href="{href(fname)}"><b>{esc(label)}</b>'
                         f'<span>{esc(desc)}</span></a>')
            continue
        layer, place = sel
        sub = [r for r in rows if r["layer"] == layer
               and (place is None or r.get("placement") == place)]
        nd = sum(1 for r in sub if r["tier"] == "detail")
        links.append(f'<a class="pcard" href="{href(fname)}"><b>{esc(label)}</b>'
                     f'<span>{esc(layer)}・{len(sub)} 項目（詳細 {nd}）</span></a>')
    page_links = "".join(links)

    layer_cards = "".join(
        f'<div class="lay {k}"><b>{k}　{LAYER_LABEL[k]}</b><div>{v}</div></div>'
        for k, v in [
            ("L1", "人が指示を出す面と、計画・ツール実行のループ。実行場所で <b>ターミナル / IDE / クラウド</b> に分かれる。"),
            ("L2", "エージェントとモデルの間に挟まる層。ルーティング・課金の一本化・圧縮・観測。OpenRouter と OpenCode が別物なのはここで分かる。"),
            ("L3", "プロトコル・指示形式・配布など、全層の下敷き。<b>分類は暫定</b>（後述）。"),
            ("L0", "モデルそのものの提供元。ツールではないので比較表には出すが詳細は書かない。"),
        ])

    fil = "".join(
        f'<input class="filters" type="radio" name="f" id="f-{i}"{" checked" if i == "all" else ""}>'
        for i in ["all", "L1", "L2", "L3", "L0", "live", "dead"])
    fbar = "".join(
        f'<label for="f-{i}">{lbl}</label>' for i, lbl in [
            ("all", "すべて"), ("L1", "L1 エージェント"), ("L2", "L2 アクセス層"),
            ("L3", "L3 共通基盤"), ("L0", "L0 提供元"),
            ("live", "現役のみ"), ("dead", "終了・停滞のみ")])

    body = f"""
<h2>1. この分類はどうやって導いたか</h2>
<p>
  「OpenCode と OpenRouter をまとめて」という問いは、実は<strong>層が違うものを並べる問い</strong>だった。
  OpenCode は人が指示を出すエージェント本体で、OpenRouter はその下でモデルに繋ぎにいく中継層。
  だから主軸は<strong>リクエストが通る経路上の位置</strong>に取った。この軸なら役割が一意に決まる。
</p>
{conv.convert(AXIS_TABLE)}
<p>主軸から出る層は 4 つ。</p>
<pre><code>{esc(LAYER_DIAGRAM)}</code></pre>
<div class="layers">{layer_cards}</div>

<div class="note">
  <strong>母集団を私の印象で選ばないための手当て。</strong>
  「有名なツール」を感覚で挙げると恣意的になるので、出発点には外部の実データを使った。
  具体的には Headroom というプロキシの <code>headroom wrap</code> 対応リスト — 実在の統合プロジェクトが
  「対応する価値がある」と判断して名指しした 15 個のエージェント CLI — を種にし、
  そこに欠けている著名どころを足した。調査中に GitHub の実測で見つかったもの（Oh My Pi、Kilo Code、
  ponytail など）も、私が知っていたかどうかと無関係に入れてある。
</div>

<h2>2. いつ現れ、いま動いているか</h2>
<p>
  横棒は<strong>登場から現在（または終了）まで</strong>。色は層、灰色は終了・アーカイブ済み、
  薄いものは停滞。赤い縁取りは直近 90 日のリリースが 10 件以上あるもの。
  L0（モデル提供元）はツールではないので描いていない。
</p>
<div class="note">
  <strong>この図は全部を含んでいない。</strong>
  対象 {len(tl_target)} 項目のうち描けたのは {len(tl_target) - len(tl_missing)} 項目。
  残る {len(tl_missing)} 項目（{esc("、".join(r["name"] for r in tl_missing))}）は
  <strong>登場日の裏が取れず、公開リポジトリも無い</strong>ため起点を置けなかった。
  それらしい日付を置くより空けておくほうが誠実だと判断した。一覧表には出ている。
</div>
{timeline(rows, tnow)}
<p class="legend">
  <span><i class="sw" style="background:var(--l1)"></i>L1 エージェント</span>
  <span><i class="sw" style="background:var(--l2)"></i>L2 アクセス層</span>
  <span><i class="sw" style="background:var(--l3)"></i>L3 共通基盤</span>
  <span><i class="sw" style="background:var(--dead)"></i>終了</span>
  <span><i>斜体のラベル</i> = 公表日が裏取りできず、リポジトリ作成日で代用</span>
  <span>左端を切った棒 = {TL_START[0]} 年より前に始まっている</span>
</p>

<h3>「ホット」を何で判定したか</h3>
<p>印象ではなく、取得できた数字だけで機械的に決めている。基準はこれだけ。</p>
<ul>
  <li><strong>勢いあり</strong> — 直近 {ACTIVE_DAYS} 日に push があり、かつ同期間のリリースが 10 件以上</li>
  <li><strong>現役</strong> — 直近 {ACTIVE_DAYS} 日に push がある</li>
  <li><strong>停滞</strong> — {STALE_DAYS} 日以上 push がない</li>
  <li><strong>終了</strong> — 公式に終了が告知された、またはリポジトリがアーカイブ済み</li>
  <li><strong>指標なし</strong> — 公開リポジトリが無く、同じ物差しに載せられない</li>
</ul>

<h2>3. 一覧（{len(rows)} 項目すべて）</h2>
<p>
  <strong>人気を理由にして落としたものは無い。</strong>詳細を書くかどうかだけが違う。
  自動で詳細に回したのは「現役かつ star {STAR_THRESHOLD:,} 以上」。
  星の数が取れない商用製品のうち層を代表するものは手で詳細に上げ、その旨をカードに明示した。
</p>
{fil}
<div class="fbar">{fbar}</div>
<div class="tblwrap">
<table>
<thead><tr>
  <th>名前</th><th>層</th><th>登場</th><th>終了</th><th>状態</th>
  <th style="text-align:right">star</th><th>直近リリース</th><th>一言</th>
</tr></thead>
<tbody>{table(rows)}</tbody>
</table>
</div>

<h2>4. 層ごとのページ</h2>
<p>詳細はここには置かず、層ごとのページに分けてある。1 ページが長くなりすぎると読めないため。</p>
<div class="pagegrid">{page_links}</div>

<h2>5. この表が答えていないこと</h2>
<p>ランドスケープの類は、何を載せたかより<strong>何を載せなかったか</strong>で誤解を生む。先に書いておく。</p>
<ul>
  <li><strong>モデル名と価格は載せていない。</strong>週単位で動くので、このページの更新周期では必ず嘘になる。
      L0 は「誰が作っているか」だけに留めた。</li>
  <li><strong>star は人気であって品質ではない。</strong>新しいものほど伸びやすく、
      古く安定したものほど伸びが鈍る。順位として読まないこと。</li>
  <li><strong>活動量の指標は GitHub に偏っている。</strong>実例として Aider は
      「直近リリース」列が 2025-08 のまま止まっており、その列だけ見ると死んで見える。
      実際には 2026-05 に push があり、PyPI では 2026-02 に v0.86.2 が出ているので、判定は「現役」になっている。
      列を一つだけ見て判断できない、という例。
      公開リポジトリを持たない商用製品に至っては、そもそも同じ土俵に載っていない。</li>
  <li><strong>L3 の分類は暫定。</strong>プロトコル・指示形式・配布・索引が同じ引き出しに入っていて、
      まだ割り方が見えていない。後から割り直せるよう、データ側には性格のメモだけ残してある
      （<code>registry.yaml</code> の <code>subkind</code>）。画面には出していない。</li>
  <li><strong>使ってみた評価ではない。</strong>公開情報と実測値を並べただけで、使用感は一切含まない。</li>
</ul>

"""
    return shell("index.html", "AI コーディングツール・ランドスケープ",
                 f"{len(rows)} 項目を 4 層に分けて並べた。星の数・直近リリース・アーカイブ状態は "
                 f"GitHub API の実測値（取得日 <b>{esc(fetched)}</b>）で、状態の判定はすべて"
                 f"その数字から機械的に出している。詳細は層ごとのページに分けた。",
                 body, fetched)


def main() -> int:
    reg, metrics = load()
    rows = build_rows(reg, metrics)
    warnings: list[str] = []

    seen_repo: dict[str, str] = {}
    for r in rows:
        if not r.get("verified"):
            warnings.append(f'確認日が無い: {r["slug"]}')
        else:
            age = days_since(str(r["verified"]))
            if age is not None and age > VERIFY_STALE_DAYS:
                warnings.append(
                    f'確認から {age} 日経っている（{VERIFY_STALE_DAYS} 日超）: {r["slug"]}')
        if r["tier"] == "detail" and not (r.get("sources") or []):
            warnings.append(f'詳細ティアだが出典が無い: {r["slug"]}')
        # 同じ repo が 2 項目に付いていたら、統合の取り込み漏れ。
        if r.get("repo"):
            key = r["repo"].lower()
            if key in seen_repo:
                warnings.append(
                    f'repo が重複している（統合の取り込み漏れの可能性）: '
                    f'{seen_repo[key]} と {r["slug"]} がどちらも {r["repo"]}')
            seen_repo[key] = r["slug"]
        # registry に repo があるのに metrics が無い = fetch を流し忘れている。
        if r.get("repo") and not r["m"]:
            warnings.append(
                f'repo があるのに実測値が無い（fetch_metrics.py を流し直すこと）: {r["slug"]}')

    # 前回の状態を読み、遷移を出す。index.html を diff させるより確実で、
    # git 管理下に無くても機能する。
    st_path = SRC / "data" / "status.json"
    prev_status = {}
    if st_path.exists():
        prev_status = json.loads(st_path.read_text(encoding="utf-8")).get("status", {})
    now_status = {r["slug"]: r["status"] for r in rows}
    transitions = [(k, prev_status.get(k), v) for k, v in now_status.items()
                   if prev_status.get(k) != v]
    gone = [k for k in prev_status if k not in now_status]
    if prev_status != now_status:
        st_path.write_text(json.dumps({"status": now_status}, ensure_ascii=False,
                                      indent=2, sort_keys=True) + "\n", encoding="utf-8")

    written, unchanged = [], []
    def emit(topic: str, fname: str, html_text: str) -> None:
        if not html_text:
            return
        rel = f"{topic}/{fname}"
        f = OUT / topic / fname
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.read_text(encoding="utf-8") == html_text:
            unchanged.append(rel)
        else:
            f.write_text(html_text, encoding="utf-8")
            written.append(rel)

    STATIC_ROWS[:] = rows
    emit("landscape", "index.html", page(reg, metrics, rows, warnings))
    for fname, label, sel, topic in PAGES:
        if sel is None:
            continue
        if sel == "static":
            emit(topic, fname, static_page(fname, label, topic, metrics, warnings))
        else:
            emit(topic, fname, layer_page(fname, label, sel, rows, metrics, warnings))
    for fname, html_text in idea_pages(warnings).items():
        emit("ideas", fname, html_text)

    if written:
        print("生成: " + "、".join(written))
    if unchanged:
        print(f"変更なし: {len(unchanged)} ページ")

    n = {"detail": 0, "history": 0}
    for r in rows:
        n[r["tier"]] += 1
    print(f"  項目 {len(rows)}（詳細 {n['detail']} / 履歴 {n['history']}）")
    if transitions or gone:
        print("\n== 状態が変わった項目 ==")
        for slug, old, new in sorted(transitions):
            label = "新規" if old is None else STATUS_LABEL.get(old, old)
            print(f"  {slug}: {label} -> {STATUS_LABEL.get(new, new)}")
        for slug in sorted(gone):
            print(f"  {slug}: registry から消えた（削除は原則禁止。意図的か確認すること）")
    else:
        print("  状態の変化なし")

    if warnings:
        print(f"\n== 警告 {len(warnings)} 件 ==")
        for w in sorted(set(warnings)):
            print("  " + w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
