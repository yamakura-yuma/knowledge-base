# Backstage 本体と、環境を切り替えるタブ

> 新しいフロントエンドシステムで組んだアプリと、dev・prod を切り替えて中身を出すタブの仕組み、注釈の規約、確かめ役のサンプルの API。ほかのプラグインのページは、この規約に乗っている。

<p class="eli5">同じお店を 2 店舗（dev と prod）出しているとします。台帳のページを店舗ごとに分けると、同じ説明を 2 回書くことになります。そこで home-k8s では、サービスのページは 1 枚にし、ページの上に「dev / prod」の切り替えボタンを付けました。ページの余白（注釈）には「dev 店の電話番号はこれ、prod 店はこれ」と店舗ごとの連絡先を書いておき、ボタンで選んだ店舗の連絡先だけを中の部品に渡します。部品のほうは店舗が 2 つあることを知らなくてよく、いつもどおり「この番号に電話する」だけです。クラスタの側でも、同じ設計図（ApplicationSet）から店舗ごとに同じものを建てます。</p>

<!-- archify: app.architecture -->

**図の読み方**

- ① サービスの `catalog-info.yaml` に、環境の並び（`home-k8s/environments`）と環境ごとの値（`home-k8s/env.<環境>.<キー>`）を書く
- ② タブの上の切り替えが、選んだ環境を URL の `?env=` に持つ。無い・知らない値なら並びの先頭（`dev`）
- ③ 1 つのインスタンスしか想定していないプラグイン（Grafana・ArgoCD・Azure）には、環境の値をプラグインの注釈に重ねたエンティティを作って渡す。④ プラグインの部品には手を入れない
- ⑤ 自前の部品（Swagger・Temporal・Environments）は、環境の値を直接受け取る
- ⑥ クラスタの側では、ApplicationSet が環境ごとに Application `<名前>-<環境>` を作り、⑦ namespace `dev`・`prod` に同期する

（色と線の読み方: 上の枠が Backstage のフロントエンド、下の枠が kind クラスタ。緑の線は主な流れ。）

## なぜこの形にしたか

- **ページを環境ごとに分けない**: Component は `sample-api` の 1 つのまま、環境ごとの接続先を注釈で持ち、タブの中で切り替える。Swagger のタブも、別のエンティティへ移らずに Component のページの中で読める（[Swagger](swagger.md)）
- **プラグインに手を入れない**: Grafana・ArgoCD・Azure のプラグインは、注釈（`grafana/host-id`・`argocd/app-name`・`azure.com/microsoft-web-sites`）を 1 つしか読まない。環境の値をその注釈に重ねたエンティティを `EntityProvider` で渡せば、プラグインは自分のエンティティを読んでいるつもりのまま、選んだ環境のものを出す
- **資格情報は注釈に置かない**: 資格情報はバックエンドのプロキシの `headers` に環境変数で置き、注釈にはプロキシの経路や Application の名前のような、知られても困らない値だけを書く
- **環境は namespace**: kind クラスタは 1 つのまま、namespace `dev`・`prod` を環境にする。クラスタを環境ごとに分けるのは、この作業の範囲外とした

## セットアップの項目

### パッケージと版

`backstage/packages/app/package.json` と `backstage/yarn.lock` で確かめた版。

| パッケージ | 版 | 役割 |
|---|---|---|
| `@backstage/frontend-defaults` | 0.5.6 | `createApp`。新しいフロントエンドシステムのアプリを作る |
| `@backstage/frontend-plugin-api` | 0.18.1 | `createFrontendPlugin`。自前のプラグイン `environments` を作る |
| `@backstage/plugin-catalog-react` | 3.2.3 | `EntityContentBlueprint`（`/alpha`）。エンティティのタブの拡張を作る |
| `@backstage/plugin-catalog` | 2.0.9 | カタログ（`/alpha`）。入口のページ |
| `@backstage/core-compat-api` | 0.5.15 | 旧 API で書かれた部品とプラグインを新しいシステムで使う（`compatWrapper`・`convertLegacyPlugin`） |

