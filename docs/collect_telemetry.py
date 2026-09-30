#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""home-k8s の Grafana から Claude Code と Orca のテレメトリを集計し、日報（週報）の数字の節を書く。

方針: 取れた値しか書かない。取れなかった値は「—」にし、推測で埋めない。
比べるのは直近の 1 期間と、その前の 1 期間。期間の長さは --period で決める
（日報は 1d、週報は 7d）。あわせて直近 7 日の日別の推移を出す。

出力は 2 つ。
- docs/src/data/telemetry/<名前>.json   集計した数字（実測値。手で編集しない）
- <out-dir>/<名前>.md                   数字の節。`<!-- numbers:begin -->` から
  `<!-- numbers:end -->` までだけを書き換え、提案の節（人かエージェントが書く）には触らない

データ源の使い分け（home-k8s の docs/observability と、このスクリプトを書いたときの実測による）:
- コスト・キャッシュ・依頼・ツール・skill・MCP は Loki の Claude Code のイベントから取る。
  Prometheus の claude_code_*_total は、セッション ID をラベルから外しているため別々の
  プロセスが同じ系列に書き、カウンタのリセットが頻発する。increase() が実際の数十倍になる
  ことがあるので、合計には使わず「データの質」の欄に比較だけ出す
- Fable（advisor）は Loki に api_request が出ないので、Prometheus から取る。リセット回数も併記する
- Orca は home-k8s の orca-exporter のゲージ（Prometheus）から、Dispatch の開始時刻で期間に振り分ける

パスワードはファイルから読むだけで、どこにも書き出さない。依頼文・コマンドの全文・
利用者の ID も書き出さない（このリポジトリは公開）。

使い方:
  uv run docs/collect_telemetry.py --period 1d --out-dir docs/src/telemetry-daily
  uv run docs/collect_telemetry.py --period 7d --out-dir docs/src/telemetry-weekly
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
DATA_DIR = HERE / "src" / "data" / "telemetry"
GRAFANA = "http://localhost:3000"
PASSWORD_FILE = pathlib.Path.home() / ".local/share/home-k8s/observability/grafana-admin-password"
JST = dt.timezone(dt.timedelta(hours=9))
CC = '{service_name="claude-code"}'
ORCA_JOB = 'job="home-k8s/orca"'
# 入れている skill の置き場所。ホスト全体と、主なリポジトリの本体の checkout に apm install が
# 展開した先。ここに無いものは「使われていない skill」の母集団に入らない
SKILL_DIRS = [
    pathlib.Path.home() / ".claude/skills",
    *(pathlib.Path.home() / r / ".claude/skills" for r in ("dotfiles", "coordinator", "knowledge-base", "k8s-workspace/home-k8s")),
]
BEGIN, END = "<!-- numbers:begin -->", "<!-- numbers:end -->"
FAILED, BASH, MCP, CONNECTED = ' | success="false"', ' | tool_name="Bash"', ' | tool_name="mcp_tool"', ' | status="connected"'
MIN_REQUESTS = 10  # home-k8s playbook 場面 8: 依頼が 10 件未満のうちは判断しない


class Grafana:
    def __init__(self) -> None:
        pw = PASSWORD_FILE.read_text().strip()
        self.auth = "Basic " + base64.b64encode(f"admin:{pw}".encode()).decode()

    def _get(self, path: str, params: dict) -> dict:
        url = f"{GRAFANA}{path}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"Authorization": self.auth})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.load(r)
        if body.get("status") != "success":
            raise RuntimeError(f"{path}: {body}")
        return body["data"]

    def prom(self, q: str, t: int) -> list[dict]:
        return self._get("/api/datasources/uid/prometheus/resources/api/v1/query", {"query": q, "time": t})["result"]

    def loki(self, q: str, t: int) -> list[dict]:
        return self._get("/api/datasources/uid/loki/resources/query", {"query": q, "time": t})["result"]

    def loki_logs(self, q: str, start: int, end: int) -> list[dict]:
        return self._get(
            "/api/datasources/uid/loki/resources/query_range",
            {"query": q, "start": start, "end": end, "limit": 5000},
        )["result"]


def by(rows: list[dict], *keys: str) -> dict:
    """ベクトルの結果を {ラベルの組: 値} にする。"""
    out = {}
    for r in rows:
        k = tuple(r["metric"].get(x, "") for x in keys)
        out[k[0] if len(k) == 1 else k] = float(r["value"][1])
    return out


