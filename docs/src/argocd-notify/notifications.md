# ① Argo CD Notifications

> **位置づけ:** 推奨構成からは外した。trigger・template・送信先を `argocd` namespace の ConfigMap に書くので、通知を変えるたびに基盤側の設定を触ることになるため。Argo CD の設定を管理しているチームが、通知も持つ場合の代替として残す。
>
> Argo CD に同梱の `argocd-notifications-controller` が、Application を informer で見て trigger の条件式を評価し、template で組んだ本文を service（webhook・Slack など）で送る。**デプロイ完了は取れるが、削除完了は原理的に取れない。**

<div class="grwb">
<svg class="wb" viewBox="0 0 1000 560" role="img" aria-label="グラレコ：Notifications の設定は argocd namespace の中にあり、利用者は外から頼むしかない。on-deleted は消え始めで鳴り、4 回失敗すると諦める">
<path class="hl" d="M40,52 L520,48"/>
<text class="th" x="40" y="58">設定は基盤の部屋の中</text>
<text class="ts" x="560" y="56">Argo CD Notifications</text>
<g filter="url(#wob)">
  <!-- 部屋 -->
  <path class="wb-b fb" d="M40,110 L600,110 L600,500 L40,500 Z"/>
  <rect class="wk fw" x="560" y="270" width="40" height="80"/>
  <rect class="wk fw" x="572" y="296" width="22" height="18" rx="3"/>
  <path class="wk" d="M577,296 v-7 a6,6 0 0 1 12,0 v7"/>
  <!-- ConfigMap の紙 -->
  <path class="wk fw" d="M80,150 l150,0 l0,120 l-150,0 z"/>
  <path class="wk thin" d="M96,196 l110,0 M96,218 l90,0 M96,240 l116,0"/>
  <!-- ベル（on-deleted） -->
  <path class="wr fr" d="M320,230 q0,-50 40,-50 q40,0 40,50 l14,20 l-108,0 z"/>
  <circle class="wr fw" cx="360" cy="262" r="8"/>
  <path class="wr thin" d="M294,190 l-16,-10 M292,214 l-20,0 M426,190 l16,-10 M428,214 l20,0"/>
  <!-- まだ消えていない Namespace -->
  <rect class="wk fw" x="470" y="170" width="70" height="56" rx="6"/>
  <!-- 4 回投げて諦める -->
  <path class="wk" d="M120,360 l30,0 l0,20 l-30,0 z M120,360 l15,11 l15,-11"/>
  <path class="wk thin" d="M156,372 C230,340 300,340 360,372" marker-end="url(#ak)"/>
  <path class="wk thin" d="M156,378 C230,392 300,392 360,380" marker-end="url(#ak)"/>
  <path class="wk thin" d="M156,384 C230,430 300,430 360,392" marker-end="url(#ak)"/>
  <path class="wk thin" d="M156,388 C230,470 300,470 362,402" marker-end="url(#ak)"/>
  <rect class="wr fr" x="370" y="352" width="46" height="70" rx="4"/>
  <path class="wk" d="M440,420 l60,0 l-8,56 l-44,0 z M436,420 l68,0"/>
  <!-- 利用者（部屋の外） -->
  <circle class="wk fw" cx="800" cy="250" r="20"/>
  <path class="wk" d="M800,270 L800,330 M800,290 L760,296 M800,290 L840,300 M800,330 L780,370 M800,330 L820,370"/>
  <path class="wk" d="M700,300 l-60,0" marker-end="url(#ak)"/>
  <path class="wk fw" d="M680,150 h240 a12,12 0 0 1 12,12 v44 a12,12 0 0 1 -12,12 h-120 l-20,18 l4,-18 h-104 a12,12 0 0 1 -12,-12 v-44 a12,12 0 0 1 12,-12 z"/>
</g>
<text class="tb" x="54" y="140">argocd namespace（基盤）</text>
<text class="ts" x="96" y="176">notifications-cm</text>
<text class="ts tr" x="310" y="300">on-deleted</text>
<text class="ts tr" x="292" y="322">消え始めで鳴る</text>
<text class="ts" x="468" y="246">まだある</text>
<text class="ts" x="130" y="350">送信</text>
<text class="ts tr" x="372" y="444">500</text>
<text class="ts" x="428" y="530">4 回で諦める</text>
<text x="700" y="190">cm を変えてください…</text>
<text class="ts" x="760" y="400">利用者</text>
<text class="ts" x="640" y="470">デプロイ完了は oncePer で 1 回だけ</text>
<text class="ts" x="640" y="494">→ Argo CD を持つチームなら代替になる</text>
</svg>
</div>




## アーキテクチャ

