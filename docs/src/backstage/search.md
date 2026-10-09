# 検索

> `@backstage/plugin-search` と `-backend` を、TechDocs の文書の画面のために載せる。索引は Pod のメモリ（Lunr）に持ち、カタログと TechDocs の 2 種類を集める。

<p class="eli5">TechDocs の本の画面には、最初から検索の窓が付いています。窓の向こうに索引係（検索の API）がいないと、本の画面そのものが開けません。そこで索引係を雇いました。索引係は案内所の机の上（Pod のメモリ）にカードを並べ、起動したときと 10 分ごとに作り直します。本の索引カードは「刷り上がった本」からしか作れないので、起動した直後はまだ本の索引がありません。そのとき上流の索引係は「索引が無い」と怒って（500 を返して）しまうので、home-k8s では「まだ 0 件です」と穏やかに答えるように手を入れました。</p>

<!-- archify: search.architecture -->

**図の読み方**

- ① 文書の画面（TechDocs のタブ・`/docs`）の検索欄が、② search-backend の `/api/search/query` に問い合わせる
- ③ 索引は Lunr でメモリに持ち、起動後と 10 分ごとに作り直す
- ④ カタログのエンティティと、⑤ build 済みの TechDocs の文書を索引に集める。起動直後は文書を build していないので、TechDocs の索引は無い
- ⑥ 索引の無い種類の問い合わせを、500 ではなく 0 件で返す（`searchEngine.ts`）

（色と線の読み方: 枠が Backstage のバックエンド。緑の線は主な流れ、破線は自前の置き換え。）

## 何を選び、なぜそうしたか

| 項目 | 選んだもの | 理由 |
|---|---|---|
| 載せる理由 | TechDocs の画面が要るから | 文書の画面（TechDocs のタブと `/docs`）は検索欄を出し、検索の API が無いと開けない |
| 索引の置き場 | Lunr（メモリ） | 外の検索エンジン（Elasticsearch など）を立てずに Pod の中で完結する。索引は起動後と 10 分ごとに作り直すので、Pod を作り直して消えても困らない |
| 集める種類 | カタログと TechDocs | 索引を作るモジュールは `module-catalog` と `module-techdocs` の 2 つだけを載せる |
| 索引の無い種類 | 0 件で返す | 上流の Lunr は 0 件の種類の索引を作らず、その種類の問い合わせで `MissingIndexError` を投げ、search-backend が 500 を返す。起動直後（最初に文書を開いてから最大 10 分）は TechDocs の索引が無いので、文書の画面の検索が 500 になる |

## セットアップの項目

### パッケージと版

| パッケージ | 版 | 置き場所 |
|---|---|---|
| `@backstage/plugin-search` | 1.7.8（`/alpha`） | `backstage/packages/app` |
| `@backstage/plugin-search-backend` | 2.1.7 | `backstage/packages/backend` |
| `@backstage/plugin-search-backend-node` | 1.4.8 | 同上（`LunrSearchEngine`） |
| `@backstage/plugin-search-backend-module-catalog` | 0.3.19 | 同上 |
| `@backstage/plugin-search-backend-module-techdocs` | 0.4.18 | 同上 |

[`packages/backend/src/index.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/backend/src/index.ts) の載せ方。

```ts
backend.add(import('@backstage/plugin-search-backend'));
// まだ索引の無い種類の検索 (起動直後の techdocs) を 500 でなく 0 件で返す (searchEngine.ts)
backend.add(searchModuleEmptyOnMissingIndex);
backend.add(import('@backstage/plugin-search-backend-module-catalog'));
backend.add(import('@backstage/plugin-search-backend-module-techdocs'));
```

`searchModuleEmptyOnMissingIndex` は [`searchEngine.ts`](https://github.com/yamakura-yuma/home-k8s/blob/main/backstage/packages/backend/src/searchEngine.ts) にある。`LunrSearchEngine` を継いだ `EmptyOnMissingIndexLunrSearchEngine` が、`query` で `MissingIndexError` を受けたら 0 件を返す。

### app-config

無し。索引の作り直しの間隔（10 分）は既定のまま。

### エンティティの注釈

無し。TechDocs の索引に入るのは、`backstage.io/techdocs-ref` を持ち、build 済みの文書だけ（[TechDocs](techdocs.md)）。

### Secret・資格情報

無し。

### バックエンドのプロキシ

無し。search-backend が自分の API（`/api/search/query`）で答える。共有（`just share`）の caddy は `/api/search/query` の GET を通す。

### chart の values・ArgoCD の Application

無し。

### kind のポート

無し（Backstage の 7007 だけ）。

### 確認の方法

```sh
tok=$(curl -s -X POST http://localhost:7007/api/auth/guest/refresh | jq -r .backstageIdentity.token)
curl -s -H "Authorization: Bearer $tok" 'http://localhost:7007/api/search/query?term=backstage&types%5B0%5D=techdocs' -o /dev/null -w '%{http_code}\n'   # 200 (起動直後でも 500 にならない)
```

画面では、TechDocs の文書を開いて検索欄が出ることを見る。文書を開いてから最大 10 分後の作り直しのあとは、その文書の中身が検索に出る。

## 詳しい手順

- [docs/cluster/backstage.md](https://github.com/yamakura-yuma/home-k8s/blob/main/docs/cluster/backstage.md) の「TechDocs」（検索の箇条）
