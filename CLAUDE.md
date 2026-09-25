# knowledge-base

調べたことを溜めておく場所。コードではなく文書が主で、markdown を正本にし、読む用の
HTML はそこから生成する。いま入っているのは AI ツールのランドスケープ、ハーネスに
入れる外部ツールの調査、ハーネスのパターン・カタログの3つ。

ハーネス（エージェント設定）そのものの説明はここに書かない。正本は dotfiles リポジトリの
[`docs/`](https://github.com/yamakura-yuma/dotfiles/tree/main/docs)（手元では
`~/dotfiles/docs/`）。線引きは、ハーネスを変えたときに一緒に変わるものは dotfiles、
変わらないものはここ。

実測値で裏を取れたものだけを書く、というのがこのリポジトリの縛り。星の数や直近リリース
のような数字は GitHub API から取り、取れなかったものは空欄のままにする。推測で埋めない。

## 構成技術

- Python 3.11 以上。依存はスクリプト先頭の PEP 723 ブロックに書いてあり、`uv run` が
  その場で解決する。ホストに何も入れなくてよい
- 正本は markdown と YAML、出力は自己完結の HTML（外部 CDN・Web フォント・JS を使わない）

## レイアウト

`docs/` は2軸に分かれている。**正本 `src/` と生成物 `site/`**、そして**話題ごとの
ディレクトリ**。生成物は正本の話題に従う。

- `docs/src/landscape/` — 話題① AI コーディングツールのランドスケープ。
  `registry.yaml` が全項目の正本、`tools/<slug>.md` が詳細ティアの本文、
  `index.md` が分類軸と母集団の決め方、`UPDATE_PROMPT.md` が更新手順の正本
- `docs/src/tool-research/` — 話題② ハーネスに入れる外部ツールの調査。
  `context-optimization.md`（Headroom / CodeGraph / graphify を対抗馬と比較）
- `docs/src/patterns/` — 話題③ ハーネスのパターン・カタログ。`catalog.yaml` が正本
  （行はパターン、4 層 × 自作ハーネスでの状態）。HTML は `docs/patterns_page.py` が描き、
  既存の話題の `PAGES`・ナビには入れていない（既存ページに差分を出さないため）。
  `harness-form.md` はハーネスの形式についての見立て（意見）で、`harness-form.html` に出し、
  要約をカタログの冒頭に置く
- `docs/src/data/` — `fetch_metrics.py` が GitHub API から取った実測値
  （`metrics.json`）と、そこから機械的に決まる状態（`status.json`）。
  実測値の置き場所であって意見の置き場所ではないので、手で編集しない
- `docs/site/` — `build.py` が吐く HTML。次のビルドで消えるので直接編集しない。
  直すのは必ず `docs/src/` 側
- `docs/build.py` / `docs/fetch_metrics.py` / `docs/collect_candidates.py` /
  `docs/patterns_page.py` — 生成系。このリポジトリのコードはこれだけ。
  `collect_candidates.py` はパターンの出典候補を `data/candidates.json` に落とす。
  候補はランドスケープの母集団（`registry.yaml`）には入れない
- `.apm/skills/` — このリポジトリ固有のエージェント設定

## コマンド

```bash
uv run docs/fetch_metrics.py   # GitHub から実測値を取る。認証は gh に任せる
uv run docs/collect_candidates.py  # パターンの出典候補を集める。gh の認証が必須
uv run docs/build.py           # docs/site/ 以下の HTML を組み直す
apm install                    # apm.yml から ./.claude/ にエージェント設定を展開する
```

この順番を守る。`build.py` は `docs/src/data/metrics.json` を読むだけで自分では取りに
行かないので、先に流しても前回の数字が出るだけになる。

どのスクリプトも冪等で、実データに差が無ければファイルに触らない。続けて2回流して
git の差分が出ないことが、正しく終わった証拠になる。

`build.py` は警告を出して終わることがある。「改名 / 移転を検出」なら `registry.yaml`
の `repo` を直して取り直す。「詳細ティアだが本文が無い」は自動昇格した項目に本文が
要るという意味で、書くまでは既知の警告として残る。

## スキル

エージェント設定は2箇所から来る。どちらも `apm install` が `./.claude/` に展開する
（`apm.yml` 参照）。

- `.apm/` — このリポジトリが自分で書いているエージェント設定はこれだけ。編集・レビュー
  対象はこのディレクトリ
  - `update-landscape` — ランドスケープを実測値で更新する手順。スキル側は入口で、
    手順の正本は `docs/src/landscape/UPDATE_PROMPT.md`
- `core-principal` — 共有ハーネス（ルール、git のガードフック、`core-*` スキル）。
  [dotfiles](https://github.com/yamakura-yuma/dotfiles) リポジトリからコミットで
  固定して取得する。変更は向こうで行い、ここでは `apm update` で `ref` を上げる。
  ローカルでフォークしないこと。

他のリポジトリでも同じに読めるものは `.apm/` ではなく `core-principal` に属する。
`update-landscape` はこのリポジトリの `docs/` の形そのものに依存しているので、ここに置く。

`.claude/` と `apm_modules/` は生成物で gitignore してある。

## graphify

知識グラフは `graphify-out/` に置くが、機械ローカルの生成物なので gitignore してあり、
チェックアウト直後には無い。`graphify update .` で作れる。

規約:
- コードベースについての質問は、graphify-out/graph.json があればまず
  `graphify query "<質問>"` を実行する。関係を辿るなら `graphify path "<A>" "<B>"`、
  特定の概念に絞るなら `graphify explain "<概念>"`。いずれも範囲を絞った部分グラフを
  返すので、GRAPH_REPORT.md や生の grep 出力よりずっと小さい。
- graphify-out/wiki/index.md があれば、生のソースを辿る代わりに全体の案内として使う。
- graphify-out/GRAPH_REPORT.md を読むのは、アーキテクチャ全体を見直すときか、
  query / path / explain で十分な文脈が出てこないときだけ。
- コードを変更したら `graphify update .` を実行してグラフを最新に保つ
  （AST のみ、API 費用なし）。

この節は `graphify install --platform claude` が生成したもの。再実行すると英語に戻ることがある。
