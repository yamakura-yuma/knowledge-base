# Swagger（api-docs）

> `@backstage/plugin-api-docs` で、sample-api の Component のページに **Swagger** のタブを置く。OpenAPI の定義を Swagger UI で出し、Try it out の向き先を dev・prod のプロキシで切り替える。

<p class="eli5">API の定義（OpenAPI）は、お店のメニュー表のようなものです。Backstage では本来、メニュー表は「API」という別のページに載ります。でも、お店（Component）のページを見ている人に「メニューは隣の建物です」と言うのは不親切です。そこで home-k8s では、お店のページのタブにメニュー表をそのまま貼りました。さらに「試しに注文する」ボタン（Try it out）を押したときの注文先を、dev 店か prod 店かで切り替えます。注文は直接お店に行かず、受付（Backstage のプロキシ）を通るので、受付が通す注文（GET）しか届きません。</p>

<!-- archify: swagger.architecture -->

**図の読み方**

- ① Component `sample-api` は `providesApis: [sample-api]` で ② API エンティティと結ばれる。API の定義はサービスのコードの隣の `openapi.yaml` を `$text` で読む
- ③ タブは API エンティティの定義を、プラグインの部品 `OpenApiDefinitionWidget`（swagger-ui-react のラッパー）に渡す。そのとき `servers` を選んだ環境のプロキシ 1 つに差し替える
- ④ Try it out の要求は、Backstage のトークン（`Authorization: Bearer`）を付けてプロキシへ。プロキシは GET だけを通す
- ⑤ プロキシの先は namespace `dev`・`prod` の Service `sample-api`

（色と線の読み方: 左の枠が Backstage、右の枠が環境の namespace。緑の線は主な流れ。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| プラグイン | `@backstage/plugin-api-docs` の `/alpha` | 新しいフロントエンドシステムの入口がある。入れると API エンティティの **Definition**（`entity-content:api-docs/definition`）、Component の **APIs**（`entity-content:api-docs/apis`）、`/api-docs` の一覧も付く |
| 部品 | `OpenApiDefinitionWidget` を自前のタブで使う | 同じパッケージの `ApiDefinitionCard` は、いま開いているエンティティ（Component）の `spec.definition` を読むので、Component のタブには使えない。`providesApis` の API を `useRelatedEntities` で引き、その定義を部品に渡す |
| 向き先の切り替え | `servers` を選んだ環境のプロキシ 1 つに差し替える | `openapi.yaml` に書いた `servers`（相対の経路 2 つ）のままだと、Try it out にトークンが付かず、バックエンドに 401 で断られる |
| 定義の置き場 | `services/sample-api/openapi.yaml`（正本は 1 つ） | `app.py` が `/openapi.yaml` で配るものと、API エンティティが読むものを同じファイルにする |

## セットアップの項目

### パッケージと版

| パッケージ | 版 | 置き場所 |
|---|---|---|
| `@backstage/plugin-api-docs` | 0.14.5（`/alpha`） | `backstage/packages/app` |
| `js-yaml` | 4.3.2（`package.json` は `^4.1.0`） | `backstage/packages/app`。定義を読んで `servers` を差し替える |

`App.tsx` の `features` に `apiDocsPlugin`（`@backstage/plugin-api-docs/alpha`）を足す。タブそのものは自前の [`SwaggerView.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/SwaggerView.tsx) と [`openapi.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/openapi.ts) で、[本体と環境のタブ](app.md) の `createEnvironmentContent` に乗せる（拡張 `entity-content:environments/swagger`、経路 `/swagger`）。

### app-config

`app.extensions` には何も書かない（api-docs の拡張は既定のまま有効）。使うのは下のプロキシだけ。

### エンティティの注釈

[`services/sample-api/catalog-info.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/services/sample-api/catalog-info.yaml) に、Component と API を同じファイルで書く。

```yaml
kind: Component
metadata:
  name: sample-api
  annotations:
    home-k8s/environments: dev,prod
    home-k8s/env.dev.api-proxy: /sample-api-dev
    home-k8s/env.prod.api-proxy: /sample-api-prod
spec:
  providesApis:
    - sample-api
---
kind: API
metadata:
  name: sample-api
spec:
  type: openapi
  definition:
    $text: ./openapi.yaml
```

タブが要るのはキー `api-proxy` だけ。注釈の無い環境は切り替えに並ばない。

### Secret・資格情報

無し。sample-api は認証を持たない。Try it out には Backstage のゲストのトークンが要る（バックエンドの認証のため）。swagger-ui の fetch は Backstage の `fetchApi` を通らないので、`requestInterceptor` で向き先への要求にだけ `Authorization: Bearer` を付ける（`identityApi.getCredentials()`）。ほかの URL にはトークンを渡さない。

### バックエンドのプロキシ

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

`servers` は `discoveryApi.getBaseUrl('proxy')` に注釈の値を続けたもの（`http://localhost:7007/api/proxy/sample-api-dev`）。プロキシが GET だけを通すので、タブも Try it out を GET に絞っている（`SwaggerView.tsx` の `SUBMIT_METHODS`）。POST などを足すときは、`allowedMethods` と `SUBMIT_METHODS` を一緒に直す。

### chart の values・ArgoCD の Application

Backstage の側は無し。sample-api は ApplicationSet `sample-api`（[`apps/sample-api.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/argocd/apps/sample-api.yaml)）が Application `sample-api-dev`・`sample-api-prod` として同期する。

### kind のポート

無し。ブラウザが開くのは Backstage（7007）だけで、sample-api の Service は ClusterIP のまま。

### 確認の方法

```sh
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
curl -s -H "Authorization: Bearer $tok" http://localhost:7007/api/proxy/sample-api-dev/info    # "environment": "dev"
curl -s -H "Authorization: Bearer $tok" http://localhost:7007/api/catalog/entities/by-name/component/default/sample-api \
  | jq '.relations[] | select(.type=="providesApi")'
```

画面は <http://localhost:7007/catalog/default/component/sample-api/swagger> を開く（`?env=prod` で prod）。`GET /info` の Try it out → Execute で、Response body の `environment` が選んだ環境になる。URL は `/catalog/default/component/sample-api/swagger` のままで、別のエンティティへ移らない。

API エンティティの Definition（<http://localhost:7007/catalog/default/api/sample-api/definition>）でも同じ定義が読めるが、こちらは `openapi.yaml` の `servers` のままでトークンが付かないので、Try it out は 401 で断られる。共有（`just share`）の caddy は `/api/proxy/*` を通さないので、共有先では Try it out が動かない（定義は読める）。

## 詳しい手順

- [docs/cluster/swagger-tab.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/swagger-tab.md)
- [`services/sample-api/openapi.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/services/sample-api/openapi.yaml)

home-k8s の swagger-tab.md の「マージ後に、クラスタで確かめる手順」にあるイメージのタグ `0.5.0` は、この PR を入れた時点の値。いまのイメージは `home-k8s-backstage:0.10.0`（[入口](index.md#common)）。