[`backstage/packages/app/src/App.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/App.tsx) は、`createApp({ features: [...] })` に各プラグインの `/alpha` の入口と、自前の `environmentsPlugin`・`azurePlugin`・`navModule` を並べるだけ。新しいフロントエンドシステムでは、ルートやエンティティのページを JSX で組まない。タブの有無と順番は拡張（extension）と `app-config.yaml` の `app.extensions` で決まる。

### タブを作る関数

[`modules/environments/index.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/index.tsx) の `createEnvironmentContent` が、`EntityContentBlueprint.make` でエンティティのタブを作る。

```tsx
const temporalContent = createEnvironmentContent({
  name: 'temporal',            // 拡張の名前 entity-content:environments/temporal
  path: '/temporal',           // エンティティのページの下の経路
  title: 'Temporal',
  requires: [ENV_KEYS.temporalUrl],  // 使う環境のキー。どの環境にも揃っていないエンティティにはタブを出さない
  render: env => <TemporalView env={env} />,
});
```

いまあるタブは 6 つ。

| タブ | 拡張 | 経路 | `requires` |
|---|---|---|---|
| Environments | `entity-content:environments/service` | `/environments` | `api-proxy` |
| Swagger | `entity-content:environments/swagger` | `/swagger` | `api-proxy` |
| ArgoCD | `entity-content:environments/argocd` | `/argocd` | `argocd-app-name` |
| Temporal | `entity-content:environments/temporal` | `/temporal` | `temporal-url` |
| Grafana | `entity-content:environments/grafana` | `/grafana` | `grafana-host-id`・`grafana-dashboard-selector` |
| Azure | `entity-content:azureSites/azure` | `/azure` | `azure-web-sites` |

Azure のタブだけ拡張の名前（`azureSites/azure`）が違うのは、`azure-sites` の旧プラグインを `convertLegacyPlugin` で包んだプラグインの拡張として足しているため（[Azure](azure.md)）。作る関数は同じ `createEnvironmentContent`。

### app-config

