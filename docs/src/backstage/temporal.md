# Temporal（Helm chart と iframe）

> 環境（dev・prod）ごとに Temporal の公式 Helm chart を ArgoCD で立て、sample-api のページの **Temporal** のタブに、その環境の Temporal Web UI を iframe で出す。

<p class="eli5">Temporal 用の Backstage のプラグインは見つからなかったので、Temporal の画面（Web UI）を、Backstage のページに窓（iframe）を開けてそのまま映すことにしました。ところが Temporal の画面は「よその家の窓から覗かれたくない」という札（<code>X-Frame-Options: SAMEORIGIN</code>）を掛けていて、ポート番号が違うだけでも「よその家」扱いになります。そこで画面の手前に門番（Caddy）を立て、札を外す代わりに「覗いてよいのは Backstage の窓だけ」という札（<code>frame-ancestors</code>）に掛け替えました。Backstage の側でも「この 2 つの家の窓なら開けてよい」と自分の決まり（CSP の <code>frame-src</code>）に書き足しています。</p>

<!-- archify: temporal.architecture -->

**図の読み方**

- ① タブは、選んだ環境の注釈 `home-k8s/env.<環境>.temporal-url` を iframe の `src` にする。② Backstage の CSP は `frame-src` に 2 つの URL だけを許す
- ③ ブラウザはホストの `localhost:8233`（dev）・`8234`（prod）を開く。kind の `extraPortMappings` が NodePort 30233・30234 につなぐ
- ④ 門番の Caddy（`temporal-ui-embed`）が、`X-Frame-Options` を外し、`frame-ancestors` を付ける。本文は書き換えない
- ⑤ Web UI（chart の `temporal-web`）は ⑥ `temporal-frontend` を読み、⑥ は ⑦ PostgreSQL に状態を持つ。④〜⑦ は環境ごとに 1 組ずつある

（色と線の読み方: 左の枠が Backstage、右の枠が namespace `dev`。緑の線は主な流れ、破線は許可の設定。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| 見せ方 | Web UI を iframe で出す | Temporal 用の Backstage のプラグインは npm に見つからなかった |
| Temporal 本体 | 公式 chart `temporal` 1.7.0（`https://go.temporal.io/helm-charts`、サーバー 1.32.0、Web UI 2.54.1）を ApplicationSet で環境ごと | 環境ごとに置くものは ApplicationSet で、values を共通（`values.yaml`）と環境ごと（`values-<環境>.yaml`）に分ける規約（[本体と環境のタブ](app.md)）に乗る |
| DB | PostgreSQL 17.6 の StatefulSet を別の Application（`temporal-support`）に置く | chart の schema ジョブは `helm.sh/hook: pre-install,pre-upgrade` で、ArgoCD では PreSync になる。DB を同じ Application に入れると、ジョブが DB より先に走って待ち続け、DB はジョブが終わるまで作られない。分ければジョブが DB の起動まで再試行する（`schema.backoffLimit` 100） |
| `schema.useHelmHooks` | `false` にしない | フックなしだとジョブの名前に release の revision が入る。ArgoCD ではいつも 1 なので、chart の版を上げたときに immutable な Job を更新しようとして落ちる |
| 埋め込みの許可 | Caddy で `X-Frame-Options` を外し、`frame-ancestors 'self' http://localhost:7007` を付ける | Web UI はこのヘッダーを返し、設定で変えられない。外しただけではどのページにも埋め込めるので、親を Backstage と Web UI 自身に絞る。`'self'` は、Web UI がお知らせを自分の `/render` の iframe に入れるため |

## セットアップの項目

### パッケージと版

Backstage の側に追加のパッケージは無い。タブは自前の [`TemporalView.tsx`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/app/src/modules/environments/TemporalView.tsx)（拡張 `entity-content:environments/temporal`、経路 `/temporal`）。クラスタの側の版は次のとおり。

| もの | 版 |
|---|---|
| chart `temporal` | 1.7.0（サーバー 1.32.0、Web UI 2.54.1） |
| PostgreSQL | `postgres:17.6-alpine` |
| 門番 | `caddy:2.11.6-alpine` |

### app-config

```yaml
backend:
  csp:
    # Temporal のタブの iframe。この 2 つのオリジンだけ埋め込みを許す
    frame-src: ["'self'", 'http://localhost:8233', 'http://localhost:8234']
```

Backstage の CSP は `default-src 'self'` で、`frame-src` を書かないと `'self'` 以外の iframe を拒む。

### エンティティの注釈

```yaml
home-k8s/env.dev.temporal-url: http://localhost:8233
home-k8s/env.prod.temporal-url: http://localhost:8234
```

値はブラウザが開く URL。`http`・`https` 以外の値（`javascript:` など）は iframe に渡さず、案内を出す（`TemporalView.tsx` の `temporalEmbedUrl`）。URL を変えたら、CSP の `frame-src`、門番の NodePort、kind-config も揃える。

