# ⑥ Argo CD API stream

> Argo CD の API server が公開している `/api/v1/stream/applications` を、常駐クライアントが購読する。API server の broadcaster が informer のイベントを中継するので DELETED も届く。**ただし、消費者の受け取りが遅れているとイベントを捨てる。切断していた間のイベントも取り戻せない。**

<div class="grwb">
<svg class="wb" viewBox="0 0 1000 500" role="img" aria-label="グラレコ：API stream は 2 ms で届くが、受け取りが詰まると捨て、切れている間の分は戻らない">
<path class="hl" d="M40,52 L480,48"/>
<text class="th" x="40" y="58">速いけど、あふれたら捨てる</text>
<text class="ts" x="600" y="56">Argo CD API stream</text>
<g filter="url(#wob)">
  <!-- argocd-server（蛇口） -->
  <rect class="wb-b fb" x="60" y="160" width="160" height="110" rx="10"/>
  <path class="wb-b" d="M220,200 L330,200 L330,250"/>
  <path class="wb-b thin" d="M300,250 l60,0"/>
  <!-- 稲妻 2ms -->
  <path class="wb-b" d="M260,150 l-16,26 l18,0 l-14,26"/>
  <!-- バケツ（クライアント） -->
  <path class="wk fw" d="M280,320 l110,0 l-14,110 l-82,0 z"/>
  <path class="wb-b thin" d="M330,262 l0,10 M330,284 l0,10 M330,306 l0,10"/>
  <path class="wr" d="M390,330 q20,10 10,30 M398,356 q14,20 4,40"/>
  <circle class="wr fr" cx="420" cy="410" r="7"/><circle class="wr fr" cx="440" cy="440" r="6"/>
  <!-- 切れたケーブル -->
  <path class="wk" d="M560,260 C620,240 650,280 690,262"/>
  <path class="wk" d="M740,262 C780,246 820,286 900,262"/>
  <path class="wr" d="M704,250 l20,24 M724,250 l-20,24"/>
  <rect class="wk fw" x="520" y="240" width="40" height="40" rx="6"/>
  <rect class="wk fw" x="900" y="236" width="60" height="52" rx="6"/>
</g>
<text class="tb" x="80" y="220">argocd-server</text>
<text class="ts tb" x="276" y="142">2 ms</text>
<text class="ts" x="290" y="460">自前のクライアント</text>
<text class="ts tr" x="452" y="400">drop</text>
<text class="ts tr" x="600" y="320">切れていた間の DELETED は戻らない</text>
<text class="ts" x="560" y="420">retry・HA・重複除去は全部自前</text>
</svg>
</div>




## アーキテクチャ

```diagram
title: API stream のアーキテクチャ
caption: 状態はどこにも持たない。Kubernetes の RBAC ではなく Argo CD のトークンで入る
height: 330
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 560, 260]}
  - {label: "クライアントと外部", kind: ext, box: [590, 30, 400, 260]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", box: [25, 60, 220, 44]}
  - {id: srv, label: "argocd-server", lines: ["informer → broadcaster"], mono: ["チャネルが満杯なら捨てる"], box: [270, 60, 285, 70]}
  - {id: rbac, kind: crd, label: "argocd-rbac-cm", mono: ["p, role:notify, applications, get, …"], box: [270, 170, 285, 54]}
  - {id: cli, label: "常駐クライアント（自作）", mono: ["apiKey のトークン（Secret）"], box: [605, 60, 370, 54]}
  - {id: ext, kind: ext, label: "送信先", box: [605, 170, 370, 44]}
edges:
  - {from: srv, to: app, kind: watch, label: watch}
  - {from: cli, to: srv, kind: http, label: "HTTP stream（SSE）"}
  - {from: cli, to: ext, kind: http}
  - {from: rbac, to: srv, kind: rbac}
```

- API server の broadcaster は、購読者のチャネルに空きが無いとイベントを捨てる（[server/broadcast/broadcaster.go](https://github.com/argoproj/argo-cd/blob/v3.5.3/server/broadcast/broadcaster.go) の `// drop event if cannot send right away`）
- 送る前に、`sendIfPermitted` がトークンの主体に閲覧権限があるかを確かめる（`server/application/application.go`）

## 権限分離

```diagram
title: API stream の権限分離
caption: Platform は Argo CD のアカウントと RBAC を発行する。App 側は許された project の Application しか受け取れない
height: 300
zones:
  - {label: "Platform 側", kind: platform, box: [10, 30, 480, 230]}
  - {label: "App 側", kind: app, box: [510, 30, 480, 230]}
nodes:
  - {id: acc, kind: crd, label: "argocd-cm の accounts.<name>", mono: ["apiKey を発行"], box: [25, 60, 450, 54]}
  - {id: rbac, kind: crd, label: "argocd-rbac-cm", mono: ["team-a の project の applications, get"], box: [25, 140, 450, 54]}
  - {id: cli, label: "チームのクライアント", mono: ["トークンを Secret に置く"], box: [525, 60, 450, 54]}
  - {id: ext, label: "送信先の資格情報", mono: ["クライアントが持つ"], box: [525, 140, 450, 54]}
edges:
  - {from: acc, to: cli, kind: rbac, label: "トークン"}
  - {from: rbac, to: cli, kind: rbac}
```

- **越境:** stream が返すのは、トークンの主体が閲覧を許された Application だけ（`sendIfPermitted`）。Argo CD の RBAC で project ごとに絞れば、他チームの Application は見えない。この絞り込みは実測していない（実測は admin のトークンで行った）
- **資格情報:** 長寿命の apiKey トークンをクライアント側の Secret に持つことになる。漏れたときの影響範囲は、RBAC で絞った範囲になる

## 導入・運用の労力

### 基盤側の作業

| 作業 | 頻度 |
|---|---|
| Argo CD のアカウントと apiKey の発行、RBAC | 初回と更新 |

### 利用者側の作業

| 作業 |
|---|
| 常駐クライアントを書いて運用する（retry・重複除去・HA をすべて自前） |
| トークンを Secret に置いて更新する |

## 評価

**削除完了の検知: ○。** `DELETED` が、オブジェクトの消滅から 2 ms で届いた（[run3](report.html#run3)）。

**検知層の耐障害性: ×。** 切断していた間の削除は、再接続したときの一覧に出てこない。

**配送層の回復性: ×。** 受け取った後の処理は、すべて自前のクライアントの仕事になる。stream 自体には再送の仕組みが無い。

**配送保証: ×。** 受け取りが詰まるとイベントを捨てるので、at-most-once にも届かない。

**可用性: △。** クライアントを複数並べると、全員が同じイベントを受け取って重複する。重複を除く仕組みも自前で作ることになる。

**疎結合・スケーラビリティ: △。** 送信先の管理もファンアウトも、自分で書く。

**可観測性: △。** すべて自前。

**セキュリティ・権限分離: ○。** Argo CD の RBAC で、見える範囲を絞れる。

**運用負荷: ×。** 自作のクライアントを保守することになる。しかも ⑤ ほどの保証は得られない。

**レイテンシ: ◎。** オブジェクトの消滅から 2 ms（[run3](report.html#run3)）。
