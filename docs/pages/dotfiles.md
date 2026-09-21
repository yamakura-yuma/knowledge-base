# dotfiles の構成

> `~/k8s-workspace/dotfiles` が、何を、どこへ、どの順で配っているか。追跡ファイルは 34 個だけで、`.claude/` と `apm_modules/` は生成物として gitignore されている。

## 何をするリポジトリか

**プロジェクトのツールチェーンは持たない。** 置いてあるのは「どのリポジトリで作業しても同じであってほしいもの」だけ、
つまりエージェントの設定、ホスト共通のツール、シェルの見た目の 3 つ。
言語やビルドは各プロジェクトの `flake.nix` や `.devcontainer/` の仕事、という線が引かれている。

<div class="dgm">
<div class="cap">配る先は 3 つのスコープに分かれる</div>
<div class="row3">
  <div class="box k1"><b>ホスト</b><span>Nix で入れる CLI（jq / uv / node / starship）、シェルのプロンプト、statusline。ホストに 1 つ。</span></div>
  <div class="box k2"><b>ホスト全体のエージェント</b><span><code>host-apm.yml</code> → <code>~/.apm/apm.yml</code> → MCP サーバだけを <code>~/.claude.json</code> へ。</span></div>
  <div class="box k3"><b>リポジトリごと</b><span><code>core-principal/</code> パッケージ → そのリポジトリの <code>./.claude/</code>。ルール・スキル・hook・コマンド。</span></div>
</div>
</div>

**この 3 分割が設計の芯**にあたる。振る舞いを変えるもの（ルール、スキル、hook）は必ずリポジトリ単位に閉じ、
ホスト全体に置くのは能力を足すだけのもの（MCP サーバ）に限る。
だから無関係なリポジトリで作業しても、ここの設定に引きずられない。

---

## setup.sh — 4 つのサブコマンドと責任範囲

<div class="dgm">
<div class="cap">./setup.sh &lt;subcommand&gt;　引数なしは上から順に全部</div>
<div class="map">
  <div class="h r">サブコマンド</div><div class="h"></div><div class="h">触るもの</div>
  <div class="s">install-nix</div><div class="a">──▶</div><div class="d">Nix 本体。ホストにつき 1 回、sudo が要る</div>
  <div class="s">nix-tools</div><div class="a">──▶</div><div class="d">flake.nix のバンドルを nix profile へ</div>
  <div class="s">reload</div><div class="a">──▶</div><div class="d">シンボリックリンク、~/.bashrc のフック、apm/codegraph/graphifyy/headroom-ai の更新、apm install -g、apm install</div>
  <div class="s">agents-init</div><div class="a">──▶</div><div class="d">headroom 常駐プロキシ、graphify の統合。長時間プロセスを起こすので reload には含めない</div>
</div>
</div>

`reload` は**何度流しても安全**で、リポジトリを別の場所に移した後でも動くように作られている。
`~/.bashrc` にはマーカー付きの 1 ブロックだけを書き、その中身は `~/.config/dotfiles/prompt.sh` という
固定パスを読むだけ。実体はシンボリックリンクなので、リポジトリを移動しても `~/.bashrc` を書き換え直す必要がない。

---

## APM が何をどこへ展開するか

エージェントの設定ファイルを手で書かない、というのがこのリポジトリの方針。
すべて `core-principal/` という APM パッケージの中にあり、`apm install` が所定の場所へ展開する。

