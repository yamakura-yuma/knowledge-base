# ハーネスの組み合わせ表 — 土台 × ペルソナ × モデル × ツール

> アイデア（未検証）。スキルを全部積むのをやめ、役割ごとに組んだハーネスを起動時に差し込み、評価で比べる構想。

<div class="note"><strong>アイデア（未検証）。</strong>
このページは構想で、試していない部分を含む。主張ごとに [確認済み] / [未確認] を付けた。
確認済みは末尾の出典で裏を取ったもの、未確認は試すまで分からないもの。</div>

## たとえ話 — 道具箱を役割ごとに詰め替える

大工さんが、持っている道具を全部腰にぶら下げて現場に出ると、重いうえに、どれを使うか毎回迷う。
だから普通は、今日の仕事（解体・下地・仕上げ）に合わせて道具箱を詰め替えて持っていく。
道具箱の中身は現場に置きっぱなしにせず、帰るときに持ち帰る。現場は施主の家だからだ。

エージェントのスキルも同じで、**役割（ペルソナ）ごとに詰めた道具箱（ハーネス）を、起動するときだけ手渡す**。
道具箱は作業場（worktree）の外に置く。作業場に置くと、施主に渡す荷物（push）に混ざる。

<pre><code>  worktree の外（ハーネスの置き場。push されない）                 worktree（対象リポジトリ。push される）
 ┌──────────────────────────────────────────────────┐           ┌─────────────────────────────────┐
 │ harnesses/yystack-dev-opus55/apm.yml  ← 1 ハーネス │           │ .claude/skills/   ← tracked のもの │
 │   土台 stack + ペルソナ + モデル差分 を依存に並べる │           │ apm.yml / apm.lock.yaml          │
 │   apm.lock.yaml で版を固定                       │           │ ソースコード                     │
 │        │ apm install --root DIR                  │           └─────────────────────────────────┘
 │        ▼                                         │                        ▲
 │   展開先 DIR  ──(apm pack --format agent-plugin)──┼─→ plugin ─┐            │ ここに置くと
 └──────────────────────────────────────────────────┘           │            │ ✗ tracked を上書きし push に混ざる
                                                                ▼            │ ✗ .git/info/exclude は効かない
  起動時に差す:  claude --plugin-dir &lt;plugin&gt; --model &lt;model&gt;   ─→ セッションが worktree で動く
                 copilot --plugin-dir …   (✗ skills がモデルに見えない報告あり)
                 CODEX_HOME=… codex -c skills.config=[…]

  評価:  claude plugin eval  ── ハーネス A の結果 JSON ┐
                             ── ハーネス B の結果 JSON ┴→ 並べて比べる     ツール横断は Harbor</code></pre>

図の ✗ は、この構想で避けたい問題か、既知の不具合。どちらも下の節で出典つきで扱う。

---

## 問題 — スキルは増やすほど一覧が重くなる

Claude Code では、スキルの本文は呼ばれたときだけ読まれるが、**一覧（name と description）は毎回の文脈に常駐する**。
[確認済み] 公式 docs の表では、既定のスキルは "Description always in context, full skill loads when invoked"。
1 スキルあたり description と `when_to_use` を合わせて 1,536 文字で切られる。[確認済み]

したがって、スキルを足すほど常駐分が増える。加えて、似た description が並ぶと
**どれを呼ぶかの選択がぶれる**と見ている。[未確認] 手元で測ったことはない。評価の節の仕組みで測るつもり。

## 構想 — 4 つの軸の組み合わせで 1 ハーネス

ハーネスを次の 4 軸の組み合わせとして作る。[未確認] 構想そのもの。

| 軸 | 例 | 役割 |
|---|---|---|
| 土台 stack | 他者の stack ベース / 自作の yystack ベース | ルール・フック・共通スキル |
| ペルソナ | coordinator / po / dev / qa | その役割で使うスキルだけ |
| モデル向け差分層 | Opus 5.5 用 | モデルの癖に合わせた言い回しや既定値 |
| ツール | Claude Code / Codex / Copilot CLI | 差し込み方がツールごとに違う（次節） |

**1 ハーネス = apm.yml 1 つ**で、4 軸の部品を依存として並べ、`apm.lock.yaml` で版を固定する。
全組み合わせを作るのではなく、**使う組み合わせだけ作る**。4 × 4 × n × 3 を全部揃える必要はない。

## 置き場所の要件 — worktree の外に置き、起動時に差す

ペルソナのファイルを対象リポジトリの worktree に展開すると、push に混ざる。

