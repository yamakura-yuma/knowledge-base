# テレメトリ日報の作成手順

このファイルは、Claude Code と Orca のテレメトリから日報を作る手順書。
Orca の automation（毎日 9:00 JST）のプロンプトはこれを読んで従えと言うだけで、中身はすべてここに書く。
人が読んでもエージェントが読んでも同じ動作になるように書いてある。

作業ディレクトリはリポジトリのルート（`README.md` がある階層）。

## 設定（期間と置き場所はここだけで変える）

| 項目 | 値 | 週報に切り替えるとき |
|---|---|---|
| 期間 `PERIOD` | `1d` | `7d` |
| 置き場所 `OUT_DIR` | `docs/src/telemetry-daily` | `docs/src/telemetry-weekly`（この手順書もそこへ移す） |
| ファイル名 | `<YYYY-MM-DD>.md` | `<YYYY>-W<WW>.md`（スクリプトが決める） |
| ブランチの接頭辞 `BRANCH` | `telemetry-daily-` | `telemetry-weekly-` |
| Issue にするまでの回数 `REPEAT` | 3 回続けて出た候補 | 2 回続けて出た候補 |

週報に切り替えるときは、上の表の右の列に書き換え、automation の `--trigger` を `weekly --day 1 --time 09:00` に変える。
以下の本文は `PERIOD` などの名前で書いてあるので、書き換えなくてよい。

---

## 目的

テレメトリを見て、ハーネス（rule・skill・指示の書き方・モデル選択）の**どこを直すと効きそうかを提案する**。
**提案だけ**にとどめ、ハーネスは変えない。変えるかどうかは人が決める。
「1 か所だけ変えて前後を比べる」（home-k8s の `docs/observability/playbook.md` の場面 8）を崩さないため。

## 成功条件

1. `OUT_DIR/<名前>.md` に数字の節（スクリプトが書く）と提案の節（あなたが書く）がそろっている
2. 提案は最大 3 つ。どれにも根拠の数字とクエリが付いているか、「判断保留」「前日と同じ」と書いてある
3. 日報が PR に載っている（開いている日報の PR があればそこに追記している）
4. Issue のルール（後述）に当たった候補だけが Issue になっている
5. 秘密の値、依頼文の本文、コマンドの全文、利用者の ID が、日報・PR・Issue のどこにも無い

---

## やること

### 1. 日報のブランチに移る

この automation は実行のたびに新しい worktree で動く。日報の PR が毎日増えないよう、
開いている日報の PR があればそのブランチに追記する。

```bash
git fetch origin
gh pr list --state open --json number,headRefName --jq '.[] | select(.headRefName | startswith("telemetry-daily-"))'
```

- **開いている PR がある**: `git checkout -B <headRefName> origin/<headRefName>`
- **無い**: `git checkout -b telemetry-daily-<今日の YYYY-MM-DD>`（いまの HEAD から切る。HEAD は automation のベースブランチで、ふだんは main）

数字はブランチを移ってから取る（同じ日の日報が PR にあると、先に取ったファイルと checkout がぶつかるため）。

main に直接 push はしない。このリポジトリの運用（core-principal の `guard-default-branch`）で、
デフォルトブランチには commit も push もしない決まりになっている。

### 2. 数字を取る

```bash
uv run docs/collect_telemetry.py --period 1d --out-dir docs/src/telemetry-daily
```

`--period` と `--out-dir` は上の設定表の値を使う。スクリプトは次の 2 つを書く。

- `OUT_DIR/<名前>.md` の `<!-- numbers:begin -->` から `<!-- numbers:end -->` まで（ファイルが無ければ雛形ごと作る）
- `docs/src/data/telemetry/<名前>.json`（集計した実測値。手で編集しない）

**「Grafana から取れなかった」で終わったら、日報を作らずに止める。**
観測スタック（home-k8s の kind クラスタ）が止まっている可能性が高い。推測で数字を埋めない。
automation の実行結果に「Grafana に届かなかった」と書いて終える。

Grafana の場所と資格情報、各数字の出し方はスクリプトの冒頭に書いてある。
**パスワードの値はどこにも書き写さない。**

### 3. 前の日報を読む

`OUT_DIR` にある直前の日報（ファイル名で 1 つ前）と、その前の日報を読む。
いまのブランチには、開いている PR の分と main に入った分の両方がある。
提案の節と、各提案の `候補キー` を控える。

### 4. 提案を書く

`OUT_DIR/<名前>.md` の `## 提案` の中身を書き換える。数字の節には触らない。

**まず判断保留かどうかを決める。** 次のどれかに当てはまる数字は、それを根拠に提案しない。

- 今回の依頼が 10 件未満（数字の節に「判断保留」と出る）。home-k8s の playbook の場面 8 と同じ基準
- 比べる前回の値が「—」（前回のデータが無い）。その数字は変化としては書かず、「目立つ値」としてだけ扱う
- ワーカー（Dispatch）が 10 未満のときの、Orca のモデル別の比較

