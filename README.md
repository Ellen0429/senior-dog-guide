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

- [ ] Cloudflare Pages で公開URL(`*.pages.dev` または独自ドメイン)を取得
- [ ] `sitemap.xml` を実際の公開URLへ更新
- [ ] `robots.txt` の `Sitemap:` 行を有効化
- [ ] 全ページへ `canonical` URLを追加
- [ ] 必要に応じて `og:url` を追加
- [ ] 実画像を用意した場合のみ `og:image` を追加
- [ ] 問い合わせ先が確定した場合のみ `about/index.html` へ追加
