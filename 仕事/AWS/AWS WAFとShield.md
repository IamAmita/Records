# AWS WAF と Shield

調査日：2026-11-09
きっかけ：（未記入）

## 結論

- **WAF**：HTTP/HTTPS のリクエスト（L7）を、ルールに従って通す・止める。守るリソースに Web ACL を付けて使い、使った分だけ課金される
- **Shield Standard**：L3/L4 の DDoS（SYN フラッド、UDP リフレクションなど）への対策。すべての AWS 利用者に、設定なし・無料で効いている
- **Shield Advanced**：有料（月 3,000 USD、1年契約、Organizations なら組織で1契約）。L3/L4 に加えて L7 の DDoS も対象。専門チーム（SRT）への相談、DDoS で増えた料金の補償、守るリソースの WAF 料金の一部込み、など
- ふつうの Web アプリなら、WAF を自分で設定し、L3/L4 は Shield Standard に任せる形から始める。大きな DDoS を受けたときの支援や料金の補償が必要なら Shield Advanced を検討する
- Shield Advanced の L7 自動緩和は 2027-01-29 にサポートが終わり、WAF の Anti-DDoS マネージドルールグループに置き換わる（下記）

## 調べたこと

### 3つの違い

| | WAF | Shield Standard | Shield Advanced |
| --- | --- | --- | --- |
| 防ぐもの | L7 の攻撃全般（SQL インジェクション、XSS、不正なボット、特定の IP など） | L3/L4 の DDoS | L3/L4 と L7 の DDoS、大量のボット、脆弱性を狙う試行 |
| 守る対象 | CloudFront、ALB、API Gateway など（下記） | AWS の入り口全般（特に Route 53、CloudFront、Global Accelerator） | 申し込んで指定したリソース（下記） |
| 料金 | 従量（Web ACL・ルール・リクエスト） | 無料 | 月 3,000 USD ＋ データ転送量 |
| 設定 | 自分でルールを書く | 不要（自動） | 守るリソースを指定する |

コンソールは「AWS WAF & Shield」としてまとまっていて、ドキュメントも1冊（WAF、Firewall Manager、Shield Advanced、Shield network security director）になっている。

### AWS WAF

#### 守れるリソース

- CloudFront ディストリビューション
- API Gateway の REST API
- Application Load Balancer（ECS のコンテナは ALB 経由で守る）
- AppSync の GraphQL API
- Cognito ユーザープール
- App Runner サービス
- Bedrock AgentCore Gateway
- Verified Access インスタンス
- Amplify

1つのリソースに付けられる Web ACL は1つだけ。CloudFront 用の Web ACL は us-east-1 に作り、ほかの種類のリソースには使えない。Amplify 用も CloudFront 側（グローバル）で作る。

#### しくみ

| 要素 | 内容 |
| --- | --- |
| Web ACL | ルールの集まり。リソースに付ける単位。新しいコンソールでは「protection pack (web ACL)」と呼ぶ |
| ルール | 条件とアクションの組。上から順に評価される |
| ルールグループ | ルールをまとめて使い回すもの。自分で作るか、マネージドルールグループ（AWS や AWS Marketplace の販売者が作ったもの）を使う |
| デフォルトアクション | どのルールにも当たらなかったときに、通すか止めるか |
| WCU | ルールの重さを表す単位。1つの Web ACL で 1,500 まで（超えると追加料金） |

- 条件に使えるもの：送信元 IP（[IP セット](AWS%20WAFのIPセット.md)）、国、ヘッダー、文字列・正規表現、リクエストの大きさ、SQL インジェクションや XSS らしさ、一定時間あたりのリクエスト数（レートベースルール）など
- アクション：Allow（通す）、Block（止める。403 か自分で決めた応答）、Count（何もせず数えるだけ。新しいルールを試すときに使う）、CAPTCHA、Challenge（ブラウザかどうかを裏で確かめる）

#### 有料のマネージドルール

| 名前 | 内容 |
| --- | --- |
| Bot Control | ボットを見分けて扱いを決める。一般的なボット向け（Common）と、狙ってくるボット向け（Targeted）がある |
| Fraud Control | ログイン画面への総当たり・使い回しパスワード攻撃（ATP）と、偽アカウントの大量作成（ACFP）を防ぐ |
| Anti-DDoS（`AWSManagedRulesAntiDDoSRuleSet`） | L7 の DDoS を見つけて抑える。2025年6月に出た。Shield Advanced に入っていなくても使える |

#### 料金（2026-11-09 時点）

| 項目 | 料金 |
| --- | --- |
| Web ACL | 1つにつき月 5 USD |
| ルール | 1つにつき月 1 USD（ルールグループやマネージドルールグループを1つ足すのも同じ） |
| リクエスト | 100 万件につき 0.60 USD |
| WCU が 1,500 を超えた分 | 500 WCU ごとに、100 万件につき 0.20 USD |
| CAPTCHA | 1,000 回につき 0.40 USD |
| Bot Control | Web ACL ごとに月 10 USD ＋ リクエスト料金（Common は月 1,000 万件、Targeted は月 100 万件まで無料） |
| Fraud Control | ATP・ACFP それぞれ Web ACL ごとに月 10 USD ＋ リクエスト料金 |

Allow・Block・Count のアクションには追加料金はない。

### Shield Standard

- すべての AWS 利用者が対象。申し込みも設定もいらず、無料
- よくある L3/L4 の DDoS（SYN フラッド、UDP リフレクションなど）から、AWS の入り口を守る
- Route 53 のホストゾーン、CloudFront、Global Accelerator の前に置くと効果が大きい

