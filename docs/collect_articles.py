#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""パターン・カタログの使用報告の候補として、人気の技術記事を集めて docs/src/data/articles.json に落とす。

方針:
  - LLM を使わない。媒体ごとの API で「AI コーディングエージェントとハーネス」のトピック・タグ・
    検索語から記事を引き、直近 WINDOW_DAYS 日以内・反応数の下限・題名の語で足切りして、
    媒体ごとに反応数の多い順に上位を残す。媒体をまたいで反応数を比べない（尺度が違う）。
  - 反応数は媒体ごとの数をそのまま使う。Zenn はいいね、Qiita はいいね、Hacker News は
    ポイント、dev.to はリアクション。
  - 認証の要る API は使わない。Qiita は未認証だと 60 req/h なので、1 回の実行の呼び出しは 12 回（1 時間に 5 回まで流せる）。
    Qiita の検索はいいね数で絞れないので、ストック数で先に絞ってからいいね数で並べる。
  - テーマは 2 つ。harness（ハーネスの型）と slop（AI が書いた文章・コードの質の低さと、その除去）。
    取得元・足切りの語・残す件数をテーマごとに持ち、記事には theme を付ける。
  - 名前を挙げたハーネス（poteto-mode ほか）は、題名にその名前がある記事を別枠（reputation）に
    数える。評判を比べるための数で、カタログへの反映は記事を読んでから手で行う。
  - 冪等。反応数の微小な増減と順位の入れ替わりだけならファイルに触らない。

使い方:  uv run docs/collect_articles.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "src" / "data" / "articles.json"

WINDOW_DAYS = 365
# 媒体ごとの取得元と、残す件数・反応数の下限。
ZENN_TOPICS = ["claudecode", "codex", "cursor", "mcp", "aiagent", "agentskills"]
QIITA_TAGS = ["ClaudeCode", "Codex", "Cursor", "MCP", "AIエージェント"]
HN_QUERIES = ["claude code", "codex cli", "cursor agent", "coding agent", "agent skills",
              "subagents", "AGENTS.md", "CLAUDE.md", "MCP server"]
DEVTO_TAGS = ["claudecode", "codex", "cursor", "mcp", "aiagents"]
TOP = {"zenn": 12, "qiita": 10, "hn": 10, "devto": 6}
MIN_REACTIONS = {"zenn": 50, "qiita": 50, "hn": 100, "devto": 20}
# slop のテーマ。Qiita はタグが揃っていないので題名で引く（未認証の呼び出し回数を増やさないよう 2 回まで）。
SLOP_ZENN_TOPICS = ["aislop", "slop"]
SLOP_ZENN_SEARCH = ["AI Slop", "AIっぽい", "ヒューマナイザー"]
SLOP_QIITA_TITLES = ["AIっぽい", "slop"]
SLOP_HN_QUERIES = ["AI slop", "slop", "humanizer", "AI-generated code"]
SLOP_TOP = {"zenn": 5, "qiita": 4, "hn": 6}
SLOP_MIN_REACTIONS = {"zenn": 20, "qiita": 20, "hn": 100}
REACTION_NOISE_ABS = 10
REACTION_NOISE_PCT = 0.05

# 題名（Qiita・dev.to はタグも）にどれかが無い記事は、ハーネスの話ではないとみなして落とす。
PRACTICE = re.compile(
    r"hook|フック|skill|スキル|sub-?agent|サブエージェント|agent\.md|agents\.md|claude\.md|"
    r"mcp|worktree|並列|parallel|memory|メモリ|context|コンテキスト|harness|ハーネス|"
    r"workflow|ワークフロー|運用|実践|tips|best practice|使い方|how i use|lessons|"
    r"tdd|テスト|review|レビュー|plan|計画|rule|ルール|prompt|プロンプト|slash|コマンド|"
    r"permission|権限|sandbox|サンドボックス|autonomous|自律|loop|ループ|spec|仕様", re.I)