def total(rows: list[dict]) -> float | None:
    return float(rows[0]["value"][1]) if rows else None


def ratio(a, b):
    return a / b if a is not None and b else None


def window(g: Grafana, t: int, rng: str) -> dict:
    """[t-rng, t] の Claude Code の数字。"""
    L = lambda q: g.loki(q, t)  # noqa: E731
    ev = lambda name, extra="": f'{CC} | event_name="{name}"{extra}'  # noqa: E731
    requests = total(L(f"sum(count_over_time({ev('user_prompt')} [{rng}]))")) or 0
    cost_model = by(L(f"sum by (model) (sum_over_time({ev('api_request')} | unwrap cost_usd [{rng}]))"), "model")
    tok = {}
    for f in ("input_tokens", "cache_read_tokens", "cache_creation_tokens"):
        tok[f] = by(L(f"sum by (orca_worktree_name) (sum_over_time({ev('api_request')} | unwrap {f} [{rng}]))"), "orca_worktree_name")
    workers = sorted(set().union(*tok.values()))
    cache_worker = {}
    for w in workers:
        read = tok["cache_read_tokens"].get(w, 0)
        denom = read + tok["input_tokens"].get(w, 0) + tok["cache_creation_tokens"].get(w, 0)
        cache_worker[w or "(Orca の外)"] = {"ratio": ratio(read, denom), "input_tokens_total": denom}
    read_all = sum(tok["cache_read_tokens"].values())
    denom_all = read_all + sum(tok["input_tokens"].values()) + sum(tok["cache_creation_tokens"].values())
    cost_worker = by(L(f"sum by (orca_worktree_name, model) (sum_over_time({ev('api_request')} | unwrap cost_usd [{rng}]))"), "orca_worktree_name", "model")

    tools = total(L(f"sum(count_over_time({ev('tool_result')} [{rng}]))")) or 0
    fails = total(L(f"sum(count_over_time({ev('tool_result', FAILED)} [{rng}]))")) or 0
    fail_tool = by(L(f"sum by (tool_name) (count_over_time({ev('tool_result', FAILED)} [{rng}]))"), "tool_name")
    fail_cmd = failed_commands(g, t, rng)

    skills = by(L(f"sum by (skill_name) (count_over_time({ev('skill_activated')} [{rng}]))"), "skill_name")
    mcp_conn = by(L(f'sum by (server_name) (count_over_time({ev("mcp_server_connection", CONNECTED)} [{rng}]))'), "server_name")
    mcp_calls = by(
        L(
            f"sum by (srv) (count_over_time({ev('tool_result', MCP)}"
            ' | line_format "{{.tool_parameters}}" | json srv="mcp_server_name" | drop __error__, __error_details__'
            f' | srv!="" [{rng}]))'
        ),
        "srv",
    )
    cost_loki = sum(cost_model.values())
    return {
        "requests": requests,
        "cost_by_model": cost_model,
        "cost_total_loki": cost_loki,
        "cost_per_request": ratio(cost_loki, requests),
        "cache_read_ratio": ratio(read_all, denom_all),
        "cache_read_ratio_by_worker": cache_worker,
        "cost_by_worker_model": {f"{w or '(Orca の外)'}|{m}": v for (w, m), v in cost_worker.items()},
        "tool_results": tools,
        "tool_failures": fails,
        "tool_failure_rate": ratio(fails, tools),
        "tool_failures_by_tool": fail_tool,
        "failed_commands": fail_cmd,
        "skills_activated": skills,
        "mcp_connected": mcp_conn,
        "mcp_calls": mcp_calls,
    }


# サブコマンドまで数えると意味が変わる CLI。それ以外はプログラム名だけにする
SUBCOMMAND_CLIS = {"git", "gh", "docker", "kubectl", "orca", "nix", "uv", "just", "npm", "helm", "apm", "graphify", "codegraph", "systemctl"}


def command_head(full: str) -> str:
    """コマンド行を「プログラム名（とサブコマンド）」に縮める。引数・パス・値は捨てる。"""
    for part in re.split(r"&&|\|\||;|\|", full):
        words = [w for w in part.split() if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w)]
        if not words or words[0] in ("cd", "set", "export", "true", "echo"):
            continue
        prog = words[0].rsplit("/", 1)[-1]
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", prog):
            return "(その他)"
        if prog in SUBCOMMAND_CLIS and len(words) > 1 and re.fullmatch(r"[a-z][a-z-]*", words[1]):
            return f"{prog} {words[1]}"
        return prog
    return "(その他)"