この仕組み自体の設定は無い。タブは拡張なので、止めたいときは `app.extensions` に `entity-content:environments/<name>: false` と書ける。全体の設定（`app.baseUrl`・`backend.baseUrl` を同じ `http://localhost:7007` にする、など）は [入口のページ](index.md#common) の表にまとめた。

### エンティティの注釈

キーの一覧の正本は [`annotations.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/annotations.ts) の `ENV_KEYS`。キーを足すときは、home-k8s の [environments.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/environments.md) の表と一緒に直す。

| 注釈 | 値 |
|---|---|
| `home-k8s/environments` | 環境の並び（カンマ区切り）。切り替えに出す順。namespace の名前と同じ |
| `home-k8s/env.<環境>.api-proxy` | バックエンドのプロキシの経路（`/api/proxy` の下）。例 `/sample-api-dev` |
| `home-k8s/env.<環境>.argocd-app-name` | ArgoCD の Application の名前。プラグインの注釈 `argocd/app-name` に重ねる |
| `home-k8s/env.<環境>.temporal-url` | ブラウザが開く Temporal Web UI の URL（iframe の `src`） |
| `home-k8s/env.<環境>.grafana-host-id` | `grafana.hosts[].id`。プラグインの注釈 `grafana/host-id` に重ねる |
| `home-k8s/env.<環境>.grafana-dashboard-selector` | ダッシュボードの選び方。`grafana/dashboard-selector` に重ねる |
| `home-k8s/env.<環境>.azure-web-sites` | App Service・Functions の名前（部分一致）。`azure.com/microsoft-web-sites` に重ねる |

注釈のある環境だけが切り替えに並ぶ。`requires` のキーがどの環境にも揃っていなければ、そのエンティティにはタブ自体が出ない。

### Secret・資格情報

この仕組みは持たない。各タブの資格情報は、そのプラグインのページに書いた。決まりは 1 つで、資格情報は注釈にもブラウザにも置かず、プロキシの `headers` に環境変数で入れる。

### バックエンドのプロキシ

経路の名前は `/<サービス>-<環境>`（Grafana は `/grafana-<環境>/api`）。`app-config.yaml` の `proxy.endpoints` に環境ごとに 1 つ置き、`target` は `http://<Service>.<環境>.svc.cluster.local`。サンプルの API の分は次のとおり。

```yaml
proxy:
  endpoints:
    '/sample-api-dev':
      target: http://sample-api.dev.svc.cluster.local
      allowedMethods: [GET]
    '/sample-api-prod':
      target: http://sample-api.prod.svc.cluster.local
      allowedMethods: [GET]
```

1 つのサービスが環境をまたいで持つもの（dev と prod の Application を同じ ArgoCD が持つ）は、経路を 1 つ（`/argocd/api`）にし、環境の違いは注釈の値で渡す。

### chart の values・ArgoCD の Application

環境ごとに置くものは、`clusters/kind/argocd/apps/` に ApplicationSet を 1 つ置く。例は [`apps/sample-api.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/argocd/apps/sample-api.yaml)。

```yaml
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - list:
        elements:
          - env: dev
          - env: prod
  template:
    metadata:
      name: 'sample-api-{{.env}}'
    spec:
      destination:
        namespace: '{{.env}}'
      syncPolicy:
        syncOptions:
          - CreateNamespace=true
```

- generator は list だけ。home-k8s の `just ci` は list の要素ごとに Application へ展開してから描画・検査するので、ほかの generator は落ちる
- template の中は `{{.env}}` と空白なしで書く。`just ci` は文字列で置き換えるので、`{{ .env }}` は置き換わらずに落ちる
- chart を使うときは、values を `clusters/kind/<名前>/values.yaml`（共通）と `values-{{.env}}.yaml`（環境ごと）の 2 つにする

### サンプルの API（sample-api）

タブの確かめ役のサービス。[`services/sample-api/`](https://github.com/yamakura-yuma/home-k8s/tree/main/services/sample-api) にある。

| ファイル | 中身 |
|---|---|
| `app.py` | 標準ライブラリの HTTP サーバー。`/info`（サービス名・環境・版）、`/hello`、`/healthz`、`/openapi.yaml` |
| `openapi.yaml` | OpenAPI 3。`app.py` が配り、API エンティティが `$text` で読む |
| `kustomization.yaml`・`deployment.yaml` | `app.py` と `openapi.yaml` を ConfigMap にし、`python:3.13-alpine` で動かす。イメージは作らない |
| `catalog-info.yaml` | Component `sample-api`（`providesApis: [sample-api]`、環境の注釈）と API `sample-api` |

環境の名前は Pod の namespace から Downward API（環境変数 `APP_ENV`）で取るので、dev と prod は同じ manifest になる。カタログには、repo の直下の `catalog-info.yaml` の Location `home-k8s-services` が読ませる。

### kind のポート

この仕組みが使うのは Backstage の 7007 だけ。環境ごとの画面のポート（Grafana 3001・3002、Temporal UI 8233・8234）は、Temporal の PR（#86）がまとめて `kind-config.yaml` に足した。`extraPortMappings` はクラスタを作るときにしか効かないので、足したら `just down && just up` で作り直す。

### 確認の方法

```sh
kubectl --context kind-study-kind -n argocd get applicationsets,applications | grep sample-api
kubectl --context kind-study-kind -n dev get pods,svc     # prod も同じ
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
curl -s -H "Authorization: Bearer $tok" http://localhost:7007/api/proxy/sample-api-dev/info    # "environment": "dev"
```

画面は <http://localhost:7007/catalog/default/component/sample-api/environments> を開き、`dev`・`prod` を切り替えて `/info` の `environment` が変わることを見る。

## 詳しい手順

- [docs/cluster/environments.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/environments.md)（規約の正本）
- [docs/cluster/backstage.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage.md)（Backstage 全体）
- [`backstage/packages/app/src/modules/environments/`](https://github.com/yamakura-yuma/home-k8s/tree/main/backstage/packages/app/src/modules/environments)
