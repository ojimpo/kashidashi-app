# kashidashi — 図書館貸出資料管理アプリ

図書館で借りた CD・本・DVD を記録・管理するセルフホスト型 Web アプリです。

---

## 背景

葛飾区立図書館をよく使うのですが、「いつ何を借りたか」「CD はリッピングしたか」「返却期限はいつか」を手元で一元管理したくなりました。図書館の Web サイト自体にも貸出履歴は表示されますが、種別やリッピング状況でフィルタしたり、外部ツールと連携したりするのには不十分です。

そこで作ったのが **kashidashi**（「貸出し」から）です。

---

## 設計思想：アプリはデータストアとビューに徹する

kashidashi 自体はシンプルな REST API と Web UI だけを持ちます。情報の取得・リッピング連携・リマインダー通知といったロジックは **外部のエージェントやスクリプト** に任せ、アプリは「データを受け取って保存する」「データを返す」「見せる」ことだけに集中します。

このおかげで、

- 人間が UI から操作するのも
- AI エージェントが API を叩くのも

同じインターフェースで動きます。

---

## OpenClaw との連携

**[OpenClaw](https://github.com/openclaw/openclaw)** は、ローカルで動作するパーソナル AI アシスタントです。WhatsApp や Telegram などのメッセージングプラットフォームとの統合、ブラウザ自動化、クロンジョブなど幅広い自動化機能を持っています。kashidashi はその自動化機能を借りて、図書館との連携を実現しています。

### 新規貸出の自動登録

1. OpenClaw が図書館のマイページにログインして貸出情報を取得
2. 資料の詳細ページから種別（CD / 本 / DVD）・タイトル・著者 / アーティスト・貸出日・返却期限を取得
3. `POST /api/items` で kashidashi に登録（重複チェックあり）

資格情報は 1Password に保管しており、OpenClaw がそこから取得します。

### CD リッピングとの自動紐づけ

1. CD を借りたら手元でリッピング（FLACに変換）し、MusicBrainz 等のメタデータを埋め込む
2. NAS 上のリッピング履歴（`meta.json`）をスキャンして、借りた CD と照合
3. タイトル・アーティストのファジーマッチ + 貸出日からの時間窓で対応する CD を特定
4. `PATCH /api/items/{id}` でリッピング完了日時と MusicBrainz Release ID を記録

### 変更検知と通知

定期実行スクリプトが図書館の貸出状況を巡回し、前回と差分があれば OpenClaw に通知します。OpenClaw はその通知をトリガーに「新しく借りた資料がある」「返却期限が近い」などのアクションを取ります。

---

## 機能

- 貸出資料の登録・一覧・詳細・更新・削除（REST API）
- 種別（CD / 本 / DVD）、ステータス（未返却 / 返却済 / 未リッピング / リッピング済）でのフィルタ
- テーブル表示・タイル（ジャケット画像）表示
- FastAPI の `/docs` で Swagger UI を提供（人間にも AI エージェントにも読みやすい API ドキュメント）

---

## 技術スタック

| | |
|---|---|
| バックエンド | Python / FastAPI |
| DB | SQLite（WAL モード） |
| フロントエンド | バニラ JS（フレームワークなし） |
| インフラ | Docker、自宅 NAS（arigato-nas）上で稼働 |
| ネットワーク | Tailscale + Cloudflare Tunnel |

---

## ローカルでの起動

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

KASHIDASHI_DATABASE_URL=sqlite:///./data/dev.db uvicorn app.main:app --reload --port 18080
```

または Docker Compose で：

```bash
docker compose up
```

API ドキュメントは `http://localhost:18080/docs` で確認できます。

---

## 将来の展望

- **Last.fm との連携**：リッピング済み CD の `musicbrainz_release_id` をキーに Last.fm のスクロブルデータと紐づけ、「借りた CD を何回聴いたか」を追跡する
- **読書管理との連携**：`isbn` をキーに外部の読書管理サービスと連携する
- **返却期限リマインダー**：OpenClaw が期限を取得して通知する
- **他の図書館への対応**：`library` フィールドで複数館を管理できる設計になっている

---

## ライセンス

個人利用・参考用途に公開しています。
