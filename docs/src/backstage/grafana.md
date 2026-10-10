# Grafana（環境ごとの観測スタックと複数 host）

> `@backstage-community/plugin-grafana` の `grafana.hosts` で Grafana を 3 つ（既存・dev・prod）持たせ、sample-api のページの **Grafana** のタブに、選んだ環境の Grafana のダッシュボードの一覧を出す。環境ごとの Prometheus・Loki・Tempo・OTel Collector・Grafana は ApplicationSet で立てる。

<p class="eli5">Grafana はグラフの掲示板です。home-k8s には、もともと Claude Code の観測用の掲示板が 1 枚あり、そこへ dev 用と prod 用の掲示板を 1 枚ずつ足しました。Backstage の Grafana 係（プラグイン）は、はじめ「掲示板は 1 枚」と思い込んでいるように見えましたが、実は「掲示板の住所録」（<code>grafana.hosts</code>）を持てます。住所録に 3 枚を書いておき、タブの上で dev を選ぶと「dev の掲示板を見て」と係に頼みます。掲示板を見るには見るだけの合言葉（Viewer のユーザー <code>backstage</code>）が要りますが、合言葉は受付（プロキシ）が持っていて、ブラウザには渡りません。窓（iframe）で掲示板を映す方法もありますが、Grafana は窓から覗かれるのを既定で断るので、係に一覧を取ってきてもらう形にしました。</p>

<!-- archify: grafana.architecture -->

**図の読み方**

- ① タブが、選んだ環境の `grafana-host-id`・`grafana-dashboard-selector` をプラグインの注釈に重ね、② プラグインのダッシュボードのカードに渡す
- ② カードは、その host のプロキシ `/api/proxy/grafana-<環境>/api` で Grafana の `/api/search` を読む。③ プロキシは Basic 認証を付け、GET だけを通す
- ④ 環境の Grafana は、Viewer の専用ユーザー `backstage` として答える。⑤ データソースは同じ namespace の Prometheus・Loki・Tempo
- ⑥ 一覧の各行は、その環境の Grafana の画面（`localhost:3001`・`3002`）へのリンク

（色と線の読み方: 左の枠が Backstage、右の枠が環境の namespace。緑の線は主な流れ、破線はブラウザが開くリンク。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| プラグイン | `@backstage-community/plugin-grafana` 1.1.0（もともと入れていた） | `grafana.hosts` で host を複数持ち、注釈 `grafana/host-id` で選べる。`/alpha` に新しいフロントエンドシステムの入口がある。新しいプラグインを足さずに済む |
| 画面 | プラグインの `EntityGrafanaDashboardsCard` を環境のタブの中で出す | 注釈は 1 つしか書けないので、環境の値を重ねたエンティティを `EntityProvider` で渡す。旧 API の部品なので `compatWrapper` で包む |
| iframe にしない | プロキシ経由のカード | Grafana は既定で埋め込みを拒み（`allow_embedding: false`）、許すと匿名か cookie のログインが要る。プロキシなら資格情報をバックエンドに置いたまま、既存のカードと同じ見た目で出せる |
| ダッシュボードの選び方も環境の注釈に | `grafana-dashboard-selector` | エンティティ自身に `grafana/dashboard-selector` を書くと、既存の観測スタックの Grafana の既定のカードが、そのエンティティのページにも出る |
| 環境の観測スタック | 5 つの ApplicationSet。永続化なし（emptyDir）、保持 2 日、kube-state-metrics・node-exporter なし、Loki・Tempo は単一バイナリ | kind の 1 つのクラスタに 2 環境ぶんを足すので、既存の観測スタックより絞る |
| 既存の観測スタック | namespace `observability` のまま残す | Claude Code・Orca の観測は作り替えない。注釈 `grafana/host-id` を持たない `home-k8s` のページは `defaultHost` の `default` を向くので、既存のカードは変わらない |

## セットアップの項目

### パッケージと版

| パッケージ | 版 | 置き場所 |
|---|---|---|
| `@backstage-community/plugin-grafana` | 1.1.0（`/alpha`） | `backstage/packages/app` |
| `@backstage/core-compat-api` | 0.5.15 | `backstage/packages/app` |

