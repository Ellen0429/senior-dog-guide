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
│   └── slip-prevention/index.html      # 記事: シニア犬の滑り対策
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

## 新しい記事を公開するとき

1. `articles/<slug>/index.html` を作成する(タイトルは `<title>記事タイトル | シニア犬のくらし手帖</title>` の形式にする)。
2. 必要であれば `index.html` の「テーマ一覧」カテゴリカードを追記する(意味的な分類なので手動判断のまま)。
3. 以下を実行する。

   ```
   python3 scripts/generate_site.py
   ```

   これにより、`articles/` 配下から新しい記事が自動検出され、`index.html` の「記事一覧」(`AUTO-GENERATED:ARTICLES` マーカーで囲まれた部分のみ)と `sitemap.xml` が自動的に更新される。`<lastmod>` は各ページを最後に変更した実際のgitコミット日(未コミットの新規/変更ファイルは当日の日付)から生成され、変更されていないページの日付が無意味に「今日」へ書き換えられることはない。
4. `git diff` で意図した変更のみになっていることを確認してからコミットする。

`--check` を付けて実行すると、書き換えは行わずに「最新かどうか」だけを確認できる(CI等向け)。

自動生成の対象外(そのまま手動運用):
- カテゴリカード(意味的な分類が必要なため)
- `robots.txt` (滅多に変わらない固定ファイル)
- `about/` `privacy/` `disclosure/` 以外の新しい固定ページを追加する場合は `scripts/generate_site.py` の `STATIC_PAGES_AFTER_ARTICLES` に手動で1行追加する

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
