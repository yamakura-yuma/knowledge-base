#!/usr/bin/env python3
"""markdown の内部リンク切れを検査する。`just ci` から呼ぶ。

見るのは、相対リンクの指す先のファイル（またはディレクトリ）が git の追跡下に
あることと、`#断片` が指す見出し・id が先のファイルにあること。

見ないもの:
- 外部リンク（http(s)、mailto）。ネットワーク頼みで揺れ、PR を理由なく止めるため
  必須にしない
- コードブロックとインラインコードの中
- 生成物（docs/site/）と apm_modules/。.gitignore と追跡ファイルで決まる

断片の slug は、記号を落として小文字にし、空白を `-` に直す（日本語はそのまま残す）。
MkDocs と GitHub で規則が少し違うので、重複サフィックスは `-1` と `_1` のどちらも受ける。

標準ライブラリだけで動く（Actions の runner に uv は入っていない）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

FENCE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
# [text](dest "title") / ![alt](dest)。dest は <...> で囲まれることもある
INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
HTML_ATTR = re.compile(r"""\b(?:href|src)=["']([^"']+)["']""")
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
ID_ATTR = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""")
ATTR_LIST_ID = re.compile(r"\{[^}]*#([\w-]+)[^}]*\}")
EXTERNAL = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")


def tracked_markdown() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return sorted(ROOT / p for p in out.split("\0") if p and (ROOT / p).is_file())


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def plain_heading(raw: str) -> str:
    raw = ATTR_LIST_ID.sub("", raw)
    raw = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"[`*_~]", lambda m: "_" if m.group(0) == "_" else "", raw)
    return raw.strip()


def lines_outside_fences(text: str):
    in_fence = False
    for no, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield no, line


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path in cache:
        return cache[path]
    found: set[str] = set()
    seen: dict[str, int] = {}
    for _, line in lines_outside_fences(path.read_text(encoding="utf-8")):
        m = HEADING.match(line)
        if m:
            raw = m.group(2)
            ids = ATTR_LIST_ID.findall(raw)
            slug = ids[0] if ids else slugify(plain_heading(raw))
            n = seen.get(slug, 0)
            seen[slug] = n + 1
            found.add(slug)
            if n:
                found.add(f"{slug}_{n}")
                found.add(f"{slug}-{n}")
        found.update(ID_ATTR.findall(line))
    cache[path] = found
    return found


def destinations(line: str) -> list[str]:
    line = INLINE_CODE.sub("", line)
    out = [m.group(1) for m in INLINE_LINK.finditer(line)]
    out += HTML_ATTR.findall(line)
    m = REF_DEF.match(line)
    if m:
        out.append(m.group(1))
    return out


def check(md: Path, cache: dict[Path, set[str]]) -> list[str]:
    errors = []
    for no, line in lines_outside_fences(md.read_text(encoding="utf-8")):
        for dest in destinations(line):
            if EXTERNAL.match(dest):
                continue
            target, _, fragment = dest.partition("#")
            target = unquote(target.partition("?")[0])
            fragment = unquote(fragment)
            if target.startswith("/"):
                resolved = ROOT / target.lstrip("/")
            else:
                resolved = (md.parent / target) if target else md
            where = f"{md.relative_to(ROOT)}:{no}"
            if not resolved.exists():
                errors.append(f"{where}: リンク先が無い: {dest}")
            elif fragment and resolved.suffix == ".md" and fragment not in anchors_of(resolved, cache):
                errors.append(f"{where}: 見出し・id が無い: {dest}")
    return errors


def main() -> int:
    cache: dict[Path, set[str]] = {}
    files = tracked_markdown()
    errors = [e for md in files for e in check(md, cache)]
    for e in errors:
        print(e, file=sys.stderr)
    print(f"check_links: {len(files)} ファイル、リンク切れ {len(errors)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
