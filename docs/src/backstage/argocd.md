# ArgoCD（Roadie のプラグイン）

> `@roadiehq/backstage-plugin-argo-cd` で、sample-api のページに **ArgoCD** のタブを置く。dev・prod の切り替えで、Application `sample-api-dev`・`sample-api-prod` の同期状態（Sync）と健全性（Health）を出す。

<p class="eli5">ArgoCD は「Git に書いた設計図どおりに部屋が片づいているか」を見張る管理人です。Backstage から管理人に様子を聞くには合鍵（API トークン）が要ります。ただ、管理人の親玉（admin）の鍵を渡すと、部屋を勝手に作り直すこともできてしまいます。そこで home-k8s では「見るだけ」の専用アカウント <code>backstage</code> を作り、その合鍵だけを Backstage の受付（プロキシ）に預けました。ブラウザには合鍵が渡りません。受付は「見せて」（GET）の頼みしか通さないので、鍵とプロキシの両方で読み取りに絞っています。</p>

<!-- archify: argocd.architecture -->

**図の読み方**

- ① タブが、選んだ環境の注釈 `home-k8s/env.<環境>.argocd-app-name` をプラグインの注釈 `argocd/app-name` に重ね、プラグインの部品に渡す
- ② 部品はバックエンドのプロキシ `/api/proxy/argocd/api` を読む。プロキシは GET だけを通す
- ③ プロキシは Secret `backstage-argocd` から来た環境変数 `ARGOCD_AUTH_TOKEN` を `Authorization: Bearer` に付ける。④ トークンは `just up` が作る
- ⑤ `argocd-server` のアカウント `backstage` は、Application の get だけを許されている。⑥ Application を読んで返す

（色と線の読み方: 左の枠が namespace `backstage`、右の枠が namespace `argocd`。緑の線は主な流れ、破線は資格情報の受け渡し。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| プラグイン | `@roadiehq/backstage-plugin-argo-cd` 2.13.1 | 同期状態・健全性・デプロイ履歴の部品が揃っている。`/alpha` に新しいフロントエンドシステムの入口があり、API の拡張（`ApiBlueprint`）をそのまま使える |
| 画面 | 部品 `EntityArgoCDOverviewCard`・`EntityArgoCDHistoryCard` を環境のタブの中で出す | 注釈 `argocd/app-name` は 1 つしか書けない。環境の値を重ねたエンティティを渡せば、プラグインに手を入れずに切り替えられる |
| 旧 API の部品 | `@backstage/core-compat-api` の `compatWrapper` で包む | 2 つの部品は旧 API（`createComponentExtension`）で作られている |
| プロキシ | `/argocd/api` の 1 つ | dev・prod の Application は同じ ArgoCD にある。環境の違いは Application の名前で渡す |
| 資格情報 | 読み取り専用アカウント `backstage` の API トークン | admin のパスワードは Backstage に渡さない |

## セットアップの項目

### パッケージと版

| パッケージ | 版 | 置き場所 |
|---|---|---|
| `@roadiehq/backstage-plugin-argo-cd` | 2.13.1（範囲を付けず固定） | `backstage/packages/app` |
| `@backstage/core-compat-api` | 0.5.15 | `backstage/packages/app` |

