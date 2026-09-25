# ⑥ Argo CD API stream

> Argo CD の API server が公開している `/api/v1/stream/applications` を、常駐クライアントが購読する。API server の broadcaster が informer のイベントを中継するので DELETED も届く。**ただし、消費者の受け取りが遅れているとイベントを捨てる。切断していた間のイベントも取り戻せない。**

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

## 評価

**削除完了の検知: ○。** `DELETED` が、オブジェクトの消滅から 2 ms で届いた（run3）。

**検知層の耐障害性: ×。** 切断していた間の削除は、再接続したときの一覧に出てこない。

**配送層の回復性: ×。** 受け取った後の処理は、すべて自前のクライアントの仕事になる。stream 自体には再送の仕組みが無い。

**配送保証: ×。** 受け取りが詰まるとイベントを捨てるので、at-most-once にも届かない。

**可用性: △。** クライアントを複数並べると、全員が同じイベントを受け取って重複する。重複を除く仕組みも自前で作ることになる。

**疎結合・スケーラビリティ: △。** 送信先の管理もファンアウトも、自分で書く。

**可観測性: △。** すべて自前。

**セキュリティ・権限分離: ○。** Argo CD の RBAC で、見える範囲を絞れる。

**運用負荷: ×。** 自作のクライアントを保守することになる。しかも ⑤ ほどの保証は得られない。

**レイテンシ: ◎。** オブジェクトの消滅から 2 ms（run3）。