SLOP = re.compile(r"slop|スロップ|humaniz|ヒューマナイ|aiっぽ|ai臭|ai 臭|ai-generated|ai generated|"
                  r"生成aiが書いた|aiが書いた|ai が書いた|ai writing|llm-generated|machine-written", re.I)
# HN は検索が曖昧なので、題名にエージェントの文脈があることも求める。
AGENT = re.compile(r"claude|codex|cursor|agent|エージェント|devin|copilot|mcp|llm|ai ", re.I)
# 評判を数えるハーネス。名前: (検索語, 題名の正規表現)。題名に一致した記事だけを数える。
# poteto は同名の Go の Web フレームワーク、pstack は同名のスタックダンプ・ツールがあるので、
# 題名の一致は Cursor の pstack と分かる形に限る。
NAMED = {
    "poteto-mode": ("pstack", r"poteto[- ]?mode|^pstack$|guide to pstack|cursor.{0,20}pstack|pstack.{0,20}(cursor|plugin)"),
    "Hermes Agent": ("Hermes Agent", r"hermes[ -]agent"),
    "DeepSeek Harness": ("DeepSeek Harness", r"deepseek[ -]harness"),
    "Devin": ("Devin", r"\bdevin\b"),
}


class ApiError(Exception):
    pass


def get(url: str, tries: int = 3):
    req = urllib.request.Request(url, headers={"User-Agent": "knowledge-base-articles",
                                               "Accept": "application/json"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            raise ApiError(f"HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if i < tries - 1:
                time.sleep(3)
                continue
            raise ApiError(str(e)) from None
    raise ApiError("retries exhausted")


def art(site, aid, title, url, reactions, published, tags=(), via=()):
    return {"id": f"{site}:{aid}", "site": site, "title": title.strip(), "url": url,
            "reactions": reactions, "published": published[:10], "tags": sorted(set(tags)),
            "via": sorted(set(via))}


# ---------------------------------------------------------------- 媒体ごとの取得

def zenn_topic(topic: str) -> list[dict]:
    out = []
    for page in (1, 2):  # alltime はいいね順。2 ページ（200 件）で下限を下回る
        d = get(f"https://zenn.dev/api/articles?topicname={topic}&order=alltime&count=100&page={page}")
        for a in d.get("articles", []):
            out.append(art("zenn", a["slug"], a["title"], "https://zenn.dev" + a["path"],
                           a["liked_count"], a["published_at"], via=[f"topic:{topic}"]))
        if not d.get("next_page"):
            break
    return out


def zenn_search(q: str) -> list[dict]:
    d = get("https://zenn.dev/api/search?" + urllib.parse.urlencode(
        {"q": q, "source": "articles", "order": "alltime"}))
    return [art("zenn", a["slug"], a["title"], "https://zenn.dev" + a["path"], a["liked_count"],
                a["published_at"], via=[f"search:{q}"]) for a in d.get("articles", [])]


def qiita(query: str, via: str, pages: int = 2) -> list[dict]:
    out = []
    for page in range(1, pages + 1):
        d = get("https://qiita.com/api/v2/items?" + urllib.parse.urlencode(
            {"query": query, "per_page": 100, "page": page}))
        out += [art("qiita", a["id"], a["title"], a["url"], a["likes_count"], a["created_at"],
                    tags=[t["name"] for t in a.get("tags", [])], via=[via]) for a in d]
        if len(d) < 100:
            break
    return out


def hn(query: str, since: int, min_points: int) -> list[dict]:
    d = get("https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": query, "tags": "story", "hitsPerPage": 100,
         "numericFilters": f"points>={min_points},created_at_i>={since}"}))
    return [art("hn", h["objectID"], h["title"],
                h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                h["points"], h["created_at"], via=[f"query:{query}"])
            for h in d.get("hits", [])]


def devto(tag: str) -> list[dict]:
    d = get(f"https://dev.to/api/articles?tag={tag}&top={WINDOW_DAYS}&per_page=100")
    return [art("devto", a["id"], a["title"], a["url"], a["public_reactions_count"],
                a["published_at"], tags=a.get("tag_list") or [], via=[f"tag:{tag}"]) for a in d]


# ---------------------------------------------------------------- 選別

def merge(pool: dict, items: list[dict]) -> None:
    for a in items:
        if a["id"] in pool:
            pool[a["id"]]["via"] = sorted(set(pool[a["id"]]["via"]) | set(a["via"]))
        else:
            pool[a["id"]] = a


def keep_slop(a: dict, since: str) -> bool:
    if a["published"] < since or a["reactions"] < SLOP_MIN_REACTIONS[a["site"]]:
        return False
    # slop のトピックに付いた記事は題名を問わない。それ以外は題名かタグに slop の語を求める。
    # HN は slop の語そのものが AI の文脈なので、エージェントの語は求めない。
    if any(v in (f"topic:{t}" for t in SLOP_ZENN_TOPICS) for v in a["via"]):
        return True
    return bool(SLOP.search(a["title"] + " " + " ".join(a["tags"])))


def keep(a: dict, since: str) -> bool:
    if a["published"] < since or a["reactions"] < MIN_REACTIONS[a["site"]]:
        return False
    text = a["title"] + " " + " ".join(a["tags"])
    if a["site"] == "hn" and not AGENT.search(a["title"] + " "):
        return False
    return bool(PRACTICE.search(text))


def same(old: list[dict], new: list[dict]) -> bool:
    """顔ぶれと反応数以外の値が同じで、反応数の差が閾値未満なら同じとみなす。"""
    if {a["id"] for a in old} != {a["id"] for a in new}:
        return False
    by = {a["id"]: a for a in old}
    for n in new:
        o = by[n["id"]]
        for k in ("title", "url", "published", "tags", "via", "site", "theme"):
            if o.get(k) != n.get(k):
                return False
        a, b = o.get("reactions") or 0, n.get("reactions") or 0
        if abs(a - b) > max(REACTION_NOISE_ABS, int(a * REACTION_NOISE_PCT)):
            return False
    return True


def main() -> int:
    today = dt.date.today()
    since = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    since_ts = int(dt.datetime.combine(today - dt.timedelta(days=WINDOW_DAYS), dt.time()).timestamp())
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

    pool: dict[str, dict] = {}
    failures = []
    jobs = ([(f"zenn topic:{t}", lambda t=t: zenn_topic(t)) for t in ZENN_TOPICS]
            + [(f"qiita tag:{t}", lambda t=t: qiita(f"tag:{t} created:>{since} "
                                                      f"stocks:>{MIN_REACTIONS['qiita']}", f"tag:{t}"))
               for t in QIITA_TAGS]
            + [(f"hn {q}", lambda q=q: hn(q, since_ts, MIN_REACTIONS["hn"])) for q in HN_QUERIES]
            + [(f"devto tag:{t}", lambda t=t: devto(t)) for t in DEVTO_TAGS])
    for name, fn in jobs:
        try:
            items = fn()
        except ApiError as e:
            failures.append((name, str(e)))
            continue
        print(f"  {name:28s} {len(items):4d} 件")
        merge(pool, items)

    slop_pool: dict[str, dict] = {}
    jobs = ([(f"zenn topic:{t}", lambda t=t: zenn_topic(t)) for t in SLOP_ZENN_TOPICS]
            + [(f"zenn search:{q}", lambda q=q: zenn_search(q)) for q in SLOP_ZENN_SEARCH]
            + [(f"qiita title:{t}", lambda t=t: qiita(f"title:{t} created:>{since}", f"title:{t}", pages=1))
               for t in SLOP_QIITA_TITLES]
            + [(f"hn {q}", lambda q=q: hn(q, since_ts, SLOP_MIN_REACTIONS["hn"])) for q in SLOP_HN_QUERIES])
    for name, fn in jobs:
        try:
            items = fn()
        except ApiError as e:
            failures.append((name, str(e)))
            continue
        print(f"  slop {name:23s} {len(items):4d} 件")
        merge(slop_pool, items)

    picked = []
    for theme, src, top, ok in (("harness", pool, TOP, keep), ("slop", slop_pool, SLOP_TOP, keep_slop)):
        taken = {a["id"] for a in picked}
        for site, n in top.items():
            cand = sorted((a for a in src.values() if a["site"] == site and a["id"] not in taken
                           and ok(a, since)), key=lambda a: (-a["reactions"], a["id"]))
            for i, a in enumerate(cand[:n], 1):
                picked.append({**a, "theme": theme, "rank": i})
            print(f"  {theme:7s} {site:6s} 母集団 {len(cand):4d} 件から上位 {min(n, len(cand))} 件")

    # 名前を挙げたハーネスの評判。期間で切らない（古い評判も比べたい）。反応数の下限も置かない。
    reputation = {}
    for label, (q, pat) in NAMED.items():
        rx = re.compile(pat, re.I)
        hits: dict[str, dict] = {}
        for name, fn in [(f"zenn search:{q}", lambda: zenn_search(q)),
                         (f"qiita title:{q}", lambda: qiita(" ".join(f"title:{w}" for w in q.split()), f"title:{q}", pages=1)),
                         (f"hn {q}", lambda: hn(q, 0, 1))]:
            try:
                items = fn()
            except ApiError as e:
                failures.append((name, str(e)))
                continue
            merge(hits, [a for a in items if rx.search(a["title"])])
        top = sorted(hits.values(), key=lambda a: (-a["reactions"], a["id"]))
        reputation[label] = {
            "query": q, "pattern": pat,
            "count": {s: sum(1 for a in top if a["site"] == s) for s in ("zenn", "qiita", "hn")},
            "reactions": {s: sum(a["reactions"] for a in top if a["site"] == s)
                          for s in ("zenn", "qiita", "hn")},
            "top": [{k: a[k] for k in ("id", "site", "title", "url", "reactions", "published")}
                    for a in top[:5]],
        }
        print(f"  評判 {label:18s} " + " ".join(f"{s}={c}" for s, c in reputation[label]["count"].items()))

    config = {"schema_version": 1, "window_days": WINDOW_DAYS, "top": TOP,
              "min_reactions": MIN_REACTIONS, "zenn_topics": ZENN_TOPICS, "qiita_tags": QIITA_TAGS,
              "hn_queries": HN_QUERIES, "devto_tags": DEVTO_TAGS,
              "slop": {"top": SLOP_TOP, "min_reactions": SLOP_MIN_REACTIONS, "zenn_topics": SLOP_ZENN_TOPICS,
                       "zenn_search": SLOP_ZENN_SEARCH, "qiita_titles": SLOP_QIITA_TITLES,
                       "hn_queries": SLOP_HN_QUERIES}, "named": {k: list(v) for k, v in NAMED.items()}}
    # 評判は本数と上位の顔ぶれで比べる。反応数の微小な増減による順位の入れ替わりでは書き直さない。
    rep_same = old.get("reputation", {}).keys() == reputation.keys() and all(
        old["reputation"][k]["count"] == v["count"] and
        {a["id"] for a in old["reputation"][k]["top"]} == {a["id"] for a in v["top"]}
        for k, v in reputation.items())
    if failures:
        print("\n== 取得失敗 ==（ファイルは更新しない）")
        for what, why in failures:
            print(f"  {what} — {why}")
        return 1
    if old and all(old.get(k) == v for k, v in config.items()) and rep_same \
            and same(old.get("articles", []), picked):
        print("\n実質的な変更なし。ファイルは更新しない。")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fetched_at": today.isoformat(), **config, "articles": picked,
                               "reputation": reputation}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"\n書き出した: {OUT}（{len(picked)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
