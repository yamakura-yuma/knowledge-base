# ⑤ 自前 finalizer コントローラ

> Application に自分の finalizer（例 `notify.example.com/deletion`）を付けておく。`deletionTimestamp` が立ち、**残っている finalizer が自分だけ**になったら送信し、送信に成功してから finalizer を外す。**削除完了を保証して送れるのは、6 方式の中でこれだけ。** 代わりに、止まっている間は削除も止まる。

## アーキテクチャ

```diagram
title: 自前 finalizer コントローラのアーキテクチャ
caption: 状態は Application の finalizer 自身が持つ。コントローラは状態を持たず、毎回全件を見直す
height: 380
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 330, 310]}
  - {label: "notify namespace（Platform）", kind: platform, box: [360, 30, 330, 310]}
  - {label: "外部 / Broker", kind: ext, box: [710, 30, 280, 310]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", box: [25, 60, 300, 44]}
  - {id: fin, kind: state, label: "metadata.finalizers", mono: ["resources-finalizer.argocd…", "post-delete-finalizer.argocd…", "notify.example.com/deletion"], box: [25, 130, 300, 86]}
  - {id: argo, label: "application-controller", mono: ["argocd の finalizer を順に外す"], box: [25, 250, 300, 54]}
  - {id: ctl, label: "notify-finalizer", lines: ["作成時に付ける"], mono: ["残りが自分だけ → 送信 → 外す", "controller-runtime・Lease"], box: [375, 60, 300, 86]}
  - {id: lease, kind: state, label: "Lease", mono: ["リーダー選出"], box: [375, 250, 300, 54]}
  - {id: ext, kind: ext, label: "Broker / 任意の HTTP", mono: ["Idempotency-Key: uid"], box: [725, 60, 250, 70]}
edges:
  - {from: ctl, to: app, kind: watch, label: watch}
  - {from: ctl, to: fin, kind: patch, via: [[350, 170]], label: "付ける / 外す", dy: -4}
  - {from: argo, to: fin, kind: patch}
  - {from: ctl, to: ext, kind: ce, label: "送信"}
  - {from: ctl, to: lease, kind: patch}
```

- **状態を持つ場所は finalizer そのもの。** 「まだ送っていない削除」は、自分の finalizer が残っていることで表される。コントローラが落ちても、Kubernetes が Application を消さずに持っていてくれる
- 検証には、Python で 40 行ほどの試作を使った（1 秒ごとに全件を見直す）。本番なら controller-runtime で書き、Manager の `LeaderElection` でリーダーを 1 つにする（[controller-runtime v0.25.1 の pkg/manager/manager.go](https://github.com/kubernetes-sigs/controller-runtime/blob/v0.25.1/pkg/manager/manager.go)）

## 権限分離

```diagram
title: 自前 finalizer の権限分離
caption: Application に書き込む権限が要るので、Platform が持つ部品になる。App 側は Broker の先で受けるだけ
height: 330
zones:
  - {label: "Platform 側", kind: platform, box: [10, 30, 480, 260]}
  - {label: "App 側", kind: app, box: [510, 30, 480, 260]}
nodes:
  - {id: ctl, label: "notify-finalizer（Platform が運用）", mono: ["ServiceAccount: finalizer-ctrl"], box: [25, 60, 450, 54]}
  - {id: role, kind: crd, label: "Role in argocd", mono: ["applications: get/list/watch/patch/update"], box: [25, 140, 450, 54]}
  - {id: adm, kind: crd, label: "admission（任意）", mono: ["作成時に finalizer を足す（Kyverno など）"], box: [25, 220, 450, 54]}
  - {id: sub, label: "Trigger と受け手", mono: ["type=…app.deleted を購読"], box: [525, 60, 450, 54]}
  - {id: sec, label: "受け手の Secret", mono: ["送信先の資格情報は App が持つ"], box: [525, 140, 450, 54]}
edges:
  - {from: role, to: ctl, kind: rbac}
  - {from: ctl, to: sub, kind: ce, label: "Broker 経由"}
```

- **Platform が持つ部品。** Argo CD が所有する CR の `metadata.finalizers` に書き込むので、applications への `patch`（または `update`）が要る。ほかの方式より権限が広く、App 側に渡してはいけない
- **越境:** App 側は Broker の先で受けるだけなので、Application そのものには触れない。受け手を分ければ、他チームの削除通知を購読させない構成にもできる（Trigger の filter で `subject` を絞る）

## 評価

**削除完了の検知: ◎。** 自分の finalizer だけが残った時点では、Argo CD はすでに `resources-finalizer` と `post-delete-finalizer` を外し終えている。つまり、管理リソースの削除も PostDelete hook の完了も保証された状態で送れる。自分の finalizer を外した直後に、オブジェクトは消える。run6 では、送信から 45 ms 後に Application が消えた。

**検知層の耐障害性: ◎。** レベルトリガで、起動するたびに全件を見直すので、止まっていた間の削除も復旧後に拾える。run4 では、コントローラを止めたまま削除すると、Application は自前の finalizer 1 つを残して待った。復旧から 2.4 秒後に送信され、Application が消えた。

**配送層の回復性: ○。** 送信に成功するまで finalizer を外さないので、retry は実装で自由に書ける（`RequeueAfter` によるバックオフなど）。DLQ や circuit breaker は付いてこないので、自分で持つか、Broker に任せる。

**配送保証: ◎。** 送ってから外すので at-least-once になる。外す前に落ちれば、重複しうる。冪等キーには Application の `uid` を使える（試作では `Idempotency-Key` ヘッダに入れた）。

**可用性: ×。** 止まっている間は削除が完了しない。これは確実さと引き換えの性質で、削除できるかどうかをこのコントローラに預けることになる。2 レプリカ以上とリーダー選出が要る。完全に失われた場合の抜け道（finalizer を手で外す手順）も、運用手順として用意しておく。

**疎結合: ○。** 単体だと、送信先がコードに入る。CloudEvent を Broker に出す形にすれば、送信先の追加は Trigger 側で済み、◎ になる（推奨構成）。

**スケーラビリティ: △。** 処理するのはリーダー 1 つ。Application の数が数千程度なら問題にならないと読めるが、測っていない。

**可観測性: ○。** 自分で OTel SDK を入れ、送信の span を切り、`traceparent` を付けて送れる。組み込みではないので ○ にした。

**セキュリティ・権限分離: △。** applications への `patch` が要り、権限が広い。

**運用負荷: △。** 自作のコントローラを保守することになる。

**レイテンシ: ○。** Argo CD の最後の finalizer が外れてから、次のループで送る。試作は 1 秒ごとのポーリングだったので、最大で約 1 秒遅れる。watch で書けば、この遅れは縮む。