def failed_commands(g: Grafana, t: int, rng: str) -> dict:
    """失敗した Bash を「プログラム名 (エラー種別)」で数える。全文は書き出さない。"""
    span = {"d": 86400, "h": 3600}[rng[-1]] * int(rng[:-1])
    res = g.loki_logs(f'{CC} | event_name="tool_result"{FAILED}{BASH}', t - span, t)
    out: dict[str, float] = {}
    for s in res:
        try:
            full = json.loads(s["stream"].get("tool_parameters", "{}")).get("full_command", "")
        except json.JSONDecodeError:
            full = ""
        k = f"{command_head(full)} ({s['stream'].get('error_type') or '-'})"
        out[k] = out.get(k, 0) + len(s["values"])
    return out


def prom_quality(g: Grafana, t: int, rng: str) -> dict:
    """Prometheus 側のコストと、系列のリセット回数（Loki との食い違いの説明）。"""
    inc = by(g.prom(f"sum by (model) (increase(claude_code_cost_usage_USD_total[{rng}]))", t), "model")
    resets = by(g.prom(f"sum by (model) (resets(claude_code_cost_usage_USD_total[{rng}]))", t), "model")
    return {"increase_by_model": inc, "resets_by_model": resets}


def orca(g: Grafana, t: int, span: int) -> dict:
    """[t-2*span, t] に始まった Dispatch の手戻り。期間は開始時刻で振り分ける。"""
    rng = f"{2 * span}s"
    info = g.prom(f"max by (orca_dispatch_id, orca_worktree_name, orca_model, orca_dispatch_status, orca_release_retained_reason) (last_over_time(orca_dispatch_info{{{ORCA_JOB}}}[{rng}]))", t)
    metric = lambda name: by(g.prom(f"max by (orca_dispatch_id) (last_over_time(orca_dispatch_{name}{{{ORCA_JOB}}}[{rng}]))", t), "orca_dispatch_id")  # noqa: E731
    start = metric("start_time_seconds")
    cols = {n: metric(n) for n in ("followups", "questions", "escalations", "worker_done", "worker_done_rejected", "time_to_done_seconds", "failures")}
    rows = []
    for r in info:
        m = r["metric"]
        d = m.get("orca_dispatch_id")
        s = start.get(d)
        if not d or s is None or s < t - 2 * span:
            continue
        rows.append(
            {
                "dispatch": d,
                "period": "current" if s >= t - span else "previous",
                "worker": m.get("orca_worktree_name", ""),
                "model": m.get("orca_model", ""),
                "status": m.get("orca_dispatch_status", ""),
                "user_takeover": m.get("orca_release_retained_reason") == "user_takeover",
                **{k: v.get(d) for k, v in cols.items()},
            }
        )
    return {"dispatches": sorted(rows, key=lambda x: x["dispatch"])}


