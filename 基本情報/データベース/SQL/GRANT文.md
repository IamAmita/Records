SQLの`GRANT`文は、**ユーザやロールに権限を与える命令**のこと。

基本情報技術者試験では、データベースのアクセス権限管理としてよく出る。

---

## 基本形

```sql
GRANT 権限
ON 対象
TO ユーザ名;
```

例

```sql
GRANT SELECT
ON 社員表
TO user1;
```

これは、`user1`に対して`社員表`を参照する権限を与えるという意味。

---

## 代表的な権限

| 権限 | 意味 |
| --- | --- |
| `SELECT` | 表を検索・参照できる |
| `INSERT` | 行を追加できる |
| `UPDATE` | データを更新できる |
| `DELETE` | 行を削除できる |
| `ALL PRIVILEGES` | すべての権限を与える |

複数の権限をまとめて与えることもできる。

```sql
GRANT SELECT, INSERT
ON 商品表
TO user2;
```

これは、`user2`に`商品表`の参照と追加を許可するという意味。

---

## 権限を取り消す場合

`GRANT`の反対は`REVOKE`。

```sql
REVOKE SELECT
ON 社員表
FROM user1;
```

これは、`user1`から`社員表`の参照権限を取り消すという意味。

---

## WITH GRANT OPTION

```sql
GRANT SELECT
ON 社員表
TO user1
WITH GRANT OPTION;
```

`WITH GRANT OPTION`が付くと、`user1`は自分がもらった権限を**他のユーザにも与えられる**ようになる。

つまり、

```text
管理者
  ↓ GRANT SELECT WITH GRANT OPTION
user1
  ↓ GRANT SELECT
user2
```

のように、権限をさらに渡せる。

---

## 試験でのポイント

| SQL | 意味 |
| --- | --- |
| `GRANT` | 権限を与える |
| `REVOKE` | 権限を取り消す |
| `WITH GRANT OPTION` | もらった権限を他人にも与えられる |

かなり短く覚えるなら、

> **GRANTは権限付与、REVOKEは権限取消。WITH GRANT OPTIONがあると、権限を再付与できる。**

でOK。