### Secret・資格情報

Backstage の側は無し。Web UI に認証は無いので、門番はホストの `127.0.0.1` にだけ出す（`0.0.0.0` には開けない）。DB のパスワード `temporal` は Git に書いた固定値で、Secret `temporal-postgres` は `postgres.yaml` が作る（DB の起動と chart が同じ 1 か所を読む）。DB は ClusterIP の Service だけで外に出さない学習用なので、ほかの Secret のように `just up` で Git の外から作ることはしていない。

### バックエンドのプロキシ

無し。iframe はブラウザが Web UI を直接開くので、Backstage のバックエンドを通らない。共有（`just share`）の caddy は Temporal UI を通さないので、共有先ではタブの中身が出ない。

### chart の values・ArgoCD の Application

| もの | 置き場所 | 中身 |
|---|---|---|
| ApplicationSet `temporal` | [`clusters/kind/argocd/apps/temporal.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/argocd/apps/temporal.yaml) | Application `temporal-dev`・`temporal-prod`。`releaseName: temporal`（Service は `temporal-frontend`・`temporal-web`）。values は `values.yaml` と `values-{{.env}}.yaml` を `$values` の参照で重ねる |
| ApplicationSet `temporal-support` | [`apps/temporal-support.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/argocd/apps/temporal-support.yaml) | Application `temporal-support-dev`・`-prod`。`clusters/kind/temporal/overlays/<環境>`（PostgreSQL と門番） |
| 共通の values | [`clusters/kind/temporal/values.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/temporal/values.yaml) | 下の表 |
| 環境ごとの values | `values-dev.yaml`・`values-prod.yaml` | namespace `default` の保存期間（dev 1d・prod 7d） |
| 環境ごとの overlay | `overlays/dev`・`overlays/prod` | 門番の NodePort（30233・30234） |

共通の values の要点。

| 項目 | 値 | 理由 |
|---|---|---|
| レプリカと資源 | frontend・history・matching・worker・web はレプリカ 1、すべてに requests/limits | kind の 1 つのクラスタに 2 環境ぶん立てる |
| `admintools.enabled` | `false` | 管理用の Pod は置かない（schema・namespace のジョブは同じイメージを別に使う） |
| `server.config.persistence.numHistoryShards` | `4`（既定 512） | history のメモリが減る。**DB を作ったあとでは変えられない** |
| DB の接続 | `datastores.default.sql`・`visibility.sql` に `pluginName: postgres12`、`connectAddr: temporal-postgres:5432`、`databaseName: temporal`・`temporal_visibility`、`existingSecret: temporal-postgres` | chart は DB を持たない。`createDatabase`・`manageSchema` が既定で true なので、schema ジョブがデータベースとスキーマを作る |
| `server.config.namespaces.create` | `true` | Temporal の namespace `default` を作る（Web UI が最初に開く） |
| `web.service` | ClusterIP のまま | ホストへ出すのは門番 |

環境 1 つの requests の合計は約 560Mi、limits は約 2.1GiB（home-k8s の temporal.md の見込み。実測はマージ後に取り直す）。

### kind のポート

| 画面 | ホスト | NodePort |
|---|---|---|
| dev の Temporal UI | `127.0.0.1:8233` | 30233 |
| prod の Temporal UI | `127.0.0.1:8234` | 30234 |

[`clusters/kind/kind-config.yaml`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/kind-config.yaml) の control-plane の `extraPortMappings` に足した（Grafana の 3001・3002 も同じ PR で足した）。`extraPortMappings` はクラスタを作るときにしか効かないので、足したあとは人が `just down && just up` でクラスタを作り直す。

### 確認の方法

```sh
kubectl --context kind-study-kind -n argocd get applicationsets,applications | grep temporal   # 4 つの Application が Synced / Healthy
kubectl --context kind-study-kind -n dev get pods,svc,pvc | grep temporal
# X-Frame-Options が無く、frame-ancestors がある
curl -s -D - -o /dev/null http://localhost:8233/ | grep -i -E 'HTTP|frame|content-security'
# Backstage の CSP に frame-src がある
curl -s -D - -o /dev/null http://localhost:7007/ | grep -i content-security-policy | tr ';' '\n' | grep frame-src
```

画面は <http://localhost:7007/catalog/default/component/sample-api/temporal> を開き、dev の Web UI（Workflows の一覧、namespace `default`）が iframe の中に出ることを見る。`prod` に切り替えると UI の URL が 8233 から 8234 に変わる。ブラウザの開発者ツールに `Refused to frame` が出ていないことも見る。

## 詳しい手順

- [docs/cluster/temporal.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/temporal.md)（メモリの見込み、手元の docker での確かめ方）
- [`clusters/kind/temporal/base/Caddyfile`](https://github.com/yamakura-yuma/home-k8s/blob/main/clusters/kind/temporal/base/Caddyfile)