1 日分はデータが少ない。迷ったら判断保留にする。**提案が 0 でもよい。**

**提案は最大 3 つ。** 1 つずつ次の形で書く。

```markdown
### <番号>. <悪化した・目立つ数字を一言で>

- 候補キー: `<英小文字とハイフンの短い名前。例: cache-ratio-low-home-k8s>`
- 数字: <今回と前回の値。数字の節から写す>
- クエリ: `<その数字を出した LogQL / PromQL。スクリプトの該当箇所から写す>`
- 疑うところ: <ハーネスのどこか。rule / skill / CLAUDE.md / spec の雛形 / モデル選択 / 観測の仕組み>
- 直す候補: <1 か所だけ。どのリポジトリのどのファイルを、どう変えるか>
- 連続: <この候補キーが何日続けて出たか（今日を含む）>
```

「疑うところ」と「直す候補」は home-k8s の `docs/observability/playbook.md` の場面（3〜6、11）と
`claude-code-improve.md` の「パネルの使い方」の表に沿って選ぶ。当てはまらないときは、表に無いと書いてから推す。

**同じ提案を毎日くり返さない。** 前の日報と同じ候補キーで、数字の向きも変わらないなら、
その提案は次の 1 行で済ませる。連続の日数だけ数え続ける。

```markdown
- `<候補キー>`: 前日と同じ（<数字を 1 つ>、連続 <N> 日）
```

**書き写さないもの。** 依頼文の本文（件数か、依頼の種類の要約だけにする）、コマンドの全文（数字の節と同じく
プログラム名とサブコマンドまで）、パスワードやトークン、`user_email` などの利用者の ID。
このリポジトリは公開されている。

### 5. Issue のルール

直す候補を Issue にするのは、同じ候補キーが `REPEAT` 回（日報なら 3 日）続けて出たときだけ。1 日だけの候補は日報に書くにとどめる。

- 起こす先: 直す候補が指すリポジトリ（`yamakura-yuma/dotfiles`・`yamakura-yuma/home-k8s`・`yamakura-yuma/coordinator`）
- 題: `[telemetry] <候補キー>: <一言>`
- 本文: 日報への リンク、根拠の数字とクエリ、直す候補（1 か所）。「提案であって、変えるかどうかは人が決める」と書き添える
- 先に重複を探す: `gh issue list -R <repo> --state open --search "[telemetry] <候補キー> in:title"`
  - 開いている Issue があれば、新しく起こさない。最後のコメントから 7 日以上経っていて数字が動いていれば、
    コメントで今日の数字を追記する。それ以外は何もしない
  - 閉じた Issue しか無ければ、新しく起こし、閉じた Issue に言及する

起こした・追記した Issue は、提案の `候補キー` の行の後ろに URL を足す。

### 6. PR に載せる

```bash
git add docs/src/telemetry-daily docs/src/data/telemetry
git commit -m "Add the telemetry daily report for <名前>"
git push -u origin HEAD
```

- 新しいブランチなら `gh pr create --base main --title "Telemetry daily reports from <最初の日付>" --body <後述>` で PR を出す
- 開いている PR に追記したなら、PR の本文の一覧に今日の行を足す（`gh pr edit <番号> --body ...`）

PR の本文は、日報ごとに 1 行ずつ（日付・依頼数・コスト・提案の数・起こした Issue）並べる。
マージするかどうかは人が決める。

---

## 出力フォーマット（automation の実行結果として出す）

```
## テレメトリ日報 <名前>

- 日報: <PR の URL>（新規 / 追記）
- 提案: <N> 件（うち前日と同じ <M> 件、判断保留 <K> 件）
- Issue: <起こした・追記した URL。無ければ「なし」>
- 人の判断が要るもの: <あれば>
```

---

## 知っておくこと

- テレメトリは 2026-09-30 10:00 JST ごろから入っている。それより前は空で、前回の値が「—」になる
- 観測スタックの保持期間は 14 日（Prometheus・Loki・Tempo とも）。それより前とは比べられない
- Prometheus の `claude_code_*_total` は、セッション ID をラベルから外しているため系列のリセットが多く、
  `increase()` が実際の数十倍になることがある（初回の 2026-10-01 の実測で、Opus は Loki の $460 に対し Prometheus は $21,820）。
  コストとキャッシュは Loki を正とし、Prometheus の値は数字の節の「データの質」に比べるためにだけ出している。
  home-k8s のダッシュボードの `increase(... anchored)` のパネルも同じ影響を受ける
- advisor（Fable）の呼び出しは Loki に `api_request` が出ないので、その行だけ Prometheus から取っている。
  リセット回数を「データの質」で確かめてから使う
- Orca の数字は home-k8s の orca-exporter が 30 秒ごとに送るゲージ。Dispatch の開始時刻で期間に振り分ける。
  `(不明)` のモデルは、Orca が起動時のモデルを記録していない古い Dispatch
- この automation はモデルを指定できない（`orca automations create` に `--model` が無い）。Orca の既定のモデルで動く
