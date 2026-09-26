# ② PostSync / PostDelete Job

> application-controller が、アプリのマニフェストに入っている hook（Job）を、sync の後や削除の途中で作って実行する。Job の中から送信先へ HTTP で送る。**PostDelete が捉えるのは、管理リソースは消えたが Application はまだ残っている時点。**

<p class="eli5">引っ越し業者は、荷物を全部運び出すと「終わりました」と電話をくれますが、それは部屋の鍵を返す前です。Argo CD の PostDelete hook も同じ形で、アプリの Pod や ConfigMap を消し終えたあと、アプリ自身の Job（一回だけ動いて終わる Pod）が知らせを送ります。ところがその時点で、アプリの登録（Application）はまだ残っています。しかも Job が失敗すると Argo CD は片づけを終えないので、宛先が落ちていると削除そのものが止まります。</p>

<!-- archify: hooks.architecture -->

**図の読み方**

- ① application-controller（基盤側）が、アプリのマニフェストにある hook の Job を作る
- ② 先に Pod・ConfigMap（利用者側）が消える
- ③ PostDelete Job は利用者側のマニフェストに入る。⚠ 失敗すると削除が詰まる（評価マトリクス「可用性 ×」）
- 宛先の鍵（Secret）は利用者側に置く。⚠ 全アプリのマニフェストと Secret を直すことになる（変更時の作業の表で ×）

（色と線の読み方: 橙の破線の枠が基盤側、赤の破線の枠が利用者側。緑の線は主な流れ、赤の線と「⚠」は問題点、紫の破線は鍵などの参照。）

<!-- archify: hooks-time.sequence -->

**図の読み方**

- ① 0〜3.45 秒: controller が管理リソースを消す
- ② 4.29 秒: hook の Job が通知する。⚠ この時点で Application はまだある（評価マトリクス「削除完了の検知 △ CR 消滅前」）
- ③ 6.80 秒: Job が成功してから札が外れ、Application が消える。⚠ Job が失敗すると、ここで止まる

（色と線の読み方: 橙の破線の枠が基盤側、赤の破線の枠が利用者側。緑の線は主な流れ、赤の線と「⚠」は問題点、紫の破線は鍵などの参照。）





## アーキテクチャ

```diagram
title: PostSync / PostDelete のアーキテクチャ
caption: hook はアプリのデプロイ先 namespace で、アプリの一部として動く
height: 400
zones:
  - {label: "argocd namespace", kind: platform, box: [10, 30, 330, 330]}
  - {label: "デプロイ先 namespace（demo）", kind: app, box: [360, 30, 330, 330]}
  - {label: "外部", kind: ext, box: [710, 30, 280, 330]}
nodes:
  - {id: app, kind: app, label: "Application（CR）", mono: ["finalizers:", "resources-finalizer…", "post-delete-finalizer…"], box: [25, 60, 300, 86]}
  - {id: ctl, label: "application-controller", lines: ["hook を作る・待つ・消す"], mono: ["StatefulSet（シャード）"], box: [25, 200, 300, 70]}
  - {id: res, label: "管理リソース", mono: ["Deployment / ConfigMap …"], box: [375, 60, 300, 54]}
  - {id: ps, label: "Job: notify-postsync", mono: ["hook: PostSync"], box: [375, 150, 300, 54]}
  - {id: pd, label: "Job: notify-postdelete", mono: ["hook: PostDelete"], box: [375, 240, 300, 54]}
  - {id: sec, kind: state, label: "Secret（送信先の資格情報）", mono: ["アプリごとに置く"], box: [375, 305, 300, 44]}
  - {id: ext, kind: ext, label: "任意の HTTP", mono: ["Job の中で curl など"], box: [725, 150, 250, 54]}
edges:
  - {from: ctl, to: app, kind: patch, label: "finalizer を外す"}
  - {from: ctl, to: res, kind: http, via: [[350, 87]], label: apply/delete, dy: -4}
  - {from: ctl, to: ps, kind: http}
  - {from: ctl, to: pd, kind: http}
  - {from: ps, to: ext, kind: http, label: HTTP}
  - {from: pd, to: ext, kind: http}
```

- **状態を持つ場所は Application の finalizer。** PostDelete hook があると、Argo CD は `post-delete-finalizer.argocd.argoproj.io` と `…/cleanup` を自動で付ける（`controller/appcontroller.go` の `SetPostDeleteFinalizer`）。hook が Healthy になるまで、この finalizer は外れない
- PostDelete は v2.10 から使える（[sync-waves.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/sync-waves.md)）

