# TechDocs

> `@backstage/plugin-techdocs` と `-backend` で、home-k8s・knowledge-base・dotfiles の markdown を Backstage の中で読む。文書は開かれたときに Backstage の Pod の中の mkdocs が build する。

<p class="eli5">TechDocs は、各リポジトリの markdown を Backstage の中で本の形にして読ませる仕組みです。本の印刷所（build）をどこに置くかで作り方が変わります。大きな会社だと CI で印刷して倉庫（S3 など）に置いておきますが、home-k8s では倉庫を持たず、読みたい人が本を開いたときに案内所の奥（Backstage の Pod の中）で印刷します。初めて開くときは数秒待ちますが、2 回目からは印刷済みの本が出ます。原稿（GitHub の main）が変わっていれば、開いたときに刷り直します。Pod を作り直すと刷った本は消えますが、次に開いたときに刷り直すだけです。</p>

<!-- archify: techdocs.architecture -->

**図の読み方**

- ① エンティティの TechDocs のタブ（または左の「Docs」の `/docs`）を開く
- ② techdocs-backend は、Pod の中に build 済みの HTML が無いか古ければ、③ GitHub からリポジトリの `mkdocs.yml` と `docs_dir` を取る
- ④ イメージに入れた mkdocs（`/opt/venv`、`mkdocs-techdocs-core` 1.7.1）が HTML にし、⑤ Pod の中に置いて配る（publisher `local`）
- ⑤ の HTML は Pod を作り直すと消え、次に開いたときに ② から build し直す

（色と線の読み方: 枠が Backstage の Pod。緑の線は主な流れ。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| build する場所 | Pod の中（`techdocs.builder: local`、`generator.runIn: local`） | CI も、build 済みの HTML の置き場（S3 など）も持たずに済む。代わりに初回は 1 つあたり数秒待つ |
| mkdocs の入れ方 | 実行用のイメージに Python の venv（`/opt/venv`）を作り、pip で `mkdocs-techdocs-core==1.7.1` を入れる | 上流の Dockerfile のコメントの手順。mkdocs などの版は `mkdocs-techdocs-core` が固定する版に任せる |
| GitHub のトークン | 渡さない（`integrations.github` を書かない） | 3 つとも公開リポジトリ。トークン無しだと、カタログは raw.githubusercontent.com から読み、GitHub API（トークン無しは IP ごとに 1 時間 60 回）を使うのは TechDocs の build と更新の確認だけ |
| 外のフォント | 読まない（`techdocs.generator.mkdocs.disableExternalFonts: true`） | mkdocs-material は既定で Google Fonts を読む。build の前に `theme.font: false` を足す |

## セットアップの項目

### パッケージと版

| パッケージ | 版 | 置き場所 |
|---|---|---|
| `@backstage/plugin-techdocs` | 1.18.2（`package.json` は `^1.18.1`、`/alpha`） | `backstage/packages/app` |
| `@backstage/plugin-techdocs-backend` | 2.3.0 | `backstage/packages/backend` |
| `mkdocs-techdocs-core`（pip） | 1.7.1 | [`backstage/Dockerfile`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/Dockerfile) の実行用のステージ |

`App.tsx` の `features` に `techdocsPlugin`（`@backstage/plugin-techdocs/alpha`）を、`packages/backend/src/index.ts` に `backend.add(import('@backstage/plugin-techdocs-backend'))` を足す。文書の画面は検索の API が無いと開けないので、[検索](search.md) も一緒に載せる。

### app-config

```yaml
techdocs:
  builder: local
  generator:
    runIn: local
    mkdocs:
      disableExternalFonts: true
  publisher:
    type: local
```

### エンティティの注釈

文書を出すリポジトリの `catalog-info.yaml` に `backstage.io/techdocs-ref: dir:.` を書き、同じ場所に `mkdocs.yml`（`plugins: [techdocs-core]`）を置く。

| エンティティ | リポジトリ | `mkdocs.yml` の `docs_dir` |
|---|---|---|
| `home-k8s` | yamakura-yuma/home-k8s | `docs` |
| `knowledge-base` | yamakura-yuma/knowledge-base | `docs/src`（`data/` は `exclude_docs` で出さない） |
| `dotfiles` | yamakura-yuma/dotfiles | `docs` |

このリポジトリ（knowledge-base）の `catalog-info.yaml` と `mkdocs.yml` もこの形で、このページ自身も TechDocs で読める。

### Secret・資格情報

いまは無し（公開リポジトリだけを読む）。ログに `API rate limit exceeded` が出るようになったら、GitHub のトークンを Secret にして `integrations.github` に渡す。非公開のリポジトリを足すときもトークンが要る。

### バックエンドのプロキシ

無し。techdocs-backend が自分の API（`/api/techdocs/…`）で配る。

### chart の values・ArgoCD の Application

読むリポジトリは、`clusters/kind/backstage/values.yaml` の `appConfig.catalog.locations` に `catalog-info.yaml` の URL を足す。

```yaml
appConfig:
  catalog:
    locations:
      - type: url
        target: https://github.com/yamakura-yuma/home-k8s/blob/main/catalog-info.yaml
      - type: url
        target: https://github.com/yamakura-yuma/knowledge-base/blob/main/catalog-info.yaml
      - type: url
        target: https://github.com/yamakura-yuma/dotfiles/blob/main/catalog-info.yaml
```

### kind のポート

無し（Backstage の 7007 だけ）。

### 確認の方法

```sh
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
for e in home-k8s knowledge-base dotfiles; do   # build させる (最後に event: finish が出る)
  curl -s -H "Authorization: Bearer $tok" "http://localhost:7007/api/techdocs/sync/default/component/$e" | tail -n 2
done
```

画面では、`home-k8s`・`knowledge-base`・`dotfiles` のページの「TechDocs」タブで本文が出ることを見る（初回は build で数秒待つ）。手元で見た目を確かめるなら、リポジトリの直下で `mkdocs serve`（要 `pip install mkdocs-techdocs-core`）。knowledge-base では `uvx --with mkdocs-techdocs-core mkdocs build --strict -d /tmp/kb-techdocs` が警告なしで通ることを確かめる。

1 度 build した文書は、開くたびに GitHub の `main` と比べ、変わっていれば build し直す（同じ文書の確認は 1 分に 1 回まで）。

## 詳しい手順

- [docs/cluster/backstage.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage.md) の「TechDocs」「イメージ」
