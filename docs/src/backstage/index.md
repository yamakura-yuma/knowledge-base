# home-k8s の Backstage の設定

> home-k8s（kind クラスタ）で動かしている Backstage のセットアップの項目を、アプリ・プラグインごとにまとめた。各ページは「何を入れ、どこに何を書いたか」と「なぜそうしたか」に絞り、手順の細部は home-k8s の docs へリンクする。

<p class="eli5">Backstage は、社内のサービスを一冊にまとめた「案内所の台帳」のようなものです。台帳の 1 ページ（エンティティのページ）がサービス 1 つに当たり、ページの上のタブを切り替えると、API の説明書（Swagger）、配置の状況（ArgoCD）、ワークフローの画面（Temporal）、グラフ（Grafana）、クラウドの資源（Azure）を同じ場所で見られます。home-k8s では、同じサービスを練習用（dev）と本番役（prod）の 2 つの部屋（namespace）で動かしていて、タブの上のボタンで部屋を切り替えます。案内所の係（Backstage のバックエンド）は鍵束（Secret）を預かっていて、ブラウザの代わりに各部屋へ問い合わせます。だからブラウザには鍵が渡りません。</p>

<!-- archify: index.architecture -->

**図の読み方**

- ① ブラウザは `localhost:7007` の Backstage だけを開く。② Backstage は 1 つの Pod で、画面（フロントエンド）も API も配る
- ③ カタログ（どのサービスがあるか）と文書は、GitHub の `main` から読む。手で登録しない
- ④ 資格情報は `just up` が Git の外のファイルから Secret にし、Pod の環境変数になる。Git にもブラウザにも値は出ない
- ⑤ dev・prod の中身（sample-api・Grafana）と ⑥ ArgoCD へは、バックエンドのプロキシが資格情報を付けて問い合わせる
- ⑦ Azure は資格情報があるときだけ読む。無いあいだも Backstage は起動する

（色と線の読み方: 枠が kind クラスタの中。緑の線は主な流れ、破線は資格情報か、条件付きの流れ。）

## どのページに何があるか

| ページ | 対象 | 見せ方 |
|---|---|---|
| [本体と環境のタブ](app.md) | Backstage 本体（新しいフロントエンドシステム）、dev・prod を切り替えるタブの仕組み、注釈の規約、サンプルの API | 自前のフロントエンドプラグイン `environments` |
| [Swagger](swagger.md) | `@backstage/plugin-api-docs` | Component のタブに OpenAPI を出す。Try it out は環境のプロキシへ |
| [ArgoCD](argocd.md) | `@roadiehq/backstage-plugin-argo-cd` | プラグインの部品を環境のタブで出す |
| [Azure](azure.md) | `@backstage-community/plugin-azure-sites` と `plugin-catalog-backend-module-azure-resources` | App Service・Functions の表と、取り込んだ Resource の表。資格情報が無ければその旨を出す |
| [Temporal](temporal.md) | Temporal の公式 Helm chart | プラグインが無いので Web UI を iframe で出す |
| [Grafana](grafana.md) | `@backstage-community/plugin-grafana` と環境ごとの観測スタック | プラグインのカードを、環境ごとの Grafana（複数 host）で出す |
| [TechDocs](techdocs.md) | `@backstage/plugin-techdocs` | リポジトリの markdown を Pod の中の mkdocs で HTML にする |
| [検索](search.md) | `@backstage/plugin-search` | TechDocs の画面が要る検索の API |

どのページも同じ順に項目を並べた。パッケージと版、app-config、エンティティの注釈、Secret・資格情報、バックエンドのプロキシ、chart の values と ArgoCD の Application、kind のポート、確認の方法。そのプラグインに当てはまらない項目は「無し」と書き、理由を添えた。

## 全体に共通する設定 {#common}

ここに書くのは、どのプラグインのページにも前提として効いている設定。

