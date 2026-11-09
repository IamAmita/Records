# AWS WAF の IP セット

調査日：2026-11-09
きっかけ：（未記入）

## 結論

- IP セットは、IP アドレスと CIDR の一覧を Web ACL とは別のリソースとして持っておき、ルールの IP セット一致ステートメント（`IPSetReferenceStatement`）から参照するもの。1つの IP セットを複数のルール・Web ACL で使い回せる
- 1つのセットに入れるのは IPv4 か IPv6 のどちらか一方で、最大 10,000 件（引き上げ不可）。`/0` 以外の CIDR はすべて使える
- CloudFront 用は Scope を `CLOUDFRONT` にして us-east-1（バージニア北部）で作る。ALB・API Gateway など用は `REGIONAL` にして、守るリソースと同じリージョンで作る
- `UpdateIPSet` はアドレス一覧を丸ごと置き換える（追記ではない）。`GetIPSet` で取った `LockToken` を付けて送る
- コンソールは「AWS WAF & Shield」とまとまっているが、IP セットは WAF の機能。Shield Advanced と IP セットの関係はドキュメントに見当たらない

## 調べたこと

### 基本

- 先に IP セットを作り、ルールの IP セット一致ステートメントで参照する。IP セットを変えると、参照しているすべてのルールに反映される
- WCU（Web ACL の容量単位）は 1。転送 IP の位置（下記）を `ANY` にすると 4 増える。アドレスの件数で WCU が変わるという記載はない
- 名前は作ったあとで変えられない
- 新しいコンソールでは、Web ACL を「protection pack (web ACL)」と呼ぶ。中身は Web ACL と同じ。IP 一致ルールを足す画面から、その場で IP セットを作れる。API と従来のコンソールでは Web ACL のまま

### Scope とリージョン

| Scope | 使う先 | 作るリージョン |
| --- | --- | --- |
| `REGIONAL` | ALB、API Gateway など（リージョンのリソース） | 守るリソースと同じリージョン |
| `CLOUDFRONT` | CloudFront（コンソールでは「Global (CloudFront)」） | us-east-1 |

- `REGIONAL` の IP セットは、リージョンのリソースを守る Web ACL でしか使えない。逆も同じ
- CLI で CloudFront 用を扱うときは `--scope CLOUDFRONT --region us-east-1`。API・SDK でも、すべての呼び出しを us-east-1 のエンドポイントに送る

### IPv4 と IPv6

- 作るときに `IPAddressVersion` を `IPV4` か `IPV6` のどちらか1つ指定する。混ぜてよいかの明文はないが、指定は1つだけなので、両方を扱うならセットを2つ作り、ルールで OR にする
- CIDR は `/0` 以外すべて使える（例：`192.0.2.44/32`、`192.0.2.0/24`、`1111:0000:0000:0000:0000:0000:0000:0111/128`、`1111:0:0:0:0:0:0:0/64`）

### 上限

| 項目 | 値 | 引き上げ |
| --- | --- | --- |
| IP セットの数（アカウント・リージョンごと） | 100 | 申請できる |
| 1つの IP セットに入れる CIDR の数 | 10,000 | できない |

- アドレス1件の文字列は最大 50 文字
- 上限はリージョンごとに別々に数える

### 更新

- `UpdateIPSet` は、いま入っている一覧を送った一覧で丸ごと置き換える。1件だけ足したいときも、`GetIPSet` で今の一覧を取り、足した一覧を全部送る。空の一覧 `[]` も送れる
- 楽観的ロックがある。`GetIPSet`（または `List`）の応答の `LockToken` を付けて送り、成功すると次に使う `NextLockToken` が返る。取ってから送るまでのあいだに誰かが変えていると `WAFOptimisticLockException` になるので、取り直して送り直す

```sh
# 今の一覧と LockToken を取る
aws wafv2 get-ip-set --name 名前 --scope REGIONAL --id ID --region ap-northeast-1

# 一覧を丸ごと送る（書かなかったアドレスは消える）
aws wafv2 update-ip-set --name 名前 --scope REGIONAL --id ID \
  --addresses 192.0.2.0/24 198.51.100.10/32 \
  --lock-token 取ったLockToken --region ap-northeast-1
```

- 反映には数秒から数分かかる。そのあいだは、足したアドレスが、ある場所ではブロックされ、別の場所ではまだ通る、ということが起こりうる

### 転送 IP（X-Forwarded-For など）

ふつうはリクエストの送信元 IP（WAF をつけたリソースに直接つないできた相手）を見る。手前にプロキシや別の CDN があると、送信元はそのプロキシになる。CloudFront の後ろの ALB に WAF をつけた場合も、送信元は CloudFront になる。そういうときは `IPSetForwardedIPConfig` で、ヘッダーに書かれた IP を見るようにできる。

| 項目 | 内容 |
| --- | --- |
| `HeaderName` | 見るヘッダー（例：`X-Forwarded-For`） |
| `FallbackBehavior` | ヘッダーの IP が正しい形でないとき、一致とみなす（`MATCH`）か、一致しないとみなす（`NO_MATCH`）か |
| `Position` | ヘッダーに IP が複数あるとき、どれを見るか。`FIRST`（先頭）、`LAST`（末尾）、`ANY`（全部。10個を超えたら末尾の10個） |

- ヘッダー自体がないリクエストには、ルールを適用しない。「許可リストにない IP をブロックする」（NOT で反転する）形で使うと、ヘッダーを付けずに来たリクエストはブロックされない可能性があるので、使う前に試す
- 一般的な話として、`X-Forwarded-For` はクライアントが自由に書けるので、先頭（`FIRST`）の値は偽装できる。許可リストに使うときは、信頼できるプロキシが付け足した位置を見る

### 削除

- ルールや Web ACL から参照されている IP セットは消せない（`WAFAssociatedItemException`）
- コンソールは使用中なら警告を出すが、まれに検出できないことがあると書かれている。消す前に、Web ACL とルールグループで使っていないか確かめる

### 料金（2026-11-09 時点）

- 料金ページの課金項目に IP セットはない。かかるのは、Web ACL（月 5 USD）、ルール（1つにつき月 1 USD。IP セットを参照するルールもこれに入る）、リクエスト（100 万件につき 0.60 USD）など

### Shield との関係

- コンソールは「AWS WAF & Shield」としてまとまっているが、IP セットは WAF のリソース。Shield Advanced のドキュメントに IP セットとの関係は見当たらない
- Shield Advanced に入っていると、AWS WAF の一部の利用料が契約に含まれる（料金ページ）

## 参考

- [Creating and managing an IP set](https://docs.aws.amazon.com/waf/latest/developerguide/waf-ip-set-managing.html)
- [IP set match rule statement](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-ipset-match.html)
- [AWS WAF quotas](https://docs.aws.amazon.com/waf/latest/developerguide/limits.html)
- [CreateIPSet（API）](https://docs.aws.amazon.com/waf/latest/APIReference/API_CreateIPSet.html)
- [UpdateIPSet（API）](https://docs.aws.amazon.com/waf/latest/APIReference/API_UpdateIPSet.html)
- [DeleteIPSet（API）](https://docs.aws.amazon.com/waf/latest/APIReference/API_DeleteIPSet.html)
- [IPSetForwardedIPConfig（API）](https://docs.aws.amazon.com/waf/latest/APIReference/API_IPSetForwardedIPConfig.html)
- [Introducing a new console experience for AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-testing.html)
- [AWS WAF Pricing](https://aws.amazon.com/waf/pricing/)