- 対象リポジトリが自分でハーネスを持っていると、`.claude/skills` や `apm.yml` / `apm.lock.yaml` が tracked になっている。
  そこへ別のペルソナを展開すると tracked ファイルを上書きし、差分として push に乗る。
  [確認済み] このリポジトリ自身も `apm.yml` と `apm.lock.yaml` を tracked にしている（`git ls-files`）。
- `.git/info/exclude` で隠す手は使えない。exclude は全 worktree で 1 つを共有しており
  （`git rev-parse --git-path info/exclude` が共通の `.git/` を指す）、しかも既に tracked のファイルには効かない。[確認済み]

よって要件は、**ハーネスは worktree の外に置き、起動するときに差し込む**こと。

## 起動時に差す手段

ツールごとに、セッションだけに効く差し込み口がある。

### Claude Code

| 手段 | 何ができるか | 印 |
|---|---|---|
| `claude --plugin-dir <dir>` | ディレクトリか `.zip` の plugin を**そのセッションだけ**読む。繰り返し指定できる | [確認済み] |
| `--model` | セッションのモデルを指定。`model` 設定と `ANTHROPIC_MODEL` より優先 | [確認済み] |
| `skillOverrides`（設定） | スキルごとに `on` / `name-only` / `user-invocable-only` / `off`。SKILL.md を書き換えずに一覧から外せる | [確認済み] |
| `disable-model-invocation: true`（frontmatter） | description が文脈から消え、`/name` でしか呼べなくなる | [確認済み] |
| サブエージェントの `skills:` | **preload するだけで、絞れない**。書いていないスキルも Skill ツールで呼べる。絞るなら Skill ツールごと外すしかない | [確認済み] |

最後の行が効いてくる。サブエージェント単位でペルソナを切るという道は無く、
**ペルソナはセッション単位（= 起動単位）で切る**ことになる。

### Copilot CLI

| 手段 | 何ができるか | 印 |
|---|---|---|
| `--plugin-dir=DIRECTORY` | ローカルの plugin を読む。複数回指定できる | [確認済み] |
| 同上の不具合 | `--plugin-dir` の skills が起動時には見つかるのに、対話セッションのモデルからは使えない（#4883、1.0.86-0、2026-09-16 に close）。`/skills` と `/env` に出ない（#4886、1.0.86-1、open） | [確認済み] |
| `COPILOT_HOME` | 設定ディレクトリ（既定 `~/.copilot`）を差し替える。`--config-dir` は legacy 扱い | [確認済み] |

#4883 が close された版で直っているかは試していない。[未確認]

### Codex CLI

| 手段 | 何ができるか | 印 |
|---|---|---|
| `CODEX_HOME` | ローカル状態の置き場（既定 `~/.codex`）を差し替える | [確認済み] |
| `-c skills.config=[…]` | 1 回の実行だけ任意の設定キーを上書き。skills.config をこれで渡すと効く、と #20210 の報告者が確かめている | [確認済み] |
| project 層の `.codex/config.toml` | `[[skills.config]]` を書いても**無視される**（#20210。enhancement として自動 close） | [確認済み] |
| サブエージェント単位 | agent TOML の `[[skills.config]]` は有効化・無効化どちらも効かない（#14161） | [確認済み] |

Codex もサブエージェント単位では絞れないので、Claude Code と同じくセッション単位で切る。

### apm（0.31）

| 手段 | 何ができるか | 印 |
|---|---|---|
| `apm pack --format agent-plugin` | apm パッケージから Portable Agent Plugins v1 の bundle を出す | [確認済み] 手元の 0.31.0 の `--help` |
| `apm install --root DIR` | `$PWD` の代わりに DIR へ展開する（`apm_modules/`、`apm.lock.yaml`、`.claude/` 等） | [確認済み] 同上 |

この 2 つを繋ぐと「worktree の外で組んで、plugin として差す」の形になる。
**ただし `apm pack` の出力をそのまま `--plugin-dir` に渡せるかは試していない。**[未確認]
なお apm は 2026-09-25 に 0.32.0 が出ている。

## 評価 — ハーネスどうしを数字で比べる

| 何を比べるか | 手段 | 印 |
|---|---|---|
| ハーネスあり / なし | `claude plugin eval`。各ケースを plugin あり・なしの 2 アームで既定 3 回ずつ流し、差（Δ）を出す。v2.1.269 以降 | [確認済み] |
| ハーネス A / B | eval は「あり / なし」しか比べないので、A と B をそれぞれ流し、結果の `aggregate-result.json` を並べる | [未確認] |
| モデル | eval に `--model` があり、試す側のモデルを 1 回の実行ごとに固定できる。複数モデルを 1 回で回す仕組みは docs に無い | [確認済み] / 一括は [未確認] |
| ツール横断 | Harbor（エージェントの評価と改善の枠組み）でツールをまたいで同じ課題を流す | [未確認] |

