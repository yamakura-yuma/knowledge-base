#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""パターン・カタログの出典候補を GitHub から集めて docs/src/data/candidates.json に落とす。

方針:
  - LLM を使わない。GitHub の topic 検索と awesome 系リストのリンクだけから、機械的に並べる。
  - 並べる物差しは star の総数ではなく増加速度（作成日から今日までの 1 日あたり star）。
    直近 push と非アーカイブで足切りしてから並べる。GitHub API は star の履歴を返さないので、
    全候補に同じ物差しを当てられるのは作成以来の平均しかない。
  - 結果はパターンの出典候補であって、ランドスケープの母集団ではない。registry.yaml には入れない。
  - 冪等。star の微小な増減と順位の入れ替わりだけならファイルに触らない。
  - 認証・API 呼び出し・「実質同じ」の判定は fetch_metrics.py のものをそのまま使う。

使い方:  uv run docs/collect_candidates.py [--top 30]
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse

import yaml

from fetch_metrics import STAR_NOISE_ABS, STAR_NOISE_PCT, ApiError, api_get, gh_token

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = SRC / "data" / "candidates.json"

# 情報源。topic は「skills・ハーネス・エージェント設定」を名乗っているもの。
TOPICS = ["claude-code", "claude-skills", "agent-skills", "agent-harness",
          "coding-agent", "codex-cli"]
AWESOME = ["hesreallyhim/awesome-claude-code", "ComposioHQ/awesome-claude-skills",
           "VoltAgent/awesome-agent-skills", "travisvn/awesome-claude-skills"]
PUSH_DAYS = 90          # これより古い push は候補にしない
MIN_AGE_DAYS = 14       # 作成直後の repo の速度が発散しないよう、年齢の下限を置く
PER_TOPIC = 100         # topic ごとに取る件数（search API の 1 ページ上限）
MAX_LIST_LOOKUPS = 200  # awesome リスト由来で個別に引く repo の上限
# リンク先として拾わないもの。リスト自身・GitHub の機能ページなど。
SKIP_OWNERS = {"features", "topics", "orgs", "apps", "marketplace", "sponsors", "settings",
               "user-attachments"}
REPO_LINK = re.compile(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)")


def slim(r: dict) -> dict:
    return {
        "repo": r["full_name"],
        "stars": r.get("stargazers_count"),
        "created_at": (r.get("created_at") or "")[:10] or None,
        "pushed_at": (r.get("pushed_at") or "")[:10] or None,
        "archived": bool(r.get("archived")),
        "description": r.get("description"),
        "topics": sorted(r.get("topics") or []),
    }


def search_topic(topic: str, since: str, token: str | None) -> list[dict]:
    q = urllib.parse.quote(f"topic:{topic} pushed:>={since} archived:false")
    res = api_get(f"search/repositories?q={q}&sort=stars&order=desc&per_page={PER_TOPIC}", token)
    return [slim(r) for r in res.get("items", [])]


def awesome_links(repo: str, token: str | None) -> set[str]:
    res = api_get(f"repos/{repo}/readme", token)
    text = base64.b64decode(res.get("content", "")).decode("utf-8", "replace")
    out = set()
    for owner, name in REPO_LINK.findall(text):
        name = name.removesuffix(".git").rstrip(".")
        if owner.lower() in SKIP_OWNERS or not name:
            continue
        out.add(f"{owner}/{name}")
    out.discard(repo)
    return out


def velocity(c: dict, today: dt.date) -> float:
    """作成以来の 1 日あたり star。"""
    age = max((today - dt.date.fromisoformat(c["created_at"])).days, MIN_AGE_DAYS)
    return c["stars"] / age


def landscape_repos() -> set[str]:
    reg = yaml.safe_load((SRC / "landscape" / "registry.yaml").read_text(encoding="utf-8"))
    return {t["repo"].lower() for t in reg.get("tools") or [] if t.get("repo")}


