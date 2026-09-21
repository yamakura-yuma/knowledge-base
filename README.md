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
    dotfiles/           # 話題② dotfiles の構成検討
    data/               # 取得物・状態（metrics.json / status.json）
  site/                 # 生成物。直接編集しない
    landscape/  dotfiles/
```

```bash
uv run docs/fetch_metrics.py   # GitHub から実測値を取る
uv run docs/build.py           # HTML を生成する
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

### 話題② dotfiles の構成検討

ランドスケープで並べたツールのうち、実際に手元で使っているものの話。

- [`docs/site/dotfiles/dotfiles.html`](./docs/site/dotfiles/dotfiles.html)
  — このホストのエージェント環境が、どう組み立てられているか
  （正本 [`docs/src/dotfiles/dotfiles.md`](./docs/src/dotfiles/dotfiles.md)）
- [`docs/site/dotfiles/context-optimization.html`](./docs/site/dotfiles/context-optimization.html)
  — Headroom / CodeGraph / graphify を対抗馬と並べて比較する
  （正本 [`docs/src/dotfiles/context-optimization.md`](./docs/src/dotfiles/context-optimization.md)）
