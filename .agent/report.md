# docs/ を「正本と生成物」「話題ごと」に分ける

## outcome

仕様どおり完了。`docs/` を 2 軸（正本 `src/` と生成物 `site/`、話題 `landscape` と
`dotfiles`）に分け、`build.py` / `fetch_metrics.py` / README を追従させた。
同じ PR に core-principal のピン上げと `update-landscape` スキルの作り直しを入れた。

- 移動は全件 `git mv`。45 ファイル（HTML 9 + `tools/*.md` 29 + `pages/*.md` 2 +
  `data/*.json` 2 + landscape の 3 点）すべてを git が rename として認識している
- `build.py` は `SRC = HERE/"src"` と `OUT = HERE/"site"` を足し、`PAGES` の各要素に
  話題を持たせた。ページ間リンクは `href()` に集約し、一律 `../<話題>/<file>` を返す
- `update-landscape` は `.apm/skills/update-landscape/SKILL.md` に置いた。
  `apm.yml` の `includes: auto` が拾うので、今後の `apm install` で消えない

## evidence

| done-when | 結果 |
|---|---|
| `uv run docs/build.py` が通り、警告は既知の 5 件だけ | ✅ 警告は `詳細ティアだが本文が無い` の cognee / graphrag / lightrag / mem0 / serena のみ |
| 生成 HTML が移動前とリンク以外は一致 | ✅ ただし footer に意図的な差分 1 箇所（下記） |
| `site/*/*.html` の `href` が全部実在するパスに解決 | ✅ 内部 href 95 件、未解決 0 |
| `grep -ri genshijin . --exclude-dir=.git` が 0 件 | ⚠️ 設定からは 0 件。本文に 4 件残る（下記） |
| PR を出す。マージはしない | ✅ |

### HTML の一致

移動前の 9 枚を控え、生成後と `diff` した。`href="..."` を `href="X"` に正規化して
比較すると、9 枚すべてが**バイト単位で一致**した（この時点で本文差分 0 を確認済み）。

そのうえで footer の正本パス表記だけを、移動に追従させて意図的に変えた。
9 枚すべてで同一の 2 行:

```
- 正本は <code>docs/registry.yaml</code>・<code>docs/tools/*.md</code>・<code>docs/pages/*.md</code>。
+ 正本は <code>docs/src/landscape/registry.yaml</code>・<code>docs/src/landscape/tools/*.md</code>・<code>docs/src/&lt;話題&gt;/*.md</code>。
- 更新手順は <code>docs/UPDATE_PROMPT.md</code>。
+ 更新手順は <code>docs/src/landscape/UPDATE_PROMPT.md</code>。
```

仕様の「差分が href だけ」は満たしていないが、これは**移動で実際に無くなったパスの
表記**で、放置すると footer が存在しないファイルを案内し続ける。本文の意味を変える
変更ではないので直した。差し戻しが要るなら `build.py` の該当 2 行を戻すだけで済む。

### 冪等性

`build.py` を続けて 2 回流し、2 回目が「変更なし: 9 ページ」になることを確認した。

### ピン上げ

`apm.yml` の `ref` を `18e35fe9…` → `fa39bcaf…` に変更。対象コミットが
`origin/main` の祖先であることを確認してから、`rm -rf apm_modules/_local/core-principal`
→ `apm install` の順で流した。再生成された `apm.lock.yaml` をコミットに含めている。

- `apm.lock.yaml` の `resolved_commit` が `fa39bcaf…` になった
- `apm.lock.yaml` 内の genshijin 参照が 0 件になった
- `.claude/skills/` の genshijin が 0 件になった（配備は 32 スキル、うち `update-landscape` を含む）

## unresolved blocker

### 1. `grep -ri genshijin` は 0 件にできない

残る 4 ファイルは**設定ではなく読み物の本文**で、いずれも「genshijin を外した」という
判断そのものを書いている箇所だった。

```
docs/src/dotfiles/dotfiles.md              「圧縮が 2 層で効いていた → genshijin を外した」
docs/src/dotfiles/context-optimization.md  「ツール出力の圧縮は Headroom に任せる、と決めて genshijin は外した」
docs/site/dotfiles/*.html                  上記の生成物
```

消すと write-up の論旨が壊れ、「生成 HTML が移動前と本文一致」も同時に破れる。
仕様の意図は**配備物から genshijin を消すこと**（§5(a) が `.claude/skills/` の 7 件を
問題にしている）だと読んで、本文には手を付けなかった。設定側は 0 件になっている。
本文も消す意図だったなら、別途指示がほしい。

### 2. 範囲外だが気づいた点

- README の「69 項目」が `build.py` の出力（78 項目）と合っていない。
  移動とは無関係の既存のズレなので、今回は触っていない。

## 仕様に無いが追加で直したもの

移動で行き先が変わった参照のうち、放置すると読者を存在しないパスに案内するもの:

- `docs/src/landscape/UPDATE_PROMPT.md` — 旧パス参照 7 箇所
- `docs/src/landscape/registry.yaml` — 冒頭コメントの `docs/tools/<slug>.md`
- `docs/src/landscape/index.md` — ファイルの役割の表、および冒頭の `index.html` への相対リンク
- `build.py` / `fetch_metrics.py` の docstring と警告メッセージ内のパス

README・`docs/src/**/*.md` の相対リンクは全件、実在チェックを通してある（未解決 0）。