課題集は、過去に Orca のワーカーへ出した依頼文から作る。実際に使った仕事なので、
ペルソナが役に立つかをそのまま測れるはず。[未確認]
スキルの効き方を測る公開ベンチとしては SkillsBench がある。[確認済み] 存在のみ。

## 並列開発 — 系統ごとにワーカー 1 人

ハーネスの系統（例: 他者 stack ベース、yystack ベース）ごとに Orca の worktree ワーカーを 1 人立てて並行に作る。
系統が互いのファイルに触れないので、衝突しない。[未確認]

## 既存 OSS との関係

| 名前 | 何を借りるか | 注意点 | 印 |
|---|---|---|---|
| BMAD-METHOD | ペルソナの中身（product・architecture・UX・development・testing の視点）。比較のベースライン候補 | セットアップが対象プロジェクトに `_bmad/` を作り、共有設定とスクリプトを置く前提。worktree の外に置く要件と衝突する | [確認済み] |
| skills-manager（xingkongliang） | 「プリセット = スキルの名前付きグループ」の考え方だけ。プリセットがペルソナにあたる | プリセットの適用は一回きりのコピーで、同期しない。版の固定が無く再現性が弱い | [確認済み] |
| Agent-Profiles | 構想段階とされるもの | 指している対象を特定できていない。同名のリポジトリ・issue が複数ある | [未確認] |
| microsoft/apm#2341 | apm.yml の中に名前付きの依存プロファイルを持つ提案。入れば「1 ハーネス = apm.yml 1 つ」を 1 ファイルにまとめられる | open だが `status/needs-design` と `status/deferred` が付いており、当面は入らない | [確認済み] |

## 未確認のことと、次の一歩

試せば確かめられる問いを並べる。

1. `apm pack --format agent-plugin` の出力を `claude --plugin-dir` がそのまま読めるか。[未確認]
2. Orca のワーカー起動に、`--plugin-dir` や `--model` のような追加の起動引数を渡せるか。[未確認]
3. `claude plugin eval` で、ハーネスとモデルの組み合わせを一括で切り替えて回せるか。`--model` で 1 回ずつ切り替えられることは確認済みで、まとめて回す手段が無いかが未確認。[未確認]

**最初の一歩は、yystack を層（土台 / ペルソナ / モデル差分）に分け、2 版を起動時に切り替えられるところまで。**
評価や他ツールへの展開はその後に回す。

## 出典

- Claude Code — Skills: <https://code.claude.com/docs/en/skills>
- Claude Code — Sub-agents（`skills:` の preload）: <https://code.claude.com/docs/en/sub-agents>
- Claude Code — CLI reference（`--plugin-dir`、`--model`）: <https://code.claude.com/docs/en/cli-reference>
- Claude Code — Plugin evals（`claude plugin eval`）: <https://code.claude.com/docs/en/plugin-evals>
- Copilot CLI — config directory（`COPILOT_HOME`）: <https://github.com/github/docs/blob/main/content/copilot/reference/copilot-cli-reference/cli-config-dir-reference.md>
- Copilot CLI — command reference（`--plugin-dir`）: <https://github.com/github/docs/blob/main/content/copilot/reference/copilot-cli-reference/cli-command-reference.md>
- github/copilot-cli#4883: <https://github.com/github/copilot-cli/issues/4883>
- github/copilot-cli#4886: <https://github.com/github/copilot-cli/issues/4886>
- Codex — Advanced config（`CODEX_HOME`、`-c`）: <https://learn.chatgpt.com/docs/config-file/config-advanced>
- Codex — Skills（`[[skills.config]]`）: <https://learn.chatgpt.com/docs/build-skills>
- openai/codex#20210: <https://github.com/openai/codex/issues/20210>
- openai/codex#14161: <https://github.com/openai/codex/issues/14161>
- apm: <https://github.com/microsoft/apm>（`apm pack` / `apm install --root` は手元の 0.31.0 の `--help` で確認）
- microsoft/apm#2341: <https://github.com/microsoft/apm/issues/2341>
- BMAD-METHOD: <https://github.com/bmad-code-org/BMAD-METHOD>（`_bmad/` は docs/start/install-bmad.md）
- skills-manager: <https://github.com/xingkongliang/skills-manager>
- Harbor: <https://github.com/harbor-framework/harbor>
- SkillsBench: <https://github.com/benchflow-ai/skillsbench>

確認日はすべて 2026-09-26。
