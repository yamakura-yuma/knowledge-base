# knowledge-base

調べたことを溜めておく場所。情報は markdown を正本にし、読む用の HTML は生成する。

## docs/ の構え

手で書く正本は `docs/src/`、`build.py` が吐く HTML は `docs/site/` に分けてある。
どちらも話題ごとのディレクトリに入っていて、**生成物は正本の話題に従う**。

```
docs/
  build.py  fetch_metrics.py
  src/                  # 正本。手で書くもの
    landscape/          # 話題① AI ツールのランドスケープ
    tool-research/      # 話題② ハーネスに入れる外部ツールの調査
    argocd-notify/      # 話題③ Argo CD の完了通知
    patterns/           # 話題④ ハーネスのパターン・カタログ
    data/               # 取得物・状態（metrics.json / status.json / candidates.json）
  site/                 # 生成物。直接編集しない
    landscape/  tool-research/  argocd-notify/  patterns/
```

```bash
uv run docs/fetch_metrics.py   # GitHub から実測値を取る
uv run docs/collect_candidates.py  # パターンの出典候補を集める（話題④）
uv run docs/build.py           # HTML を生成する（landscape / tool-research / patterns）
uv run docs/build_argocd_notify.py  # 話題③ の HTML を生成する
```

## いま入っているもの

### 話題① AI コーディングツール・ランドスケープ

エージェント CLI、IDE 統合、クラウドエージェント、モデルゲートウェイ、共通基盤を
**リクエストが通る経路上の位置**で 4 層に分けて並べたもの。69 項目。

- 読む: [`docs/site/landscape/index.html`](./docs/site/landscape/index.html)（自己完結。外部通信もスクリプトも無し）
- 作り: [`docs/src/landscape/index.md`](./docs/src/landscape/index.md)（分類軸・母集団の決め方・ファイルの役割）
- 更新: [`docs/src/landscape/UPDATE_PROMPT.md`](./docs/src/landscape/UPDATE_PROMPT.md)、または `/update-landscape`

星の数・直近リリース・アーカイブ状態は GitHub API の実測値で、
「いまホットか」の判定はすべてその数字から機械的に出している。
裏が取れなかった値は空欄のままにしてあり、推測では埋めていない。

### 話題② ハーネスに入れる外部ツールの調査

ランドスケープで並べたツールのうち、手元のハーネスに入れているもの・入れるか検討したものを、
対抗馬と並べて調べた話。ハーネスを変えても書き換わらない、ツールそのものについての調査だけを置く。

- [`docs/site/tool-research/context-optimization.html`](./docs/site/tool-research/context-optimization.html)
  — Headroom / CodeGraph / graphify を対抗馬と並べて比較する
  （正本 [`docs/src/tool-research/context-optimization.md`](./docs/src/tool-research/context-optimization.md)）

ハーネスそのもの（何をどこへ配り、どう検証しているか）の説明はここには置かない。
正本は dotfiles リポジトリの [`docs/`](https://github.com/yamakura-yuma/dotfiles/tree/main/docs)
（手元では `~/dotfiles/docs/`）で、ハーネスを変えたときに一緒に変わるものはすべてそちらに書く。

### 話題③ Argo CD の完了通知：イベントをどう発行するか

Argo CD の `Application` や Namespace の作成・更新・削除から、「デプロイ完了」「削除完了」の
イベントをどう発行するかを、kind 上の実測とソースを根拠に比べたもの。

- [`docs/site/argocd-notify/index.html`](./docs/site/argocd-notify/index.html) — 概要と評価マトリクス。
  方式ごとのページ（Notifications / PostSync・PostDelete / Knative / Argo Events /
  finalizer / API stream）と実測の報告書へはここから辿る
- 正本は [`docs/src/argocd-notify/`](./docs/src/argocd-notify/)。ほかの話題とは独立していて、
  `docs/build_argocd_notify.py` だけで生成する（Node と `apm install` が要る）

### 話題④ ハーネスのパターン・カタログ

各ハーネス・スキル集から学べる**型**（ツールではなく）を、プロンプト ⊂ ハーネス ⊂ ループ ⊂ グラフ
の 4 層に分けて並べ、自作ハーネス（`~/dotfiles` の core-principal）での状態（採用済・部分的・
未採用・観察）を付けたもの。出典は公式ドキュメントか README の原文だけ。

- 読む: [`docs/site/patterns/index.html`](./docs/site/patterns/index.html)（先頭の図で、どの層が薄いか分かる）
- 正本: [`docs/src/patterns/catalog.yaml`](./docs/src/patterns/catalog.yaml)
- 見立て（意見）: どういう形式のハーネスがよいか。[`docs/site/patterns/harness-form.html`](./docs/site/patterns/harness-form.html)
  （正本 [`docs/src/patterns/harness-form.md`](./docs/src/patterns/harness-form.md)。件数は catalog.yaml から生成時に数える）
- 出典候補: `docs/collect_candidates.py` が GitHub の topic 検索と awesome 系リストから、
  LLM を使わずに star/日で上位を集める（[`docs/src/data/candidates.json`](./docs/src/data/candidates.json)）。
  ランドスケープの母集団には入れない
- 更新: [`UPDATE_PROMPT.md`](./docs/src/landscape/UPDATE_PROMPT.md) の 7、または `/update-landscape`
