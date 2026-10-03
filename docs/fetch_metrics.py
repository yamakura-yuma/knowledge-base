#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""GitHub から実測値を取って docs/src/data/metrics.json に落とす。

方針:
  - 取れた値しか書かない。取れなければ前回値を温存する。推測は一切しない。
  - 冪等。実データに差が無ければファイルに触らない（fetched_at も更新しない）ので、
    続けて 2 回流しても git の差分は出ない。
  - 認証は `gh` に任せる。gh が無い / 未認証なら未認証の API に落として続行する。

使い方:  uv run docs/fetch_metrics.py [--registry docs/src/landscape/registry.yaml]
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

import yaml

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src"
API = "https://api.github.com"
WINDOW_DAYS = 90
# star は大きなリポジトリだと数秒で動く。そのまま比較すると定期実行のたびに
# 中身の無いコミットが出るので、意味のある変化だけを「変化」とみなす。
STAR_NOISE_ABS = 50
STAR_NOISE_PCT = 0.01
# 保守モードの告知は README の冒頭に置かれる。深い節の「maintenance mode」（運用機能の
# 説明など）を拾わないよう、先頭だけを見る。語句は microsoft/graphrag の告知
# （"largely in maintenance mode"）と、registry の全リポジトリの README で誤検出が出ないことを
# 見て決めた。広げるときは docs/test_fetch_metrics.py に実例を足す。
README_HEAD_CHARS = 4000
MAINTENANCE_PATTERN = re.compile(
    r"\b(?:in|into)\s+maintenance[\s-]+(?:only[\s-]+)?mode\b"
    r"|\bmaintenance[\s-]+only\b",
    re.IGNORECASE,
)


def gh_token() -> str | None:
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=15
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    tok = out.stdout.strip()
    return tok or None


class ApiError(RuntimeError):
    pass