### Shield Advanced

#### 料金と契約

- 月 3,000 USD（料金ページの計算例）＋ 守るリソースからのデータ転送量（例：ALB は 1GB あたり 0.050 USD、CloudFront は 0.025 USD）
- 1年契約で、毎年自動で更新される。やめるときは更新日の 30 日前から 5 日前までに申し出る
- Organizations では支払いアカウントに請求され、一括請求の組織全体が1契約で対象になる

#### 守れるリソース

申し込んだだけでは守られない。守るリソースを1つずつ指定するか、Firewall Manager のポリシーで指定する。

- CloudFront ディストリビューション
- Route 53 のホストゾーン
- Global Accelerator（標準アクセラレーター）
- Elastic IP（EC2 インスタンスや NLB・CLB などは Elastic IP を通して守る）
- Application Load Balancer、Classic Load Balancer、Network Load Balancer

#### できること

- **SRT（Shield Response Team）**：攻撃を受けているときに、AWS の DDoS 専門チームに相談でき、対策を作ってもらえる。使うには、AWS サポートの Business か Enterprise の契約が要る
- **先回りの連絡（Proactive engagement）**：Route 53 のヘルスチェックを結び付けておくと、攻撃でヘルスチェックが失敗したときに SRT のほうから連絡してくる
- **ヘルスベースの検知**：Route 53 のヘルスチェックを使い、アプリの状態も見て攻撃を判断する
- **料金の補償**：DDoS で増えた料金（データ転送料を含む）を、クレジットで返してもらえる。1年契約を守っていることが条件
- **保護グループ**：複数のリソースをまとめて1つとして扱う
- **見える化**：攻撃の状況を、コンソール・API・CloudWatch で見られる
- **WAF 料金込み**：守るリソースに付けた Web ACL の基本料金（Web ACL・ルール・リクエスト。WCU 1,500 まで、月 500 億リクエストまで）が含まれる。Bot Control、CAPTCHA、Marketplace のルールなどは含まれない
- **Firewall Manager**：Shield Advanced のポリシーを Firewall Manager から配るのに、追加料金はかからない

### Shield Advanced の L7 自動緩和の終了

Shield Advanced には、L7 の DDoS を見つけると WAF のルールを自動で作って止める機能（L7 自動緩和）がある。これを WAF の Anti-DDoS マネージドルールグループに置き換える、と AWS のブログで発表された（2026-07-27。2026-09-14 に日程を延期）。

| | 今までの L7 自動緩和 | Anti-DDoS ルールグループ |
| --- | --- | --- |
| WCU | 150 | 50 |
| アクション | Block、Count | Block、Count、Challenge |
| 設定の単位 | リソースごと（Shield の API） | Web ACL ごと（WAF の API） |
| 感度 | なし | Low / Medium / High |

| 段階 | 時期 | 内容 |
| --- | --- | --- |
| 1 | 2026-07-27〜08-07 | Count で配置。メトリクスとラベルを無料で有効にした |
| 2 | 2026-07-27〜10-24 | 無料で試せる期間 |
| 3 | 2026-10-25〜 | 条件に合う Web ACL を AWS が自動で切り替え（今の Block/Count を引き継ぎ、感度は Low、Challenge は無効） |
| 4 | 〜2027-01-28 | 自動で切り替わらない Web ACL は、この期間に自分で移す |
| 5 | 2027-01-29 | L7 自動緩和のサポート終了（性能の更新と優先サポートがなくなる） |

- 自動で切り替わらないのは、Block と Count が混ざった Web ACL や、自動緩和を有効にしていないリソースを含む Web ACL など
- 自動で切り替わったあとも、Challenge・感度・対象の URI などは自分で調整する
- 2027-01-29 のあと、今までの機能が止まるのかどうかは、ブログにははっきり書かれていない

### 関連するサービス

- **Firewall Manager**：複数のアカウントにまたがって、WAF、Shield Advanced、セキュリティグループ、Network Firewall、Route 53 Resolver DNS Firewall の設定をまとめて配る。新しいアカウントやリソースにも自動で当てる
- **Shield network security director**：アカウント内のネットワーク構成を調べて、設定の弱いところを重要度つきで教えてくれる。2025年6月にプレビューで出たが、今のドキュメントでは「パブリックプレビューは終わり、コンソールは使えない」となっている。一般提供の時期は書かれていない

## 参考

- [What is AWS WAF?](https://docs.aws.amazon.com/waf/latest/developerguide/what-is-aws-waf.html)
- [Resources that you can protect with AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html)
- [AWS Shield Standard overview](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-standard-summary.html)
- [AWS Shield Advanced overview](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-summary.html)
- [Resources that Shield Advanced protects](https://docs.aws.amazon.com/waf/latest/developerguide/ddos-advanced-summary-protected-resources.html)
- [AWS Shield network security director](https://docs.aws.amazon.com/waf/latest/developerguide/nsd-chapter.html)
- [AWS WAF Pricing](https://aws.amazon.com/waf/pricing/)
- [AWS Shield Pricing](https://aws.amazon.com/shield/pricing/)
- [AWS Shield Advanced is embracing the AWS WAF Anti-DDoS managed rule group](https://aws.amazon.com/blogs/security/aws-shield-advanced-is-embracing-the-aws-waf-anti-ddos-managed-rule-group-what-changes-and-how-to-prepare/)
- [AWS Shield network security director findings are now available in AWS Security Hub](https://aws.amazon.com/about-aws/whats-new/2026/03/network-security-director-findings)
