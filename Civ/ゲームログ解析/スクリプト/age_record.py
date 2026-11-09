# Civ7 の Logs から、1つの時代の出来事を、指定したプレイヤーについてターンごとの Markdown に書き出す。
# 使い方: python age_record.py <Logsフォルダ> <出力.md> [--player 0] [--segment -1] [--game <Civ7のインストール先>]
#   --segment: Game_Gossip.csv をターンが戻る位置で区切ったときに、何番目の区切りを使うか（-1 が最新、-2 がその前）
# DiplomacyDeals.log はターンだけでは時代やゲームの区切りが決まらないので使わない（宣戦と講和は Gossip から拾う）。
import argparse, collections, glob, os, re

ap = argparse.ArgumentParser()
ap.add_argument('logs')
ap.add_argument('out')
ap.add_argument('--player', default='0')
ap.add_argument('--segment', type=int, default=-1)
ap.add_argument('--game', default=r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VII")
args = ap.parse_args()
pid = args.player


def read(name):
    with open(os.path.join(args.logs, name), encoding='utf-8', errors='replace') as f:
        return f.read().splitlines()


def cells(line, sep=','):
    return [x.strip() for x in line.split(sep)]


def int0(s):
    try:
        return int(str(s).strip())
    except ValueError:
        return None


def num(s):
    try:
        return str(int(round(float(s))))
    except ValueError:
        return s


def segments(rows, turn_of):
    # ゲームの読み込みや時代の移行でターンが戻るので、そこで区切る
    out, cur, prev = [], [], None
    for r in rows:
        t = turn_of(r)
        if t is None:
            continue
        if prev is not None and t < prev:
            out.append(cur)
            cur = []
        cur.append(r)
        prev = t
    if cur:
        out.append(cur)
    return out


SEGS = segments([cells(l) for l in read('Game_Gossip.csv')[1:]], lambda p: int0(p[0]))
gi = args.segment % len(SEGS)
G = SEGS[gi]
first_turn, last_turn = int0(G[0][0]), int0(G[-1][0])


def first_cities(seg):
    return {(int(p[3]), int(p[4])): (p[1], p[2]) for p in seg
            if p[5] == 'GOSSIP_FOUND_CITY' and p[-1] == 'PlayerCount=1' and int0(p[0]) <= 3}


# 2つ目以降の時代は最初の都市を建てないので、このゲームの最初の時代の区切りまでさかのぼる
gk = gi
while gk > 0 and not first_cities(SEGS[gk]):
    gk -= 1
GAME = [p for s in SEGS[gk:gi + 1] for p in s]


def same_age(rows, turn_of):
    # ほかのログでは、最後のターンが Gossip の最後のターンに近い、いちばん新しい区切りを同じ時代とみなす
    for s in reversed(segments(rows, turn_of)):
        if last_turn - 5 <= turn_of(s[-1]) <= last_turn:
            return s
    return []


# ゲーム本体の日本語テキスト
tags = {}
for fn in sorted(glob.glob(os.path.join(args.game, 'Base', 'modules', '*', 'l10n', 'ja_JP_Text.xml'))) + \
        sorted(glob.glob(os.path.join(args.game, 'DLC', '*', 'modules', 'l10n', 'ja_JP_Text.xml'))):
    with open(fn, encoding='utf-8') as f:
        for k, v in re.findall(r'<Replace Tag="([^"]+)" Language="ja_JP">\s*<Text>(.*?)</Text>', f.read(), re.S):
            tags.setdefault(k, v.strip())


def clean(text):
    text = re.sub(r'\[[^\]]*\]', '', text)
    text = re.sub(r'\{\d+_[Hh]omeland_[Ii]ndependent\}', '〈独立勢力〉', text)
    text = re.sub(r'\{\d+_[Cc]apital\}', '〈首都〉', text)
    text = re.sub(r'\{\d+_(child_)?reward\}', '〈報酬〉', text)
    return re.sub(r'\{[^}]*\}', '〈…〉', text)


SPECIAL = {'ORDER_TOWN_UPGRADE': '町から都市への昇格'}


def item_name(code):
    if code in SPECIAL:
        return SPECIAL[code]
    m = re.match(r'LEGACY_(AQ|EX|MO)_(\w+)_CRISIS_(\d+)$', code)
    if m:
        age = {'AQ': 'ANTIQUITY', 'EX': 'EXPLORATION', 'MO': 'MODERN'}[m.group(1)]
        return f"{tags.get(f'LOC_{age}_{m.group(2)}_CRISIS_NAME', code)}（{m.group(3)}）"
    if code.startswith('LOC_'):
        return clean(tags.get(code, code))
    # 資源の上に造る改善（IMPROVEMENT_FISHING_BOAT_RESOURCE など）は資源なしの名前で、
    # 上位のユニット（UNIT_YUMI_2 など）は数字なしの名前で引く
    for c in (code, re.sub(r'_RESOURCE$', '', code), re.sub(r'_\d+$', '', code)):
        if f'LOC_{c}_NAME' in tags:
            return clean(tags[f'LOC_{c}_NAME'])
    return code


def loc_words(text):
    # 文中の LOC_ タグを和名にする（行動名は _NAME がなく _PROJECT_NAME だけのものがある）
    return re.sub(r'LOC_\w+', lambda m: tags.get(m.group(0), tags.get(m.group(0).replace('_NAME', '_PROJECT_NAME'), m.group(0))), text)


def city_name(code):
    m = re.search(r';(.+?);', code)
    return m.group(1) if m else item_name(code)


# 文明：AdvancedStart の開始位置と、T1〜T3 に建てた最初の都市の座標を、近いものどうしで突き合わせる
leader_civ = {}
for p in GAME:
    if p[2] and p[2] != '村':
        leader_civ.setdefault(p[1], p[2])
capitals = first_cities(SEGS[gk])
blocks = []
for p in (cells(l) for l in read('AdvancedStart.csv')[1:]):
    m = re.search(r'\((\d+)-(\d+)\)', p[2]) if len(p) > 2 else None
    if not m:
        continue
    if p[1] == '0':
        blocks.append({})
    if blocks:
        blocks[-1][p[1]] = (int(m.group(1)), int(m.group(2)))


def d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def assign(block):
    out = {}
    for i, xy in block.items():
        near = min(capitals, key=lambda c: d2(c, xy), default=None)
        if near is not None and d2(near, xy) <= 9:
            out[i] = capitals[near]
    return out


majors = max((assign(b) for b in reversed(blocks)), key=len)
me = majors[pid]
# 時代ごとに文明が変わることがあるので（平安日本→戦国日本など）、行は指導者の名前で見分け、
# 文明の名前はこの時代の区切りに出てくるものを使う
age_civ = {}
for p in G:
    if p[2] and p[2] != '村':
        age_civ.setdefault(p[1], p[2])


def is_me(leader, civ):
    return leader == me[0] and civ != '村'

# 独立勢力：Independents.csv の CREATE TRIBE（番号・種類・座標）
tribes = []
for p in same_age([cells(l, ', ') for l in read('Independents.csv')[1:]], lambda p: int0(p[0])):
    m = re.match(r'CREATE TRIBE (\d+)$', p[2]) if len(p) > 3 else None
    if m:
        x, y = p[3].split()
        n = re.sub(r'^INDEPENDENT_', '', p[1])
        tribes.append(dict(turn=int0(p[0]), id=m.group(1), x=int(x), y=int(y),
                           major=tags.get(f'LOC_INDEPENDENT_{n}_MAJOR_NAME', p[1]),
                           minor=tags.get(f'LOC_INDEPENDENT_{n}_MINOR_NAME', '')))


def tribe_label(t):
    return f"{t['major']}（{t['minor']}）" if t['minor'] else t['major']


def civ_label(leader, civ):
    return f'{civ}／{leader}'


def who(i, turn):
    if i == pid:
        return '自国'
    if i in majors:
        return leader_label(majors[i][0])
    cands = [t for t in tribes if t['id'] == i and t['turn'] <= turn]
    return tribe_label(cands[-1]) if cands else f'プレイヤー{i}'


def leader_label(leader):
    civ = age_civ.get(leader) or leader_civ.get(leader)
    return civ_label(leader, civ) if civ else leader


def nearest_tribe(x, y, turn):
    cands = [t for t in tribes if t['turn'] <= turn]
    if not cands:
        return None
    t = min(cands, key=lambda t: d2((t['x'], t['y']), (x, y)))
    return t if d2((t['x'], t['y']), (x, y)) <= 9 else None


ev = collections.defaultdict(list)


def add(turn, text):
    if text not in ev[turn]:
        ev[turn].append(text)


def kv(rest):
    return dict(x.split('=', 1) for x in rest if '=' in x)


# --- Gossip（出来事の中心）
my_cities = {(p[3], p[4]): p[6] for p in GAME if p[5] == 'GOSSIP_FOUND_CITY' and is_me(p[1], p[2])}
# 時代が変わると、前の時代の都市と同じ名前の都市を建てることがある（鎌倉が2つなど）。
# 名前が重なる都市には、建てた大陸の名前を付けて見分ける
city_cont = {(p[3], p[4]): p[8] for p in GAME if p[5] == 'GOSSIP_FOUND_CITY' and is_me(p[1], p[2])}
dup_names = {n for n, k in collections.Counter(my_cities.values()).items() if k > 1}
my_cities = {xy: f'{n}（{city_cont[xy]}）' if n in dup_names else n for xy, n in my_cities.items()}


def tag_city(name, x, y):
    if name not in dup_names or int0(x) < 0:
        return name
    xy = (int0(x), int0(y))
    c = min((c for c, n in city_cont.items() if my_cities[c].startswith(name + '（')),
            key=lambda c: d2((int(c[0]), int(c[1])), xy))
    return my_cities[c]


all_cities = {(p[3], p[4]): (p[6], p[1], p[2]) for p in GAME if p[5] == 'GOSSIP_FOUND_CITY'}


def city_at(x, y):
    # 改宗させた都市など。独立勢力から都市国家になった居住地は、文明名が「村」になっている
    if (x, y) not in all_cities:
        return f'({x},{y})'
    name, leader, civ = all_cities[(x, y)]
    if is_me(leader, civ):
        return my_cities.get((x, y), name)
    return f'{name}（{leader_label(leader) if civ != "村" else civ + "の都市国家"}）'
wonders = {p[6] for p in G if p[5] == 'GOSSIP_WONDER_STARTED'}
founded, wonder_done, meets, suzerains, celebrations = [], [], [], [], []
pop = collections.defaultdict(list)
damaged = collections.Counter()
SKIP = {'GOSSIP_INDEPENDENT_INFLUENCE', 'GOSSIP_TRIGGER_DISCOVERY', 'GOSSIP_DIPLOMACY_RESPONSE',
        'GOSSIP_RELATIONSHIP_CHANGED', 'GOSSIP_DIPLOMACY_ACTION_STARTED'}
met_today = set()
lost_races = set()
before_age = GAME[:len(GAME) - len(G)]


def former_city(x, y, turn):
    # 焼き払った・残した都市の名前と、自国が奪う前の持ち主。名前はその座標で最後に名前が出た行から、
    # 持ち主は建設・人口・占領の行のうち最後の他国の行から引く（都市は何度も持ち主が変わることがある）
    name = owner = None
    for q in before_age + [q for q in G if int0(q[0]) <= turn]:
        if (q[3], q[4]) != (x, y) or is_me(q[1], q[2]):
            continue
        if q[5] in ('GOSSIP_FOUND_CITY', 'GOSSIP_CITY_POPULATION_HEIGHT_CHANGED') and q[6]:
            name, owner = q[6], q
        elif q[5] in ('GOSSIP_CONQUER_CITY', 'GOSSIP_URBAN_CONTROL_CHANGED', 'GOSSIP_OCCUPY_CITY'):
            owner = q
    if not name:
        return f'({x},{y}) の都市'
    return f"{name}（{'都市国家' if owner[2] == '村' else leader_label(owner[1])}）"


def near_city(x, y):
    # ユニットは都市の隣のタイルに出ることがあるので、2タイル以内の自国の都市をその場所とみなす
    xy = (int(x), int(y))
    if xy[0] < 0:
        return None
    c = min(my_cities, key=lambda c: d2((int(c[0]), int(c[1])), xy), default=None)
    return my_cities[c] if c and d2((int(c[0]), int(c[1])), xy) <= 4 else None


for p in G:
    t, kind, rest = int0(p[0]), p[5], p[6:]
    if is_me(p[1], p[2]):
        rest = [tag_city(x, p[3], p[4]) for x in rest]
    r0 = rest[0] if rest else ''
    at = f'({p[3]},{p[4]})'
    place = my_cities.get((p[3], p[4])) or near_city(p[3], p[4]) or at
    first = '（最初の発見者）' if kv(rest).get('Discoverer') == 'true' else ''
    if not is_me(p[1], p[2]):
        others = ', '.join(x for x in rest if x)
        # 都市国家の行は、文明名が「村」で、指導者の欄に国の名前が入っている
        actor = f'{p[1]}（都市国家）' if p[2] == '村' else leader_label(p[1])
        if kind == 'GOSSIP_CONVERT_CITY' and (p[3], p[4]) in my_cities:
            add(t, f"**{leader_label(p[1])}が{my_cities[(p[3], p[4])]}を改宗させる**")
            continue
        # 戦闘は CombatLog、出会いは自国側の行から拾う
        if me[0] not in others or kind in ('GOSSIP_UNIT_COMBAT_DEATH', 'GOSSIP_PLAYERS_MEET', 'GOSSIP_ALLIED'):
            continue
        if kind == 'GOSSIP_LOST_WONDER_RACE':
            d = kv(rest)
            add(t, f"遺産「{rest[3]}」の建設競争で、{actor}の{d.get('Losing City')}に勝つ（相手の進み具合 {d.get('Percent Complete')}%）")
        elif kind == 'GOSSIP_TRADE_ROUTE_STARTED':
            add(t, f"{actor}が、{place}への交易路を開く")
        elif kind == 'GOSSIP_MAKE_DOW':
            add(t, f"**{actor}が自国に宣戦布告**")
        elif kind == 'GOSSIP_MAKE_PEACE':
            add(t, f"**{actor}と講和**")
        else:
            add(t, f"{actor}：{kind.replace('GOSSIP_', '')} {others}")
        continue
    if kind in SKIP:
        continue
    if kind == 'GOSSIP_FOUND_CITY':
        founded.append((t, r0, rest[1], rest[2]))
        add(t, f"**居住地「{r0}」を建設** {at}（{rest[1]}、{rest[2]}）")
    elif kind == 'GOSSIP_CITY_POPULATION_HEIGHT_CHANGED':
        # 同じターンに何度も増えたときは最後の値だけ残す
        pop[t] = [x for x in pop[t] if x[0] != r0] + [(r0, rest[1].split(':')[-1])]
    elif kind == 'GOSSIP_CONSTRUCT_BUILDING':
        if r0 in wonders:
            wonder_done.append((t, r0, rest[1]))
            add(t, f"**遺産「{r0}」が完成**（{rest[1]}）")
        else:
            add(t, f"{rest[1]}：{r0}を建設")
    elif kind == 'GOSSIP_TRAIN_UNIT':
        add(t, f"{place}：{r0}が完成")
    elif kind == 'GOSSIP_COMPLETED_PROGRESSION_TREE_NODE':
        depth = kv(rest).get('Depth')
        if not rest[1]:
            add(t, f"{r0}を得る")
        else:
            kind_jp = '技術' if '技術' in r0 else '社会制度'
            add(t, f"{kind_jp}「{rest[1]}」の習熟を完了" if depth and depth != '1' else f"{kind_jp}「{rest[1]}」を完了")
    elif kind == 'GOSSIP_CHANGE_GOVERNMENT':
        add(t, f"**政体を{kv(rest).get('New Government')}にする**")
    elif kind == 'GOSSIP_TRADITION_ACTIVATED':
        add(t, f"社会政策「{r0}」を入れる")
    elif kind == 'GOSSIP_TRADITION_DEACTIVATED':
        add(t, f"社会政策「{r0}」を外す")
    elif kind == 'GOSSIP_POLICY_SLOTS_CHANGED':
        add(t, "社会政策スロットの数が変わる")
    elif kind == 'GOSSIP_SPEND_ATTRIBUTE':
        add(t, "属性ポイントを使う")
    elif kind == 'GOSSIP_GATHER_RESOURCE':
        add(t, f"資源「{r0}」を確保 {at}")
    elif kind in ('GOSSIP_FIND_RIVER', 'GOSSIP_FIND_VOLCANO', 'GOSSIP_FIND_NATURAL_WONDER'):
        add(t, f"{r0}を見つける {at}{first}")
    elif kind == 'GOSSIP_FIND_CONTINENT':
        add(t, f"{r0}大陸を見つける {at}")
    elif kind == 'GOSSIP_WONDER_STARTED':
        add(t, f"{rest[1]}で遺産「{r0}」に着工")
    elif kind == 'GOSSIP_MEET_INDEPENDENT':
        tr = nearest_tribe(int(p[3]), int(p[4]), t)
        name = tribe_label(tr) if tr else '名前不明'
        if tr and name not in [m[1] for m in meets]:
            meets.append((t, name))
        if (t, name) not in met_today:
            met_today.add((t, name))
            add(t, f"独立勢力「{name}」と接触 {at}")
    elif kind == 'GOSSIP_PLAYERS_MEET':
        meets.append((t, leader_label(r0)))
        add(t, f"**{leader_label(r0)}と出会う**")
    elif kind == 'GOSSIP_GOLDEN_AGE':
        celebrations.append(t)
        add(t, f"祝宴が始まる（政体：{r0}）")
    elif kind == 'GOSSIP_BECOME_SUZERAIN':
        suzerains.append((t, r0))
        add(t, f"**都市国家「{r0}」の宗主になる**（ボーナス：{rest[1]}）")
    elif kind == 'GOSSIP_INDEPENDENT_ASSAULT':
        add(t, f"独立勢力「{rest[1]}」が「{r0}」を襲う {at}")
    elif kind == 'GOSSIP_CREATE_PANTHEON':
        add(t, f"**パンテオン「{r0}」を創始**")
    elif kind == 'GOSSIP_FOUND_RELIGION':
        add(t, f"**宗教「{r0}」を創始**")
    elif kind == 'GOSSIP_TRADE_ROUTE_STARTED':
        add(t, f"{leader_label(r0)}への交易路を開く {at}")
    elif kind == 'GOSSIP_MAKE_DOW':
        add(t, f"**{leader_label(r0)}に宣戦布告**")
    elif kind == 'GOSSIP_MAKE_PEACE':
        add(t, f"**{leader_label(r0)}と講和**")
    elif kind == 'GOSSIP_RANDOM_EVENT_DAMAGE':
        d = kv(rest)
        add(t, f"災害「{r0}」{at}：被害タイル {d.get('Damaged Tiles')}、人口減少 {d.get('Pop Lost')}、失ったユニット {d.get('Units Killed')}")
    elif kind == 'GOSSIP_RANDOM_EVENT_DAMAGED_CONSTRUCTIBLE':
        damaged[t] += 1
    elif kind == 'GOSSIP_CONSTRUCTIBLE_REPAIRED':
        add(t, f"{rest[1]}：{r0}を修理")
    elif kind == 'GOSSIP_RELIC_RECEIVED':
        add(t, "遺物を得る")
    elif kind == 'GOSSIP_UNIT_DESTROYED':
        add(t, f"{r0}がなくなる {at}")
    elif kind == 'GOSSIP_ARMY_FILLED':
        d = kv(rest)
        add(t, f"軍隊が満員になる {at}（戦闘ユニット {d.get('Combat Units')}、戦闘力 {d.get('Combat Strength')}）")
    elif kind == 'GOSSIP_BELIEF_ADDED':
        d = kv(rest)
        add(t, f"宗教「{d.get('Religion')}」に信条「{d.get('Belief')}」を加える")
    elif kind == 'GOSSIP_CONVERT_CITY':
        add(t, f"{city_at(p[3], p[4])}を改宗させる")
    elif kind == 'GOSSIP_NEW_RELIGIOUS_MAJORITY':
        add(t, f"{city_at(p[3], p[4])}で多数派の宗教が変わる")
    elif kind == 'GOSSIP_PLACED_WORKER':
        add(t, f"専門家を置く（{r0}のある区画 {at}）")
    elif kind == 'GOSSIP_SCORE_DISBAND_UNIT':
        add(t, f"ユニットを解散して得点を得る {at}")
    elif kind == 'GOSSIP_UNIT_COMBAT_DEATH':
        continue  # 戦闘は CombatLog から拾う
    elif kind in ('GOSSIP_CONQUER_CITY', 'GOSSIP_URBAN_CONTROL_CHANGED'):
        continue  # 都市の占領は DiplomacySummary の City Capture から拾う
    elif kind == 'GOSSIP_ARTIFACT_EXTRACTED':
        add(t, f"遺物を発掘する {at}")
    elif kind == 'GOSSIP_DISBANDED_UNIT':
        add(t, f"{r0}を解散する {at}")
    elif kind == 'GOSSIP_REJECT_DEAL':
        add(t, "取引の申し出を断る")
    elif kind == 'GOSSIP_UNIT_PROMOTION':
        add(t, "ユニットが昇格する")
    elif kind == 'GOSSIP_ALLIED':
        # 同盟は DiplomacySummary の行から書く
        pass
    elif kind == 'GOSSIP_LOST_WONDER_RACE':
        # 自国が建設競争に負けたとき。Winning City には自国の首都の名前が入っていて当てにならないので、
        # 同じターンにその遺産を完成させた他国の行から勝った都市を引く
        d = kv(rest)
        win = [q for q in G if int0(q[0]) == t and q[5] == 'GOSSIP_CONSTRUCT_BUILDING'
               and q[6:7] == [rest[3]] and not is_me(q[1], q[2])]
        by = f"{leader_label(win[0][1])}の{win[0][7]}が先に完成させた。" if win else ''
        lost_races.add((t, rest[3]))
        add(t, f"遺産「{rest[3]}」の建設競争に負ける（{by}{d.get('Losing City')}の進み具合 "
               f"{d.get('Percent Complete')}%、生産 {d.get('Production Refund')} が戻る）")
    elif kind == 'GOSSIP_CITY_RAZED':
        add(t, f"**{former_city(p[3], p[4], t)}を焼き払う** {at}")
    elif kind == 'GOSSIP_OCCUPY_CITY':
        # 奪った都市を焼き払わずに残したとき（他国の行にも、奪ったあとに出る）
        add(t, f"奪った{former_city(p[3], p[4], t)}を、焼き払わずに残す {at}")
    elif kind == 'GOSSIP_CITY_UNREST':
        # 「不安」は居住地の状態（購入と修理ができなくなる）。ログには施設の名前が一緒に出る
        xy = (int0(p[3]), int0(p[4]))
        c = min(my_cities, key=lambda c: d2((int(c[0]), int(c[1])), xy))
        add(t, f"不安：{my_cities[c] if d2((int(c[0]), int(c[1])), xy) <= 9 else at}（{r0} {at}）")
    else:
        add(t, f"{kind.replace('GOSSIP_', '')} {at} {', '.join(x for x in rest if x)}")
for t, items in pop.items():
    add(t, '人口：' + '、'.join(f'{c} {n}' for c, n in items))
for t, n in damaged.items():
    add(t, f"災害で施設が {n} か所傷む")

# --- 発見イベント：Historian の座標とターン → NarrativeStories のストーリーID → 本文
hist = same_age([cells(l) for l in read('Historian.csv')[1:]], lambda p: int0(p[2]))
disc = {}
for p in hist:
    if p[0] == 'DISCOVERY_TRIGGERED' and p[5] == pid:
        disc[(p[3], p[4])] = (int0(p[2]), p[8])
    elif p[0] == 'OVERBUILDING' and p[5] == pid:
        add(int0(p[2]), f"({p[3]},{p[4]}) の{p[8]}を建て替える")
    elif p[0] == 'UNFINISHED_WONDER' and p[5] == pid:
        if (int0(p[2]), p[8]) not in lost_races:
            add(int0(p[2]), f"遺産「{p[8]}」の建設競争に負ける ({p[3]},{p[4]})")
    elif p[0] == 'VOLCANO_ERUPTION' and p[5] == pid:
        add(int0(p[2]), f"火山の噴火 ({p[3]},{p[4]})：{p[8]}")
    elif p[0] == 'RIVER_FLOODED' and p[5] == pid:
        add(int0(p[2]), f"川の氾濫 ({p[3]},{p[4]})：{p[8]}")
    elif p[0] == 'UNIQUE_IMPROVEMENT_REPLACED' and p[5] == pid:
        add(int0(p[2]), f"固有の施設「{p[8]}」が置き換えられる ({p[3]},{p[4]})")
    elif pid in (p[5], p[6]) and p[0] not in ('UNIT_KILLED', 'SHIP_SUNK', 'UNFINISHED_WONDER'):
        add(int0(p[2]), f"記録：{p[0]} ({p[3]},{p[4]}) {p[7]} {p[8]}")
ns = read('NarrativeStories.log')
# 同じ起動中に同じ地図で遊んだ前のゲームの行を拾わないよう、この時代の最初の発見の行から読む
start = 0
if disc:
    fx, fy = min(disc, key=lambda k: disc[k][0])
    hits = [i for i, l in enumerate(ns) if l.startswith(f'Player {pid}, Coord x: {fx}, y: {fy}, ')]
    start = hits[-1] if hits else 0
chains = collections.OrderedDict()
for l in ns[start:]:
    m = re.match(r'Player (\d+), Coord x: (\d+), y: (\d+), Requirements met for story (\S+)', l)
    if m and m.group(1) == pid and (m.group(2), m.group(3)) in disc:
        chains.setdefault((m.group(2), m.group(3)), []).append(m.group(4))
discoveries = []
for xy, ids in chains.items():
    t, kind = disc[xy]
    base = ids[0][:-1]
    letters = [s[-1] for s in ids if s[:-1] == base]
    title = clean(tags.get(f'LOC_{base}A_STORYTITLE', base))
    lines = [f"発見イベント「{title}」（{kind}、({xy[0]},{xy[1]})）"]
    if f'LOC_{base}A_COMPLETION' in tags:
        lines.append(f"  > {clean(tags[f'LOC_{base}A_COMPLETION'])}")
    for c in letters:
        if c in 'BC' and f'LOC_{base}{c}_NAME' in tags:
            lines.append(f"  * 選択：「{clean(tags[f'LOC_{base}{c}_NAME'])}」")
        elif c not in 'ABC':
            if f'LOC_{base}{c}_COMPLETION' in tags:
                lines.append(f"  * 結果：「{clean(tags[f'LOC_{base}{c}_COMPLETION'])}」")
            if f'LOC_{base}{c}_DESCRIPTION' in tags:
                lines.append(f"  * 効果：{clean(tags[f'LOC_{base}{c}_DESCRIPTION'])}")
    if len({s[:-1] for s in ids}) > 1:
        lines.append(f"  * 注：この座標には別のストーリー（{', '.join(sorted({s[:-1] for s in ids} - {base}))}）も記録されている")
    discoveries.append((t, title))
    add(t, '\n'.join(lines))
for xy, (t, kind) in disc.items():
    if xy not in chains:
        add(t, f"発見イベント（{kind}、({xy[0]},{xy[1]})）：ストーリーは不明")

# --- 外交：DiplomacySummary（行動の開始と終了、同盟、都市の占領）
RESULT = {'Success': '成功', 'Canceled': '取り消し', 'Failure': '失敗'}
started = {}
for p in same_age([cells(l) for l in read('DiplomacySummary.csv')[1:]], lambda p: int0(p[0])):
    t, ini, rec, act = int0(p[0]), p[1], p[2], p[3]
    if pid not in (ini, rec):
        continue
    det = re.sub(r'\{\d+_villageName\}', who(rec, t), loc_words(p[4]))
    if act == 'Diplomacy Action Started':
        target = f'{who(rec, t)}に対して' if rec != '-1' and who(rec, t) not in det else ''
        started[(ini, rec, det)] = t
        add(t, f"外交：{who(ini, t)}が{target}「{det}」を始める".replace('外交：自国が', '外交：'))
    elif act == 'Diplomacy Action Ended':
        m = re.match(r'(.*) result: (\w+)', det)
        name, result = (m.group(1), m.group(2)) if m else (det, '')
        if result == 'Canceled' and started.get((ini, rec, name)) == t:
            # 始めたターンに取り消されたもの（居住地を建てたときの領有宣言など）は省く
            ev[t] = [e for e in ev[t] if not (e.startswith('外交：') and f'「{name}」を始める' in e)]
            continue
        add(t, f"外交：「{name}」が終わる（{RESULT.get(result, result)}。{who(ini, t)}→{who(rec, t)}）")
    elif act == 'Allied':
        add(t, f"**{who(ini, t)}と{who(rec, t)}が同盟**")
    elif act == 'City Capture':
        add(t, f"**{who(ini, t)}が{who(rec, t)}の都市「{city_name(det)}」を占領**")
    elif act in ('At War', 'Peace') and ini in majors and rec in majors:
        add(t, f"{who(ini, t)}と{who(rec, t)}：{'戦争' if act == 'At War' else '平和'}")

# --- 購入
for p in same_age([cells(l) for l in read('CityPurchase.csv')[1:]], lambda p: int0(p[0])):
    if p[1] == pid:
        t, n, item = int0(p[0]), city_name(p[2]), item_name(p[3])
        # 購入の記録には座標がないので、名前が重なる都市は、同じターンに同じものを建てた都市とみなす
        if n in dup_names:
            hit = {e.split('：')[0] for e in ev[t] if e.startswith(n + '（') and f'：{item}' in e}
            n = hit.pop() if len(hit) == 1 else n
        add(t, f"{n}：{item}を購入")

# --- レガシー（Player_Legacies.csv に Apply Reward として記録されたもの）
legacies = []
# レガシーはターンがまばらで、時代の最後のターンまで記録が続かないことがある。
# そこで、コードの時代（AQ／EX／MO）が同じ区切りのうち、いちばん新しいものを使う
AGE = ['AQ', 'EX', 'MO'][min(gi - gk, 2)]
leg_rows = [cells(l) for l in read('Player_Legacies.csv')[1:]]
leg = next((s for s in reversed(segments(leg_rows, lambda p: int0(p[1])))
            if any(len(p) > 2 and p[2].startswith(f'LEGACY_{AGE}_') for p in s)), [])
for p in leg:
    if p[0] == pid and p[2].startswith(f'LEGACY_{AGE}_'):
        name = item_name(re.sub(r'\(\d+\)$', '', p[2]))
        legacies.append((int0(p[1]), name))
        add(int0(p[1]), f"**レガシー「{name}」**")

# --- 戦闘：CombatLog（回復は除く）
SRC = {'Unit vs Unit': 'ユニット同士', 'Unit vs City': '都市', 'Unit vs District': '地区',
       'Unit vs Location': '区画', 'Unit vs Army': '軍隊'}
CTYPE = {'Melee': '近接', 'Ranged': '遠隔', 'Bombard': '砲撃'}
DEST = {'Attacker': '攻撃側が倒れる', 'Defender': '防御側を倒す', 'District': '区画の守りを破る'}


def unit(s):
    code = re.sub(r'^\(-?\d+\)', '', s)
    return item_name(code) if code not in ('N/A', '') else ''


for p in same_age([cells(l) for l in read('CombatLog.csv')[1:]], lambda p: int0(p[0])):
    if pid not in (p[3], p[4]) or p[1] == 'Unit Heal':
        continue
    t = int0(p[0])
    loc = ','.join(re.findall(r'\((-?\d+)\)', p[2]))
    # 都市や区画への攻撃なら、そこにある都市の名前を添える（ユニット同士の戦闘は、まだ都市がない時期のことがある）
    if p[1] in ('Unit vs City', 'Unit vs District', 'Unit vs Location') and tuple(loc.split(',')) in all_cities:
        loc += f'、{city_at(*loc.split(","))}'
    kind = SRC.get(p[1], p[1]) + ('・' + CTYPE.get(p[5], p[5]) if p[5] else '')
    dest = f"。{DEST.get(p[14], p[14])}" if p[14] not in ('N/A', '') else ''
    add(t, f"戦闘（{kind}、({loc})）：{who(p[3], t)}の{unit(p[6])} → {who(p[4], t)}の{unit(p[7])}。"
           f"攻撃側の被害 {p[12]}、防御側の被害 {p[13]}{dest}")

# --- 国力
stats = same_age([cells(l) for l in read('Player_Stats.csv')[1:]], lambda p: int0(p[0]))
by_turn = {(int0(p[0]), p[1]): p for p in stats}
end = max(t for t, _ in by_turn)
# 時代の最後のターンは、自国の分だけ書かれて終わることがあるので、全員がそろう最後のターンで比べる。
# 時代の途中で滅んだ文明は、比べる相手から外す
last_seen = collections.Counter()
for t, i in by_turn:
    last_seen[i] = max(last_seen[i], t)
alive = [i for i in majors if last_seen[i] >= end - 1]
compare = max(t for t in {t for t, _ in by_turn} if all((t, i) in by_turn for i in alive))

# --- 勝利と滅亡：GameCore.log の時刻を、Telemetry.log のターンの終わり（CampaignTurnEnd）と
# 時代の終わり（AgeEnd）の時刻でターンに直す。出来事の直後に終わったターンを、そのターンとする。
# 調べる時刻の範囲は、この時代に入ったとき（T1 の CampaignEnter）から、次に T1 で入るときまで
# （前のゲームの勝利は、最後のターンの終わりより後に記録されるので、ターンの終わりでは区切れない）
tele = []
for l in read('Telemetry.log'):
    m = re.search(r'^\[([\d\- :]+)\].*SendCampaignStatusTelemetry - statusName: (CampaignTurnEnd|AgeEnd|CampaignEnter) iCurrentTurn: (\d+)', l)
    if m:
        tele.append((m.group(1), m.group(2), int(m.group(3))))
tsegs = segments([x for x in tele if x[1] == 'CampaignTurnEnd'], lambda x: x[2])
tk = next((k for k in reversed(range(len(tsegs))) if last_turn - 5 <= tsegs[k][-1][2] <= last_turn), None)
victories, defeats, minor_defeats = [], [], 0
if tk is not None:
    enters = [x[0] for x in tele if x[1] == 'CampaignEnter' and x[2] == 1]
    lo = max((e for e in enters if e <= tsegs[tk][0][0]), default='')
    hi = min((e for e in enters if e > tsegs[tk][-1][0]), default='9999')
    marks = [x for x in tele if lo < x[0] < hi and x[1] != 'CampaignEnter']

    def turn_at(ts):
        return next((x[2] for x in marks if x[0] >= ts), last_turn)

    for l in read('GameCore.log'):
        m = re.match(r'^\[([\d\- :]+)\]\s+(.*)', l)
        if not m or not lo < m.group(1) < hi:
            continue
        v = re.match(r"Team (\d+) has won 1 place in a '(\w+)' victory!", m.group(2))
        d = re.match(r'Player (\d+) has been defeated', m.group(2))
        if v and v.group(1) == pid:
            t = turn_at(m.group(1))
            name = clean(tags.get(f'LOC_{v.group(2)}_NAME', v.group(2))) + 'による勝利'
            victories.append((t, name))
            add(t, f'**{name}**')
        elif d and d.group(1) in majors:
            t = turn_at(m.group(1))
            defeats.append((t, who(d.group(1), t)))
            add(t, f'**{who(d.group(1), t)}が滅ぶ**')
        elif d:
            minor_defeats += 1

# --- 書き出し
leader, civ = me[0], age_civ.get(me[0], me[1])
o = []
w = o.append
w(f"# {civ_label(leader, civ)}：T{first_turn}〜T{last_turn} の行動記録\n")
w("Civ7 の Logs フォルダから取り出した、ゲーム上の出来事の記録。解釈は入れず、ログにあることだけを書く。\n")
w(f"* プレイヤー{pid}：{civ_label(leader, civ)}")
w(f"* 範囲：T{first_turn}〜T{last_turn}")
w("* 発見イベントの本文と選択肢、独立勢力の名前は、ゲーム本体の日本語テキスト（ja_JP_Text.xml）から引いた。〈首都〉〈独立勢力〉〈報酬〉は、ゲーム画面では具体的な名前や量に置き換わる部分")
w("* ログに残らないもの：ユニットの移動、見つけただけで訪れていない集落、選択肢で得た報酬の量\n")
w("---\n")
w("## 1. まとめ\n")
if victories or defeats:
    w("### 勝利と滅んだ文明\n")
    for t, n in victories:
        w(f"* T{t}：{n}")
    for t, n in defeats:
        w(f"* T{t}：{n}が滅ぶ")
    if minor_defeats:
        w(f"* ほかに、都市国家などのプレイヤーが {minor_defeats} つ敗退した（名前はログから分からない）")
    w("")
w("### 建設した居住地\n")
for t, n, b, c in founded:
    w(f"* T{t}：{n}（{b}、{c}）")
w("\n### 出会った文明と独立勢力\n")
for t, n in meets:
    w(f"* T{t}：{n}")
if suzerains:
    w("\n### 宗主になった都市国家\n")
    for t, n in suzerains:
        w(f"* T{t}：{n}")
if wonder_done:
    w("\n### 完成した遺産\n")
    for t, n, c in wonder_done:
        w(f"* T{t}：{n}（{c}）")
if discoveries:
    w("\n### 発見イベント\n")
    for t, n in sorted(discoveries):
        w(f"* T{t}：{n}")
if legacies:
    w("\n### レガシー\n")
    for t, n in legacies:
        w(f"* T{t}：{n}")
if celebrations:
    w(f"\n### 祝宴\n\n* {'、'.join(f'T{t}' for t in celebrations)}")
w("\n### 国力の推移\n")
w("| ターン | 都市 | 町 | 人口 | 技術 | 陸上ユニット | 海上ユニット | 領土 | ゴールド | 科学 | 文化 | ゴールド収入 | 生産 | 食料 | 幸福 | 影響力 |")
w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for t in sorted({first_turn, end} | set(range(10, end, 10))):
    p = by_turn.get((t, pid))
    if p:
        w(f"| T{t} | {p[2]} | {p[3]} | {int(p[6]) + int(p[7])} | {p[8]} | {p[9]} | {p[10]} | {p[11]} | "
          + ' | '.join(num(x) for x in p[13:21]) + ' |')
w(f"\n### T{compare} の各文明\n")
w("| 文明 | 都市 | 町 | 人口 | 技術 | 領土 | 科学 | 文化 | 生産 | ゴールド収入 |")
w("|---|---|---|---|---|---|---|---|---|---|")
for i in sorted(alive, key=lambda i: -(int(by_turn[(compare, i)][6]) + int(by_turn[(compare, i)][7]))):
    p = by_turn[(compare, i)]
    label = f'**{civ_label(leader, civ)}**' if i == pid else who(i, compare)
    w(f"| {label} | {p[2]} | {p[3]} | {int(p[6]) + int(p[7])} | {p[8]} | {p[11]} | {num(p[14])} | {num(p[15])} | {num(p[17])} | {num(p[16])} |")
w("\n---\n")
w("## 2. ターンごとの出来事\n")
for t in range(first_turn, last_turn + 1):
    w(f"### T{t}\n")
    if not ev.get(t):
        w("* 記録なし\n")
        continue
    for e in ev[t]:
        w(f"* {e}")
    w("")
with open(args.out, 'w', encoding='utf-8') as f:
    f.write('\n'.join(o) + '\n')
print(f"T{first_turn}-T{last_turn}: {sum(len(v) for v in ev.values())} events -> {args.out}")