`App.tsx` の `features` に `@roadiehq/backstage-plugin-argo-cd/alpha` を足す。使うのは API の拡張で、画面は自前の [`ArgoCdView.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/ArgoCdView.tsx)（拡張 `entity-content:environments/argocd`、経路 `/argocd`）。

### app-config

```yaml
app:
  extensions:
    # プラグインの既定のタブとカードは、すべての Component に出る。環境のタブだけにする
    - entity-content:argocd/ArgoCdPage: false
    - entity-card:argocd/overviewCard: false
    - entity-card:argocd/historyCard: false

argocd:
  baseUrl: http://localhost:8080   # Application の名前から ArgoCD の画面へ飛ぶリンク先
  revisionsToLoad: 10              # 必ず書く
```

`revisionsToLoad` を書かないと、プラグインは履歴を `slice(0, -1)` で最後の 1 件を落として出す。履歴が 1 件しかない Application では、履歴が空になる。

### エンティティの注釈

```yaml
home-k8s/env.dev.argocd-app-name: sample-api-dev
home-k8s/env.prod.argocd-app-name: sample-api-prod
```

値は ApplicationSet が作る Application の名前（`<名前>-<環境>`）。この注釈を持つエンティティにだけタブが出て、`home-k8s` のページには出ない。

### Secret・資格情報

ArgoCD の API トークンは admin のセッションでしか作れず、値を指定して作ることもできない。そのため Grafana のように「ファイルから Secret を作る」だけでは足りず、`just up` が ArgoCD を入れたあとにトークンを作る。

| 何を | どこに | 中身 |
|---|---|---|
| アカウント | [`clusters/kind/argocd/values.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/argocd/values.yaml) の `configs.cm` | `accounts.backstage: apiKey`（トークンだけ。パスワードでのログインはできない） |
| 権限 | 同じ values の `configs.rbac.policy.csv` | `p, role:backstage-readonly, applications, get, */*, allow` と `g, backstage, role:backstage-readonly`。`policy.default` は空なので、ほかの操作はすべて拒否される |
| トークンを作る | [`just/argocd-secrets.sh`](https://github.com/yamakura-yuma/home-k8s/blob/main/just/argocd-secrets.sh)（`just up` の `_argocd-secrets`） | `argocd-server` の Pod の中の `argocd` CLI で admin としてログインし、トークンを作る。admin のパスワードは `argocd-initial-admin-secret` から読み、標準入力で渡す |
| 置くファイル | `~/.local/share/home-k8s/argocd/backstage-token`（Git の外、本人だけが読める） | 今の ArgoCD で通るうちは作り直さない。クラスタを作り直して通らなくなったときだけ作る |
| Secret | namespace `backstage` の `backstage-argocd`（キー `ARGOCD_AUTH_TOKEN`） | `kubectl apply` ではなく `replace`・`create` で入れる（`apply` は値を `last-applied-configuration` の注釈に残す） |
| 環境変数にする | [`clusters/kind/backstage/values.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/backstage/values.yaml) の `extraEnvVarsSecrets` | `backstage-argocd` を名前で参照する |

admin のパスワードを変えて `argocd-initial-admin-secret` を消した場合は、`just up` がこの手順で止まる。そのときは `argocd account generate-token --account backstage` で作ったトークンを上のファイルに置く。手順は home-k8s の backstage-argocd.md の「トークンの作り方」。

### バックエンドのプロキシ

```yaml
proxy:
  endpoints:
    '/argocd/api':
      target: http://argocd-server.argocd.svc.cluster.local/api/v1
      headers:
        Authorization: Bearer ${ARGOCD_AUTH_TOKEN}
      allowedMethods: [GET]
```

### chart の values・ArgoCD の Application

ArgoCD 自身の values は上の「Secret・資格情報」の表のとおり（`just up` が `helm upgrade --install argocd` で入れ、以後は Application `argocd` が同じ values を同期する）。タブが読む Application は ApplicationSet `sample-api` が作る `sample-api-dev`・`sample-api-prod`。

### kind のポート

Backstage の側は無し。`argocd.baseUrl` のリンク先 `http://localhost:8080` は、ArgoCD の画面（NodePort 30080）の既存のポート。

### 確認の方法

```sh
ctx=kind-study-kind
kubectl --context $ctx -n argocd get cm argocd-cm -o jsonpath='{.data.accounts\.backstage}{"\n"}'          # apiKey
kubectl --context $ctx -n backstage get secret backstage-argocd -o jsonpath='{.data.ARGOCD_AUTH_TOKEN}' | wc -c   # 0 でない
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
for e in dev prod; do
  curl -s -H "Authorization: Bearer $tok" http://localhost:7007/api/proxy/argocd/api/applications/sample-api-$e \
    | jq -r '[.metadata.name, .status.sync.status, .status.health.status] | @tsv'
done
# 読み取り専用であること: 同期の操作 (POST) はプロキシが通さない (4xx)
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H "Authorization: Bearer $tok" \
  http://localhost:7007/api/proxy/argocd/api/applications/sample-api-dev/sync
```

画面は <http://localhost:7007/catalog/default/component/sample-api/argocd> を開き、`dev`・`prod` で Application の名前、Sync Status・Health Status が出ることを見る。

| 症状 | 見るところ |
|---|---|
| 401・403 | トークンが通っていない。トークンのファイルを消して `just up` で作り直す |
| 404 | 注釈の値と Application の名前が違う |
| Backstage の Pod が `CreateContainerConfigError` | Secret `backstage-argocd` が無い |
| プラグインの既定のタブが出る | `app.extensions` の 3 つの `false` が効いていない |

## 詳しい手順

- [docs/cluster/backstage-argocd.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage-argocd.md)
- [`just/argocd-secrets.sh`](https://github.com/yamakura-yuma/home-k8s/blob/main/just/argocd-secrets.sh)