## 権限分離

```diagram
title: PostSync / PostDelete の権限分離
caption: Platform は AppProject で Job の作成を許すだけ。送信と資格情報は App 側に閉じる
height: 330
zones:
  - {label: "Platform 側", kind: platform, box: [10, 30, 480, 260]}
  - {label: "App 側（デプロイ先 namespace）", kind: app, box: [510, 30, 480, 260]}
nodes:
  - {id: ctl, label: "application-controller", mono: ["デプロイ先に Job を作る権限（Argo CD 既定）"], box: [25, 60, 450, 54]}
  - {id: proj, kind: crd, label: "AppProject", mono: ["namespaceResourceWhitelist に batch/Job"], box: [25, 150, 450, 54]}
  - {id: man, kind: crd, label: "アプリのマニフェスト（Git）", mono: ["hook の Job を App チームが書く"], box: [525, 60, 450, 54]}
  - {id: job, label: "Job の Pod", mono: ["namespace の ServiceAccount で動く"], box: [525, 150, 450, 54]}
  - {id: sec, kind: state, label: "Secret", mono: ["送信先の資格情報（アプリの数だけ置く）"], box: [525, 225, 450, 50]}
edges:
  - {from: proj, to: man, kind: rbac, label: "Job を許可"}
  - {from: ctl, to: job, kind: http}
```

- **Platform の役割は小さい。** AppProject が Job の作成を許していれば済む（AppProject の `namespaceResourceWhitelist` / `Blacklist`、[projects.md](https://github.com/argoproj/argo-cd/blob/v3.5.3/docs/user-guide/projects.md)）
- **越境:** Job はデプロイ先 namespace で、その namespace の ServiceAccount を使って動く。他チームの Application を見る経路は無い。ただし通知の本文は Job が自分で組むので、Job を書けるチームなら、他のアプリ名を名乗る通知を送れてしまう。受け手が送り元を検証する必要がある
- **資格情報:** 送信先の資格情報は、アプリの数だけ各 namespace に置く

## 導入・運用の労力

### 基盤側の作業

| 作業 | 頻度 |
|---|---|
| AppProject で Job の作成を許す | 初回だけ |
| 削除が PostDelete hook で詰まったときの手当て（hook を消す） | 障害のたび |

### 利用者側の作業

| 作業 |
|---|
| 全アプリのマニフェストに hook の Job を書く |
| 送信先の資格情報を各 namespace に置いて更新する |
| 受け手を用意する |

## 評価

**削除完了の検知: △。** ドキュメントは「全リソースが消えた後に実行し、hook が Healthy になるまで待ってから Application を消す」としている。実測では、管理リソースが消えた 0.8 秒後に Job が送信し、その 2.5 秒後に Application が消えた（[run3](report.html#run3)）。hook が失敗すると、Application は `DeletionError` の状態で残る。つまり「送った」とは言えても、「消えた」とは言えない。

**デプロイ完了: 取れる。** PostSync は Healthy になった後に実行された（Healthy の 1.3 秒後）。ただし sync のたびに実行され、重複を除く仕組みは無い。

**検知層の耐障害性: ◎。** 実行するのは application-controller 自身なので、通知専用の部品が無い。ほかの通知系を全部止めた [run5](report.html#run5) でも、PostDelete hook だけは送った。

**配送層の回復性: △。** 再試行は Job の `backoffLimit` と、コンテナ内の実装（今回は `curl --retry 5`）に頼る。DLQ は無い。

**配送保証: △。** Job が成功するまで Argo CD が待つので、削除時は at-least-once になる。PostSync は sync のたびに走るため、重複する。

**可用性: ×。** hook が失敗し続けると、Application の削除がそこで詰まる。送信先が落ちていると、削除ができなくなる。

**疎結合: ×。** hook は各アプリのマニフェストに入る。送信先を変えるには、全アプリのマニフェストを変えることになる。

**スケーラビリティ: ×。** ファンアウトは Job の中に自分で書く。

**可観測性: △。** Job の中で OTel SDK を使えば出せる。Argo CD から trace context は渡されない。

**セキュリティ・権限分離: △。** 分離はできるが、資格情報がアプリごとに散らばる。通知の偽装も防げない。

**運用負荷: △。** 部品は増えないが、全アプリに Job を書くことになる。

**レイテンシ: △。** 管理リソースの消滅から 0.8 秒で送信。Application の消滅は、その 2.5 秒後。