```diagram
title: Notifications のアーキテクチャ
caption: 何がどの namespace で動き、状態をどこに持つか
height: 400
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 640, 330]}
  - {label: "外部", kind: ext, box: [670, 30, 320, 330]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", mono: ["spec / status"], box: [25, 60, 250, 54]}
  - {id: ann, kind: state, label: "annotation", mono: ["notified.notifications.argoproj.io", "送信済みの記録（oncePer キー）"], box: [25, 140, 250, 70]}
  - {id: sub, kind: crd, label: "subscribe annotation", mono: ["notifications.argoproj.io/", "subscribe.<trigger>.<service>"], box: [25, 235, 250, 70]}
  - {id: ncc, label: "argocd-notifications-controller", lines: ["informer（Add / Update のみ）"], mono: ["Deployment 1 レプリカ・Recreate"], box: [330, 60, 300, 70]}
  - {id: cm, kind: crd, label: "argocd-notifications-cm", mono: ["trigger / template / service", "subscriptions"], box: [330, 170, 300, 60]}
  - {id: sec, kind: crd, label: "argocd-notifications-secret", mono: ["送信先の資格情報（$key で参照）"], box: [330, 260, 300, 54]}
  - {id: ext, kind: ext, label: "Webhook / Slack など", mono: ["go-retryablehttp", "既定 retryMax 3・1〜5 秒"], box: [690, 60, 280, 70]}
  - {id: brk, kind: ext, label: "Knative Broker（任意）", mono: ["CloudEvent を template で組む"], box: [690, 170, 280, 54]}
edges:
  - {from: ncc, to: app, kind: watch, label: watch}
  - {from: ncc, to: ann, kind: patch, via: [[300, 175]], label: "記録", dy: -4}
  - {from: ncc, to: cm, kind: watch}
  - {from: ncc, to: ext, kind: http, label: HTTP}
  - {from: ncc, to: brk, kind: ce, via: [[660, 197]]}
```

