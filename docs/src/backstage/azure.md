# Azure（azure-sites のタブと azure-resources の取り込み）

> sample-api のページの **Azure** のタブ。上に、カタログへ取り込んだ Azure のリソース（`plugin-catalog-backend-module-azure-resources`）、下に App Service・Functions（`plugin-azure-sites`）を環境ごとに出す。資格情報はまだ無いので、無いあいだは「Azure の資格情報が無い」を出す。

<p class="eli5">Azure の様子を Backstage に出すには、Azure に入るための「見るだけの入館証」（サービスプリンシパル）が要ります。home-k8s にはまだ入館証がありません。入館証が無いまま Azure 担当の係（公式のプラグイン）を雇うと、係は初日に「入館証がない」と言って案内所ごと止めてしまいます。そこで、入館証があるときだけ本物の係を置き、無いときは「入館証がまだ届いていません」と答えるだけの代役を置くことにしました。入館証は家の金庫（Git の外のファイル）にしまい、<code>just up</code> のときだけ案内所に渡します。もう一人の係（azure-resources）は、30 分ごとに Azure の名簿を見て、「dev 用」「prod 用」の荷札（タグ）が付いた資源を台帳に写します。</p>

<!-- archify: azure.architecture -->

**図の読み方**

- ① 資格情報のファイル `~/.local/share/home-k8s/backstage/azure.env` は Git の外にあり、無くてよい。② `just up` が、ファイルがあるときだけ Secret `backstage-azure` を作る
- ③ バックエンドは、資格情報が揃えば公式の azure-sites のバックエンドを、欠ければ同じ pluginId の代役を載せる。④ タブは `/api/azure-sites/health` を見て、503 なら「資格情報が無い」を出す
- ⑤ azure-resources の取り込みは、資格情報が揃うときだけ載る。dev・prod でプロバイダーを分け、⑥ Resource Graph を KQL で引き、⑦ Resource エンティティ（namespace `dev`・`prod`）としてカタログに入れる
- ⑦ の Resource は `spec.dependencyOf` で sample-api に結ばれ、タブが選んだ環境の分を表にする

（色と線の読み方: 枠が Backstage の Pod。緑の線は主な流れ、破線は資格情報か、資格情報があるときだけの流れ。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| Web アプリの表 | `@backstage-community/plugin-azure-sites` と `-backend` | Azure の API（ARM の Resource Graph）で読むプラグインのうち、保守されている（2026-04 に更新）のはこれだけ。`@vippsno/plugin-azure-resources` は 2024-03 で止まり、React 16/17 と古い `core-components` に固定されていて入らない |
| 任意のリソース | `@backstage-community/plugin-catalog-backend-module-azure-resources` | azure-sites の問い合わせは `microsoft.web/sites` に固定で、VM・ストレージ・Key Vault などを出せない。このモジュールは KQL で引いた任意のリソースを Resource エンティティにする。カタログが 30 分ごとに取り込むので、タブはカタログを読むだけで済む |
| 新しいフロントエンドシステム | `convertLegacyPlugin` と `compatWrapper` | azure-sites には `/alpha` の入口が無い。API（`azureSiteApiRef`）を `convertLegacyPlugin` で新しいシステムの拡張にし、部品は `compatWrapper` で包む |
| 資格情報が無いとき | 公式のバックエンドを載せず、代役を載せる | 公式のバックエンドは起動時に `azureSites.domain`・`tenantId` が無いと落ち、バックエンドは 1 つのプロセスなので Backstage ごと起動しなくなる |
| 取り込みを環境で分ける | dev・prod でプロバイダーを 2 つ | 片方の問い合わせが落ちても、もう片方の Resource は消えない（プロバイダーごとに全部を入れ替えるため）。対応づけ（`mapping`）にはプロバイダーごとの固定値を書けないので、KQL の `extend environment = 'dev'` で列を足して `metadata.namespace` に引かせる |
| 環境を namespace に | Resource は `resource:dev/<名前>`・`resource:prod/<名前>` | Resource の名前は Azure のリソースの名前そのままで、環境をまたいで同じ名前がありうる |

## セットアップの項目

### パッケージと版

