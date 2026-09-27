# senior-dog-guide

「シニア犬のくらし手帖」の公開Webサイトです。テーマは「シニア犬 × 日常生活を楽にする用品」。

## 概要

シニア犬との暮らしで感じやすい日常の困りごと(滑り対策・段差対策・ベッド・食事補助・日常ケアなど)について、情報や用品選びの考え方を紹介する情報サイトです。

## 技術構成

- 完全静的サイト(HTML / CSS)。V1ではJavaScriptは未使用です。
- フレームワーク(React/Next.js等)は使用していません。
- 外部フォント・外部JSライブラリは使用していません。
- Cloudflare Pages でビルド不要のままデプロイできる構成です。

## ディレクトリ構成

```
/
├── index.html                          # トップページ
├── articles/
│   ├── index.html                      # 全記事一覧(HTML sitemap、カテゴリ別)
│   └── slip-prevention/index.html      # 記事: シニア犬の滑り対策
├── category/
│   └── mobility-support/index.html     # カテゴリページ(自動生成)
├── about/index.html                    # 運営者情報
├── privacy/index.html                  # プライバシーポリシー
├── disclosure/index.html               # 広告・アフィリエイトについて
├── 404.html
├── assets/css/style.css
├── robots.txt
├── sitemap.xml
├── _headers                            # Cloudflare Pages用セキュリティヘッダー
└── README.md
```

## 新しい記事を公開するとき(正式な公開手順)

STEP 12Cで、GoogleがSearch Consoleの手動「インデックス登録をリクエスト」に依存せず記事を自動発見できるよう、通常のHTML内部リンクによる発見経路(カテゴリページ・関連記事・HTML全記事一覧・パンくず)を追加した。これらはすべて `scripts/generate_site.py` が自動生成するため、新しい記事を公開するたびに以下の手順を踏むことが**必須**になる。

1. `articles/<slug>/index.html` を作成する(タイトルは `<title>記事タイトル | シニア犬のくらし手帖</title>` の形式にする)。既存記事(例: `articles/dog-diaper/index.html`)を複製して書き換えるのが安全(ヘッダーnav・フッター・見出し構造が既にテンプレート通りになる)。
2. `scripts/generate_site.py` の `ARTICLE_CATEGORIES` に、この記事のslugと分類先カテゴリキー(`CATEGORIES` の既存キーのいずれか)を1行追加する。**この手順を忘れると次のステップでスクリプトがエラーで停止する**(未分類の記事を黙って見落とさない、fail-closedな設計)。既存の6カテゴリに自然に当てはまらない全く新しいテーマの場合のみ、`CATEGORIES` に新しいカテゴリを追加してよい。
3. 以下を実行する。

   ```
   python3 scripts/generate_site.py
   ```

   これにより、以下がすべて自動的に同期される。
   - `sitemap.xml`(新記事・新カテゴリページ・HTML全記事一覧を含む)
   - `index.html` の「記事一覧」(`AUTO-GENERATED:ARTICLES` マーカー)と「テーマ一覧」カテゴリカード(`AUTO-GENERATED:CATEGORIES` マーカー)
   - `category/<key>/index.html`(カテゴリページ、全文自動生成)
   - `articles/index.html`(全記事一覧、カテゴリ別、全文自動生成)
   - 各記事のパンくず(`AUTO-GENERATED:BREADCRUMB` マーカー)・関連記事(`AUTO-GENERATED:RELATED` マーカー)・BreadcrumbList JSON-LD(`AUTO-GENERATED:JSONLD` マーカー) -- これらのマーカーが記事にまだ無い場合(初回移行時、または手動で書いた新しい記事ファイルにまだ無い場合)は、既存のテンプレート構造(`<article class="article-body"><div class="container">` の開始位置・`</div></article></main>` の終了位置・`</head>`)を目印に自動で挿入される。

   `<lastmod>` は各ページを最後に変更した実際のgitコミット日(未コミットの新規/変更ファイルは当日の日付)から生成され、変更されていないページの日付が無意味に「今日」へ書き換えられることはない。
4. `git diff` で意図した変更のみになっていることを確認してからコミットする。

### 生成物が最新か確認する(`--check`)

```
python3 scripts/generate_site.py --check
```

書き換えは行わず、「最新かどうか」だけを確認し、古い場合は非ゼロで終了する。**現時点でこのリポジトリにはCIが無いため、コミット前に手動でこのコマンドを実行することが、生成漏れ(新しい記事を追加したのに `generate_site.py` を実行し忘れる事故)を防ぐ唯一の手段になっている。** 将来CI(GitHub Actions等)を導入する場合は、この `--check` コマンドをそのままジョブに追加すればよい(新たな仕組みを作る必要はない)。

`.git/hooks/pre-commit` はclone時に共有されないため、恒久的な防止策としては使わない。上記の手動実行手順を必ず踏むこと。

自動生成の対象外(そのまま手動運用):
- `robots.txt` (滅多に変わらない固定ファイル)
- `about/` `privacy/` `disclosure/` 以外の新しい固定ページを追加する場合は `scripts/generate_site.py` の `STATIC_PAGES_AFTER_ARTICLES` に手動で1行追加する
- 記事のカテゴリ分類そのもの(`ARTICLE_CATEGORIES` への1行追加、上記手順2)

## ローカルでの確認方法

このリポジトリのルートで以下を実行すると、ローカルで表示を確認できます。

```
python3 -m http.server 8000
```

ブラウザで `http://localhost:8000/` を開いて確認してください。

## Publicリポジトリとしての注意

本リポジトリは Public です。以下は絶対に含めないでください。

- APIキー、`.env`、secrets
- 個人情報
- 認証情報・アカウント情報

## 公開URL取得後のTODO

- [x] Cloudflare Pages で公開URL(`*.pages.dev` または独自ドメイン)を取得
      → `https://senior-dog-guide.pages.dev/`
- [x] `sitemap.xml` を実際の公開URLへ更新
- [x] `robots.txt` の `Sitemap:` 行を有効化
- [x] 全ページへ `canonical` URLを追加
- [x] 必要に応じて `og:url` を追加
- [ ] 実画像を用意した場合のみ `og:image` を追加
- [ ] 問い合わせ先が確定した場合のみ `about/index.html` へ追加
- [ ] 独自ドメインを使用する場合は、上記URLを独自ドメインへ再度更新