def api_get(path: str, token: str | None):
    req = urllib.request.Request(f"{API}/{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "knowledge-base-landscape")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 403 and "rate limit" in e.read().decode("utf-8", "replace").lower():
            raise ApiError("rate-limited") from e
        raise ApiError(f"HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ApiError(f"network: {e.reason}") from e


def detect_maintenance(readme: str) -> str | None:
    """README の冒頭に保守モードの告知があれば、該当した語句を返す。無ければ None。"""
    m = MAINTENANCE_PATTERN.search(readme[:README_HEAD_CHARS])
    return m.group(0) if m else None


def fetch_repo(repo: str, token: str | None) -> dict:
    r = api_get(f"repos/{repo}", token)
    out = {
        # full_name は改名・移転を検出するために持つ。registry と食い違ったら人間に上げる。
        "resolved_repo": r.get("full_name"),
        "stars": r.get("stargazers_count"),
        "created_at": (r.get("created_at") or "")[:10] or None,
        "pushed_at": (r.get("pushed_at") or "")[:10] or None,
        "archived": r.get("archived"),
        "license": (r.get("license") or {}).get("spdx_id"),
        "description": r.get("description"),
        "homepage": r.get("homepage") or None,
    }
    try:
        rels = api_get(f"repos/{repo}/releases?per_page=100", token)
    except ApiError:
        rels = []
    dates = sorted(
        ((x.get("published_at") or "")[:10] for x in rels if x.get("published_at")),
        reverse=True,
    )
    # 集計せずに日付そのものを持つ。「直近 90 日」のような窓の計算は build.py 側でやる。
    # ここで数えてしまうと、上流に何も起きていなくても日付が変わるだけでファイルが動く。
    out["release_dates"] = dates
    out["last_release"] = dates[0] if dates else None
    out["first_release"] = dates[-1] if dates else None
    # releases が 100 件で頭打ちなら first_release は「取れた中で最古」でしかない
    out["releases_truncated"] = len(rels) >= 100
    # README が取れなかったときは判定しない（キーを置かない）。None は「告知なしと確認した」の意味。
    try:
        readme = api_get(f"repos/{repo}/readme", token)
        text = base64.b64decode(readme.get("content") or "").decode("utf-8", "replace")
        out["maintenance_phrase"] = detect_maintenance(text)
    except (ApiError, ValueError):
        pass
    return out


def materially_same(old: dict, new: dict) -> bool:
    """star の微小な増減を無視して、実質的に同じデータかを判定する。"""
    if old.keys() != new.keys():
        return False
    for slug, nv in new.items():
        ov = old.get(slug)
        if ov is None:
            return False
        for field in set(ov) | set(nv):
            if field == "stars":
                continue
            if ov.get(field) != nv.get(field):
                return False
        o, n = ov.get("stars"), nv.get("stars")
        if (o is None) != (n is None):
            return False
        if o is not None:
            if abs(n - o) > max(STAR_NOISE_ABS, int(o * STAR_NOISE_PCT)):
                return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=str(SRC / "landscape" / "registry.yaml"))
    ap.add_argument("--out", default=str(SRC / "data" / "metrics.json"))
    ap.add_argument("--only", default=None,
                    help="スラグをカンマ区切りで指定。そのリポジトリだけ引き直す（改名対応の再実行用）")
    ap.add_argument("--allow-unauthenticated", action="store_true",
                    help="未認証でも実行する。必ず途中でレート制限に当たるので通常は使わない")
    args = ap.parse_args()

    registry = yaml.safe_load(pathlib.Path(args.registry).read_text(encoding="utf-8"))
    tools = registry.get("tools") or []

    out_path = pathlib.Path(args.out)
    previous = {}
    if out_path.exists():
        previous = json.loads(out_path.read_text(encoding="utf-8")).get("repos", {})

    repos = {t["slug"]: t["repo"] for t in tools if t.get("repo")}
    if args.only:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        unknown = want - set(repos)
        if unknown:
            print(f"error: registry に repo つきで存在しないスラグ: {sorted(unknown)}", file=sys.stderr)
            return 2
        repos = {k: v for k, v in repos.items() if k in want}

    token = gh_token()
    needed = len(repos) * 3  # repos/{r}、releases/、readme で 3 回ずつ
    if not token:
        print(f"error: gh の認証トークンが取れない。"
              f"今回は {needed} リクエストが必要だが、未認証の上限は 60 req/h しかなく、"
              f"{'必ず' if needed > 60 else 'おそらく'}途中で失敗する。\n"
              f"       `gh auth login` で認証してから実行すること。"
              f"どうしても未認証で流すなら --allow-unauthenticated を付ける。", file=sys.stderr)
        if not args.allow_unauthenticated:
            return 2

    print(f"{len(repos)} 件のリポジトリを引く（全 {len(tools)} 項目中、{needed} リクエスト）")

    # --only のときは対象外の項目を落とさないよう、前回値から始める。
    # （ここを空 dict から始めると、指定しなかった全項目が metrics.json から消える）
    fetched = dict(previous) if args.only else {}
    failures, renamed = [], []
    for slug, repo in repos.items():
        try:
            data = fetch_repo(repo, token)
        except ApiError as e:
            # 新規項目の初回取得失敗は、既存項目の失敗と意味が違う。
            # 前者は「何も残らない」ので、黙って消えないよう別扱いにする。
            kind = "既存" if slug in previous else "新規・初回値なし"
            failures.append((slug, repo, f"{str(e)}（{kind}）"))
            if slug in previous:
                fetched[slug] = previous[slug]
            continue
        if data["resolved_repo"] and data["resolved_repo"].lower() != repo.lower():
            renamed.append((slug, repo, data["resolved_repo"]))
        # README が取れなかった回は判定を持たない。前回の判定があれば温存する。
        if "maintenance_phrase" not in data and "maintenance_phrase" in previous.get(slug, {}):
            data["maintenance_phrase"] = previous[slug]["maintenance_phrase"]
        fetched[slug] = data
        star = data["stars"]
        print(f"  {slug:24s} {repo:36s} ★{star if star is not None else '-':>7}"
              f"  last={data['last_release'] or '-'}  rel={len(data['release_dates'])}")

    # 全件取得のときだけ、registry から消えた項目を metrics からも落とす。
    if not args.only:
        fetched = {k: v for k, v in fetched.items() if k in repos}
    payload = {"schema_version": 1, "window_days": WINDOW_DAYS, "repos": fetched}

    # 冪等性: 実データが前回と同じならファイルに触らない（fetched_at も動かさない）。
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        same_meta = all(old.get(k) == payload[k] for k in ("schema_version", "window_days"))
        if same_meta and materially_same(old.get("repos", {}), fetched):
            print(f"\n実質的な変更なし（star の増減が ±{STAR_NOISE_ABS} / {STAR_NOISE_PCT:.0%} 未満）。"
                  "ファイルは更新しない。")
            if failures:
                print(f"※ ただし取得失敗が {len(failures)} 件ある。"
                      "全件失敗していれば前回値がそのまま残るため「変更なし」に見えるだけなので、"
                      "下の失敗一覧を必ず読むこと。")
            _report(failures, renamed)
            return 1 if failures else 0

    payload_with_ts = {"fetched_at": dt.date.today().isoformat(), **payload}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload_with_ts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\n書き出した: {out_path}")
    _report(failures, renamed)
    return 1 if failures else 0


def _report(failures, renamed):
    if renamed:
        print("\n== 改名 / 移転を検出（registry.yaml の repo を直すこと）==")
        for slug, old, new in renamed:
            print(f"  {slug}: {old} -> {new}")
    if failures:
        print("\n== 取得失敗（推測で埋めないこと。repo を調べ直すか null のままにする）==")
        for slug, repo, why in failures:
            print(f"  {slug}: {repo} — {why}")
    else:
        print("\n取得失敗なし。")


if __name__ == "__main__":
    sys.exit(main())