| パッケージ | 版 | 置き場所 |
|---|---|---|
| `@backstage-community/plugin-azure-sites` | 0.13.0 | `backstage/packages/app` |
| `@backstage-community/plugin-azure-sites-backend` | 0.16.0 | `backstage/packages/backend` |
| `@backstage-community/plugin-catalog-backend-module-azure-resources` | 0.12.0 | `backstage/packages/backend` |
| `@backstage-community/plugin-azure-resources-node` | 0.15.0（上のモジュールの依存。認証と Resource Graph のクライアント） | 同上 |
| `@backstage/core-compat-api` | 0.5.15 | `backstage/packages/app` |

フロントエンドは [`modules/azure/index.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/azure/index.tsx) が `convertLegacyPlugin(azureSitesPlugin, { extensions: [azureContent] })` で包み、タブ（拡張 `entity-content:azureSites/azure`、経路 `/azure`）は `createEnvironmentContent` で作る。バックエンドは [`packages/backend/src/index.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/backend/src/index.ts) が、どちらのプラグインも直接ではなく、資格情報を見て載せ分ける loader を足す。

| loader | ファイル | 揃っているときに載せるもの | 欠けているとき |
|---|---|---|---|
| `azureSitesFeatureLoader` | [`azureSites.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/backend/src/azureSites.ts) | `@backstage-community/plugin-azure-sites-backend` | 代役（pluginId `azure-sites`）。`/health` に 503 を返すだけ |
| `azureResourcesFeatureLoader` | [`azureResources.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/backend/src/azureResources.ts) | `@backstage-community/plugin-catalog-backend-module-azure-resources` | 何も載せない |

azure-sites の「揃っている」は `azureSites` の `domain`・`tenantId`・`clientId`・`clientSecret` と `subscriptions[].id`。azure-resources の「揃っている」は `azureResources.credentials` の `tenantId`・`clientId`・`clientSecret` と、各プロバイダーの `scope.subscriptions` が空でないこと。azure-resources は 3 つのどれかが欠けると認証が `DefaultAzureCredential` に落ち、30 分ごとに失敗のログを出し続けるので、載せない。

### app-config

```yaml
azureSites:
  domain: ${AZURE_DOMAIN}
  tenantId: ${AZURE_TENANT_ID}
  clientId: ${AZURE_CLIENT_ID}
  clientSecret: ${AZURE_CLIENT_SECRET}
  subscriptions:
    - id: ${AZURE_SUBSCRIPTION_ID}

azureResources:
  credentials:                       # azure-sites と同じサービスプリンシパル
    tenantId: ${AZURE_TENANT_ID}
    clientId: ${AZURE_CLIENT_ID}
    clientSecret: ${AZURE_CLIENT_SECRET}

catalog:
  providers:
    azureResources:
      - id: sample-api-dev           # prod も同じ形で、'dev' を 'prod' にしたもの
        query: |
          resources
          | where tolower(tostring(tags['environment'])) == 'dev'
          | where tolower(tostring(tags['service'])) == 'sample-api'
          | extend environment = 'dev'
        scope:
          subscriptions:
            - ${AZURE_SUBSCRIPTION_ID}
        schedule:
          frequency: { minutes: 30 }
          timeout: { minutes: 5 }
        defaultOwner: user:default/yamakura-yuma
        mapping:
          metadata:
            namespace: environment     # KQL で足した列
            annotations:
              home-k8s/environment: environment
          spec:
            dependencyOf:
              - component:default/sample-api
```

- 環境変数の無い項目は設定から消える。それで loader が「欠けている」と判断できる
- `mapping` の文字列の値は「Azure の行のその項目の値」を引く。配列（`dependencyOf`）は書いたとおりの値になる
- namespace が `default` でないので、`dependencyOf` と `defaultOwner` は `default/` を省略せず書く（省略すると `dev` の中を探して解決できない）
- `catalog.rules` に `Resource` を許しておく（入口のページの表）

### エンティティの注釈

```yaml
# services/sample-api/catalog-info.yaml
home-k8s/env.dev.azure-web-sites: sample-api-dev
home-k8s/env.prod.azure-web-sites: sample-api-prod
```

azure-sites はプラグインの注釈 `azure.com/microsoft-web-sites` で Web アプリを探す（部分一致、大文字小文字を問わない）。タブが環境の値をこの注釈に重ねる。値を `sample-api` だけにすると、dev と prod のどちらにも両方が出る。

タブはこの注釈を持つ環境にだけ出る。取り込んだ Resource だけを出したいサービス（Web アプリが無いサービス）でも、タブを出すにはこの注釈を付ける（使わない名前でもよい）。