def same(old: list[dict], new: list[dict]) -> bool:
    """顔ぶれと star 以外の値が同じで、star の差が閾値未満なら同じとみなす。"""
    if {c["repo"] for c in old} != {c["repo"] for c in new}:
        return False
    by = {c["repo"]: c for c in old}
    for n in new:
        o = by[n["repo"]]
        for k in ("created_at", "archived", "description", "topics", "sources", "in_landscape"):
            if o.get(k) != n.get(k):
                return False
        a, b = o.get("stars") or 0, n.get("stars") or 0
        if abs(a - b) > max(STAR_NOISE_ABS, int(a * STAR_NOISE_PCT)):
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30, help="残す件数")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    token = gh_token()
    if not token:
        print("error: gh の認証トークンが取れない。search API は未認証だと 10 req/min しかない。"
              "`gh auth login` してから実行すること。", file=sys.stderr)
        return 2

    today = dt.date.today()
    since = (today - dt.timedelta(days=PUSH_DAYS)).isoformat()
    out_path = pathlib.Path(args.out)
    old = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}

    pool: dict[str, dict] = {}
    sources: dict[str, set[str]] = {}
    failures, dead = [], []
    for t in TOPICS:
        try:
            hits = search_topic(t, since, token)
        except ApiError as e:
            failures.append((f"topic:{t}", str(e)))
            continue
        print(f"  topic:{t:16s} {len(hits):4d} 件")
        for c in hits:
            pool.setdefault(c["repo"], c)
            sources.setdefault(c["repo"], set()).add(f"topic:{t}")

    listed: dict[str, set[str]] = {}
    for lst in AWESOME:
        try:
            links = awesome_links(lst, token)
        except ApiError as e:
            failures.append((lst, str(e)))
            continue
        print(f"  list:{lst:40s} {len(links):4d} リンク")
        for r in links:
            listed.setdefault(r, set()).add(f"list:{lst}")

    # リストに複数回挙がっているものから順に、まだ検索で拾っていないものを個別に引く。
    known = {k.lower() for k in pool}
    todo = sorted((r for r in listed if r.lower() not in known),
                  key=lambda r: (-len(listed[r]), r.lower()))[:MAX_LIST_LOOKUPS]
    for r in todo:
        try:
            c = slim(api_get(f"repos/{r}", token))
        except ApiError as e:
            # リストの死にリンクは取得失敗ではない。数えて報告するだけにする。
            (dead if str(e) == "HTTP 404" else failures).append((r, str(e)))
            continue
        pool.setdefault(c["repo"], c)
        known.add(c["repo"].lower())
    lower = {k.lower(): k for k in pool}
    for r, srcs in listed.items():
        if r.lower() in lower:
            sources.setdefault(lower[r.lower()], set()).update(srcs)

    in_ls = landscape_repos()
    ranked = []
    for repo, c in pool.items():
        if c["archived"] or not c["pushed_at"] or c["pushed_at"] < since:
            continue
        if c["stars"] is None or not c["created_at"]:
            continue
        if repo.split("/")[1].lower().startswith("awesome"):
            continue  # リストそのものはパターンの出典にならない
        ranked.append({**c, "stars_per_day": round(velocity(c, today), 1),
                       "sources": sorted(sources.get(repo, [])),
                       "in_landscape": repo.lower() in in_ls})
    ranked.sort(key=lambda c: (-c["stars_per_day"], c["repo"].lower()))
    top = ranked[: args.top]
    for i, c in enumerate(top, 1):
        c["rank"] = i
    for i, c in enumerate(top, 1):
        print(f"  {i:2d}. {c['repo']:44s} ★{c['stars']:>7}  {c['stars_per_day']:>7}/日")

    payload = {"schema_version": 1, "push_days": PUSH_DAYS, "topics": TOPICS,
               "awesome_lists": AWESOME, "pool_size": len(ranked), "candidates": top}
    if old and all(old.get(k) == payload[k] for k in ("schema_version", "push_days", "topics",
                                                     "awesome_lists")) \
            and same(old.get("candidates", []), top):
        print("\n実質的な変更なし。ファイルは更新しない。")
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"fetched_at": today.isoformat(), **payload},
                                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"\n書き出した: {out_path}（母集団 {len(ranked)} 件から上位 {len(top)} 件）")
    if dead:
        print(f"\nリストの死にリンク {len(dead)} 件（無視した）: " + "、".join(r for r, _ in dead))
    if failures:
        print("\n== 取得失敗 ==")
        for what, why in failures:
            print(f"  {what} — {why}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
