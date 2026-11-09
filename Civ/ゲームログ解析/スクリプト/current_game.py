# Civ7 の Logs フォルダから、最後に遊んだゲームの出来事を、指定したプレイヤーについてターンごとに書き出す。
# 使い方: python current_game.py "<Logsフォルダ>" 出力.txt <プレイヤー番号>
import sys, os, re, collections

d, out, pid = sys.argv[1], sys.argv[2], sys.argv[3]

def read(name):
    with open(os.path.join(d, name), encoding='utf-8', errors='replace') as f:
        return f.read().splitlines()

def int0(s):
    try: return int(s.strip())
    except ValueError: return None

def last_segment(lines, turn_of):
    # ゲームの読み込みや時代の移行でターンが戻るので、最後に戻った位置以降を今のゲームとみなす
    start, prev = 0, None
    for i, l in enumerate(lines):
        t = turn_of(l)
        if t is None: continue
        if prev is not None and t < prev: start = i
        prev = t
    return lines[start:]

def rows(name, turn_col, sep=','):
    lines = last_segment(read(name)[1:], lambda l: int0(l.split(sep)[turn_col]) if len(l.split(sep)) > turn_col else None)
    return [[x.strip() for x in l.split(sep)] for l in lines]

ev = collections.defaultdict(list)
def add(t, src, text):
    entry = f"[{src}] {text}"
    if entry not in ev[t]: ev[t].append(entry)

# Gossip: 開始位置で建てた都市から、プレイヤーの指導者名と文明名を特定する
g = rows('Game_Gossip.csv', 0)
adv = [l for l in read('AdvancedStart.csv')[1:] if l.split(',')[1].strip() == pid]
x0, y0 = re.search(r'\((\d+)-(\d+)\)', adv[-1]).groups()
me = next((p[1], p[2]) for p in g if p[5] == 'GOSSIP_FOUND_CITY' and (p[3], p[4]) == (x0, y0))
for p in g:
    t, rest = int0(p[0]), ', '.join(x for x in p[6:] if x)
    kind = p[5].replace('GOSSIP_', '')
    if (p[1], p[2]) == me:
        add(t, 'Gossip', f"{kind} ({p[3]},{p[4]}) {rest}")
    elif me[0] in rest:
        add(t, 'Gossip/他者', f"{p[1]}/{p[2]}: {kind} {rest}")

# Historian: 発見イベントなど。発見の座標とターンは NarrativeStories と結びつけるのに使う
disc = {}
for p in rows('Historian.csv', 2):
    if pid in (p[5], p[6]):
        add(int0(p[2]), 'Historian', f"{p[0]} ({p[3]},{p[4]}) player={p[5]} opp={p[6]} {p[7]} {p[8]}")
    if p[0] == 'DISCOVERY_TRIGGERED' and p[5] == pid:
        disc[(p[3], p[4])] = int0(p[2])

# NarrativeStories: ターンが入らないので、座標で発見イベントのターンに結びつける
# 同じ地図で前のゲームを遊んでいると、同じ座標の古い行も拾うことがある
for l in read('NarrativeStories.log'):
    m = re.match(r'Player (\d+), Coord x: (\d+), y: (\d+), Requirements met for story (\S+)', l)
    if m and m.group(1) == pid and (m.group(2), m.group(3)) in disc:
        add(disc[(m.group(2), m.group(3))], 'Story', f"{m.group(4)} ({m.group(2)},{m.group(3)})")

# CityBuildQueue: 生産対象が変わったターン（完成または変更）と、都市の改名
last, names = {}, {}
for p in rows('CityBuildQueue.csv', 0, ', '):
    if p[1] != pid: continue
    t, city, item = int0(p[0]), p[2], p[4]
    key = re.sub(r'^\{(LOC_CITY_NAME_\w+):.*', r'\1', city)
    m = re.search(r';(.+?);', city)
    name = m.group(1) if m else city
    if key in names and names[key] != name: add(t, 'Build', f"都市名 {names[key]} → {name}")
    names[key] = name
    if key in last and last[key] != item: add(t, 'Build', f"{name}: {last[key]} → {item}")
    last[key] = item

for p in rows('CityPurchase.csv', 0):
    if p[1] == pid: add(int0(p[0]), 'Purchase', f"{p[2]} {p[3]}")

# Player_Stats: 都市数・人口・技術数・ユニット数・領土の変化
prev = None
for p in rows('Player_Stats.csv', 0):
    if p[1] != pid: continue
    cur = dict(cities=p[2], towns=p[3], pop=int(p[6]) + int(p[7]), techs=p[8], land=p[9], naval=p[10], tiles=p[11])
    if prev:
        diff = [f"{k}:{prev[k]}→{v}" for k, v in cur.items() if str(prev[k]) != str(v)]
        if diff: add(int0(p[0]), 'Stats', ' '.join(diff))
    prev = cur

# DiplomacySummary: 接触と外交行動。毎ターン繰り返される戦争・平和の状態は除く
for p in rows('DiplomacySummary.csv', 0):
    if pid in (p[1], p[2]) and p[3] not in ('At War', 'Peace'):
        add(int0(p[0]), 'Diplo', f"{p[1]}→{p[2]} {p[3]} {p[4]}")

for p in rows('CombatLog.csv', 0):
    if pid in (p[3], p[4]) and p[1] != 'Unit Heal':
        add(int0(p[0]), 'Combat', ','.join(p[1:]))

with open(out, 'w', encoding='utf-8') as f:
    f.write(f"player {pid} = {me[0]}/{me[1]}, start ({x0},{y0})\n")
    for t in sorted(k for k in ev if k is not None):
        f.write(f"\n## T{t}\n")
        for e in ev[t]: f.write(f"  {e}\n")