取り込みの側は、注釈ではなく Azure 側のタグで選ぶ。タグ `environment` が `dev` か `prod`、かつタグ `service` が `sample-api` のリソースだけが入る。リソースグループのタグはリソースに引き継がれないので、リソースごとに付ける。

```sh
az tag update --resource-id "$id" --operation Merge --tags environment=dev service=sample-api
```

### Secret・資格情報

| 何を | 中身 |
|---|---|
| 作るもの | 読み取り用のサービスプリンシパル。`az ad sp create-for-rbac --name home-k8s-backstage-reader --role Reader --scopes "/subscriptions/$sub"` |
| 要る権限 | 対象のサブスクリプションの **Reader** だけ。azure-sites の Web アプリの起動・停止のボタンは、Contributor を付けないので押しても拒否される。Resource Graph は Reader を持つ範囲のリソースだけを返す（Reader の無いリソースグループは黙って出ない） |
| 置くファイル | `~/.local/share/home-k8s/backstage/azure.env`。`KEY=VALUE` の行で、値は引用符で囲まない（シェルとして実行しないので、引用符も値に入る） |
| 項目 | `AZURE_DOMAIN`（ポータルへのリンク）・`AZURE_TENANT_ID`・`AZURE_CLIENT_ID`・`AZURE_CLIENT_SECRET`・`AZURE_SUBSCRIPTION_ID` の 5 つ |
| Secret を作る | [`just/backstage-azure-secret.sh`](https://github.com/yamakura-yuma/home-k8s/blob/main/just/backstage-azure-secret.sh)（`just up` の `_backstage-azure-secret`）。ファイルが無い・空なら Secret を作らず、前の Secret があれば消し、失敗しない。項目が欠けていれば、欠けた名前を出して止まる |
| Secret | namespace `backstage` の `backstage-azure`（鍵は 5 つ） |
| 環境変数にする | `clusters/kind/backstage/values.yaml` の `extraEnvVars`。5 つとも `secretKeyRef` に `optional: true` を付けるので、Secret が無くても Pod は起動する |

`AZURE_DOMAIN` だけが欠けると、azure-resources の取り込みは走るが、azure-sites は代役になり、タブは「資格情報が無い」を出す（表は `/health` が 200 のときだけ出る）。5 つとも置く。`clientSecret` には期限がある（既定 1 年）。切れたら `az ad sp credential reset` で作り直してファイルを書き換える。

環境変数は Pod の起動時にしか読まれないので、ファイルを置いたら `just up` のあとに Backstage の Pod を作り直す。

### バックエンドのプロキシ

無し。どちらも Backstage のバックエンドのプラグインが Azure を読む。ブラウザは azure-sites のバックエンド（`/api/azure-sites/…`）とカタログの API を読むだけで、Azure を直接読まない。

### chart の values・ArgoCD の Application

Backstage の chart の `extraEnvVars` だけ（上の表）。Azure のリソースはクラスタに置かないので、ApplicationSet は無い。

### kind のポート

無し。

### 確認の方法

資格情報のファイルが無い、いまの状態での期待値。

```sh
ctx=kind-study-kind
kubectl --context $ctx -n backstage get secret backstage-azure                       # NotFound
kubectl --context $ctx -n backstage logs deploy/backstage | grep -ci 'azure-resource' # 0 (取り込みのモジュールは載らない)
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:7007/api/azure-sites/health  # 503
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
curl -s -H "Authorization: Bearer $tok" 'http://localhost:7007/api/catalog/entities?filter=kind=resource' | jq length  # 0
```

画面は <http://localhost:7007/catalog/default/component/sample-api/azure> を開き、「Azure の資格情報が無い」と出て、`dev`・`prod` を切り替えられることを見る。

資格情報を置いて `just up` と Pod の作り直しを済ませたあとは、`/health` が 200 になり、ログに `Registered scheduled task: azure-resource-provider-sample-api-dev`（と `-prod`）が出る。`filter=kind=resource` がタグを付けたリソースの数だけ返り（`metadata.namespace` が `dev`・`prod`）、タブの上の表に同じものが出る。出ないときは `az graph query` でタグが引けるか、サービスプリンシパルの Reader を確かめる。

## 詳しい手順

- [docs/cluster/backstage-azure.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage-azure.md)（サービスプリンシパルの作り方、手元の docker での確かめ方、偽の Resource Graph）