def summarize_orca(rows: list[dict]) -> dict:
    def agg(rs):
        n = len(rs)
        done = sorted(x["time_to_done_seconds"] for x in rs if x["time_to_done_seconds"] is not None)
        return {
            "dispatches": n,
            "followups": sum(x["followups"] or 0 for x in rs),
            "followups_per_dispatch": ratio(sum(x["followups"] or 0 for x in rs), n),
            "time_to_done_median_min": done[len(done) // 2] / 60 if done else None,
            "worker_done_rejected": sum(x["worker_done_rejected"] or 0 for x in rs),
            "user_takeover": sum(1 for x in rs if x["user_takeover"]),
            "escalations": sum(x["escalations"] or 0 for x in rs),
            "questions": sum(x["questions"] or 0 for x in rs),
        }

    out = {}
    for p in ("current", "previous"):
        rs = [x for x in rows if x["period"] == p]
        out[p] = agg(rs)
        out[p]["by_model"] = {m: agg([x for x in rs if x["model"] == m]) for m in sorted({x["model"] for x in rs})}
    return out


def installed_skills() -> list[str]:
    names = set()
    for d in SKILL_DIRS:
        if d.is_dir():
            names |= {p.parent.name for p in d.glob("**/SKILL.md")}
    return sorted(names)


def trend(g: Grafana, t: int) -> list[dict]:
    """t で終わる日別（24 時間ずつ）の推移、7 点。"""
    start, step = t - 6 * 86400, 86400
    ev = lambda name, extra="": f'{CC} | event_name="{name}"{extra}'  # noqa: E731
    qs = {
        "requests": f"sum(count_over_time({ev('user_prompt')} [1d]))",
        "cost_usd": f"sum(sum_over_time({ev('api_request')} | unwrap cost_usd [1d]))",
        "cache_read": f"sum(sum_over_time({ev('api_request')} | unwrap cache_read_tokens [1d]))",
        "input": f"sum(sum_over_time({ev('api_request')} | unwrap input_tokens [1d]))",
        "cache_creation": f"sum(sum_over_time({ev('api_request')} | unwrap cache_creation_tokens [1d]))",
        "tools": f"sum(count_over_time({ev('tool_result')} [1d]))",
        "tool_failures": f"sum(count_over_time({ev('tool_result', FAILED)} [1d]))",
    }
    # step=1d の query_range は Loki が点を落とすので、日ごとに瞬間クエリを打つ
    days = []
    for i in range(7):
        ts = start + i * step
        vals = {k: total(g.loki(q, ts)) or 0.0 for k, q in qs.items()}
        get = vals.get
        denom = get("cache_read") + get("input") + get("cache_creation")
        days.append(
            {
                "end": dt.datetime.fromtimestamp(ts, JST).strftime("%m-%d %H:%M"),
                "requests": get("requests"),
                "cost_usd": get("cost_usd"),
                "cache_read_ratio": ratio(get("cache_read"), denom),
                "tool_failure_rate": ratio(get("tool_failures"), get("tools")),
            }
        )
    return days


# ---- markdown ------------------------------------------------------------


def usd(x):
    return "—" if x is None else f"${x:,.2f}"


def pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def num(x, f="{:,.0f}"):
    return "—" if x is None else f.format(x)


def delta(a, b, kind="num"):
    if a is None or b is None or b == 0:
        return "—"
    if kind == "pct":
        return f"{(a - b) * 100:+.1f}pt"
    return f"{(a - b) / b * 100:+.0f}%"


def render(d: dict) -> str:
    c, p, o = d["current"], d["previous"], d["orca"]
    lines = [
        BEGIN,
        "<!-- この節は docs/collect_telemetry.py が書く。手で直さない -->",
        "",
        f"- 期間: 今回 {d['window']['current']}、前回 {d['window']['previous']}（JST）",
        f"- 依頼数: 今回 {num(c['requests'])}、前回 {num(p['requests'])}"
        + ("（今回は 10 件未満。比べる数字は判断保留）" if c["requests"] < MIN_REQUESTS else ""),
        f"- データの始まり: {d['data_since'] or '—'}。これより前はテレメトリが無い",
        "",
        "### コスト",
        "",
        "| モデル | 今回 | 前回 | 差 |",
        "|---|--:|--:|--:|",
    ]
    models = sorted(set(c["cost_by_model"]) | set(p["cost_by_model"]))
    for m in models:
        a, b = c["cost_by_model"].get(m), p["cost_by_model"].get(m)
        lines.append(f"| {m} | {usd(a)} | {usd(b)} | {delta(a, b)} |")
    lines.append(f"| **合計（Loki）** | **{usd(c['cost_total_loki'])}** | **{usd(p['cost_total_loki'])}** | {delta(c['cost_total_loki'], p['cost_total_loki'])} |")
    fa, fb = d["fable"]["current"], d["fable"]["previous"]
    for m in sorted(set(fa) | set(fb)):
        lines.append(f"| {m}（advisor、Prometheus） | {usd(fa.get(m))} | {usd(fb.get(m))} | {delta(fa.get(m), fb.get(m))} |")
    lines += [
        f"| 1 依頼あたり（Loki） | {usd(c['cost_per_request'])} | {usd(p['cost_per_request'])} | {delta(c['cost_per_request'], p['cost_per_request'])} |",
        "",
        "### キャッシュ読み出し割合",
        "",
        f"全体: 今回 {pct(c['cache_read_ratio'])}、前回 {pct(p['cache_read_ratio'])}（{delta(c['cache_read_ratio'], p['cache_read_ratio'], 'pct')}）。目安は 8 割。",
        "",
        "| ワーカー | 今回 | 入力トークン（今回） | 前回 |",
        "|---|--:|--:|--:|",
    ]
    ws = sorted(c["cache_read_ratio_by_worker"].items(), key=lambda kv: -kv[1]["input_tokens_total"])[:10]
    for w, v in ws:
        prev = p["cache_read_ratio_by_worker"].get(w, {}).get("ratio")
        lines.append(f"| {w} | {pct(v['ratio'])} | {num(v['input_tokens_total'])} | {pct(prev)} |")
    lines += [
        "",
        "入力トークンの多い順に 10 件。",
        "",
        "### ツールの失敗",
        "",
        f"失敗率: 今回 {pct(c['tool_failure_rate'])}（{num(c['tool_failures'])} / {num(c['tool_results'])}）、"
        f"前回 {pct(p['tool_failure_rate'])}（{num(p['tool_failures'])} / {num(p['tool_results'])}）",
        "",
        "| 失敗したコマンド（先頭 2 語、エラー種別） | 今回 | 前回 |",
        "|---|--:|--:|",
    ]
    for k, v in sorted(c["failed_commands"].items(), key=lambda kv: -kv[1])[:10]:
        lines.append(f"| `{k}` | {num(v)} | {num(p['failed_commands'].get(k, 0))} |")
    lines += ["", "ツール別: " + ("、".join(f"{k} {num(v)}" for k, v in sorted(c["tool_failures_by_tool"].items(), key=lambda kv: -kv[1])) or "なし"), ""]
    unused = [s for s in d["installed_skills"] if s not in d["skills_activated_7d"]]
    lines += [
        "### skill と MCP",
        "",
        "起動した skill: " + ("、".join(f"{k} {num(v)}" for k, v in sorted(c["skills_activated"].items(), key=lambda kv: -kv[1])) or "なし"),
        "",
        f"入れているが直近 7 日に一度も起動しなかった skill: {len(unused)} / {len(d['installed_skills'])}"
        + "（名前は " + f"`docs/src/data/telemetry/{d['name']}.json` の `installed_skills`）",
        "",
        "| MCP サーバー | 接続した回数 | 呼び出し（今回） | 呼び出し（前回） |",
        "|---|--:|--:|--:|",
    ]
    for s in sorted(set(c["mcp_connected"]) | set(c["mcp_calls"])):
        lines.append(f"| {s} | {num(c['mcp_connected'].get(s, 0))} | {num(c['mcp_calls'].get(s, 0))} | {num(p['mcp_calls'].get(s, 0))} |")
    oc, op = o["current"], o["previous"]
    lines += [
        "",
        "### Orca の手戻り",
        "",
        "期間は Dispatch の開始時刻で振り分ける。",
        "",
        "| 数字 | 今回 | 前回 |",
        "|---|--:|--:|",
        f"| ワーカー（Dispatch）数 | {num(oc['dispatches'])} | {num(op['dispatches'])} |",
        f"| 1 ワーカーあたりの追加指示 | {num(oc['followups_per_dispatch'], '{:.2f}')} | {num(op['followups_per_dispatch'], '{:.2f}')} |",
        f"| worker_done までの時間（中央値、分） | {num(oc['time_to_done_median_min'], '{:.0f}')} | {num(op['time_to_done_median_min'], '{:.0f}')} |",
        f"| 拒否された worker_done | {num(oc['worker_done_rejected'])} | {num(op['worker_done_rejected'])} |",
        f"| user_takeover | {num(oc['user_takeover'])} | {num(op['user_takeover'])} |",
        f"| escalation | {num(oc['escalations'])} | {num(op['escalations'])} |",
        f"| question | {num(oc['questions'])} | {num(op['questions'])} |",
        "",
        "#### モデル別（Orca が起動したモデル）",
        "",
        "| モデル | ワーカー数 | 1 ワーカーあたりの追加指示 | worker_done までの中央値（分） | Claude Code 側のコスト（今回） |",
        "|---|--:|--:|--:|--:|",
    ]
    for m, v in oc["by_model"].items():
        lines.append(
            f"| {m or '(不明)'} | {num(v['dispatches'])} | {num(v['followups_per_dispatch'], '{:.2f}')} | "
            f"{num(v['time_to_done_median_min'], '{:.0f}')} | {usd(c['cost_by_model'].get(m))} |"
        )
    q = d["prom_quality"]
    lines += [
        "",
        "### 直近 7 日の推移（24 時間ずつ）",
        "",
        "| 終わり | 依頼 | コスト | キャッシュ読み出し | ツール失敗率 |",
        "|---|--:|--:|--:|--:|",
    ]
    for day in d["trend"]:
        lines.append(f"| {day['end']} | {num(day['requests'])} | {usd(day['cost_usd'])} | {pct(day['cache_read_ratio'])} | {pct(day['tool_failure_rate'])} |")
    lines += [
        "",
        "### データの質",
        "",
        "Prometheus の `increase(claude_code_cost_usage_USD_total)` は系列のリセットで膨らむので、"
        "コストは Loki の `api_request` の `cost_usd` を正にしている（advisor の行だけ Prometheus）。",
        "",
        "| モデル | Prometheus の increase（今回） | 系列のリセット回数 | Loki の合計（今回） |",
        "|---|--:|--:|--:|",
    ]
    for m in sorted(q["increase_by_model"]):
        lines.append(f"| {m} | {usd(q['increase_by_model'][m])} | {num(q['resets_by_model'].get(m))} | {usd(c['cost_by_model'].get(m))} |")
    lines += ["", END]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="1d", help="1 期間の長さ。1d か 7d")
    ap.add_argument("--out-dir", default="docs/src/telemetry-daily")
    ap.add_argument("--end", help="期間の終わり（ISO 8601）。既定は現在時刻を時の単位に切り捨てたもの")
    a = ap.parse_args()

    span = {"1d": 86400, "7d": 7 * 86400}[a.period]
    now = dt.datetime.fromisoformat(a.end) if a.end else dt.datetime.now(JST)
    end = int(now.timestamp()) // 3600 * 3600
    end_jst = dt.datetime.fromtimestamp(end, JST)
    name = end_jst.strftime("%Y-%m-%d") if a.period == "1d" else end_jst.strftime("%G-W%V")
    fmt = lambda t: dt.datetime.fromtimestamp(t, JST).strftime("%Y-%m-%d %H:%M")  # noqa: E731

    try:
        g = Grafana()
        cur, prev = window(g, end, a.period), window(g, end - span, a.period)
        fable = {
            k: {m: v for m, v in by(g.prom(f"sum by (model) (increase(claude_code_cost_usage_USD_total{{model=~\"claude-fable.*\"}}[{a.period}]))", t), "model").items()}
            for k, t in (("current", end), ("previous", end - span))
        }
        since = g.prom('min(min_over_time(timestamp(claude_code_cost_usage_USD_total)[14d:1h]))', end)
        data = {
            "name": name,
            "period": a.period,
            "window": {"current": f"{fmt(end - span)} 〜 {fmt(end)}", "previous": f"{fmt(end - 2 * span)} 〜 {fmt(end - span)}"},
            "data_since": fmt(int(float(since[0]["value"][1]))) if since else None,
            "current": cur,
            "previous": prev,
            "fable": fable,
            "prom_quality": prom_quality(g, end, a.period),
            "orca": summarize_orca(orca(g, end, span)["dispatches"]),
            "installed_skills": installed_skills(),
            "skills_activated_7d": by(g.loki(f'sum by (skill_name) (count_over_time({CC} | event_name="skill_activated" [7d]))', end), "skill_name"),
            "trend": trend(g, end),
        }
    except (OSError, urllib.error.URLError, RuntimeError) as e:
        print(f"Grafana から取れなかった: {e}", file=sys.stderr)
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    jpath = DATA_DIR / f"{name}.json"
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not jpath.exists() or jpath.read_text() != text:
        jpath.write_text(text)

    out = REPO / a.out_dir / f"{name}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    block = render(data)
    if out.exists():
        old = out.read_text()
        new = re.sub(re.escape(BEGIN) + ".*?" + re.escape(END), lambda _: block, old, flags=re.S) if BEGIN in old else old + "\n" + block + "\n"
    else:
        title = "日報" if a.period == "1d" else "週報"
        new = f"# テレメトリの{title} {name}\n\n## 提案\n\n（手順書に従って書く）\n\n## 数字\n\n{block}\n"
    if not out.exists() or out.read_text() != new:
        out.write_text(new)
    print(f"{out.relative_to(REPO)}\n{jpath.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
