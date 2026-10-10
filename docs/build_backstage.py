#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "markdown"]
# ///
"""docs/src/backstage/*.md から docs/site/backstage/ 以下の HTML を組む。

argocd-notify と同じく独立した系統で、build.py の PAGES やナビには載せない。
CSS と archify の図の描き方は build_argocd_notify.py のものをそのまま使い、ナビとフッターだけをこの話題のものにする。

使い方:  uv run docs/build_backstage.py   （build.py とは別に流す）
"""

from __future__ import annotations

import html
import pathlib
import sys

import markdown as md_lib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_argocd_notify as base  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src" / "backstage"
OUT = HERE / "site" / "backstage"

# (ファイル名の stem, ナビのラベル)。index が入口、app が本体と環境のタブの仕組み、残りがプラグインごとのページ。
PAGES = [
    ("index",    "入口"),
    ("app",      "本体と環境のタブ"),
    ("swagger",  "Swagger"),
    ("argocd",   "ArgoCD"),
    ("azure",    "Azure"),
    ("temporal", "Temporal"),
    ("grafana",  "Grafana"),
    ("techdocs", "TechDocs"),
    ("search",   "検索"),
]


def nav(active: str) -> str:
    items = "".join(f'<a href="{s}.html" class="{"on" if s == active else ""}">{html.escape(l)}</a>'
                    for s, l in PAGES)
    return f'<nav class="nav">{items}</nav>'


def page(stem: str, label: str, warnings: list[str]) -> str:
    src = SRC / f"{stem}.md"
    if not src.exists():
        warnings.append(f"原稿が無い: docs/src/backstage/{src.name}")
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
    body_md = base.render_diagrams(body_md, warnings, src.name, SRC)
    conv = md_lib.Markdown(extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
    body = base.md_links_to_html(conv.convert(body_md))
    sub_html = md_lib.markdown(sub).removeprefix("<p>").removesuffix("</p>")
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{base.CSS}</style>
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
  正本は <code>docs/src/backstage/*.md</code>。この HTML は <code>docs/build_backstage.py</code>
  の生成物なので直接編集しないこと。書いた事実は yamakura-yuma/home-k8s の main（2026-10-10 時点）のファイルと照らし合わせた。
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
        print("backstage 生成: " + "、".join(written))
    if unchanged:
        print(f"backstage 変更なし: {len(unchanged)} ページ")
    if warnings:
        print("警告:")
        for w in warnings:
            print(f"  {w}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