| 項目 | 値 | どこに |
|---|---|---|
| Backstage の版 | 1.55.0（`@backstage/create-app@0.9.2` の雛形から作った） | [`backstage/backstage.json`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/backstage.json) |
| イメージ | `home-k8s-backstage:0.10.0`。レジストリに置かず、`just up` が build して `kind load` する（`pullPolicy: Never`） | [`just/backstage.just`](https://github.com/yamakura-yuma/home-k8s/blob/main/just/backstage.just) の `backstage_image` と [`clusters/kind/backstage/values.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/backstage/values.yaml) の `tag` |
| chart | `backstage` 2.10.2（`https://backstage.github.io/charts`）。ArgoCD の Application `backstage` が同期する | [`clusters/kind/argocd/apps/backstage.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/argocd/apps/backstage.yaml) |
| ポート | NodePort 30707 を、kind の `extraPortMappings` でホストの `127.0.0.1:7007` に出す | [`clusters/kind/kind-config.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/kind-config.yaml) |
| DB | インメモリの SQLite（`better-sqlite3`、`:memory:`）。カタログは起動のたびに GitHub から読み直す | [`backstage/app-config.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/app-config.yaml) の `backend.database` |
| ログイン | ゲストだけ（`auth.providers.guest.dangerouslyAllowOutsideDevelopment: true`）。`127.0.0.1` にしか出さないため | 同じ `app-config.yaml` の `auth` |
| カタログの入口 | `catalog.locations` に GitHub の `main` の `catalog-info.yaml` を 3 つ（home-k8s・knowledge-base・dotfiles）。`catalog.rules` は Component・System・API・Resource・Location・User を許す | `values.yaml` の `appConfig.catalog.locations`、`app-config.yaml` の `catalog.rules` |

アプリを変えたら、`backstage_image` と `values.yaml` の `tag` を一緒に上げる。同じタグのまま build し直しても Deployment が変わらないので、Pod は作り直されない（揃っているかは home-k8s の `just/test_recipes.py` が確かめる）。

### Secret の一覧

資格情報はどれも `just up` が Git の外のファイルから作る。公開リポジトリに入るのは Secret の名前と環境変数の名前だけ。

| Secret（namespace `backstage`） | 環境変数 | 元のファイル | 作るもの | 使うページ |
|---|---|---|---|---|
| `backstage-grafana` | `GRAFANA_BASIC_AUTH` | `~/.local/share/home-k8s/observability/grafana-backstage-password` | `just/grafana-secrets.sh` | [Grafana](grafana.md) |
| `backstage-grafana-env` | `GRAFANA_DEV_BASIC_AUTH`・`GRAFANA_PROD_BASIC_AUTH` | `~/.local/share/home-k8s/observability/env-grafana/<環境>-backstage-password` | `just/grafana-env-secrets.sh` | [Grafana](grafana.md) |
| `backstage-argocd` | `ARGOCD_AUTH_TOKEN` | `~/.local/share/home-k8s/argocd/backstage-token` | `just/argocd-secrets.sh` | [ArgoCD](argocd.md) |
| `backstage-azure`（任意） | `AZURE_DOMAIN`・`AZURE_TENANT_ID`・`AZURE_CLIENT_ID`・`AZURE_CLIENT_SECRET`・`AZURE_SUBSCRIPTION_ID` | `~/.local/share/home-k8s/backstage/azure.env` | `just/backstage-azure-secret.sh` | [Azure](azure.md) |

上の 3 つは chart の `extraEnvVarsSecrets` が名前で参照するので、無いと Pod が `CreateContainerConfigError` で起動しない。`backstage-azure` だけは `extraEnvVars` の `optional: true` で参照し、無くても起動する。

`just up` の順番は `_kind-up` → `_backstage-image` → `_argocd-install` → `_grafana-secrets` → `_grafana-env-secrets` → `_argocd-secrets` → `_backstage-azure-secret` → …（[`justfile`](https://github.com/yamakura-yuma/home-k8s/blob/main/justfile) の `up`）。ArgoCD のトークンは ArgoCD を入れたあとでないと作れないので、Secret の中で後ろに来る。

## 環境（dev・prod）を表す 2 つの規約

どのタブも、次の 2 つの規約に乗っている。詳しくは [本体と環境のタブ](app.md)。

- **クラスタ側**: 環境は namespace の名前（`dev`・`prod`）。環境ごとに置くものは ArgoCD の ApplicationSet（list generator の要素が `env: dev`・`env: prod`）で、Application `<名前>-<環境>` を作る
- **Backstage 側**: エンティティの注釈 `home-k8s/environments: dev,prod` と `home-k8s/env.<環境>.<キー>: <値>` で、環境ごとの接続先を持つ。タブはこの注釈を読み、選んだ環境の値で中身を出す

## 確かめ方の共通の形

クラスタの Backstage は、ゲストのトークンで API を引ける。各ページの「確認の方法」は、この形を使う。

```sh
just up
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
curl -s -H "Authorization: Bearer $tok" 'http://localhost:7007/api/catalog/entities?filter=kind=component' | jq -r '.[].metadata.name'
```

画面は <http://localhost:7007/catalog/default/component/sample-api> を開き、タブ（Environments・Swagger・ArgoCD・Temporal・Grafana・Azure）を切り替える。

## 正本

home-k8s 側の全体の説明は [docs/cluster/backstage.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage.md)。このページの事実は、home-k8s の `main`（#80・#83〜#87・#90 をマージしたもの）のファイルと照らし合わせた。
