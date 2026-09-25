# ⑤ finalizer 方式（Metacontroller）

> Application に自分の finalizer を付けておき、**残っている finalizer が自分だけ**になった時点で送信する。送信に成功してから finalizer を外す。6 方式の中で、削除完了を保証したうえで送れるのはこの方式だけ。finalizer の付け外しは Metacontroller の DecoratorController に任せ、自分で書くのは状態を持たない Webhook 1 つにとどめる。controller-runtime での自作は、得るものが少ない。

## アーキテクチャ

```diagram
title: finalizer 方式のアーキテクチャ
caption: 状態は Application の finalizer 自身が持つ。Metacontroller が付け外しと再試行を受け持ち、hook は状態を持たない
height: 400
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 330, 330]}
  - {label: "metacontroller / notify namespace", kind: platform, box: [360, 30, 330, 330]}
  - {label: "送信先", kind: ext, box: [710, 30, 280, 330]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", box: [25, 60, 300, 44]}
  - {id: fin, kind: state, label: "metadata.finalizers", mono: ["resources-finalizer.argocd…", "post-delete-finalizer.argocd…", "metacontroller.io/decorator…"], box: [25, 130, 300, 86]}
  - {id: argo, label: "application-controller", mono: ["argocd の finalizer を順に外す"], box: [25, 250, 300, 54]}
  - {id: mc, label: "Metacontroller", lines: ["DecoratorController"], mono: ["付け外し・resync・再試行"], box: [375, 60, 300, 70]}
  - {id: dc, kind: crd, label: "DecoratorController（CR）", mono: ["resources: applications", "hooks: sync / finalize"], box: [375, 160, 300, 66]}
  - {id: hook, label: "finalize hook（Webhook）", mono: ["状態なし・約 30 行・2 レプリカ"], box: [375, 255, 300, 54]}
  - {id: ext, kind: ext, label: "送信先 / Broker", mono: ["CloudEvent（Ce-Id = uid）"], box: [725, 255, 250, 54]}
edges:
  - {from: mc, to: app, kind: watch, label: watch}
  - {from: mc, to: fin, kind: patch, via: [[350, 170]], label: "付ける / 外す", dy: -4}
  - {from: argo, to: fin, kind: patch}
  - {from: mc, to: dc, kind: watch}
  - {from: mc, to: hook, kind: http, via: [[690, 95], [690, 240], [525, 240]], label: "finalize 要求"}
  - {from: hook, to: ext, kind: ce, label: "送信"}
```

**流れ:**