`App.tsx` の `features` に `grafanaPlugin`（`@backstage-community/plugin-grafana/alpha`）を足す。タブは自前の [`GrafanaView.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/GrafanaView.tsx)（拡張 `entity-content:environments/grafana`、経路 `/grafana`）。

### app-config

```yaml
app:
  extensions:
    - entity-card:grafana/dashboards          # home-k8s のページのカード（注釈 grafana/dashboard-selector を持つエンティティ）
    - entity-card:grafana/alerts: false       # アラートのルールを置いていない

grafana:
  defaultHost: default
  hosts:
    - id: default                              # 既存の observability の Grafana
      domain: http://localhost:3000
      proxyPath: /grafana/api
      unifiedAlerting: false
    - id: dev
      domain: http://localhost:3001
      proxyPath: /grafana-dev/api
      unifiedAlerting: false
    - id: prod
      domain: http://localhost:3002
      proxyPath: /grafana-prod/api
      unifiedAlerting: false
```

- `domain` はダッシュボードのリンク先（ブラウザが開く URL）
- `grafana.hosts` を書くと `grafana.domain` は無視される。既存の `grafana.domain`・`unifiedAlerting` は `hosts` の `default` に移す
- `proxyPath` が host で重なる、`defaultHost` の id が `hosts` に無い、`id` が重なる、のどれかでも Backstage は起動時に落ちる

### エンティティの注釈

```yaml
# services/sample-api/catalog-info.yaml。grafana/* はこのエンティティ自身には書かない
home-k8s/env.dev.grafana-host-id: dev
home-k8s/env.dev.grafana-dashboard-selector: sample-api
home-k8s/env.prod.grafana-host-id: prod
home-k8s/env.prod.grafana-dashboard-selector: sample-api
```

`grafana-dashboard-selector` の値は、ダッシュボードの JSON の `tags`。既存の `home-k8s` のページは、エンティティ自身に `grafana/dashboard-selector: "tags @> 'claude-code' || …"` を書いている（演算子は `||`・`&&`・`==`・`!=`・`@>`・`!`）。

### Secret・資格情報

環境の Grafana には 2 つのユーザーがいる。

| ユーザー | ロール | パスワードのファイル（Git の外） | 使う者 |
|---|---|---|---|
| `admin` | Admin | `~/.local/share/home-k8s/observability/env-grafana/<環境>-admin-password` | 人（画面に入る）。各環境の Secret `grafana-admin` |
| `backstage` | Viewer | `~/.local/share/home-k8s/observability/env-grafana/<環境>-backstage-password` | Backstage のプロキシ。各環境の Secret `grafana-backstage` |

`just up` の `_grafana-env-secrets`（[`just/grafana-env-secrets.sh`](https://github.com/yamakura-yuma/home-k8s/blob/main/just/grafana-env-secrets.sh)）が、環境ごとに次をする。パスワードのファイルが無ければ `openssl rand` で作り（本人だけが読める）、あれば再利用する。

1. namespace `dev`・`prod` を（無ければ）作る
2. 各環境の namespace に Secret `grafana-admin`（`admin-user`・`admin-password`）と `grafana-backstage`（`password`）を入れる
3. namespace `backstage` に Secret `backstage-grafana-env` を入れる。キーは `GRAFANA_DEV_BASIC_AUTH`・`GRAFANA_PROD_BASIC_AUTH`、値は `backstage:<パスワード>` の base64

Secret は `replace`・`create` で入れ、値は `--from-file` と本人だけが読める一時ファイルで渡す（引数に出ると `ps` に残る）。Grafana の横のサイドカー `backstage-user`（`curlimages/curl`）が、Pod の起動ごとに一度だけ HTTP API でユーザー `backstage` を作る。永続化しないので、Pod を作り直すたびに Secret の値で作り直される。

既存の Grafana（`default`）の分は、`just up` の `_grafana-secrets` が Secret `backstage/backstage-grafana`（`GRAFANA_BASIC_AUTH`）を作る。どちらも `clusters/kind/backstage/values.yaml` の `extraEnvVarsSecrets` で環境変数になる。

### バックエンドのプロキシ

```yaml
proxy:
  endpoints:
    '/grafana/api':
      target: http://grafana.observability.svc.cluster.local
      headers:
        Authorization: Basic ${GRAFANA_BASIC_AUTH}
    '/grafana-dev/api':
      target: http://grafana.dev.svc.cluster.local
      headers:
        Authorization: Basic ${GRAFANA_DEV_BASIC_AUTH}
      allowedMethods: [GET]
    '/grafana-prod/api':
      target: http://grafana.prod.svc.cluster.local
      headers:
        Authorization: Basic ${GRAFANA_PROD_BASIC_AUTH}
      allowedMethods: [GET]
```

経路は `grafana.hosts[].proxyPath` と同じにする。プラグインは host ごとに別の経路を要る。

### chart の values・ArgoCD の Application

5 つの ApplicationSet（`clusters/kind/argocd/apps/env-{prometheus,loki,tempo,otel-collector,grafana}.yaml`）が、環境ごとに Application `env-<名前>-<環境>` を作る。chart と版は `observability` の Application と同じ。values は `clusters/kind/env-<名前>/values.yaml`（共通）と `values-<環境>.yaml`（環境ごと）。

| ApplicationSet | chart | この環境でしていること |
|---|---|---|
| `env-prometheus` | `prometheus` 29.35.0 | cAdvisor だけをスクレイプし、その環境の namespace の Pod の CPU・メモリ・ネットワークだけを残す。ClusterRole の名前は `prometheus-server-<環境>`（`prometheus-server` は `observability` が使っていて、クラスタに 1 つしか置けない） |
| `env-loki` | `loki` 18.13.7 | 単一バイナリ。OTLP を受ける。保持 2 日。namespace の Role にする（`rbac.namespaced`） |
| `env-tempo` | `tempo` 3.0.0 | 単一バイナリ。OTLP を受ける。保持 2 日 |
| `env-otel-collector` | `opentelemetry-collector` 0.174.0 | DaemonSet。その環境の `sample-api` の Pod のログを filelog で読み、OTLP と合わせて同じ環境の Tempo・Prometheus・Loki へ渡す。`service.enabled: true` で Service を作る |
| `env-grafana` | `grafana` 13.2.7（`https://grafana-community.github.io/helm-charts`） | データソースは同じ namespace の Prometheus・Loki・Tempo。ダッシュボードは ConfigMap から provisioning。NodePort 30301（dev）・30302（prod）。匿名アクセスなし |

ダッシュボードは [`clusters/kind/env-grafana/dashboards/`](https://github.com/yamakura-yuma/home-k8s/tree/main/clusters/kind/env-grafana/dashboards)（`sample-api.json`、`kustomization.yaml`）。JSON の `tags` に `sample-api` を入れる。JSON を足したら `kustomization.yaml` の `files` も直す。

見積もりは 1 環境で requests 392Mi・limits 1.0GiB、2 環境で requests 784Mi・limits 2.1GiB（実測ではなく、`observability` の同じ部品の実測からの見積もり）。Pod が `too many open files` で起動しないときは、ホストで `fs.inotify.max_user_instances` を上げる。

### kind のポート

| 画面 | ホスト | NodePort |
|---|---|---|
| 既存の Grafana | `127.0.0.1:3000` | 30300 |
| dev の Grafana | `127.0.0.1:3001` | 30301 |
| prod の Grafana | `127.0.0.1:3002` | 30302 |

dev・prod の 2 つは Temporal の PR（#86）が `kind-config.yaml` に足した。古いクラスタでは `just down && just up` で作り直すまで開かない。

### 確認の方法

```sh
ctx=kind-study-kind
kubectl --context $ctx -n argocd get applicationsets | grep '^env-'
kubectl --context $ctx -n backstage get secret backstage-grafana-env -o jsonpath='{.data}' | python3 -c 'import sys,json; print(sorted(json.load(sys.stdin)))'
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
for e in dev prod; do
  curl -s -H "Authorization: Bearer $tok" "http://localhost:7007/api/proxy/grafana-$e/api/api/search?type=dash-db&tag=sample-api" | jq -r '.[].title'
done
```

画面は <http://localhost:7007/catalog/default/component/sample-api/grafana> を開き、`dev`・`prod` でそれぞれのダッシュボードの一覧が出ること、リンクが `localhost:3001`・`3002` に飛ぶことを見る。`home-k8s` のページの Dashboards のカードが、いままでの一覧のままであることも見る。

| 症状 | 見るところ |
|---|---|
| 401 | Basic 認証が通っていない。環境の Grafana の Pod のサイドカー `backstage-user` のログ |
| 502 | 環境の Grafana の Pod が起動していない |
| 一覧が空 | ダッシュボードの JSON の `tags` に `sample-api` があるか |
| Backstage の Pod が `CreateContainerConfigError` | Secret `backstage-grafana-env` が無い |

## 詳しい手順

- [docs/cluster/backstage-grafana.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage-grafana.md)（環境の観測スタックの中身、メモリの見積もり）
- [docs/cluster/backstage.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage.md) の「ダッシュボードの選び方」「Grafana の読み方」（既存の Grafana の分）
