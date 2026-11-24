"""Civ6 の Logs フォルダから、1つのゲームの指定したターン範囲の行動記録（Markdown）を書き出す。

使い方:
    python -I civ6_record.py <Logsフォルダ> --game 2 --from 61 --to 120 --era 古典時代 -o 出力.md

    --game  その Logs に入っているゲームの番号（1から数える。-1 は最後のゲーム）
    --player  記録するプレイヤー番号（省略すると GameCore.log の人間プレイヤー）

Civ7 用の age_record.py と違い、Civ6 には Game_Gossip.csv がないので、いくつものログを突き合わせて組み立てる。
どのログから何を取ったかは、出力の「ログについて」に書く。
"""
import argparse
import collections
import csv
import datetime
import glob
import os
import pickle
import re
import sys
import tempfile

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VI"
BARBARIAN = 63
FREE_CITIES = 62
ERA_ORDER = ['ANCIENT', 'CLASSICAL', 'MEDIEVAL', 'RENAISSANCE', 'INDUSTRIAL', 'MODERN', 'ATOMIC', 'INFORMATION', 'FUTURE']


# ---------------------------------------------------------------- ゲーム本体のデータ

def load_gamedata():
    """日本語テキスト・英語テキスト・都市名の既定の文明・遺産・政体の並びを、本体の xml から読む"""
    cache = os.path.join(tempfile.gettempdir(), 'civ6_record_gamedata_v3.pkl')
    if os.path.exists(cache):
        try:
            return pickle.load(open(cache, 'rb'))
        except Exception:
            pass
    ja, en = {}, {}
    citydef = collections.defaultdict(set)
    wonders = set()
    govs = []
    pat_ja = re.compile(r'<(?:Replace|Row)\s+Tag="([^"]+)"\s+Language="ja_JP"\s*>\s*<Text>(.*?)</Text>', re.S)
    pat_en = re.compile(r'<(?:Replace|Row)\s+Tag="([^"]+)"\s*>\s*<Text>(.*?)</Text>', re.S)
    files = sorted(glob.glob(os.path.join(GAME, '**', '*.xml'), recursive=True))
    # シナリオ用の DLC（Civロワイヤルなど）は本編の名前を上書きする（開拓者→民間人など）ので読まない
    skip = re.compile(r'[\\/](DLC[\\/][^\\/]*Scenario[^\\/]*|CTP|Debug|LaunchPad)[\\/]', re.I)
    files = [f for f in files if not skip.search(f)]
    for f in files:
        try:
            s = open(f, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        if 'ja_JP' in s:
            for tag, text in pat_ja.findall(s):
                ja[tag] = text.strip()
        if os.sep + 'en_US' + os.sep in f:
            for tag, text in pat_en.findall(s):
                en.setdefault(tag, text.strip())
        if 'CityName=' in s:
            for civ, cn in re.findall(r'CivilizationType="(\w+)"\s+CityName="(\w+)"', s):
                citydef[cn].add(civ)
        if 'IsWonder' in s:
            for row in re.findall(r'<Row\b[^>]*?/>|<Row\b[^>]*?>.*?</Row>', s, re.S):
                if re.search(r'IsWonder\s*=\s*"true"|<IsWonder>\s*true', row):
                    m = re.search(r'BuildingType\s*=\s*"(BUILDING_\w+)"|<BuildingType>\s*(BUILDING_\w+)', row)
                    if m:
                        wonders.add(m.group(1) or m.group(2))
    # 政体の番号は Governments 表に行が足された順（本体 → 拡張1 → 拡張2）
    for f in [os.path.join(GAME, 'Base', 'Assets', 'Gameplay', 'Data', 'Governments.xml')] + \
             sorted(glob.glob(os.path.join(GAME, 'DLC', 'Expansion1', 'Data', '*.xml'))) + \
             sorted(glob.glob(os.path.join(GAME, 'DLC', 'Expansion2', 'Data', '*.xml'))):
        s = open(f, encoding='utf-8', errors='replace').read()
        m = re.search(r'<Governments>(.*?)</Governments>', s, re.S)
        if m:
            for g in re.findall(r'GovernmentType="(GOVERNMENT_\w+)"', m.group(1)):
                if g not in govs:
                    govs.append(g)
    # 暦：ゲーム速度ごとの「何ターンのあいだ、1ターンで何か月進むか」と、始まりの年
    speeds = collections.defaultdict(list)
    s = open(os.path.join(GAME, 'Base', 'Assets', 'Gameplay', 'Data', 'GameSpeeds.xml'), encoding='utf-8').read()
    m = re.search(r'<GameSpeed_Turns>(.*?)</GameSpeed_Turns>', s, re.S)
    for sp, mon, n in re.findall(r'<GameSpeedType>(\w+)</GameSpeedType>\s*<MonthIncrement>(\d+)</MonthIncrement>\s*<TurnsPerIncrement>(\d+)</TurnsPerIncrement>', m.group(1)):
        speeds[sp].append((int(n), int(mon)))
    s = open(os.path.join(GAME, 'Base', 'Assets', 'Gameplay', 'Data', 'Eras.xml'), encoding='utf-8').read()
    start_year = int(re.search(r'EraType="ERA_ANCIENT"[^>]*Year="(-?\d+)"', s).group(1))
    data = dict(ja=ja, en=en, citydef=dict(citydef), wonders=wonders, govs=govs, speeds=dict(speeds), start_year=start_year)
    try:
        pickle.dump(data, open(cache, 'wb'))
    except OSError:
        pass
    return data


class Names:
    def __init__(self, data):
        self.ja, self.en = data['ja'], data['en']

    def tag(self, tag):
        if tag in self.ja:
            return self.ja[tag]
        if tag in self.en:
            return self.en[tag]
        return None

    def __call__(self, t):
        """TECH_X / UNIT_X / LOC_... などを日本語名に"""
        if not t:
            return t
        for k in ([t] if t.startswith('LOC_') else []) + ['LOC_' + t + '_NAME', 'LOC_' + t, t + '_NAME']:
            v = self.tag(k)
            if v:
                return re.sub(r'\[ICON_\w+\]\s*', '', v)
        m = re.match(r'GREAT_PERSON_INDIVIDUAL_(\w+)', t)
        if m:
            return m.group(1).replace('_', ' ').title() + '（日本語名なし）'
        return t


# ---------------------------------------------------------------- ログの読み込み

def read_csv(L, fn):
    p = os.path.join(L, fn)
    if not os.path.exists(p):
        return [], []
    rows = list(csv.reader(open(p, encoding='utf-8', errors='replace')))
    if not rows:
        return [], []
    return [h.strip() for h in rows[0]], [[x.strip() for x in r] for r in rows[1:] if r]


def turn_of(r, col=0):
    try:
        return int(r[col])
    except (ValueError, IndexError):
        return None


def segments(rows, col=0, drop=5):
    """ターンが drop より大きく戻ったところでゲームを区切る"""
    segs = [[]]
    prev = 0
    for r in rows:
        t = turn_of(r, col)
        if t is None:
            continue
        if t < prev - drop:
            segs.append([])
        segs[-1].append(r)
        prev = t
    return [s for s in segs if s]


def game_rows(L, fn, gi, col=0):
    h, rows = read_csv(L, fn)
    segs = segments(rows, col)
    return h, (segs[gi] if -len(segs) <= gi < len(segs) else [])


def players(L):
    games, cur = [], None
    for line in open(os.path.join(L, 'GameCore.log'), encoding='utf-8', errors='replace'):
        if 'Initializing player from config' in line:
            cur = {}
            games.append(cur)
            continue
        m = re.search(r'Player (\d+): Civilization - (\S+) .*Leader - (\S+) .*Level - (\S+), SlotStatus - (\w+)', line)
        if m and cur is not None:
            cur[int(m.group(1))] = dict(civ=m.group(2), leader=m.group(3), level=m.group(4), slot=m.group(5))
        elif cur:
            cur = None
    return games


def net_messages(L):
    """net_message_debug.log から、ゲームごとのターンの始まりの時刻と、プレイヤーの操作（SEND）を取る"""
    games = []
    g = None
    prev_turn = 0
    for line in open(os.path.join(L, 'net_message_debug.log'), encoding='utf-8', errors='replace'):
        m = re.match(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]\t(.*)', line)
        if not m:
            continue
        ts, body = datetime.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'), m.group(2).rstrip()
        mt = re.match(r'Game Turn: (\d+)$', body)
        if mt:
            t = int(mt.group(1))
            if g is None or t < prev_turn:
                g = dict(turns={}, ends={}, ops=[])
                games.append(g)
            g['turns'].setdefault(t, ts)
            g['cur'] = t
            prev_turn = t
            continue
        me = re.match(r'Game Turn Ended: (\d+)$', body)
        if me and g is not None:
            g['ends'][int(me.group(1))] = ts
            continue
        if g is not None and body.startswith('GameCore SEND:'):
            g['ops'].append((g['cur'], ts, body[len('GameCore SEND: '):]))
    return games


# ---------------------------------------------------------------- 本体

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('logs')
    ap.add_argument('--game', type=int, default=-1)
    ap.add_argument('--player', type=int)
    ap.add_argument('--from', dest='t0', type=int, required=True)
    ap.add_argument('--to', dest='t1', type=int, required=True)
    ap.add_argument('--era', default='')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--note', action='append', default=[], help='冒頭の箇条書きに足す行（何度でも）')
    a = ap.parse_args()
    L = a.logs
    data = load_gamedata()
    N = Names(data)
    allp = players(L)
    gi = a.game - 1 if a.game > 0 else a.game
    P = allp[gi]
    me = a.player if a.player is not None else next(k for k, v in P.items() if v['slot'] == 'Human')
    mycivt = P[me]['civ']
    MAJ = {k for k, v in P.items() if v['level'] == 'CIVILIZATION_LEVEL_FULL_CIV'}
    CS = {k for k, v in P.items() if v['level'] == 'CIVILIZATION_LEVEL_CITY_STATE'}
    civ_by_type = {v['civ']: k for k, v in P.items()}
    barb = N('LOC_CIVILIZATION_BARBARIAN_ADJECTIVE') or '蛮族の'
    barb = barb[:-1] if barb.endswith('の') else barb
    T0, T1 = a.t0, a.t1
    ev = collections.defaultdict(list)   # turn -> [(順番, 文)]
    summ = collections.defaultdict(list)

    # ---- ゲーム内の年：GameCoreAppConfig.log のゲーム速度と、本体の GameSpeeds.xml から計算する
    sp_names = re.findall(r'LOC_(GAMESPEED_\w+?)_NAME', open(os.path.join(L, 'GameCoreAppConfig.log'), encoding='utf-8', errors='replace').read())
    sp_names = [x for x in sp_names if x in data['speeds']]
    speed = sp_names[gi] if -len(sp_names) <= gi < len(sp_names) else (sp_names[-1] if sp_names else 'GAMESPEED_STANDARD')
    fmt_bc = (N('LOC_TIME_BC') or '紀元前{1}年')
    fmt_ad = (N('LOC_TIME_AD') or '西暦{1}年')

    def year_num(t):
        months, left = 0, t - 1
        for n, mon in data['speeds'][speed]:
            k = min(left, n)
            months += k * mon
            left -= k
            if left <= 0:
                break
        return data['start_year'] + months // 12

    def year(t):
        y = year_num(t)
        f = fmt_bc if y < 0 else fmt_ad
        return re.sub(r'\{1_Date[^}]*\}', str(abs(y)), f)

    def tt(t):
        return f'T{t}（{year(t)}）'

    def add(t, order, text, key=None, stext=None):
        if T0 <= t <= T1:
            ev[t].append((order, text))
            if key:
                summ[key].append(f'{tt(t)}：{stext or text}')

    def pname(i, full=False):
        i = int(i)
        if i == BARBARIAN:
            return barb
        if i in P:
            n = N('LOC_' + P[i]['civ'] + '_NAME')
            if full and i in MAJ:
                n += '／' + N('LOC_' + P[i]['leader'] + '_NAME')
            return n
        return f'プレイヤー{i}'

    def civname(civtype):
        return N('LOC_' + civtype + '_NAME')

    me_name = pname(me, True)

    # ---- Player_Stats
    h, ps = game_rows(L, 'Player_Stats.csv', gi)
    hs = h
    stats = collections.defaultdict(dict)
    for r in ps:
        stats[int(r[0])][r[1]] = r
    def st(t, civ=mycivt):
        return stats.get(t, {}).get(civ)
    col = {name: i for i, name in enumerate(hs)}

    # ---- ターンの時刻と操作
    nets = net_messages(L)
    net = nets[gi]
    myops = [(t, ts, body) for t, ts, body in net['ops'] if re.search(rf'ePlayer={me}\b|eFromPlayer={me}\b|Owner={me}\b', body)]

    # ---- 技術：研究の選択（net_message）の順に、技術数が増えたターンへ割り当てる
    research = []
    for t, ts, body in myops:
        m = re.search(r'PlayerOperation: ePlayer=\d+, InsertMode=\d+, RESEARCH, (TECH_\w+)', body)
        if m and (not research or research[-1][1] != m.group(1)):
            research.append((t, m.group(1)))
    _, boosts_rows = game_rows(L, 'Game_Boosts.csv', gi)
    myboost = collections.defaultdict(set)
    for r in boosts_rows:
        if r[1] == str(me):
            myboost[int(r[0])].add(r[2])
    techcnt = {t: int(v[mycivt][col['Techs']]) for t, v in stats.items() if mycivt in v}
    tech_done = []   # (turn, tech or None)
    cur = None
    ri = 0
    pending = 0
    turns_sorted = sorted(techcnt)
    for t in turns_sorted:
        inc = techcnt[t] - techcnt.get(t - 1, 0) if t > 1 else techcnt[t]
        inc -= pending
        pending = 0
        for _ in range(max(inc, 0)):
            tech_done.append((t, cur))
            cur = None
        while ri < len(research) and research[ri][0] == t:
            nt = research[ri][1]
            if cur is not None and cur in myboost.get(t, set()):
                # ひらめきで研究中の技術がターンの途中で完了した（数は次のターンに増える）
                tech_done.append((t, cur))
                pending += 1
            cur = nt
            ri += 1
    for t, tech in tech_done:
        if tech:
            add(t, 10, f'技術「{N(tech)}」を完了', 'tech', N(tech))
        else:
            add(t, 10, '技術を1つ完了（名前はログから分からない）', 'tech', '（名前不明）')

    # ---- 社会制度：AI_GovtPolicies.csv の候補から消えたもの
    _, gp = game_rows(L, 'AI_GovtPolicies.csv', gi)
    civic_cand = collections.defaultdict(set)
    for r in gp:
        if r[1] == str(me) and r[2] == 'Civic':
            civic_cand[int(r[0])].add(r[3])
    ts_ = sorted(civic_cand)
    for x, y in zip(ts_, ts_[1:]):
        for c in sorted(civic_cand[x] - civic_cand[y]):
            add(y, 11, f'社会制度「{N(c)}」を完了', 'civic', N(c))

    # ---- ひらめき・天啓
    prog = {'Unstarted': '研究前', 'In Progress': '研究中', 'Completed': '完了済み'}
    for r in boosts_rows:
        if r[1] != str(me):
            continue
        t = int(r[0])
        kind = 'ひらめき' if r[2].startswith('TECH_') else '天啓'
        add(t, 12, f'{kind}「{N(r[2])}」（{prog.get(r[3], r[3])}）', 'boost', f'{kind}「{N(r[2])}」')

    # ---- 政体・社会政策・使節・偉人の勧誘などの操作
    govs = data['govs']
    for t, ts, body in myops:
        m = re.search(r'CHANGE_GOVERNMENT \(\d+\), iData1=(\d+)', body)
        if m:
            g = govs[int(m.group(1))] if int(m.group(1)) < len(govs) else m.group(1)
            add(t, 13, f'**政体を{N(g)}にする**', 'gov', N(g))
        if 'MULTI_POLICY_CHANGE' in body:
            add(t, 14, '社会政策を入れ替える（どの政策かはログにない）', 'policy', '入れ替え')

    # ---- 都市：建設（UnitOperations.log）と名前（建設キューに初めて出た都市）
    _, uo = game_rows(L, 'UnitOperations.log', gi)
    found_turns = [int(r[0]) for r in uo if len(r) > 4 and r[2] == str(me) and 'UNITOPERATION_FOUND_CITY' in r[4]]
    found_turns = sorted(set(found_turns))
    _, bq = game_rows(L, 'City_BuildQueue.csv', gi)
    first_seen = {}
    for r in bq:
        first_seen.setdefault(r[1], int(r[0]))
    citydef = data['citydef']
    mine_first = sorted([(t, c) for c, t in first_seen.items() if mycivt in citydef.get(c, ())])
    owned = {}   # 都市名 -> (持ち始め, 手放した)
    pairs = []
    used = set()
    for ft in found_turns:
        cand = [(t, c) for t, c in mine_first if c not in used and t in (ft, ft + 1)]
        if cand:
            t, c = cand[0]
            used.add(c)
            pairs.append((ft, c))
            owned[c] = [ft, None]
        else:
            pairs.append((ft, None))
    for ft, c in pairs:
        nm = N(c) if c else '（名前不明）'
        add(ft, 20, f'**都市「{nm}」を建設**', 'city', nm)

    # ---- 都市の移り変わり（Cultural_Identity.csv）
    _, ci = game_rows(L, 'Cultural_Identity.csv', gi)
    owner_change = []
    for r in ci:
        t, kind, city, owner = int(r[0]), r[1], r[2], int(r[3])
        owner_change.append((t, city, owner))
        verb = '占領される' if kind == 'City Captured' else '移る'
        if city in owned and owned[city][1] is None and owner != me:
            owned[city][1] = t
            add(t, 21, f'**都市「{N(city)}」が{pname(owner)}に{verb}**', 'city', f'{N(city)}を失う（{pname(owner)}へ）')
            continue
        if owner == me:
            owned[city] = [t, None]
            add(t, 21, f'**都市「{N(city)}」が{"自国に占領される" if kind == "City Captured" else "自国に加わる"}**', 'city', f'{N(city)}が加わる')
            continue
        add(t, 90, f'（他国）都市「{N(city)}」が{pname(owner)}に{verb}（人口{r[5]}）', 'world', f'{N(city)}が{pname(owner)}へ' + ('（占領）' if kind == 'City Captured' else ''))

    def is_mine(city, t):
        o = owned.get(city)
        return o is not None and o[0] <= t and (o[1] is None or t < o[1])

    # 都市の持ち主（他国の遺産のため）：既定の文明と移り変わりから推す
    def owner_of(city, t):
        last = None
        for tt, c, o in owner_change:
            if c == city and tt <= t:
                last = o
        if last is not None:
            return pname(last)
        civs = [c for c in citydef.get(city, ()) if c in civ_by_type]
        return civname(civs[0]) if civs else '?'

    # ---- 生産の完了（City_BuildQueue.csv）
    def kind_of(item):
        if item in data['wonders']:
            return '遺産'
        if item.startswith('UNIT_'):
            return 'ユニット'
        if item.startswith('DISTRICT_'):
            return '区域'
        if item.startswith('PROJECT_'):
            return 'プロジェクト'
        return '建造物'
    done_items = set()
    for r in bq:
        t, city, item = int(r[0]), r[1], r[3]
        try:
            curp, need = float(r[4]), float(r[5])
        except ValueError:
            continue
        if curp < need or need <= 0:
            continue
        key = (t, city, item)
        if key in done_items:
            continue
        done_items.add(key)
        k = kind_of(item)
        if is_mine(city, t):
            if k == '遺産':
                add(t, 30, f'**{N(city)}：遺産「{N(item)}」が完成**', 'wonder', f'{N(item)}（{N(city)}）')
            elif k == 'ユニット':
                add(t, 31, f'{N(city)}：{N(item)}が完成', 'unit', f'{N(item)}（{N(city)}）')
            else:
                add(t, 31, f'{N(city)}：{k}「{N(item)}」が完成', 'build', f'{N(item)}（{N(city)}）')
        elif k == '遺産':
            add(t, 91, f'（他国）遺産「{N(item)}」が完成（{N(city)}、{owner_of(city, t)}）', 'world_wonder', f'遺産「{N(item)}」が完成（{N(city)}、{owner_of(city, t)}）')

    # ---- 人口
    for t in range(T0, T1 + 1):
        a_, b_ = st(t - 1), st(t)
        if a_ and b_ and a_[col['Population']] != b_[col['Population']]:
            add(t, 35, f'人口：合計 {a_[col["Population"]]}→{b_[col["Population"]]}')

    # ---- 偉人
    _, gpr = game_rows(L, 'Game_GreatPeople.csv', gi)
    for r in gpr:
        t = int(r[0])
        if r[1] == 'Granted to Player' and len(r) > 6 and r[6] == str(me):
            add(t, 40, f'**偉人「{N(r[2])}」（{N(r[3])}）を得る**', 'gp', f'{N(r[2])}（{N(r[3])}）')
        elif r[1] == 'Great Person Activated' and len(r) > 5 and r[5] == str(me):
            add(t, 41, f'偉人「{N(r[2])}」の能力を使う')

    # ---- 宗教
    _, rel = game_rows(L, 'Game_Religion.csv', gi)
    for r in rel:
        t, pl, act = int(r[0]), r[1], r[2]
        belief = N(r[3]) if r[3] != 'N/A' else ''
        city = N(r[4]) if r[4] != 'N/A' else ''
        if pl == str(me):
            if act == 'Found Pantheon':
                add(t, 50, f'**パンテオン「{belief}」を創始**', 'rel', f'パンテオン「{belief}」')
            elif act == 'Found Religion':
                add(t, 50, f'**宗教「{belief}」を創始**', 'rel', f'宗教「{belief}」を創始')
            elif act.startswith('Add belief'):
                add(t, 51, f'信仰「{belief}」を選ぶ', 'rel', f'信仰「{belief}」')
        elif act == 'Found Religion':
            add(t, 92, f'（他国）{pname(pl)}が宗教「{belief}」を創始', 'world', f'{pname(pl)}が{belief}を創始')

    # ---- 総督
    _, gov = game_rows(L, 'Governors.csv', gi)
    gv = {'Governor Appointed': '任命', 'Governor Promoted': '昇進', 'Governor Established': '着任',
          'Governor Unassigned': '配置を解く', 'Governor Assigned': '配置'}
    appointed = {(int(r[0]), r[2]) for r in gov if r[3] == mycivt and r[1] == 'Governor Appointed'}
    for r in gov:
        if r[3] != mycivt:
            continue
        t = int(r[0])
        nm = N(r[2])
        if r[2].startswith('LOC_SECRETSOCIETY_'):
            nm += '（秘密結社の総督）'
        if r[1] == 'Governor Promoted' and (t, r[2]) in appointed:
            continue   # 任命と同じターンの昇進は、任命にともなうもの
        if r[1] == 'Governor Assigned':
            add(t, 55, f'総督「{nm}」を{N(r[4])}に配置', 'gov2', f'{nm}を{N(r[4])}へ')
        elif r[1] == 'Governor Unassigned':
            add(t, 55, f'総督「{nm}」を{N(r[4])}から外す')
        elif r[1] == 'Governor Appointed':
            add(t, 55, f'総督「{nm}」を任命', 'gov2', f'{nm}を任命')
        elif r[1] == 'Governor Established':
            add(t, 56, f'総督「{nm}」が着任')
        elif r[1] == 'Governor Promoted':
            add(t, 56, f'総督「{nm}」が昇進（どの昇進かはログにない）', 'gov2', f'{nm}が昇進')

    # ---- 使節と宗主
    _, inf = game_rows(L, 'Game_Influence.csv', gi)
    tok = collections.defaultdict(list)
    for r in inf:
        t = int(r[0])
        if r[2] != str(me):
            continue
        if r[1].startswith('Token used'):
            tok[(t, int(r[3]))].append(int(r[4]))
        elif r[1].startswith('Unique Bonus'):
            add(t, 61, f'**都市国家「{pname(r[3])}」の宗主になる**（Unique Bonus received、使節 {r[4]} 人）', 'suz', pname(r[3]))
    for (t, d), ns in sorted(tok.items()):
        add(t, 60, f'使節を{pname(d)}に{len(ns)}人送る（{pname(d)}への使節は計{max(ns)}人）', 'env', f'{pname(d)}に{len(ns)}人')

    # ---- 外交
    _, dip = game_rows(L, 'DiplomacySummary.csv', gi)
    elim_turn = {}
    for k in MAJ:
        civ = P[k]['civ']
        had = False
        for t in sorted(stats):
            r = stats[t].get(civ)
            if r and int(r[col['Num Cities']]) > 0:
                had = True
            elif had and (not r or int(r[col['Num Cities']]) == 0):
                elim_turn[k] = t
                break
    def deal_text(d, frm, to):
        out = []
        for item in [x.strip() for x in d.split(';') if x.strip()]:
            m = re.match(r'(-?\d+) (.+?) for (\d+) turns from (\d+) to (\d+)', item)
            if not m:
                out.append(item)
                continue
            n, what, turns, f_, t_ = m.groups()
            what_j = {'Gold': 'ゴールド', 'Open Borders': '国境開放', 'Favor': '外交的支持'}.get(what, N(what))
            amount = '' if what == 'Open Borders' else f'{n}'
            dur = f'（{turns}ターン）' if turns != '0' else ''
            per = '毎ターン' if turns != '0' and what != 'Open Borders' else ''
            out.append(f'{pname(f_)}→{pname(t_)}：{what_j}{per}{amount}{dur}')
        return '、'.join(out)
    seen_war = set()
    for r in dip:
        t = int(r[0])
        act = r[3]
        try:
            ini = int(r[1])
        except ValueError:
            continue
        rec_s = r[2]
        mt = re.match(r'Team (\d+)', rec_s)
        rec = int(mt.group(1)) if mt else int(rec_s) if rec_s.lstrip('-').isdigit() else None
        if rec is None:
            continue
        mine = me in (ini, rec)
        other = rec if ini == me else ini
        if act == 'Met' and ini == me and other not in (BARBARIAN, FREE_CITIES):
            kind = '文明' if other in MAJ else '都市国家' if other in CS else ''
            add(t, 58, f'**{pname(other, True)}と出会う**' if other in MAJ else f'都市国家「{pname(other)}」と出会う', 'met', pname(other, True) + ('（都市国家）' if other in CS else ''))
        elif act == 'Delegation' and mine:
            add(t, 71, f'代表団を{pname(rec)}に送る' if ini == me else f'{pname(ini)}から代表団が来る', 'dip', f'代表団（{pname(ini)}→{pname(rec)}）')
        elif act == 'Embassy' and mine:
            add(t, 71, f'大使館を{pname(rec)}に置く' if ini == me else f'{pname(ini)}が大使館を置く', 'dip', f'大使館（{pname(ini)}→{pname(rec)}）')
        elif act == 'Declared Friends' and ini == me:
            add(t, 72, f'**{pname(rec)}と友好を宣言**', 'dip', f'{pname(rec)}と友好')
        elif act == 'Denounced' and mine:
            add(t, 72, f'{pname(ini)}が{pname(rec)}を非難', 'dip', f'非難（{pname(ini)}→{pname(rec)}）')
        elif act in ('Deal Proposed', 'Deal Accepted', 'Deal Closed', 'Deal Rejected') and mine:
            jp = {'Deal Proposed': '取引の提案', 'Deal Accepted': '取引の受け入れ', 'Deal Closed': '取引の成立', 'Deal Rejected': '取引の拒否'}[act]
            tail = '（どう答えたかはログにない）' if act == 'Deal Proposed' else ''
            add(t, 73, f'{jp}（{pname(ini)}から{pname(rec)}へ）：{deal_text(r[4], ini, rec)}{tail}', 'deal', f'{jp}（{pname(ini)}→{pname(rec)}）')
        elif act == 'Alliance Starts' and mine:
            add(t, 72, f'**{pname(other)}と同盟（{N(r[4]) if r[4] else ""}）**', 'dip', f'{pname(other)}と同盟')
        elif act == 'Individual Declaring War on Team START' and (mine or (ini in MAJ and rec in MAJ)):
            k = (t, ini, rec)
            if k in seen_war:
                continue
            seen_war.add(k)
            why = {'Surprise': '奇襲', 'Formal': '正式な宣戦', 'Emergency War': '緊急事態による戦争', 'Suzerain War': '宗主の戦争'}.get(r[4], r[4])
            add(t, 74 if mine else 93, f'**{pname(ini)}が{pname(rec)}に宣戦（{why}）**' if mine else f'（他国）{pname(ini)}が{pname(rec)}に宣戦（{why}）', 'war' if mine else 'world', f'{pname(ini)}→{pname(rec)}（{why}）')
        elif act == 'Peace' and (mine or (ini in MAJ and rec in MAJ)):
            if rec in elim_turn and elim_turn[rec] in (t, t + 1):
                continue
            if mine:
                add(t, 74, f'**{pname(other)}と講和**', 'war', f'{pname(other)}と講和')
            elif ini < rec:
                add(t, 93, f'（他国）{pname(ini)}と{pname(rec)}が講和', 'world', f'{pname(ini)}と{pname(rec)}が講和')
        elif act == 'City Capture' and (mine or ini in MAJ):
            pass   # Cultural_Identity.csv で書く
    for k, t in elim_turn.items():
        if k != me:
            add(t, 94, f'（他国）**{pname(k, True)}が滅びる**（最後の都市を失った）', 'world', f'{pname(k, True)}が滅びる')

    # ---- 交易路
    _, tr = game_rows(L, 'Game_TradeManager.csv', gi)
    for r in tr:
        t, evn, o, d = int(r[0]), r[1], r[2], r[3]
        if not is_mine(o, t):
            continue
        ow = owner_of(d, t)
        dest = N(d) if is_mine(d, t) else f'{N(d)}（都市国家）' if ow == N(d) else f'{N(d)}（{ow}）'
        if evn == 'Route Started':
            add(t, 80, f'交易路を開く：{N(o)}→{dest}', 'trade', f'{N(o)}→{dest}')
        else:
            why = re.sub(r'Route Ended \((.*)\)', r'\1', evn)
            why = {'Expired': '期限', 'Plundered': '略奪', 'City Destroyed': '都市の消滅', 'War Declared': '宣戦', 'Canceled': '取り消し'}.get(why, why)
            add(t, 81, f'交易路が終わる：{N(o)}→{dest}（{why}）')

    # ---- 戦闘
    _, cb = game_rows(L, 'CombatLog.csv', gi)
    fights = collections.defaultdict(list)
    for r in cb:
        t = int(r[0])
        try:
            at, df = int(r[1]), int(r[2])
        except ValueError:
            continue
        if me not in (at, df):
            continue
        fights[t].append((at, df, r[5], r[6]))
    def unit_of(pl, unit):
        """「蛮族の騎乗兵」のように名前に持ち主が入っているユニットは、そのまま"""
        n = N(unit)
        owner = pname(pl)
        return n if n.startswith(owner) else f'{owner}の{n}'
    for t, fs in fights.items():
        parts = []
        for at, df, ut, dt in fs:
            if at == me:
                parts.append(f'自国の{N(ut)}が{unit_of(df, dt)}を攻撃')
            else:
                parts.append(f'{unit_of(at, ut)}が自国の{N(dt)}を攻撃')
        c = collections.Counter(parts)
        txt = '、'.join(f'{k}' + (f'（{v}回）' if v > 1 else '') for k, v in c.items())
        add(t, 85, f'戦闘：{txt}')
        if T0 <= t <= T1:
            for at, df, ut, dt in fs:
                summ['combat_n'].append((pname(df if at == me else at), at == me))

    # ---- 英雄・秘密結社
    _, hero = game_rows(L, 'Game_HeroesManager_Events.csv', gi)
    hv = {'Goody Hut': '部族の村', 'Influence City State': '都市国家への影響力', 'Encounter': '出会い', 'Natural Wonder': '自然遺産', 'New Continent': '新しい大陸'}
    for r in hero:
        if r[1] != str(me) or r[2] == 'None':
            continue
        t = int(r[0])
        e = r[3]
        if e.startswith('Discovered by:'):
            how = e.split(':', 1)[1].strip()
            add(t, 86, f'英雄「{r[2]}」の伝説を見つける（{hv.get(how, how)}）', 'hero', f'{r[2]}を見つける')
        elif e == 'Created':
            add(t, 86, f'**英雄「{r[2]}」が現れる**', 'hero', f'{r[2]}が現れる')
        elif e == 'Lifespan expired':
            add(t, 86, f'英雄「{r[2]}」の寿命が尽きる', 'hero', f'{r[2]}の寿命が尽きる')
        elif e == 'Killed in combat':
            add(t, 86, f'英雄「{r[2]}」が戦死', 'hero', f'{r[2]}が戦死')
    _, ss = game_rows(L, 'Game_SecretSocietyManager.csv', gi)
    for r in ss:
        t = int(r[0])
        if re.search(rf'Discovered by Player {me}$', r[2]):
            add(t, 87, f'秘密結社「{N(r[1])}」を知る', 'ss', f'{N(r[1])}を知る')
        elif re.search(rf'Player {me} Joins', r[2]):
            add(t, 87, f'**秘密結社「{N(r[1])}」に入る**', 'ss', f'{N(r[1])}に入る')

    # ---- 産業・独占（Game_Economic.csv。ゲームの区切りは Initial Resources の行）
    h, eco = read_csv(L, 'Game_Economic.csv')
    egames, prev_init = [], False
    for r in eco:
        init = r[1] == 'Initial Resources'
        if init and not prev_init:
            egames.append([])
        if egames:
            egames[-1].append(r)
        prev_init = init
    if -len(egames) <= gi < len(egames):
        for r in egames[gi]:
            if r[-1] != mycivt:
                continue
            t = int(r[0])
            jp = {'Industry Established': '産業を興す', 'Monopoly Gained': '独占を得る', 'Monopoly Lost': '独占を失う'}.get(r[1], r[1])
            add(t, 88, f'{jp}：{N(r[2])}（{r[3]}）', 'eco', f'{jp}：{N(r[2])}')

    # ---- 時代と歴史的瞬間（DynamicEmpires.csv。ゲームの区切りは時代が戻るところ）
    h, de = read_csv(L, 'DynamicEmpires.csv')
    dgames, prev_era = [[]], -1
    for r in de:
        era = r[1].replace('LOC_ERA_', '').replace('_NAME', '') if len(r) > 1 else ''
        ei = ERA_ORDER.index(era) if era in ERA_ORDER else -1
        if 0 <= ei < prev_era:
            dgames.append([])
        dgames[-1].append(r)
        if ei >= 0:
            prev_era = ei
    era_info = []
    mydesc = 'LOC_' + mycivt + '_DESCRIPTION'
    if -len(dgames) <= gi < len(dgames):
        for r in dgames[gi]:
            if len(r) < 5 or r[2] != mydesc:
                continue
            t = int(r[0])
            era = N(r[1])
            if r[3] in ('-', 'DarkAge', 'DarkAge Consecutive') or r[4] in ('-', 'GoldenAge', 'GoldenAge Consecutive', 'Heroic'):
                if r[3].startswith('DarkAge'):
                    age = '暗黒時代' + ('（連続）' if 'Consecutive' in r[3] else '')
                elif r[4].startswith('GoldenAge'):
                    age = '黄金時代' + ('（連続）' if 'Consecutive' in r[4] else '')
                elif r[4] == 'Heroic':
                    age = '英雄時代'
                else:
                    age = '通常の時代'
                score = r[6] if len(r) > 6 else ''
                era_info.append((t, era, age, score))
                add(t, 1, f'**{era}に入る。{age}になる**（直前の時代の時代スコア {score}）', 'era', f'{era}に入る：{age}（直前の時代の時代スコア {score} による）')
            else:
                add(t, 2, f'歴史的瞬間「{N(r[3])}」（時代スコア +{r[4]}）', 'moment', N(r[3]))

    # ---------------------------------------------------------------- 書き出し
    tstart = net['turns'].get(T0)
    tend = net['ends'].get(T1) or net['turns'].get(T1)
    all_turns = sorted(net['turns'])
    game_start = net['turns'].get(all_turns[0]) if all_turns else None
    last_turn = max(stats) if stats else None

    out = []
    w = out.append
    w(f'# {me_name}：{a.era + " " if a.era else ""}T{T0}〜T{T1} の行動記録')
    w('')
    w('Civ6 の Logs フォルダから取り出した、ゲーム上の出来事の記録。解釈は入れず、ログにあることだけを書く。ログから割り出したものは、そう書いてある。')
    w('')
    w(f'* プレイヤー{me}：{me_name}（人間）')
    if game_start:
        w(f'* ゲーム：{game_start:%Y-%m-%d %H:%M} ごろに始めた新しいゲーム（net_message_debug.log）。ログには T{last_turn} まで残っている')
    w(f'* 範囲：{a.era + " " if a.era else ""}T{T0}〜T{T1}' + (f'（{tstart:%H:%M}〜{tend:%H:%M} ごろに遊んだ）' if tstart and tend else '') +
      f'。ゲーム内の年は {year(T0)}〜{year(T1)}')
    first_year = data['speeds'][speed][0][1] // 12
    w(f'* ゲーム内の年：ログには出ないので、ゲーム速度（{N("LOC_" + speed + "_NAME")}、GameCoreAppConfig.log）と、本体の GameSpeeds.xml の「1ターンで進む年数」から計算した。'
      f'T1 が{year(1)}で、はじめの{data["speeds"][speed][0][0]}ターンは1ターンで{first_year}年ずつ進む。ターンごとの見出しと、まとめの各項目に書いた')
    zero = [t for t in range(T0, T1 + 1) if year_num(t) == 0]
    if zero:
        w(f'  * T{zero[0]} は計算ではちょうど0年になる。ゲーム画面でどう表示されるか（{year(zero[0])}か）は確かめていない')
    for n_ in a.note:
        w(f'* {n_}')
    w(f'* 作成：[civ6_record.py](../../../ゲームログ解析/スクリプト/civ6_record.py)。名前はゲーム本体の日本語テキストから引いた')
    w('* ターンの数え方：技術・社会制度・生産・人口の変化は、そのターンの始めに起きたもの。都市の建設・政体・使節などの操作は、そのターンのうちに行ったもの')
    w('')
    w('### ログについて')
    w('')
    w('* 技術：net_message_debug.log に残る「研究の選択」の順番を、Player_Stats.csv で技術の数が増えたターンに割り当てた（割り出し）。社会制度：AI_GovtPolicies.csv で、自国の候補から消えたターン（割り出し。完了数とすべて合う）')
    w('* 生産：City_BuildQueue.csv で、生産量が必要量に達したもの。ゴールドや信仰で買ったものは出てこない')
    w('* 他国の遺産の持ち主：都市名の既定の文明と、都市の移り変わり（Cultural_Identity.csv）から推した')
    w('* ログに残らないもの：どの社会政策を入れたか、取引の提案にどう答えたか、労働者が作った施設の種類、ユニットの移動、都市ごとの人口、戦闘の勝ち負け、部族の村の中身')
    w('')
    w('---')
    w('')
    w('## 1. まとめ')
    w('')

    def section(title, key, fmt=None):
        items = summ.get(key, [])
        w(f'### {title}')
        w('')
        if not items:
            w('* なし')
        for x in items:
            w(f'* {x}')
        w('')

    # 都市
    w('### 都市')
    w('')
    before = [(ft, c) for ft, c in pairs if ft < T0 and c and is_mine(c, T0)]
    if before:
        w('* この範囲の前からあった都市：' + '、'.join(f'{N(c)}（T{ft}、{year(ft)}）' for ft, c in before))
    for x in summ.get('city', []):
        w(f'* {x}')
    if not summ.get('city'):
        w('* この範囲で建てた都市はない')
    w('')
    w('### 時代')
    w('')
    if T0 == 1:
        w(f'* {tt(1)}：{N("LOC_ERA_ANCIENT_NAME")}から始まる')
    for x in summ.get('era', []):
        w(f'* {x}')
    nxt = [x for x in era_info if x[0] == T1 + 1]
    if nxt:
        t, era, age, score = nxt[0]
        w(f'* {tt(t)}：次の時代の始まり。この範囲でためた時代スコア {score} により、{era}は{age}になる')
    w('')
    if summ.get('moment'):
        section('歴史的瞬間', 'moment')
    section('完了した技術', 'tech')
    section('完了した社会制度', 'civic')
    section('ひらめき・天啓', 'boost')
    w('### 政体と社会政策')
    w('')
    for x in summ.get('gov', []):
        w(f'* {x}')
    np_ = len(summ.get('policy', []))
    w(f'* 社会政策の入れ替え：{np_}回（中身はログにない）')
    w('')
    section('完成した遺産', 'wonder')
    section('偉人', 'gp')
    section('宗教', 'rel')
    section('総督', 'gov2')
    section('出会った文明と都市国家', 'met')
    section('宗主になった都市国家', 'suz')
    section('外交', 'dip')
    if summ.get('deal'):
        section('取引', 'deal')
    if summ.get('war'):
        section('戦争', 'war')
    w('### 交易路')
    w('')
    w(f'* 開いた交易路：{len(summ.get("trade", []))}本')
    for x in summ.get('trade', []):
        w(f'  * {x}')
    w('')
    if summ.get('hero') or summ.get('ss'):
        section('英雄', 'hero')
        section('秘密結社', 'ss')
    if summ.get('eco'):
        section('産業と独占', 'eco')
    w('### 戦闘')
    w('')
    cc = collections.Counter(summ.get('combat_n', []))
    if not cc:
        w('* なし')
    for (who, att), n in sorted(cc.items(), key=lambda x: (x[0][0], not x[0][1])):
        w(f'* {who}と：{"自国が攻撃" if att else "攻撃された"} {n}回')
    w('')

    # 国力の推移
    w('### 国力の推移')
    w('')
    w('Player_Stats.csv の、各ターンの始めの数字。')
    w('')
    cols = [('都市', 'Num Cities'), ('人口', 'Population'), ('技術', 'Techs'), ('社会制度', 'Civics'),
            ('陸上ユニット', 'Land Units'), ('海上ユニット', 'Naval Units'), ('領土', 'TILES: Owned'), ('改善済み', 'Improved'),
            ('ゴールド', 'BALANCE: Gold'), ('信仰', 'Faith'), ('科学', 'YIELDS: Science'), ('文化', 'Culture'),
            ('ゴールド収入', 'Gold'), ('信仰収入', 'Faith'), ('生産', 'Production'), ('食料', 'Food')]
    # 列名が重なるもの（Gold・Faith）は位置で引く
    idx = []
    seen = collections.Counter()
    for label, cname in cols:
        positions = [i for i, hname in enumerate(hs) if hname == cname]
        if cname in ('Gold', 'Faith'):
            # BALANCE の後ろ、YIELDS の中の Gold / Faith
            positions = [i for i in positions if i > col.get('YIELDS: Science', 0)] or positions
            if label == '信仰':
                positions = [col['BALANCE: Gold'] + 1]
        idx.append((label, positions[0] if positions else None))
    w('| ターン | 年 | ' + ' | '.join(l for l, _ in idx) + ' |')
    w('|' + '---|' * (len(idx) + 2))
    marks = sorted(set([T0] + list(range((T0 // 10 + 1) * 10, T1 + 1, 10)) + [T1]))
    for t in marks:
        r = st(t)
        if not r:
            continue
        vals = []
        for l, i in idx:
            v = r[i] if i is not None and i < len(r) else ''
            try:
                fv = float(v)
                v = str(int(fv)) if fv == int(fv) else f'{fv:.1f}'
            except ValueError:
                pass
            vals.append(v)
        w(f'| T{t} | {year(t)} | ' + ' | '.join(vals) + ' |')
    w('')

    # 各文明
    _, sc = game_rows(L, 'Game_PlayerScores.csv', gi)
    score = {(int(r[0]), int(r[1])): r[2] for r in sc}
    w(f'### {tt(T1)}の各文明')
    w('')
    w('| 文明 | 都市 | 人口 | 技術 | 社会制度 | 領土 | 科学 | 文化 | 生産 | ゴールド収入 | スコア |')
    w('|---|---|---|---|---|---|---|---|---|---|---|')
    rowsT = []
    for k in sorted(MAJ):
        r = st(T1, P[k]['civ'])
        if not r or int(r[col['Num Cities']]) == 0:
            continue
        g_i = [i for i, hname in enumerate(hs) if hname == 'Gold'][-1]
        rowsT.append((int(r[col['Population']]), k, r, g_i))
    for _, k, r, g_i in sorted(rowsT, key=lambda x: -x[0]):
        nm = pname(k, True)
        if k == me:
            nm = f'**{nm}**'
        def f(v):
            try:
                fv = float(v)
                return str(int(fv)) if fv == int(fv) else f'{fv:.1f}'
            except ValueError:
                return v
        w(f'| {nm} | {r[col["Num Cities"]]} | {r[col["Population"]]} | {r[col["Techs"]]} | {r[col["Civics"]]} | {r[col["TILES: Owned"]]} | '
          f'{f(r[col["YIELDS: Science"]])} | {f(r[col["Culture"]])} | {f(r[col["Production"]])} | {f(r[g_i])} | {score.get((T1, k), "")} |')
    gone = [k for k in sorted(MAJ) if k in elim_turn and elim_turn[k] <= T1]
    if gone:
        w('')
        w('* すでに滅んだ文明：' + '、'.join(f'{pname(k, True)}（T{elim_turn[k]}）' for k in gone))
    w('')
    w('### 世界の出来事')
    w('')
    ww = summ.get('world', []) + summ.get('world_wonder', [])
    ww.sort(key=lambda s: int(re.match(r'T(\d+)', s).group(1)))
    if not ww:
        w('* なし')
    for x in ww:
        w(f'* {x}')
    w('')
    w('---')
    w('')
    w('## 2. ターンごとの出来事')
    w('')
    for t in range(T0, T1 + 1):
        w(f'### {tt(t)}')
        w('')
        items = [x for x in sorted(ev.get(t, []), key=lambda x: x[0]) if x[1]]
        if not items:
            w('* 記録なし')
        for _, text in items:
            w(f'* {text}')
        w('')
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'w', encoding='utf-8', newline='\n').write('\n'.join(out).rstrip() + '\n')
    # 確かめ用
    sys.stdout.reconfigure(encoding='utf-8')
    print('techs named', sum(1 for _, x in tech_done if x), 'unknown', sum(1 for _, x in tech_done if not x), 'stat', techcnt.get(max(techcnt)))
    # 技術の割り出しの確かめ：完了したターンに、次の研究を選んでいるか
    rturns = collections.defaultdict(list)
    for t, tech in research:
        rturns[t].append(tech)
    odd = [(t, tech) for t, tech in tech_done if tech and t not in rturns and t != max(techcnt)]
    print('完了のターンに次の研究の選択がないもの:', odd or 'なし')
    print('cities', pairs)
    print('written', a.out)


if __name__ == '__main__':
    main()