<div class="dgm">
<div class="cap">core-principal/.apm/　──▶　&lt;consumer repo&gt;/.claude/</div>
<div class="map">
  <div class="h r">パッケージ側</div><div class="h"></div><div class="h">展開先</div>
  <div class="s">.apm/instructions/*.instructions.md</div><div class="a">──▶</div><div class="d">.claude/rules/</div>
  <div class="s">.apm/skills/&lt;name&gt;/SKILL.md</div><div class="a">──▶</div><div class="d">.claude/skills/&lt;name&gt;/</div>
  <div class="s">.apm/prompts/&lt;name&gt;.prompt.md</div><div class="a">──▶</div><div class="d">.claude/commands/&lt;name&gt;.md　（/&lt;name&gt;）</div>
  <div class="s">.apm/hooks/*.json</div><div class="a">──▶</div><div class="d">.claude/settings.json へマージ</div>
  <div class="s">host-apm.yml の dependencies.mcp</div><div class="a">──▶</div><div class="d">~/.claude.json　（ホスト全体）</div>
</div>
</div>

**このリポジトリ自身が最初の利用者**になっている点が効いている。
`apm.yml` が `./core-principal` に依存していて、他のリポジトリと同じ経路で自分にも展開する。
だから consumer を壊す変更は、ここのハーネスも同時に壊れる。気づかないまま配ることがない。

---

## ガードフック — 2 つだけ、意図的に

<div class="dgm">
<div class="cap">PreToolUse(Bash) の判定。exit 2 で拒否、exit 0 は「意見なし」であって承認ではない</div>
<div class="rail">
  <div class="q"><b>jq / git が PATH にあるか</b></div><div class="v">無ければ <span class="yes">exit 0</span>（判断しない）</div>
</div>
<div class="tie"></div>
<div class="rail">
  <div class="q"><b>MAKURA_ALLOW_MAIN が立っているか</b></div><div class="v">立っていれば <span class="yes">通す</span></div>
</div>
<div class="tie"></div>
<div class="rail">
  <div class="q"><b>HEAD がデフォルトブランチか</b><br><span style="font-size:11.5px;color:var(--ink-3)">かつ git commit / git push か</span></div><div class="v"><span class="no">exit 2</span> で拒否<br>理由を stderr で返す</div>
</div>
</div>

もう 1 つのフックは、どこにも残らない作業を消す 4 つ（`reset --hard`、`clean -f`、ツリー全体の
`checkout --` / `restore`、`push --force`）を止める。**`--force-with-lease` と `reset --soft` は通す。**
戻せる操作と戻せない操作を分けている。

### エスケープハッチが環境変数である理由

<div class="dgm">
<div class="cap">なぜマーカーファイルではなく環境変数なのか</div>
<div class="row2">
  <div class="box bad"><b>エージェントが書いた場合</b><p><code>MAKURA_ALLOW_MAIN=1 git push</code> と Bash ツールで打っても、その変数は<b>ツール呼び出しのプロセスにしか乗らない</b>。フックは Claude Code 本体の環境を継承するので見えない。<b>効かない。</b></p></div>
  <div class="box ok"><b>人間が export した場合</b><p>Claude Code を起動する前に export してあれば、本体の環境に乗っているのでフックから見える。<b>効く。</b></p></div>
</div>
</div>

つまり**エージェントが自分に許可を出せない**構造になっている。
マーカーファイルだとエージェントが書けてしまうので、意図してこの形が選ばれている。

---

## ツールを引く順番を、ルールで決めている

`codegraph` や `graphify` は入れるだけでは半分で、持っていてなお `grep` に手が伸びるなら意味がない。
だから毎プロンプト読まれる `core-principal.instructions.md` が順序を決めている。

<div class="dgm">
<div class="cap">索引が先、生の読み書きは最後</div>
<div class="row3">
  <div class="box k3"><b>① graphify</b><span><code>graphify-out/</code> があれば <code>graphify query</code> で<b>どこを見るか</b>を決める</span></div>
  <div class="box k2"><b>② codegraph</b><span><code>.codegraph/</code> があれば <code>codegraph explore</code> で<b>逐語ソースと呼び出し経路</b>を読む</span></div>
  <div class="box k1"><b>③ Read / Grep</b><span>索引が無い、索引で当たらない、編集する行の現物が要る — <b>この 3 つのときだけ</b></span></div>
</div>
</div>

索引が無いディレクトリでは、許可を待たずに作ってよい、とまで書いてある。
**能力を配るだけでなく、使う順番まで規範にしている**のがこのリポジトリの特徴的なところ。

---

## 依存とその検証

<div class="dgm">
<div class="cap">core-principal/apm.yml が抱える外部依存</div>
<div class="row3">
  <div class="box"><b>9 リポジトリ</b><span>humanlayer / vercel-labs / mattpocock / dietrichgebert / stablyai / interfacex / gonta223 / k16shikano の gist 2 つ</span></div>
  <div class="box"><b>33 個の ref ピン</b><span>すべてコミットハッシュで固定。ブランチ追跡はしない</span></div>
  <div class="box"><b>34 追跡ファイル</b><span><code>.claude/</code> と <code>apm_modules/</code> は生成物として gitignore</span></div>
</div>
</div>

検証は `make ci` の 1 本。**決定的で、ネットワークに出ず、CI と人間が同じコマンドを叩く。**
シェル構文、実行ビット、JSON / YAML の妥当性、instruction の frontmatter、ガードフックの挙動、
ハーネスの不変条件、statusline の 8 項目。

---

## 改善の提案

事実として確認できた範囲から。**上から順に、効果と確からしさが高い。**

### 1. CodeGraph と Serena の役割重複 → 実測して CodeGraph 一本に決めた（対応済み）

指摘した時点の想定は外れていた。**Serena はこのホストに入っていなかった。** PATH にも
`~/.claude.json` にも `.mcp.json` にも `~/.serena` にも無い。Serena を入れるのは
`headroom wrap claude`（`--code-memory` の既定値が `serena`）だが、`setup.sh` が呼ぶのは
`headroom install apply --target claude` と `headroom init --global claude` で、
`wrap` はリポジトリ全体で一度も使われていない。**二重化は起きていなかった。**

残る問題は「決めていない」ことだった。そこで実測した。temporal-saga（Go 3,539 行）に
同じ 5 問を投げ、codegraph だけ・serena だけの 2 条件で比べる。Read / Grep / Bash は
両条件とも禁止して、答えを索引からしか作れないようにし、headroom プロキシは迂回して
生のトークン数を測った。モデルは Sonnet。

| 指標（5 問） | CodeGraph | Serena |
| --- | ---: | ---: |
| 往復回数 中央値 | **3** | 8 |
| 所要時間 中央値 | **12.5 秒** | 19.3 秒 |
| 文脈トークン 中央値 | **74.3k** | 138.6k |
| 最悪ケース | 4 往復 / 20 秒 | **38 往復 / 233 秒 / 114 万トークン** |
| 5 問の合計コスト | **$0.59** | $1.21 |
| 索引のディスク | 6.7 MB（事前グラフ） | 72 KB ＋ gopls 42 MB |
| 回答の正確さ | 同等 | 同等 |

**正確さは互角で、差が出たのは経路の数だった。** Serena は LSP のシンボル検索を反復するので、
「型の実装先をたどる」形の問いに弱い。1 問で 38 往復・文脈 114 万トークンまで膨らんだ例がある。
CodeGraph は事前にグラフを持っている分、同じ問いを 3 往復で閉じた。

> **対応** — CodeGraph 一本に決め、`core-tools/SKILL.md` に「Serena は使わない、
> `headroom wrap` を使うなら `--code-memory none`」と明記した。索引の序列は
> graphify → codegraph → Read/Grep の 2 段のままにする。
> なお Serena は Go に gopls を別途要求する。索引を増やす側のコストはツール本体だけではない。

### 2. 圧縮が 2 層で効いていた → genshijin を外した（対応済み）

`genshijin-compress` が応答そのものを短くし、Headroom がツール出力を圧縮していた。
**別の層だが目的は重なる。** さらに実害の観測があった — サブエージェントの報告やツール結果に
`[N 語を M 語に圧縮]` という Headroom の圧縮マーカーが実際に現れており、
**オーケストレーション時に中間成果物が欠落し得る**状態だった。

> **対応** — 圧縮は Headroom 1 層に寄せると決め、`core-principal/apm.yml` から genshijin 系
> 7 パッケージの宣言を削除した。依存は 33 個から 26 個になった。
> バイナリ・フック・MCP・statusline としては元から入れていなかったので、削除は宣言 1 箇所で済んでいる。

### 3. グローバルに入れる 3 ツールが固定されていなかった → `versions.env`（対応済み）

指摘したときは graphify だけの話だと思っていたが、`setup.sh` を読み直すと
**codegraph も `@latest`、headroom-ai も版指定なし**で、3 つとも `reload` のたびに最新へ上がっていた。
graphifyy は PyPI に 233 リリースあり、最新版は前日に出ている。`reload` は事実上の自動更新だった。

> **対応** — `versions.env` に 3 つの版を書き、`setup.sh reload` がそこだけを読むようにした。
> 上げ方は `./bin/pins.sh latest` で差分を見て、`versions.env` を 1 行書き換え、`reload` して `make ci`。
> **何をいつ上げたかが git log に残る**のが、自動更新との一番の違い。
> `uv tool install <pkg>==<version>` が版の上げ下げ両方に効くことは実測で確認した（`--force` は要らない）。

### 4. `~/.claude/settings.json` を書くものが 2 系統ある → 表にした（対応済み）

`reload` が apm 経由で配るものと、`agents-init` が headroom のルーティングのために書くもの
（`ANTHROPIC_BASE_URL`）が、同じホストスコープの設定に同居している。
**どちらが所有者なのかがファイルからは読めない。**

> **対応** — 実装は変えず、README に「ホストスコープの設定は誰が書くか」の表を足した。
> 対象・書き手・どのサブコマンドで書かれるかの 3 列で、`reload` の列は何度でも収束し、
> `agents-init` の列は外部ツールの流儀に任せる、という線を明記した。

### 5. 上流ピンの更新が手作業で持続しない → `pins.tsv` と `make ci`（対応済み）

`core-principal/apm.yml` のコメント自身が「`apm update` は明示 ref を動かさないので、
上げるには手で書き換える」と書いている。**26 個を手で追うのは現実的でない。**

> **対応** — `bin/pins.sh` を足した。`refresh` が GitHub API で各ピンのコミット日を取り
> `pins.tsv` に書き出し、`check` はそれを読むだけなので**オフラインのまま** `make ci` に入る。
> 90 日を超えたピンは一覧表示するが、**ci は落とさない**（古さは判断であって違反ではない）。
> ref を書き換えて `pins.tsv` を更新し忘れると parity チェックで落ちるので、スナップショットは腐らない。
> 実際に走らせると humanizer-ja が 182 日で 1 件だけ引っかかった。

### 6. ガードフックが 2 つで止まっている点は妥当（提案なし）

README が意図的だと明記しており、理由も `core-principal/README.md` にある。
フックを増やすほど誤検知が増え、エージェントが迂回を学習するリスクがある。
**ここは現状維持が正しいと判断する。**改善提案として挙げない。