1. DecoratorController に `finalize` hook を定義すると、Metacontroller は対象の Application に finalizer `metacontroller.io/decoratorcontroller-<名前>` を付ける（[decoratorcontroller.md の Finalize Hook](https://github.com/metacontroller/metacontroller/blob/master/docs/src/api/decoratorcontroller.md)、`pkg/controller/decorator/controller.go`）。
2. Application が削除されると、Metacontroller は `finalizing: true` を付けて hook を呼ぶ。
3. hook は、自分以外の finalizer が残っているうちは `finalized: false` を返す。残りが自分だけになったら送信し、成功した場合に限って `finalized: true` を返す。
4. `finalized: true` を受け取ると、Metacontroller が finalizer を外し、Application が消える。

**hook の中身** は、試作で約 30 行だった。受け取った JSON の `object.metadata.finalizers` を見て、送るかどうかを決めるだけ。状態は持たない。

## 自作（controller-runtime）と比べる

| 観点 | Metacontroller ＋ hook | controller-runtime で自作 |
|---|---|---|
| 削除完了を取る確実さ | 同じ（どちらも finalizer が根拠） | 同じ |
| 自分で書くもの | 状態を持たない Webhook 1 つ | watch・finalizer の付け外し・再試行・リーダー選出の設定・テスト |
| 再試行 | Metacontroller が、hook が `finalized: true` を返すまで呼び直す | 自分で `RequeueAfter` などを書く |
| 権限 | Metacontroller の ClusterRole は、既定で全リソースへの全 verb（`*`）。Helm の `clusterRole.rules` で絞る | 必要な分だけ（applications の get/list/watch/patch） |
| 保守 | Metacontroller のアップグレードに追従する（1,009 star、v4.17.2、2026-08-13） | 自分のコードと、controller-runtime の追従 |

**自作の利点は、権限を最小にできることだけ。** Metacontroller でも、ClusterRole を絞れば同じところまで寄せられる。検知の確実さと配送保証は、どちらで作っても変わらない。自作にする理由は薄い。

## 権限分離

```diagram
title: finalizer 方式の権限分離
caption: Application に書き込むので、基盤側が持つ部品になる。利用者は送信先で受けるだけ
height: 330
zones:
  - {label: "基盤側", kind: platform, box: [10, 30, 480, 260]}
  - {label: "利用者側", kind: app, box: [510, 30, 480, 260]}
nodes:
  - {id: mc, label: "Metacontroller（基盤が運用）", mono: ["ClusterRole は既定で */*/*。絞ること"], box: [25, 60, 450, 54]}
  - {id: dc, kind: crd, label: "DecoratorController と hook", mono: ["クラスタスコープの CR"], box: [25, 140, 450, 54]}
  - {id: adm, kind: crd, label: "admission（任意）", mono: ["作成時に finalizer を足す（Kyverno など）"], box: [25, 220, 450, 54]}
  - {id: sub, label: "受け手", mono: ["uid で冪等に受ける"], box: [525, 60, 450, 54]}
  - {id: sec, label: "受け手の Secret", mono: ["送信先の資格情報は利用者が持つ"], box: [525, 140, 450, 54]}
edges:
  - {from: dc, to: mc, kind: rbac}
  - {from: mc, to: sub, kind: ce, label: "hook から送信"}
```

- **越境:** 利用者側は Application に触れない。DecoratorController はクラスタスコープの CR なので、作れるのは基盤側だけになる。
- **資格情報:** 直接送る場合、送信先の資格情報は hook が持つ（基盤側）。Broker を挟めば、送信先ごとの受け手（利用者側）に閉じる。

## 評価

**削除完了の検知: ◎。** 自分の finalizer だけが残った時点で、Argo CD はすでに `resources-finalizer` と `post-delete-finalizer` を外し終えている。管理リソースの削除と PostDelete hook の完了が保証された状態で送れる。実測では、自前の試作は消滅の 45 ms 前に送信した（run6）。Metacontroller の hook では、送信からオブジェクトの消滅まで約 10 ms だった（run10）。

**検知層の耐障害性: ◎。** Metacontroller と hook を止めたまま削除すると、Application は Metacontroller の finalizer を 1 つだけ残して待った（run10）。25 秒後に復旧させると、hook が送信し、約 16 秒後に Application が消えた。自前の試作でも同じ動きだった（run4）。

**配送層の回復性: ○。** 送信先を常に 500 にすると、hook は `finalized: false` を返し続けた。Metacontroller は hook を呼び直し、実測では 4 秒後、30 秒後（`resyncPeriodSeconds: 30`）と再送した（run10）。送信先を戻すと、次の呼び出しで送れて Application が消えた。DLQ は無い。送れるまで、削除も完了しない。

**配送保証: ◎。** 送ってから `finalized: true` を返すので、at-least-once になる。応答の前に落ちると重複する。CloudEvent の `Ce-Id` に Application の `uid` を入れ、受け手で重複を除く。

**可用性: ×。** Metacontroller が止まっている間は、削除が完了しない。`--leader-election` を付けて複数レプリカで動かす（[configuration.md](https://github.com/metacontroller/metacontroller/blob/master/docs/src/guide/configuration.md)）。既定のマニフェストは 1 レプリカ。複数レプリカでの動きは実測していない。

**疎結合: ○。** 直接送る形だと、送信先が hook の中に入る。Broker を挟めば、送信先の追加は Trigger 側で済む。

**スケーラビリティ: △。** Metacontroller はリーダー 1 つで処理する。hook は水平に増やせる。

**可観測性: ○。** Metacontroller は `--metrics-address` で Prometheus のメトリクスを出す。送信の span と `traceparent` は hook の側で付ける。

**セキュリティ・権限分離: △。** 既定の ClusterRole が広い。絞るのは基盤側の仕事になる。

**運用負荷: ○。** 増える部品は Metacontroller と hook。自作のコントローラを保守するよりは軽い。

**レイテンシ: ○。** 最後の Argo CD の finalizer が外れると、Metacontroller の watch がそれを拾って hook を呼ぶ。run10 では、送信から消滅まで約 10 ms だった。