- **状態を持つ場所は Application 自身の annotation だけ。** 送信済みの記録を `notified.notifications.argoproj.io` に書く。コントローラは状態を持たないので、再起動しても記録から続きを判断できる
- **informer に登録しているハンドラは Add と Update だけ。** キューから取り出したときにオブジェクトが無ければ、何もせず戻る（[notifications-engine の pkg/controller/controller.go](https://github.com/argoproj/notifications-engine/blob/0cff13b8a7178194dccd5c4edefa5a66b2cc08bc/pkg/controller/controller.go) の `NewController` と、`processQueueItem` の `if !exists`）。オブジェクトが消えた瞬間を捉える経路が無い

## 権限分離

```diagram
title: Notifications の権限分離
caption: Platform 側が controller と既定の送信先を持ち、App 側は購読と自分の namespace の送信先だけを持つ
height: 380
zones:
  - {label: "Platform 側（Argo CD 管理者）", kind: platform, box: [10, 30, 480, 310]}
  - {label: "App 側（チーム）", kind: app, box: [510, 30, 480, 310]}
nodes:
  - {id: ncc, label: "notifications-controller", lines: ["Role: argocd-notifications-controller"], mono: ["applications: get/list/watch/update/patch"], box: [25, 60, 450, 70]}
  - {id: cm, kind: crd, label: "argocd-notifications-cm / -secret", lines: ["既定の trigger・template・送信先"], mono: ["argocd namespace"], box: [25, 155, 450, 70]}
  - {id: flag, kind: crd, label: "argocd-cmd-params-cm", mono: ["application.namespaces: team-a", "notificationscontroller.selfservice.enabled"], box: [25, 250, 450, 70]}
  - {id: app, kind: app, label: "Application（team-a namespace）", mono: ["subscribe annotation を自分で付ける"], box: [525, 60, 450, 70]}
  - {id: tcm, kind: crd, label: "team-a の argocd-notifications-cm / -secret", lines: ["チーム独自の送信先と資格情報"], mono: ["self-service 有効時のみ"], box: [525, 155, 450, 70]}
  - {id: proj, kind: crd, label: "AppProject（Platform が作る）", mono: ["sourceNamespaces: [team-a]"], box: [525, 250, 450, 70]}
edges:
  - {from: ncc, to: app, kind: watch}
  - {from: ncc, to: tcm, kind: watch}
  - {from: flag, to: proj, kind: rbac, label: "許可"}
```

| 誰が | 何をする | 根拠 |
|---|---|---|
| Platform | controller・`argocd-notifications-cm`・`-secret` を管理し、既定の送信先と資格情報を持つ | [notifications/index.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/notifications/index.md) |
| Platform | self-service を有効にする（`--application-namespaces` と `--self-service-notification-enabled`、または `argocd-cmd-params-cm`） | 同上「Namespace based configuration」 |
| Platform | AppProject の `.spec.sourceNamespaces` に App 側の namespace を載せる。`argocd` namespace は絶対に載せない | [app-any-namespace.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/app-any-namespace.md) |
| App | 自分の namespace の Application に subscribe annotation を付ける | 同上 |
| App | self-service が有効なら、自分の namespace に `argocd-notifications-cm` と `-secret` を置き、独自の送信先と資格情報を持つ | notifications/index.md |

**越境:** Application を `argocd` namespace に置く従来の構成では、App 側が購読を足すのに `argocd` namespace の applications への `patch` が要る。[run9](report.html#run9) では、`team-a` に `edit` を持つ ServiceAccount でも、この権限は無かった。apps-in-any-namespace と self-service を使えば、App 側は自分の namespace だけで購読と送信先を完結でき、他チームの Application には触れない。controller の Role は applications への `update` と `patch` を持つので、Platform はこれを信頼する前提になる。

## 導入・運用の労力

### 基盤側の作業

| 作業 | 頻度 |
|---|---|
| Argo CD（Notifications 同梱）のアップグレード追従 | 既存の運用に含まれる |
| `argocd-notifications-cm` の trigger・template・送信先の管理 | 送信先を増やすたびに編集 |
| self-service を有効にする場合、`argocd-cmd-params-cm` と AppProject の `sourceNamespaces` | 初回だけ |
| 送信失敗の監視（`argocd_notifications_deliveries_total{succeeded="false"}`） | 失敗すると再送されないので必須 |

### 利用者側の作業

| 作業 |
|---|
| subscribe annotation を付ける（self-service なら自分の namespace の cm と Secret も） |
| 受け手を用意する |

## 評価

**削除完了の検知: ×。** カタログの `on-deleted` は `when: app.metadata.deletionTimestamp != nil` で、説明文は "Application is deleted." となっている（[on-deleted.yaml](https://github.com/argoproj/argo-cd/blob/v3.5.3/notifications_catalog/triggers/on-deleted.yaml)）。実測では、削除要求の 0.06 秒後、`resources-finalizer.argocd.argoproj.io` を含む finalizer がまだ 3 つ残っている時点で届いた。

条件を `deletionTimestamp != nil and app.status.health.status == 'Missing'` にしたカスタム trigger は、管理リソースが消えた直後に発火した（[run6](report.html#run6)）。Notifications で取れるのはここが最も遅い時点で、オブジェクトの消滅は取れない。

**デプロイ完了: 取れる。** カタログの `on-deployed` は、operation が Succeeded かつ health が Healthy で、`oncePer: app.status.operationState?.syncResult?.revision`。1 リビジョンにつき 1 回だけ届いた（[run3](report.html#run3)）。

**検知層の耐障害性: ○（デプロイ）／×（削除）。** 送信済みの記録を annotation に持ち、informer は 60 秒ごとに再同期する（`notification_controller/controller/controller.go` の `resyncPeriod`）。そのため、止まっていた間に完了したデプロイも、復旧後に送られる。削除は、止まっている間に消えると復旧後も何も送られなかった（[run4](report.html#run4)・[run5](report.html#run5)）。

**配送層の回復性: △。** webhook は go-retryablehttp で送り、既定は `retryMax: 3`、待ち時間 1〜5 秒（[webhook.go](https://github.com/argoproj/notifications-engine/blob/0cff13b8a7178194dccd5c4edefa5a66b2cc08bc/pkg/services/webhook.go)）。[run8](report.html#run8) では 4 回試行（間隔 1 → 2 → 4 秒）して諦め、**そのあと二度と送り直されなかった。**

ソースは、失敗したら送信済みの記録を戻す作りになっている。ところが `SetAlreadyNotified` は、`oncePer` が付いた trigger では記録を消さずに `false` を返す（[state.go](https://github.com/argoproj/notifications-engine/blob/0cff13b8a7178194dccd5c4edefa5a66b2cc08bc/pkg/controller/state.go)）。そのため `on-deployed` が失敗すると、送信済みとして残る。実測でも、失敗した送信先の分まで annotation に記録されていた。DLQ も circuit breaker も無い。

**配送保証: ○。** `oncePer` と annotation の記録で、重複は除かれる。その代わり、上のとおり失敗は at-most-once になる。

**可用性: △。** Deployment は 1 レプリカで、strategy は `Recreate`（[manifests](https://github.com/argoproj/argo-cd/blob/v3.5.3/manifests/base/notification/argocd-notifications-controller-deployment.yaml)）。リーダー選出の仕組みは見当たらなかった。

**疎結合: △。** 送信先を足すには `argocd-notifications-cm` を編集する。CloudEvent を組んで Broker に 1 本出す形にすれば、この欠点は Broker 側で解消できる（[run7](report.html#run7)）。

**スケーラビリティ: △。** 購読の数だけ、送信先ごとに個別に送る。

**可観測性: △。** 出るのは Prometheus のメトリクスが 2 本（`argocd_notifications_deliveries_total` と `argocd_notifications_trigger_eval_total`、ポート 9001、[monitoring.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/operator-manual/notifications/monitoring.md)）。application-controller などには `--otlp-address` があるが、notifications controller には無い。送信のヘッダは `Content-Type` だけで、`traceparent` は付かなかった。

**セキュリティ・権限分離: ○。** 上の節のとおり分けられるが、apps-in-any-namespace と self-service を有効にする設定が要る。

**運用負荷: ◎。** Argo CD に同梱されていて、増える部品は無い。

**レイテンシ:** デプロイ完了は、operation が Succeeded になった時点で届いた（作成から 6.05 秒）。削除完了は取れない。
