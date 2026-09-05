import urllib.request
import csv
import datetime
import math
from collections import Counter
import json
import io
import os

# mk-mode SITE が公開している第1回からの全回データCSV
# （旧ソース loto6.the-luck.jp は名前解決できなくなったため差し替え）
DATA_URL = "https://www.mk-mode.com/rails/loto/LOTO6_ALL.csv"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loto6_history.json")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loto_analysis.html")


def load_cache():
    """ローカルに保存済みの実データ（前回までの取得結果）を読み込む。"""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_cache(history):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False)


def fetch_latest():
    """公開CSVから第1回〜最新回の全データを取得してパースする。"""
    req = urllib.request.Request(DATA_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as response:
        content = response.read().decode('utf-8')

    f = io.StringIO(content)
    reader = csv.reader(f)
    next(reader, None)  # ヘッダー行をスキップ
    history = []
    skipped = 0
    for row in reader:
        if not row or len(row) < 9:
            skipped += 1
            continue
        try:
            # 本数字6つ (昇順ソート)
            main_nums = sorted(int(row[i]) for i in range(2, 8))
            rec = {
                "id": int(row[0]),
                "date": row[1],
                "main": main_nums,
                "bonus": int(row[8])
            }
            # 配当データ(1等口数・1等金額・キャリーオーバー)はトリビアで使う。
            # 古い回や形式変更で欠けていても本体は生かしたいので、ここだけ別に握りつぶす。
            try:
                rec["win1"] = int(row[9])
                rec["amt1"] = int(row[14])
                rec["carry"] = int(row[19])
            except (ValueError, IndexError):
                pass
            history.append(rec)
        except ValueError:
            skipped += 1
            continue

    if skipped:
        print(f"⚠ CSVの{skipped}行を解析できずスキップしました。データ提供元のCSV形式が変わっていないか確認してください。")

    # 時系列（古い順）に並べ替え
    history.sort(key=lambda x: x["id"])
    return history


def latest_expected_draw_date():
    """JSTの「今」から見て、すでに抽選が終わっているはずの直近の抽選日を返す。
    ロト6の抽選は毎週月曜・木曜の18:45(JST)。結果反映の余裕をみて19:30を過ぎたら
    その日の分は出ているものとして扱う。"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    d = now.date()
    if not (now.hour > 19 or (now.hour == 19 and now.minute >= 30)):
        d -= datetime.timedelta(days=1)
    while d.weekday() not in (0, 3):  # 0=月, 3=木
        d -= datetime.timedelta(days=1)
    return d


def check_freshness(history):
    """手元のデータが直近の抽選日まで追いついているかを判定する。
    データ提供元のCSV更新が遅れると取りこぼしたまま気づけないため、
    (追いついているか, 人間向けメッセージ) を返して呼び出し側に知らせる。"""
    expected = latest_expected_draw_date()
    if not history:
        return False, "データが1件もありません。"
    latest = history[-1]
    try:
        y, m, d = (int(x) for x in latest["date"].split("/"))
        latest_date = datetime.date(y, m, d)
    except (ValueError, KeyError):
        return False, f"最新回の日付「{latest.get('date')}」を解釈できませんでした。"
    if latest_date >= expected:
        return True, f"最新回まで取り込み済みです（第{latest['id']}回 / {latest['date']}）。"
    behind = 0
    d = expected
    while d > latest_date:
        if d.weekday() in (0, 3):
            behind += 1
        d -= datetime.timedelta(days=1)
    return False, (
        f"直近の抽選日({expected:%Y/%m/%d})の分がまだ入っていません"
        f"（手元の最新は第{latest['id']}回 / {latest['date']}、{behind}回分の遅れ）。"
        "データ提供元のCSV更新待ちの可能性が高く、次回の実行で自動的に追いつきます。"
    )


def compute_tier_distribution(history):
    """盤面・座標タブと同じアルゴリズム(列=昇順順位・段=move-to-front方式)で、
    (列,段)ごとの再登場回数を全期間で集計する。
    戻り値は (段ごとの再登場回数, 総数, 段ごとの平均在籍数)。
    在籍数は「その段に何個の数字がいるか」で、公平な抽選なら再登場の割合は
    在籍数÷43になるはず、という理論値を出すのに使う。"""
    tier_rows = 11
    cols = [[] for _ in range(6)]
    for i in range(1, 44):
        cols[(i - 1) % 6].append(i)
    seen = set()
    tier_counts = [0] * (tier_rows + 1)
    occupancy = [0] * (tier_rows + 1)
    total = 0
    for d in history:
        m = d["main"]
        # その回を引く直前の状態で、各段に何個いるかを数える
        for t in range(tier_rows + 1):
            occupancy[t] += sum(1 for c in cols if len(c) > t)
        for n in m:
            if n in seen:
                for ci in range(6):
                    if n in cols[ci]:
                        tier = cols[ci].index(n)
                        tier_counts[min(tier, tier_rows)] += 1
                        total += 1
                        break
            seen.add(n)
        for n in m:
            for ci in range(6):
                if n in cols[ci]:
                    cols[ci].remove(n)
                    break
        for pos, n in enumerate(m):
            cols[pos].insert(0, n)
    n_draws = max(1, len(history))
    return tier_counts, total, [o / n_draws for o in occupancy]


def compute_droughts(history):
    """各番号の過去最長の連続未出記録と、現時点(最新回)での連続未出ランキングを返す。"""
    n_draws = len(history)
    last_seen = {i: -1 for i in range(1, 44)}
    max_gap = {i: 0 for i in range(1, 44)}
    max_gap_end = {i: None for i in range(1, 44)}
    for idx, d in enumerate(history):
        for n in d["main"]:
            gap = idx - last_seen[n] - 1
            if gap > max_gap[n]:
                max_gap[n] = gap
                max_gap_end[n] = idx
            last_seen[n] = idx
    for i in range(1, 44):
        gap = n_draws - 1 - last_seen[i]
        if gap > max_gap[i]:
            max_gap[i] = gap
            max_gap_end[i] = None

    longest_num, longest_gap = max(max_gap.items(), key=lambda x: x[1])
    longest_end_idx = max_gap_end[longest_num]
    current_top = sorted(
        ((i, n_draws - 1 - last_seen[i]) for i in range(1, 44)),
        key=lambda x: -x[1],
    )[:3]
    return {
        "longest_num": longest_num,
        "longest_gap": longest_gap,
        "longest_end": history[longest_end_idx] if longest_end_idx is not None else None,
        "current_top": current_top,
    }


def compute_bonus_trivia(history):
    """ボーナス数字にまつわる俗説をいくつか実データで検証する。"""
    n = len(history)
    hit_bonus_to_next_main = 0
    hit_main_to_next_bonus = 0
    for i in range(n - 1):
        if history[i]["bonus"] in history[i + 1]["main"]:
            hit_bonus_to_next_main += 1
        if history[i + 1]["bonus"] in history[i]["main"]:
            hit_main_to_next_bonus += 1
    total_pairs = max(1, n - 1)

    within_range = 0
    for d in history:
        mn, mx = min(d["main"]), max(d["main"])
        if mn <= d["bonus"] <= mx:
            within_range += 1

    return {
        "bonus_to_next_main_rate": hit_bonus_to_next_main / total_pairs * 100,
        "main_to_next_bonus_rate": hit_main_to_next_bonus / total_pairs * 100,
        "baseline_rate": 6 / 43 * 100,
        "within_range_rate": within_range / n * 100 if n else 0,
    }


def compute_quickpick_stats(history):
    """クイックピックの条件判定と診断表示に使う、実データ側の分布をまとめて計算する。
    ここで出した割合が「この目は過去の何%と同じ形か」の根拠になる。"""
    n = len(history)
    if not n:
        return {}
    pct = lambda c: c / n * 100

    sums = sorted(sum(d["main"]) for d in history)
    band = 10
    sum_bands = {}
    for s in sums:
        key = s // band * band
        sum_bands[key] = sum_bands.get(key, 0) + 1
    quantile = lambda p: sums[min(n - 1, int(n * p))]

    odd = [0] * 7
    low = [0] * 7
    birthday = [0] * 7
    max_run = [0] * 7
    consec_pairs = [0] * 6
    last_digit = [0] * 7
    for d in history:
        m = d["main"]
        odd[sum(1 for x in m if x % 2)] += 1
        low[sum(1 for x in m if x <= 21)] += 1
        birthday[sum(1 for x in m if x <= 31)] += 1
        run = best = 1
        pairs = 0
        for a, b in zip(m, m[1:]):
            if b == a + 1:
                run += 1
                pairs += 1
            else:
                run = 1
            best = max(best, run)
        max_run[best] += 1
        consec_pairs[pairs] += 1
        digits = {}
        for x in m:
            digits[x % 10] = digits.get(x % 10, 0) + 1
        last_digit[max(digits.values())] += 1

    return {
        "n": n,
        "sumMedian": sums[n // 2],
        "sumMin": sums[0],
        "sumMax": sums[-1],
        "sumP10": quantile(0.10),
        "sumP25": quantile(0.25),
        "sumP75": quantile(0.75),
        "sumP90": quantile(0.90),
        "sumBand": band,
        "sumBands": {str(k): pct(v) for k, v in sorted(sum_bands.items())},
        "odd": [pct(c) for c in odd],
        "low": [pct(c) for c in low],
        "birthday": [pct(c) for c in birthday],
        "maxRun": [pct(c) for c in max_run],
        "consecPairs": [pct(c) for c in consec_pairs],
        "lastDigit": [pct(c) for c in last_digit],
    }


def format_yen(n):
    """金額を「約6.0億円（600,000,000円）」のように読みやすく整形する。"""
    if n >= 100000000:
        return f"約{n / 100000000:.1f}億円（{n:,}円）"
    if n >= 10000:
        return f"約{n / 10000:,.0f}万円（{n:,}円）"
    return f"{n:,}円"


def max_run_length(main):
    """並びの中でいちばん長い連番の長さ。"""
    best = run = 1
    for a, b in zip(main, main[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    return best


def compute_record_draws(history):
    """合計値や並びの「記録」になっている回を拾う。数値も回も毎回ここで出し直すので、
    データが増えれば記録も自動で更新される。"""
    by_sum = sorted(history, key=lambda d: sum(d["main"]))
    all_odd = [d for d in history if all(x % 2 for x in d["main"])]
    all_even = [d for d in history if all(x % 2 == 0 for x in d["main"])]
    runs4 = [d for d in history if max_run_length(d["main"]) >= 4]
    dig4 = [d for d in history if max(Counter(x % 10 for x in d["main"]).values()) >= 4]
    return {
        "max_sum": by_sum[-1],
        "min_sum": by_sum[0],
        "all_odd": all_odd,
        "all_even": all_even,
        "runs4": runs4,
        "dig4": dig4,
    }


def compute_myth_trivia(history):
    """「前回と同じ数字は避けるべき」「同じ組み合わせは出ない」といった俗説を、
    理論値（超幾何分布）と突き合わせて検証する。"""
    n = len(history)
    counts = Counter(len(set(history[i]["main"]) & set(history[i + 1]["main"])) for i in range(n - 1))
    pairs = max(1, n - 1)
    total_comb = math.comb(43, 6)
    rows = []
    for k in range(7):
        actual = counts.get(k, 0) / pairs * 100
        theory = math.comb(6, k) * math.comb(37, 6 - k) / total_comb * 100
        rows.append({"k": k, "actual": actual, "theory": theory})
    max_gap = max(abs(r["actual"] - r["theory"]) for r in rows)
    combo_counts = Counter(tuple(d["main"]) for d in history)
    repeats = [c for c in combo_counts.values() if c > 1]
    return {"rows": rows, "max_gap": max_gap, "repeat_count": len(repeats)}


def compute_prize_trivia(history):
    """1等の当選金額とキャリーオーバーの記録。配当データが欠けている回は除いて計算する。"""
    priced = [d for d in history if "amt1" in d and "win1" in d]
    if not priced:
        return None
    n = len(priced)
    none1 = [d for d in priced if d["win1"] == 0]
    paid = [d for d in priced if d["win1"] > 0]
    longest = current = 0
    longest_end = None
    for d in priced:
        if d["win1"] == 0:
            current += 1
            if current > longest:
                longest, longest_end = current, d
        else:
            current = 0
    carried = [d for d in priced if d.get("carry", 0) > 0]
    return {
        "n": n,
        "top": max(paid, key=lambda d: d["amt1"]) if paid else None,
        "low": min(paid, key=lambda d: d["amt1"]) if paid else None,
        "none_count": len(none1),
        "none_rate": len(none1) / n * 100,
        "none_longest": longest,
        "none_longest_end": longest_end,
        "carry_top": max(carried, key=lambda d: d["carry"]) if carried else None,
        "carry_rate": len(carried) / n * 100,
        "latest": priced[-1],
    }


def build_trivia_html(history):
    """座標分布の形・連続未出記録・ボーナス俗説の検証を、トリビアタブ用のHTMLカードにする。"""
    tier_counts, tier_total, tier_occ = compute_tier_distribution(history)
    tier_pct = [c / tier_total * 100 for c in tier_counts] if tier_total else [0] * len(tier_counts)
    top4_min, top4_max = min(tier_pct[:4]), max(tier_pct[:4])
    tail_pct = sum(tier_pct[9:])

    droughts = compute_droughts(history)
    end = droughts["longest_end"]
    end_text = f"第{end['id']}回（{end['date']}）でようやく再登場しました" if end else "まだ再登場していません"
    current_top_text = "、".join(f"{num}番（{gap}回）" for num, gap in droughts["current_top"])

    bonus = compute_bonus_trivia(history)

    def myth_verdict(rate, baseline):
        """実測が基準値からどれだけ離れているかで結論の書き方を変える。
        固定文にしてしまうと、データが増えて数値が動いたとき文章だけ取り残されるため。
        (基準値どおりか, 説明文) を返す。"""
        diff = rate - baseline
        if abs(diff) < baseline * 0.15:
            return True, "基準値とほぼ同じ"
        return False, "基準値より" + ("高め" if diff > 0 else "低め") + f"（差{diff:+.2f}ポイント）"

    flat_a, verdict_a = myth_verdict(bonus["bonus_to_next_main_rate"], bonus["baseline_rate"])
    flat_b, verdict_b = myth_verdict(bonus["main_to_next_bonus_rate"], bonus["baseline_rate"])
    if flat_a and flat_b:
        bonus_conclusion = "どちらも基準値とほぼ同じで、俗説は成立していません"
    else:
        bonus_conclusion = f"前者は{verdict_a}、後者は{verdict_b}という結果です"

    records = compute_record_draws(history)
    myth = compute_myth_trivia(history)
    prize = compute_prize_trivia(history)

    def draw_label(d):
        return f"第{d['id']}回（{d['date']}）"

    def nums(d):
        return " ".join(str(x) for x in d["main"])

    cards = [
        f'''<div class="trivia-card">
            <h3 class="trivia-title">座標(段)の分布は「なだらか→崖」の形</h3>
            <p class="trivia-body">全<span class="num">{len(history)}</span>回・のべ<span class="num">{tier_total:,}</span>回の再登場を集計すると、A〜D段は<span class="num">{top4_min:.1f}〜{top4_max:.1f}%</span>でほぼ横並び、E段あたりから急に減っていきます（J段以降は合計<span class="num">{tail_pct:.1f}%</span>）。これは「直近に出た数字が列の先頭に来る」しくみ（move-to-front方式の自己組織化リストと同じ構造）による形で、抽選そのものの偏りではありません。</p>
        </div>''',
        f'''<div class="trivia-card">
            <h3 class="trivia-title">連続未出（干上がり）記録</h3>
            <p class="trivia-body">過去最長の連続未出は<span class="num">{droughts['longest_num']}番</span>の<span class="num">{droughts['longest_gap']}回</span>連続。{end_text}。現時点で連続未出が長いのは{current_top_text}です。</p>
        </div>''',
        f'''<div class="trivia-card">
            <h3 class="trivia-title">ボーナス数字の都市伝説を検証</h3>
            <p class="trivia-body">「前回のボーナス数字は次回、本数字として出やすい」という説を検証すると<span class="num">{bonus['bonus_to_next_main_rate']:.2f}%</span>（基準値{bonus['baseline_rate']:.2f}%）、逆に「前回の本数字は次回ボーナスになりやすい」も<span class="num">{bonus['main_to_next_bonus_rate']:.2f}%</span>で、{bonus_conclusion}。ちなみにボーナス数字が本数字の最小〜最大の範囲内に収まる確率は<span class="num">{bonus['within_range_rate']:.1f}%</span>ですが、これは6個の数字が散らばれば7個目がその間に入りやすいという組み合わせ論の話で、特別な偏りではありません。</p>
        </div>''',
    ]

    # 段ごとの「実測 vs 理論」。A段には直前の回に出た6個がそのまま並ぶので、
    # 段の比較がそのまま「この前出た数字は避けるべきか」の検証になる。
    tier_rows_html = "".join(
        f'<div class="trivia-row"><span class="trivia-row-name">{chr(65 + t)}段</span>'
        f'<span class="trivia-row-val">{tier_pct[t]:.2f}%</span>'
        f'<span class="trivia-row-sub">理論 {tier_occ[t] / 43 * 100:.2f}%（{tier_occ[t]:.2f}個が在籍）</span></div>'
        for t in range(4)
    )
    tier_gap = max(abs(tier_pct[t] - tier_occ[t] / 43 * 100) for t in range(4))
    tier_verdict = (
        "どの段もほぼ理論値どおりで、ズレは最大" + f"{tier_gap:.2f}ポイント"
        if tier_gap < 1.0 else
        f"理論値とのズレが最大{tier_gap:.2f}ポイントあります"
    )
    match0 = myth["rows"][0]["actual"]
    match1 = myth["rows"][1]["actual"]
    combo_text = (
        "一度もありません" if myth["repeat_count"] == 0
        else f"{myth['repeat_count']}件あります"
    )
    cards.append(f'''<div class="trivia-card">
            <h3 class="trivia-title">「この前出た数字は避けろ」は本当か</h3>
            <p class="trivia-body">盤面の<span class="num">A段</span>には、直前の回に出た6個がそのまま並びます（引かれた数字が列の先頭に入るため）。B段はその1つ前、C段はさらに前……と、段は「どれくらい前に出た数字か」を表しています。<br>どの段にも数字は6個ずついるので、抽選が公平なら、どの段からも<span class="num">6÷43＝13.95%</span>の割合で再登場するはずです。</p>
            {tier_rows_html}
            <p class="trivia-body">{tier_verdict}。<b>直前に出たばかりのA段の数字も、4回前のD段の数字も、次に出る確率は変わりません。</b>「この前出た数字は避ける」に根拠はないということです。実際、前回の6個のうち次の回にも出た数は0個が<span class="num">{match0:.1f}%</span>、1個が<span class="num">{match1:.1f}%</span>で、これも理論値どおりでした。<br>E段から下がっていくのは、段が深いほどそこにいる数字の数自体が減るからで（上のカードの「崖」の正体）、抽選の偏りではありません。</p>
            <p class="trivia-body">ちなみに、6個の組み合わせがそっくり同じだった回は<span class="num">{combo_text}</span>（組み合わせは全部で<span class="num">{math.comb(43, 6):,}</span>通りあるので、当分は起こりません）。</p>
        </div>''')

    cards.insert(1, cards.pop())

    last_odd = records["all_odd"][-1] if records["all_odd"] else None
    last_even = records["all_even"][-1] if records["all_even"] else None
    last_run4 = records["runs4"][-1] if records["runs4"] else None
    last_dig4 = records["dig4"][-1] if records["dig4"] else None
    cards.append(f'''<div class="trivia-card">
            <h3 class="trivia-title">記録的な出目</h3>
            <p class="trivia-body">合計値がいちばん大きかったのは{draw_label(records["max_sum"])}の<span class="num">{sum(records["max_sum"]["main"])}</span>（{nums(records["max_sum"])}）、いちばん小さかったのは{draw_label(records["min_sum"])}の<span class="num">{sum(records["min_sum"]["main"])}</span>（{nums(records["min_sum"])}）でした。</p>
            <p class="trivia-body">6個すべてが奇数だった回は<span class="num">{len(records["all_odd"])}</span>回{"（直近は" + draw_label(last_odd) + "の" + nums(last_odd) + "）" if last_odd else ""}、すべて偶数は<span class="num">{len(records["all_even"])}</span>回{"（直近は" + draw_label(last_even) + "の" + nums(last_even) + "）" if last_even else ""}。4つ以上の連番が出たのは<span class="num">{len(records["runs4"])}</span>回{"（直近は" + draw_label(last_run4) + "の" + nums(last_run4) + "）" if last_run4 else ""}、下一桁が4つそろったのは<span class="num">{len(records["dig4"])}</span>回{"（直近は" + draw_label(last_dig4) + "の" + nums(last_dig4) + "）" if last_dig4 else ""}あります。</p>
        </div>''')

    if prize:
        carry_top = prize["carry_top"]
        none_end = prize["none_longest_end"]
        cards.append(f'''<div class="trivia-card">
            <h3 class="trivia-title">当選金額とキャリーオーバーの記録</h3>
            <p class="trivia-body">1等の最高額は{draw_label(prize["top"])}の<span class="num">{format_yen(prize["top"]["amt1"])}</span>（{prize["top"]["win1"]}口）。逆にいちばん少なかった1等は{draw_label(prize["low"])}の<span class="num">{format_yen(prize["low"]["amt1"])}</span>で、このときは<span class="num">{prize["low"]["win1"]}口</span>が当たって山分けになりました。同じ1等でも、何人と分けるかでこれだけ変わります。</p>
            <p class="trivia-body">1等が誰も当たらなかった回は<span class="num">{prize["none_count"]}</span>回（<span class="num">{prize["none_rate"]:.1f}%</span>）あり、最長で<span class="num">{prize["none_longest"]}</span>回連続{"（" + draw_label(none_end) + "まで）" if none_end else ""}。持ち越されたキャリーオーバーの最高額は{draw_label(carry_top) if carry_top else "—"}の<span class="num">{format_yen(carry_top["carry"]) if carry_top else "—"}</span>でした。直近の{draw_label(prize["latest"])}時点では{"キャリーオーバーは<span class=" + chr(34) + "num" + chr(34) + ">" + format_yen(prize["latest"]["carry"]) + "</span>が持ち越されています" if prize["latest"].get("carry", 0) else "キャリーオーバーはありません"}。</p>
        </div>''')

    # 「いつ時点の集計か」を必ず先頭に出す。数値は毎回計算し直しているが、
    # 見る側にとって何回目までのデータなのかが分からないと古い情報と区別できないため。
    header = (f'''<p class="trivia-range">第{history[0]["id"]}回（{history[0]["date"]}）〜第{history[-1]["id"]}回（{history[-1]["date"]}）の全{len(history)}回を集計。データ更新のたびに計算し直しています。</p>''')
    return header + "\n" + "\n".join(cards)


def main():
    print("最新の歴史データを同期中...")
    history = load_cache()
    try:
        fresh = fetch_latest()
        if not fresh:
            raise ValueError("取得したデータが空でした")
        history = fresh
        save_cache(history)
        print(f"成功！全 {len(history)} 回分の本物データを取得しました（第{history[0]['id']}回〜第{history[-1]['id']}回、キャッシュ更新済み）。")
    except Exception as e:
        if history:
            print(f"通信エラーのため最新分は取得できませんでしたが、ローカルに保存済みの本物データ（全{len(history)}回、第{history[0]['id']}回〜第{history[-1]['id']}回）を使用します: {e}")
        else:
            print(f"致命的エラー: ネットワークにも接続できず、ローカルキャッシュも見つかりません: {e}")
            return

    is_fresh, freshness_msg = check_freshness(history)
    print(("\u2713 " if is_fresh else "\u26a0 ") + freshness_msg)

    # 配当データはPython側のトリビア計算だけで使い、HTMLには埋め込まない（ページを重くしないため）
    data_json = json.dumps([{"id": d["id"], "date": d["date"], "main": d["main"], "bonus": d["bonus"]}
                            for d in history])
    qp_stats_json = json.dumps(compute_quickpick_stats(history))
    trivia_html = build_trivia_html(history)

    # HTMLテンプレート（極・完成版デザイン）
    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>LOTO 6 PREMIUM ANALYSIS - 極 -</title>
    <style>
        body {{ background-color: #0f0a07; color: white; margin: 0; display: flex; flex-direction: column; align-items: center; min-height: 100vh; font-family: sans-serif; overflow-x: hidden; }}
        .main-container {{ width: 100%; max-width: 480px; padding: 10px 0; display: flex; flex-direction: column; align-items: center; }}
        .title {{ color: #e5c100; font-size: 18px; font-weight: bold; margin-bottom: 8px; text-shadow: 0 0 15px rgba(229,193,0,0.5); }}
        .board-wrapper {{ display: flex; gap: 10px; justify-content: center; align-items: flex-start; margin-bottom: 180px; width: 100%; padding: 0 15px; box-sizing: border-box; }}
        .main-board {{ position: relative; width: 260px; height: 520px; background: rgba(0,0,0,0.85); padding: 10px; border-radius: 25px 25px 0 0; border: 2.5px solid #d4af37; border-bottom: none; box-shadow: 0 -10px 30px rgba(0,0,0,0.8); }}
        .ball {{ position: absolute; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 14px; border: 1.1px solid rgba(255, 255, 255, 0.4); box-shadow: 0 4px 8px rgba(0,0,0,0.5), inset -1px -1px 3px rgba(0,0,0,0.3); transition: left 0.8s cubic-bezier(0.34, 1.56, 0.64, 1), top 0.8s cubic-bezier(0.34, 1.56, 0.64, 1), background-color 0.6s; z-index: 10; }}
        .ball.glow-float {{ z-index: 100; transform: scale(1.6) translateY(-25px) !important; background-color: #ffffff !important; color: #000 !important; box-shadow: 0 0 30px #fff, 0 0 50px #ffd700; border-color: #fff; transition: transform 0.4s ease-out, background-color 0.3s !important; }}
        /* 塗り色が近い組み合わせでも判別できるよう、縁取りの色をもう1つの手掛かりにする */
        .ball.toned {{ border-width: 3px; box-shadow: 0 4px 8px rgba(0,0,0,0.5), inset -1px -1px 3px rgba(0,0,0,0.3), 0 0 6px rgba(255,255,255,0.15); }}
        .ball.active {{ border-color: #fff; box-shadow: 0 0 12px rgba(255,215,0,0.7); }}
        .bonus-section {{ display: flex; flex-direction: column; align-items: center; gap: 5px; min-width: 50px; }}
        .bonus-box {{ display: flex; flex-direction: column; gap: 8px; background: rgba(255, 255, 255, 0.08); padding: 10px; border-radius: 15px; border: 1.5px solid rgba(212, 175, 55, 0.3); align-items: center; }}
        .bonus-ball {{ width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; background: #222; border: 1px solid #d4af37; font-size: 11px; color: #ffd700; }}
        .bonus-ball.latest {{ width: 44px; height: 44px; font-size: 18px; box-shadow: 0 0 15px #d4af37; background: radial-gradient(circle, #ffd700, #b8860b); color: #1a120b; margin-bottom: 3px; }}
        .controls {{ position: fixed; bottom: 0; width: 100%; max-width: 480px; background: rgba(15, 10, 7, 0.98); padding: 15px 0 25px 0; display: flex; flex-direction: column; align-items: center; gap: 10px; border-top: 2.5px solid #d4af37; box-shadow: 0 -5px 20px rgba(0,0,0,0.6); }}
        .info-display {{ font-size: 16px; color: #ffd700; font-weight: 900; }}
        .slider-row {{ width: 95%; display: flex; align-items: center; justify-content: center; gap: 4px; }}
        .speed-row {{ width: 80%; display: flex; align-items: center; gap: 8px; }}
        .speed-label {{ font-size: 10px; color: #8a7a5c; white-space: nowrap; }}
        input[type=range] {{ flex-grow: 1; accent-color: #ffd700; height: 10px; cursor: pointer; }}
        .btn {{ background: linear-gradient(180deg, #3d2b1f, #1a100a); color: #ffd700; border: 1px solid #ffd700; padding: 7px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; cursor: pointer; min-width: 45px; transition: transform 0.1s; }}
        .btn:active {{ transform: scale(0.92); filter: brightness(0.8); }}
        .btn-main {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border: none; padding: 10px 40px; border-radius: 20px; font-size: 14px; }}

        /* --- タブ切り替え --- */
        .tab-bar {{ display: flex; flex-wrap: wrap; gap: 5px; width: 100%; max-width: 430px; justify-content: center; margin-bottom: 12px; }}
        .tab-btn {{ flex: 1; min-width: 50px; background: transparent; color: #8a7a5c; border: 1px solid rgba(212,175,55,0.35); padding: 8px 4px; border-radius: 14px; font-size: 13px; font-weight: bold; cursor: pointer; transition: all 0.2s; }}
        .tab-btn.active {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border-color: #d4af37; box-shadow: 0 0 12px rgba(212,175,55,0.4); }}
        .tab-panel {{ display: none; width: 100%; flex-direction: column; align-items: center; }}
        .tab-panel.active {{ display: flex; }}

        /* --- 出現頻度ランキング --- */
        .freq-toggle {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 8px; }}
        .freq-toggle .btn.active-toggle, .qp-preset-bar .btn.active-toggle, .qp-cond-opts .btn.active-toggle {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border-color: #d4af37; }}
        .freq-caption {{ font-size: 11px; color: #8a7a5c; margin: 0 0 10px 0; text-align: center; padding: 0 15px; }}
        .freq-subheading {{ width: 100%; max-width: 400px; box-sizing: border-box; padding: 0 15px; font-size: 12px; font-weight: bold; margin: 14px 0 6px 0; }}
        .freq-subheading.hot {{ color: #ffd700; }}
        .freq-subheading.cold {{ color: #5dade2; }}
        .freq-list {{ width: 100%; max-width: 400px; padding: 0 15px; box-sizing: border-box; display: flex; flex-direction: column; gap: 7px; margin-bottom: 190px; }}
        .freq-row {{ display: flex; align-items: center; gap: 8px; }}
        .freq-rank {{ width: 20px; font-size: 10px; color: #6a5a42; text-align: right; font-variant-numeric: tabular-nums; }}
        .freq-badge {{ width: 26px; height: 26px; min-width: 26px; border-radius: 50%; background: #221a10; border: 1px solid #d4af37; color: #ffd700; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; }}
        .freq-bar-wrap {{ flex-grow: 1; height: 14px; background: rgba(212,175,55,0.12); border-radius: 4px; overflow: hidden; }}
        .freq-bar {{ height: 100%; background: linear-gradient(90deg, #b8860b, #ffd700); border-radius: 0 4px 4px 0; transition: width 0.4s ease; }}
        .freq-bar.cold {{ background: linear-gradient(90deg, #2e6da4, #5dade2); }}
        .freq-count {{ width: 30px; text-align: right; font-size: 12px; color: #ccc; font-variant-numeric: tabular-nums; }}
        .freq-chip {{ width: 34px; text-align: center; font-size: 8px; font-weight: 900; padding: 2px 0; border-radius: 8px; letter-spacing: 0.5px; }}
        .freq-chip.hot {{ background: #ffd700; color: #1a120b; }}
        .freq-chip.cold {{ background: #5dade2; color: #0a1a2a; }}
        .freq-chip:empty {{ visibility: hidden; }}

        /* --- 座標マップ(段 x 列マトリクス) --- */
        .tier-window-control {{ width: 100%; max-width: 400px; padding: 0 15px; box-sizing: border-box; margin-bottom: 8px; }}
        .tier-window-row {{ display: flex; align-items: center; gap: 10px; }}
        .tier-slider {{ flex-grow: 1; accent-color: #d4af37; }}
        .tier-window-label {{ font-size: 10px; color: #8a7a5c; margin-top: 4px; text-align: center; }}
        .tier-window-label span {{ color: #ffd700; font-weight: bold; font-variant-numeric: tabular-nums; }}
        .tier-table-wrap {{ width: 100%; max-width: 400px; padding: 4px 15px 190px 15px; box-sizing: border-box; overflow-x: auto; }}
        .tier-table {{ border-collapse: separate; border-spacing: 3px; margin: 0 auto; }}
        .tier-table th {{ font-size: 10px; color: #8a7a5c; font-weight: bold; padding: 2px; }}
        .tier-table td.tier-label {{ font-size: 10px; color: #8a7a5c; text-align: right; padding-right: 4px; white-space: nowrap; }}
        .tier-total {{ font-size: 9px; color: #ffd700; font-variant-numeric: tabular-nums; }}
        .tier-cell {{ width: 40px; height: 32px; border-radius: 6px; border: 1px solid rgba(212,175,55,0.25); text-align: center; font-size: 11px; color: #fff; font-variant-numeric: tabular-nums; }}

        /* --- トリビア --- */
        .trivia-list {{ width: 100%; max-width: 400px; padding: 4px 15px 190px 15px; box-sizing: border-box; display: flex; flex-direction: column; gap: 14px; }}
        .qp-wrap {{ width: 100%; max-width: 400px; padding: 0 15px; box-sizing: border-box; }}
        .qp-preset-bar {{ display: flex; gap: 6px; justify-content: center; margin-bottom: 6px; }}
        .qp-preset-bar .btn {{ flex: 1; padding: 9px 4px; font-size: 11px; line-height: 1.5; }}
        .qp-custom {{ width: 100%; max-width: 400px; box-sizing: border-box; padding: 0 15px; margin-bottom: 10px; }}
        .qp-custom > summary {{ list-style: none; cursor: pointer; font-size: 12px; color: #8a7a5c; text-align: center; padding: 6px 0; border: 1px dashed rgba(212,175,55,0.3); border-radius: 10px; }}
        .qp-custom > summary::-webkit-details-marker {{ display: none; }}
        .qp-custom[open] > summary {{ color: #ffd700; border-style: solid; }}
        .qp-cond {{ display: flex; flex-direction: column; gap: 10px; padding: 12px 2px 4px 2px; }}
        .qp-cond-label {{ font-size: 11px; color: #ffd700; font-weight: bold; margin-bottom: 4px; }}
        .qp-cond-opts {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .qp-cond-opts .btn {{ flex: 1 1 45%; min-width: 0; padding: 11px 4px; font-size: 12.5px; color: #ffe06a; }}
        .qp-cond-opts .btn .qp-hint {{ display: block; font-size: 10px; font-weight: normal; color: #b9a577; margin-top: 2px; }}
        .qp-cond-opts .btn.active-toggle .qp-hint {{ color: #4a3300; }}
        .qp-cond-label {{ font-size: 12px; }}
        .qp-num-picker {{ display: flex; gap: 6px; overflow-x: auto; padding: 10px 2px 8px 2px; width: 100%; -webkit-overflow-scrolling: touch; }}
        .qp-num-item.keep {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border-color: #fff; box-shadow: 0 0 10px rgba(212,175,55,0.6); transform: scale(1.1); }}
        .qp-num-item.ban {{ background: #2a1414; color: #8a5555; border-color: #7a3030; text-decoration: line-through; }}
        .qp-num-summary {{ font-size: 11px; color: #ccc; line-height: 1.9; }}
        .qp-num-summary .keep-label {{ color: #ffd700; font-weight: bold; }}
        .qp-num-summary .ban-label {{ color: #d98080; font-weight: bold; }}
        .qp-num-msg {{ font-size: 11px; color: #e8a33d; min-height: 15px; line-height: 1.4; }}
        .qp-num-clear {{ margin-top: 6px; }}
        .qp-draw-btn {{ width: 100%; max-width: 370px; margin: 4px 0 14px 0; padding: 13px 0; font-size: 14px; font-weight: bold; color: #1a120b; background: linear-gradient(180deg, #ffd700, #b8860b); border: none; border-radius: 14px; cursor: pointer; box-shadow: 0 0 14px rgba(212,175,55,0.35); }}
        .qp-draw-btn:active {{ transform: scale(0.98); }}
        .qp-balls {{ display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; min-height: 44px; margin-bottom: 12px; }}
        .qp-ball {{ width: 42px; height: 42px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 16px; color: #1a120b; background: radial-gradient(circle at 32% 28%, #fff2b0, #e5c100 55%, #a8790a); border: 1.5px solid #ffe97a; box-shadow: 0 3px 8px rgba(0,0,0,0.6); animation: qp-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1) both; }}
        @keyframes qp-pop {{ from {{ transform: scale(0.3); opacity: 0; }} to {{ transform: scale(1); opacity: 1; }} }}
        .qp-ball.keep {{ box-shadow: 0 0 0 2px #fff, 0 3px 8px rgba(0,0,0,0.6); }}
        .qp-ball.hot {{ background: radial-gradient(circle at 32% 28%, #ffd0a0, #ff7a2f 55%, #a33c00); border-color: #ffb27a; color: #2a1000; }}
        .qp-diagnosis {{ width: 100%; max-width: 400px; box-sizing: border-box; padding: 0 15px; display: flex; flex-direction: column; gap: 7px; }}
        .qp-diag-head {{ font-size: 12px; font-weight: bold; color: #ffd700; border-bottom: 1px solid rgba(212,175,55,0.3); padding-bottom: 5px; margin-bottom: 2px; }}
        .qp-diag-note {{ font-size: 10px; color: #6a5a42; line-height: 1.6; margin: -2px 0 4px 0; }}
        .qp-diag-row {{ display: flex; align-items: center; gap: 7px; font-size: 11px; }}
        .qp-diag-name {{ width: 62px; min-width: 62px; color: #8a7a5c; }}
        .qp-diag-val {{ width: 88px; min-width: 88px; font-size: 10px; color: #fff; font-weight: bold; font-variant-numeric: tabular-nums; }}
        .qp-diag-bar-wrap {{ flex-grow: 1; height: 11px; background: rgba(212,175,55,0.12); border-radius: 3px; overflow: hidden; }}
        .qp-diag-bar {{ height: 100%; background: linear-gradient(90deg, #b8860b, #ffd700); transition: width 0.4s ease; }}
        .qp-diag-pct {{ width: 62px; min-width: 62px; text-align: right; color: #ccc; font-variant-numeric: tabular-nums; }}
        .qp-diag-row.top .qp-diag-val {{ color: #ffd700; }}
        .qp-diag-row.top .qp-diag-pct::after {{ content: " ★"; color: #ffd700; }}
        .qp-score {{ margin-top: 6px; padding: 10px 12px; border: 1px solid rgba(212,175,55,0.3); border-radius: 12px; background: rgba(255,255,255,0.04); display: flex; align-items: baseline; justify-content: center; gap: 8px; }}
        .qp-score-num {{ font-size: 26px; font-weight: 900; color: #ffd700; font-variant-numeric: tabular-nums; }}
        .qp-score-label {{ font-size: 11px; color: #8a7a5c; }}
        .qp-warn {{ font-size: 11px; color: #e8a33d; text-align: center; padding: 0 15px; margin: 0 0 8px 0; }}
        .qp-note {{ margin-bottom: 190px !important; line-height: 1.7; }}
        .trivia-range {{ width: 100%; max-width: 400px; box-sizing: border-box; padding: 0 2px; font-size: 11px; color: #8a7a5c; line-height: 1.7; margin: 0 0 2px 0; }}
        .trivia-row {{ display: flex; align-items: baseline; gap: 8px; font-size: 12px; padding: 3px 0 3px 4px; }}
        .trivia-row-name {{ width: 66px; min-width: 66px; color: #8a7a5c; }}
        .trivia-row-val {{ width: 56px; min-width: 56px; color: #ffd700; font-weight: bold; font-variant-numeric: tabular-nums; }}
        .trivia-row-sub {{ color: #999; font-size: 11px; font-variant-numeric: tabular-nums; }}
        .trivia-card {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(212,175,55,0.25); border-radius: 12px; padding: 14px 16px; }}
        .trivia-title {{ margin: 0 0 6px 0; font-size: 13px; color: #ffd700; font-weight: bold; }}
        .trivia-body {{ margin: 0; font-size: 12px; color: #ddd; line-height: 1.8; }}
        .trivia-body .num {{ color: #ffd700; font-weight: bold; font-variant-numeric: tabular-nums; }}

        /* --- ペア分析 --- */
        .pair-sub {{ display: none; width: 100%; flex-direction: column; align-items: center; }}
        .pair-sub.active {{ display: flex; }}
        .num-picker {{ display: flex; gap: 6px; overflow-x: auto; padding: 2px 15px 12px 15px; width: 100%; max-width: 400px; box-sizing: border-box; -webkit-overflow-scrolling: touch; }}
        .num-picker-item {{ flex: 0 0 auto; width: 30px; height: 30px; border-radius: 50%; background: #221a10; border: 1px solid rgba(212,175,55,0.4); color: #c9b37c; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; cursor: pointer; transition: all 0.15s; }}
        .num-picker-item.selected {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border-color: #fff; box-shadow: 0 0 10px rgba(212,175,55,0.6); transform: scale(1.1); }}
        .pair-badge-group {{ display: flex; align-items: center; gap: 2px; min-width: 62px; }}
        .pair-badge {{ width: 24px; height: 24px; min-width: 24px; border-radius: 50%; background: #221a10; border: 1px solid #d4af37; color: #ffd700; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; }}
        .pair-dash {{ color: #6a5a42; font-size: 11px; }}
    </style>
</head>
<body>
    <div class="main-container">
        <p class="title">LOTO 6 PREMIUM ANALYSIS - 極 -</p>
        <div class="tab-bar">
            <button id="tab-btn-board" class="tab-btn active" onclick="switchTab('board')">盤面</button>
            <button id="tab-btn-freq" class="tab-btn" onclick="switchTab('freq')">頻度</button>
            <button id="tab-btn-tier" class="tab-btn" onclick="switchTab('tier')">座標</button>
            <button id="tab-btn-pair" class="tab-btn" onclick="switchTab('pair')">ペア</button>
            <button id="tab-btn-qp" class="tab-btn" onclick="switchTab('qp')">予想</button>
            <button id="tab-btn-trivia" class="tab-btn" onclick="switchTab('trivia')">トリビア</button>
        </div>
        <div id="panel-board" class="tab-panel active">
            <div class="board-wrapper">
                <div id="main-board" class="main-board"></div>
                <div class="bonus-section"><div class="bonus-box" id="bonus-history"></div></div>
            </div>
        </div>
        <div id="panel-freq" class="tab-panel">
            <div class="tier-window-control">
                <div class="tier-window-row">
                    <input type="range" id="freq-window-slider" class="tier-slider" min="10" max="100" step="1" value="100" oninput="setFreqWindow(this.value)">
                    <button id="freq-window-all" class="btn" onclick="setFreqWindowAll()">全期間</button>
                </div>
                <div class="tier-window-label">直近<span id="freq-window-value">100</span>回で集計</div>
            </div>
            <p class="freq-caption" id="freq-caption"></p>
            <div class="freq-list" id="freq-list"></div>
        </div>
        <div id="panel-pair" class="tab-panel">
            <div class="freq-toggle">
                <button id="pair-mode-top20" class="btn active-toggle" onclick="setPairMode('top20')">全体TOP20</button>
                <button id="pair-mode-zscore" class="btn" onclick="setPairMode('zscore')">注目ペア</button>
                <button id="pair-mode-bynum" class="btn" onclick="setPairMode('bynum')">番号を選ぶ</button>
            </div>
            <div id="pair-top20-section" class="pair-sub active">
                <p class="freq-caption" id="pair-top20-caption"></p>
                <div class="freq-list" id="pair-top20-list"></div>
            </div>
            <div id="pair-zscore-section" class="pair-sub">
                <p class="freq-caption">理論上の期待出現数と比べたズレの大きさ(統計的な意外性)で並べています。</p>
                <p class="freq-subheading hot">▲ 出すぎているペア TOP10</p>
                <div class="freq-list" id="pair-over-list"></div>
                <p class="freq-subheading cold">▼ 出なさすぎているペア TOP10</p>
                <div class="freq-list" id="pair-under-list"></div>
            </div>
            <div id="pair-bynum-section" class="pair-sub">
                <div class="num-picker" id="num-picker"></div>
                <p class="freq-caption" id="pair-bynum-caption"></p>
                <div class="freq-list" id="pair-partner-list"></div>
            </div>
        </div>
        <div id="panel-tier" class="tab-panel">
            <div class="tier-window-control">
                <div class="tier-window-row">
                    <input type="range" id="tier-window-slider" class="tier-slider" min="10" max="100" step="1" value="100" oninput="setTierWindow(this.value)">
                    <button id="tier-window-all" class="btn" onclick="setTierWindowAll()">全期間</button>
                </div>
                <div class="tier-window-label">直近<span id="tier-window-value">100</span>回で集計（動かすと直近何回で色の出方が変わるか見比べられます）</div>
            </div>
            <p class="freq-caption">列(その回の何番目に小さい数字か)×段(何個前の"別の数字"以来この位置にいるか)ごとに、再登場した回数です。</p>
            <p class="freq-caption" id="tier-caption"></p>
            <div class="tier-table-wrap">
                <table class="tier-table" id="tier-table"></table>
            </div>
        </div>
        <div id="panel-qp" class="tab-panel">
            <div class="qp-wrap">
                <div class="qp-preset-bar">
                    <button id="qp-preset-btn-random" class="btn" onclick="setQpPreset('random')">🎲 大穴狙い<br>完全ランダム</button>
                    <button id="qp-preset-btn-strict" class="btn" onclick="setQpPreset('strict')">📊 統計重視<br>ガチガチ</button>
                    <button id="qp-preset-btn-hot" class="btn" onclick="setQpPreset('hot')">🔥 直近10回<br>ホット重視</button>
                </div>
            </div>
            <p class="freq-caption" id="qp-preset-desc"></p>
            <details class="qp-custom">
                <summary>カスタム条件を開く（プリセットから自由に変えられます）</summary>
                <div class="qp-cond" id="qp-cond"></div>
            </details>
            <details class="qp-custom">
                <summary>使う数字を選ぶ（必ず入れる／除外する）</summary>
                <div class="qp-num-picker" id="qp-num-picker"></div>
                <div class="qp-num-summary" id="qp-num-summary"></div>
                <div class="qp-num-msg" id="qp-num-msg"></div>
                <button class="btn qp-num-clear" onclick="clearQpNums()">選択をクリア</button>
            </details>
            <button class="qp-draw-btn" onclick="drawQuickPick()">この条件で引く</button>
            <p class="qp-warn" id="qp-warn" style="display:none"></p>
            <div class="qp-balls" id="qp-balls"></div>
            <div class="qp-diagnosis" id="qp-diagnosis"></div>
            <p class="freq-caption qp-note">※ どの条件で選んでも1等の当選確率は 1/6,096,454 のまま変わりません。条件は「過去の出目らしさ」を再現して楽しむためのものです。唯一実利があるのは、他の購入者と目が重なりにくくなる＝当たったときの山分け人数が減る、という点だけです。</p>
        </div>
        <div id="panel-trivia" class="tab-panel">
            <div class="trivia-list">
                {trivia_html}
            </div>
        </div>
    </div>
    <div class="controls">
        <div class="info-display">第 <span id="current-id">-</span> 回 (<span id="current-date">----/--/--</span>)</div>
        <div class="slider-row">
            <button class="btn" onclick="jump(-100)">-100</button>
            <button class="btn" onclick="jump(-10)">-10</button>
            <input type="range" id="slider" min="0" value="0" oninput="seekTo(this.value)">
            <button class="btn" onclick="jump(10)">+10</button>
            <button class="btn" onclick="jump(100)">+100</button>
        </div>
        <div class="btn-group" style="display:flex; gap:10px; margin-top:5px;">
            <button class="btn" style="background:#2a1a12" onclick="stepBackward()">◀ 前へ</button>
            <button id="auto-btn" class="btn btn-main" onclick="toggleAuto()">自動再生 / 停止</button>
            <button class="btn" style="background:#2a1a12" onclick="stepForward()">次へ ▶</button>
        </div>
        <div class="speed-row">
            <span class="speed-label">遅い</span>
            <input type="range" id="auto-speed-slider" class="tier-slider" min="1" max="10" step="1" value="4" oninput="setAutoSpeed(this.value)">
            <span class="speed-label">速い</span>
        </div>
    </div>
    <script>
        const fullData = {data_json};

        // 段(そのマスに何回前から居座っているか)は「位置」そのものが正確に表している
        // (1段目=一番上、2段目=その下…と、動けば見ればわかる)ので、色に段を1対1で
        // 正確に当てさせるのはやめた。色の役目は「盤面全体をパッと見た瞬間にどれが
        // 熱い(直近で出た)数字かをざっくり掴む」ことだけに絞り、七色(虹)7バンドに
        // まとめている(正確な段数は位置と「段×列マトリクス」タブで確認できる)。
        //
        // バンドの区切り方は実データ(全2125回・のべ12,707回の再登場)に基づく。
        // 数字の再登場は上位の段ほど多く(1段目14.0%, 2段目11.9%, 3段目10.7%, 4段目9.1%…と
        // 右肩下がり)、そこを潰して同じ色にすると一番見分けたい情報が消えてしまう。
        // そのため1〜4段目は必ず単独の色にし、発生頻度が下がる5段目以降だけをまとめている
        // (「上位重視案」で決定): 1 / 2 / 3 / 4 / 5-6 / 7-9 / 10-11+
        const TIER_ROWS = 11; // A段〜K段。それより深い段は最終行「L段+」にまとめる
        const TIER_LABELS = ['A','B','C','D','E','F','G','H','I','J','K','L'];
        const BAND_COLORS = ['#e52b46', '#de612b', '#d6d13d', '#29a039', '#123cef', '#207aa6', '#9629e5']; // 赤橙黄緑青藍紫(橙黄は隣接段との色相差確保のため調整済み。5-6段目↔7-9段目は「青寄り→水色寄り」の見た目順になるよう入替済み)
        const BAND_TEXT   = ['#ffffff', '#1a120b', '#1a120b', '#1a120b', '#ffffff', '#ffffff', '#ffffff'];
        // 縁取りは「自分の背景色を明るくした色」(セルフトーン)。段ごとに縁が全て異なるため、
        // 白/黒/金を使い回して重複したり黒縁が背景に溶けたりする問題が構造的に起きない。
        const BAND_RING_COLOR = ['#f3a0ac', '#f0b8a0', '#edeaa8', '#9fd4a6', '#94a7f8', '#9bc3d7', '#d09ff3'];
        // tier(0〜11) → バンド番号(0〜6) の対応表。上4段は1段=1バンド、以降は複数段をまとめる。
        const TIER_TO_BAND = [0, 1, 2, 3, 4, 4, 5, 5, 5, 6, 6, 6];
        const bandOfTier = (tier) => TIER_TO_BAND[tier];
        const NEVER_DRAWN_BG = '#efece4'; // まだ一度も出ていない数字(バンドとは別扱い)
        const NEVER_DRAWN_TEXT = '#4a4a4a';

        let ballElements = {{}}; let currentIndex = 0; let lastDrawnAt = {{}}; let columns = [[], [], [], [], [], []]; let timer = null;
        let activeTab = 'board'; let freqWindowSize = 100;
        let pairMode = 'top20'; let selectedPairNum = null;
        let tierWindowSize = 100; // 座標マップの集計対象(直近何回)。renderTierTabで表示回数に合わせてクランプする。

        function setup() {{
            const board = document.getElementById('main-board');
            for (let i = 1; i <= 43; i++) {{
                const ball = document.createElement('div');
                ball.className = 'ball'; ball.id = 'ball-' + i; ball.innerText = i;
                board.appendChild(ball); ballElements[i] = ball;
                lastDrawnAt[i] = -1; columns[(i-1) % 6].push(i);
            }}
        }}

        function setupNumPicker() {{
            const picker = document.getElementById('num-picker');
            for (let i = 1; i <= 43; i++) {{
                const item = document.createElement('div');
                item.className = 'num-picker-item'; item.id = 'num-pick-' + i; item.innerText = i;
                item.onclick = () => selectPairNum(i);
                picker.appendChild(item);
            }}
        }}

        function seekTo(idx) {{
            if(fullData.length === 0) return;
            currentIndex = Math.max(0, Math.min(parseInt(idx), fullData.length - 1));
            columns = [[], [], [], [], [], []];
            for (let i = 1; i <= 43; i++) {{ columns[(i-1) % 6].push(i); lastDrawnAt[i] = -1; }}
            for(let i=0; i<=currentIndex; i++) {{
                const d = fullData[i];
                d.main.forEach(n => {{ lastDrawnAt[n] = i; columns = columns.map(c => c.filter(v => v !== n)); }});
                d.main.forEach((n, cIdx) => {{ columns[cIdx].unshift(n); }});
            }}
            render();
        }}

        function render() {{
            const draw = fullData[currentIndex];
            if(!draw) return;
            document.getElementById('current-id').innerText = draw.id;
            document.getElementById('current-date').innerText = draw.date;
            document.getElementById('slider').value = currentIndex;
            columns.forEach((col, cIdx) => {{
                col.forEach((num, rank) => {{
                    const el = ballElements[num];
                    // 11段(TIER_ROWS)を超えて積み上がった分は最終行にまとめ、
                    // 少しずつ右下にずらして「チップが積み重なっている」ように見せる。
                    const overflowDepth = Math.max(0, rank - TIER_ROWS);
                    const displayRow = Math.min(rank, TIER_ROWS);
                    el.style.left = (cIdx * 41 + 10 + overflowDepth * 5) + 'px';
                    el.style.top = (displayRow * 41 + 10 + overflowDepth * 5) + 'px';
                    const freshness = (lastDrawnAt[num] !== -1) ? currentIndex - lastDrawnAt[num] : -1;
                    const isActive = draw.main.includes(num);
                    if (freshness === -1) {{
                        el.classList.remove('toned');
                        el.style.backgroundColor = NEVER_DRAWN_BG; el.style.color = NEVER_DRAWN_TEXT;
                    }} else {{
                        const tier = Math.min(freshness, TIER_ROWS);
                        const band = bandOfTier(tier);
                        el.style.backgroundColor = BAND_COLORS[band];
                        el.style.color = BAND_TEXT[band];
                        // 直近の抽選で出た数字(active)は縁を白で最優先表示。それ以外は段のセルフトーン。
                        el.style.borderColor = isActive ? '#ffffff' : BAND_RING_COLOR[band];
                        el.classList.add('toned');
                    }}
                    if (isActive) el.classList.add('active'); else el.classList.remove('active');
                }});
            }});
            const bHist = document.getElementById('bonus-history'); bHist.innerHTML = '';
            for(let i=0; i<5; i++) {{
                const d = fullData[currentIndex - i];
                if(d) {{
                    const b = document.createElement('div');
                    b.className = 'bonus-ball' + (i === 0 ? ' latest' : '');
                    b.innerText = d.bonus;
                    bHist.appendChild(b);
                }}
            }}
            if (activeTab === 'freq') renderFreqTab();
            if (activeTab === 'pair') renderPairTab();
            if (activeTab === 'tier') renderTierTab();
        }}

        // ===== クイックピック（予想タブ） =====
        // 分布はPython側で全データから計算済みのものを埋め込んでいる。
        const QP_STATS = {qp_stats_json};
        const QP_HOT_WINDOW = 10;
        let qpPreset = 'random';
        let qpChoice = {{}};
        let qpLast = null;

        function qpSums() {{
            if (!qpSums._cache) qpSums._cache = fullData.map(d => d.main.reduce((a, b) => a + b, 0));
            return qpSums._cache;
        }}

        function qpSumRangePct(lo, hi) {{
            const s = qpSums();
            return s.filter(v => v >= lo && v <= hi).length / s.length * 100;
        }}

        // 直近N回で2回以上出た番号を「ホット」とみなす（頻度タブの見方と揃えている）。
        function qpHotNumbers() {{
            if (!qpHotNumbers._cache) {{
                const counts = {{}};
                fullData.slice(-QP_HOT_WINDOW).forEach(d => d.main.forEach(n => counts[n] = (counts[n] || 0) + 1));
                qpHotNumbers._cache = Object.keys(counts).filter(n => counts[n] >= 2).map(Number).sort((a, b) => a - b);
            }}
            return qpHotNumbers._cache;
        }}

        function qpFeatures(m) {{
            let sum = 0, odd = 0, low = 0, birthday = 0;
            for (const x of m) {{
                sum += x;
                if (x % 2) odd++;
                if (x <= 21) low++;
                if (x <= 31) birthday++;
            }}
            let run = 1, maxRun = 1, pairs = 0;
            const runNums = [];
            for (let i = 1; i < m.length; i++) {{
                if (m[i] === m[i - 1] + 1) {{ run++; pairs++; runNums.push(m[i - 1] + '-' + m[i]); }}
                else run = 1;
                if (run > maxRun) maxRun = run;
            }}
            const byDigit = {{}};
            m.forEach(x => (byDigit[x % 10] = byDigit[x % 10] || []).push(x));
            let dup = 1;
            const dupGroups = [];
            Object.keys(byDigit).forEach(d => {{
                const g = byDigit[d];
                if (g.length > dup) dup = g.length;
                if (g.length >= 2) dupGroups.push(g.join('・') + '(末' + d + ')');
            }});
            const hot = qpHotNumbers();
            return {{
                sum, odd, low, birthday, maxRun, pairs, dup, runNums, dupGroups,
                hotCount: m.filter(x => hot.indexOf(x) >= 0).length
            }};
        }}

        // 条件の定義。hintには「過去の何%がその条件に当てはまるか」を出して、
        // 選んでいる条件がどれくらい普通/珍しいのかが分かるようにしている。
        function qpCondDefs() {{
            const hot = qpHotNumbers();
            const pctOf = arr => idx => arr[idx].toFixed(1) + '%';
            const rawSum = (arr, from, to) => {{
                let t = 0;
                for (let i = from; i <= to; i++) t += arr[i];
                return t;
            }};
            const sumOf = (arr, from, to) => rawSum(arr, from, to).toFixed(1) + '%';
            const skewOf = arr => (rawSum(arr, 0, 1) + rawSum(arr, 5, 6)).toFixed(1) + '%';
            return [
                {{ key: 'sum', label: '合計値（過去の中央値は ' + QP_STATS.sumMedian + '）', opts: [
                    {{ v: 'any', label: 'おまかせ', hint: '制限なし', test: null }},
                    {{ v: 'loose', label: '90〜174', hint: qpSumRangePct(90, 174).toFixed(1) + '%', test: f => f.sum >= 90 && f.sum <= 174 }},
                    {{ v: 'normal', label: '100〜164', hint: qpSumRangePct(100, 164).toFixed(1) + '%', test: f => f.sum >= 100 && f.sum <= 164 }},
                    {{ v: 'tight', label: '110〜154', hint: qpSumRangePct(110, 154).toFixed(1) + '%', test: f => f.sum >= 110 && f.sum <= 154 }}
                ]}},
                {{ key: 'odd', label: '奇数と偶数のバランス', opts: [
                    {{ v: 'any', label: 'おまかせ', hint: '制限なし', test: null }},
                    {{ v: 'even', label: '3 : 3', hint: pctOf(QP_STATS.odd)(3), test: f => f.odd === 3 }},
                    {{ v: 'near', label: '2:4 〜 4:2', hint: sumOf(QP_STATS.odd, 2, 4), test: f => f.odd >= 2 && f.odd <= 4 }},
                    {{ v: 'skew', label: '偏らせる', hint: skewOf(QP_STATS.odd), test: f => f.odd <= 1 || f.odd >= 5 }}
                ]}},
                {{ key: 'low', label: '低位(1〜21)と高位(22〜43)のバランス', opts: [
                    {{ v: 'any', label: 'おまかせ', hint: '制限なし', test: null }},
                    {{ v: 'even', label: '3 : 3', hint: pctOf(QP_STATS.low)(3), test: f => f.low === 3 }},
                    {{ v: 'near', label: '2:4 〜 4:2', hint: sumOf(QP_STATS.low, 2, 4), test: f => f.low >= 2 && f.low <= 4 }},
                    {{ v: 'skew', label: '偏らせる', hint: skewOf(QP_STATS.low), test: f => f.low <= 1 || f.low >= 5 }}
                ]}},
                {{ key: 'run', label: '連続する数字（23-24 のような並び）', opts: [
                    {{ v: 'any', label: 'おまかせ', hint: '制限なし', test: null }},
                    {{ v: 'yes', label: '必ず入れる', hint: (100 - QP_STATS.maxRun[1]).toFixed(1) + '%', test: f => f.pairs >= 1 }},
                    {{ v: 'three', label: '3連続', hint: sumOf(QP_STATS.maxRun, 3, 6), test: f => f.maxRun >= 3 }},
                    {{ v: 'no', label: '入れない', hint: QP_STATS.maxRun[1].toFixed(1) + '%', test: f => f.pairs === 0 }}
                ]}},
                {{ key: 'digit', label: '下一桁の被り（7と17 のような引っ掛け）', opts: [
                    {{ v: 'any', label: 'おまかせ', hint: '制限なし', test: null }},
                    {{ v: 'yes', label: '必ず入れる', hint: (100 - QP_STATS.lastDigit[1]).toFixed(1) + '%', test: f => f.dup >= 2 }},
                    {{ v: 'three', label: '3つ被り', hint: sumOf(QP_STATS.lastDigit, 3, 6), test: f => f.dup >= 3 }},
                    {{ v: 'no', label: '入れない', hint: QP_STATS.lastDigit[1].toFixed(1) + '%', test: f => f.dup === 1 }}
                ]}},
                {{ key: 'hot', label: '直近' + QP_HOT_WINDOW + '回のホット番号（現在 ' + hot.length + ' 個: ' + hot.join(' ') + '）', opts: [
                    {{ v: 'any', label: '使わない', hint: '制限なし', test: null }},
                    {{ v: '2', label: '2個以上', hint: '', test: f => f.hotCount >= 2 }},
                    {{ v: '3', label: '3個以上', hint: '', test: f => f.hotCount >= 3 }},
                    {{ v: '4', label: '4個以上', hint: '', test: f => f.hotCount >= 4 }}
                ]}}
            ];
        }}

        const QP_PRESETS = {{
            random: {{
                desc: '条件を一切かけず、43個から6個を等確率で引きます。過去の傾向を無視するぶん「誰も選ばない形」も出ます。当選確率はどの方式でも同じなので、これがいちばん素直な引き方です。',
                choice: {{ sum: 'any', odd: 'any', low: 'any', run: 'any', digit: 'any', hot: 'any' }}
            }},
            strict: {{
                desc: '過去2000回超でいちばん出やすかった形に全部そろえます（合計110〜154・奇偶3:3・高低3:3・連続あり・下一桁の被りあり）。この5条件を同時に満たした回は過去に約4%あります。',
                choice: {{ sum: 'tight', odd: 'even', low: 'even', run: 'yes', digit: 'yes', hot: 'any' }}
            }},
            hot: {{
                desc: '直近' + QP_HOT_WINDOW + '回で2回以上出ている番号を4個以上入れて、合計値だけ標準の帯に収めます。「流れが来ている番号」に乗る引き方です（統計的な裏づけはありません）。',
                choice: {{ sum: 'normal', odd: 'any', low: 'any', run: 'any', digit: 'any', hot: '4' }}
            }}
        }};

        function renderQuickPickTab() {{
            renderQpNumPicker();
            if (!Object.keys(qpChoice).length) setQpPreset('random');
            else renderQpCond();
        }}

        function setQpPreset(name, skipDraw) {{
            qpPreset = name;
            qpChoice = Object.assign({{}}, QP_PRESETS[name].choice);
            ['random', 'strict', 'hot'].forEach(k => {{
                document.getElementById('qp-preset-btn-' + k).classList.toggle('active-toggle', k === name);
            }});
            document.getElementById('qp-preset-desc').textContent = QP_PRESETS[name].desc;
            renderQpCond();
            if (!skipDraw) drawQuickPick();
        }}

        function setQpCond(key, value) {{
            qpChoice[key] = value;
            document.getElementById('qp-preset-desc').textContent = 'カスタム条件で引きます。' + QP_PRESETS[qpPreset].desc;
            renderQpCond();
        }}

        function renderQpCond() {{
            const html = qpCondDefs().map(c => {{
                const opts = c.opts.map(o => {{
                    const on = qpChoice[c.key] === o.v ? ' active-toggle' : '';
                    const hint = o.hint ? '<span class="qp-hint">' + o.hint + '</span>' : '';
                    return '<button class="btn' + on + '" onclick="setQpCond(\\'' + c.key + '\\',\\'' + o.v + '\\')">' + o.label + hint + '</button>';
                }}).join('');
                return '<div><div class="qp-cond-label">' + c.label + '</div><div class="qp-cond-opts">' + opts + '</div></div>';
            }}).join('');
            document.getElementById('qp-cond').innerHTML = html;
        }}

        // 使う数字の手動指定。qpNumState[番号] = 'keep'(必ず入れる) / 'ban'(除外)。
        // タップするたび なし → keep → ban → なし と切り替わる。
        let qpNumState = {{}};

        function qpKeepNums() {{
            return Object.keys(qpNumState).filter(n => qpNumState[n] === 'keep').map(Number).sort((a, b) => a - b);
        }}

        function qpBanNums() {{
            return Object.keys(qpNumState).filter(n => qpNumState[n] === 'ban').map(Number).sort((a, b) => a - b);
        }}

        function toggleQpNum(n) {{
            const msg = document.getElementById('qp-num-msg');
            msg.textContent = '';
            const cur = qpNumState[n];
            if (!cur) {{
                if (qpKeepNums().length >= 6) msg.textContent = '「必ず入れる」は6個までです。外したい番号をもう一度タップしてください。';
                else qpNumState[n] = 'keep';
            }} else if (cur === 'keep') {{
                // 除外に回すと残りが6個未満になる場合は指定なしに戻す
                if (43 - qpBanNums().length - 1 < 6) {{
                    msg.textContent = '除外しすぎです（残る番号が6個を下回ります）。指定なしに戻しました。';
                    delete qpNumState[n];
                }} else {{
                    qpNumState[n] = 'ban';
                }}
            }} else {{
                delete qpNumState[n];
            }}
            renderQpNumPicker();
        }}

        function clearQpNums() {{
            qpNumState = {{}};
            document.getElementById('qp-num-msg').textContent = '';
            renderQpNumPicker();
        }}

        function renderQpNumPicker() {{
            const picker = document.getElementById('qp-num-picker');
            picker.innerHTML = '';
            for (let i = 1; i <= 43; i++) {{
                const item = document.createElement('div');
                item.className = 'num-picker-item qp-num-item' + (qpNumState[i] ? ' ' + qpNumState[i] : '');
                item.textContent = i;
                item.onclick = () => toggleQpNum(i);
                picker.appendChild(item);
            }}
            const keeps = qpKeepNums(), bans = qpBanNums();
            document.getElementById('qp-num-summary').innerHTML =
                '<span class="keep-label">◎ 必ず入れる</span>： ' + (keeps.length ? keeps.join('  ') : '指定なし') + '<br>' +
                '<span class="ban-label">✕ 除外する</span>： ' + (bans.length ? bans.join('  ') : '指定なし') +
                (keeps.length >= 6 ? '<br>6個すべて指定されているので、この目で固定されます（他の条件は使いません）。' : '');
        }}

        function qpRandomSix() {{
            const keep = qpKeepNums();
            const pool = [];
            for (let i = 1; i <= 43; i++) if (!qpNumState[i]) pool.push(i);
            const need = Math.max(0, 6 - keep.length);
            for (let i = 0; i < need; i++) {{
                const j = i + Math.floor(Math.random() * (pool.length - i));
                const t = pool[i]; pool[i] = pool[j]; pool[j] = t;
            }}
            return keep.concat(pool.slice(0, need)).sort((a, b) => a - b);
        }}

        function qpActiveTests() {{
            const out = [];
            qpCondDefs().forEach(c => {{
                const opt = c.opts.find(o => o.v === qpChoice[c.key]);
                if (opt && opt.test) out.push({{ key: c.key, label: c.label.split('（')[0], test: opt.test }});
            }});
            return out;
        }}

        // 条件を満たす目が出るまで引き直す（棄却サンプリング）。
        // 厳しすぎて出ないときは、後ろの条件から順に外して必ず1口返す。
        function drawQuickPick() {{
            let tests = qpKeepNums().length >= 6 ? [] : qpActiveTests();
            const dropped = [];
            let picked = null;
            while (true) {{
                for (let t = 0; t < 30000; t++) {{
                    const m = qpRandomSix();
                    const f = qpFeatures(m);
                    if (tests.every(c => c.test(f))) {{ picked = m; break; }}
                }}
                if (picked || !tests.length) break;
                dropped.push(tests[tests.length - 1].label);
                tests = tests.slice(0, -1);
            }}
            if (!picked) picked = qpRandomSix();
            qpLast = picked;
            const warn = document.getElementById('qp-warn');
            if (dropped.length) {{
                warn.style.display = 'block';
                warn.textContent = '条件が厳しすぎて同時には満たせなかったため、「' + dropped.join('」「') + '」の条件を外して引きました。';
            }} else {{
                warn.style.display = 'none';
            }}
            renderQpResult(picked);
        }}

        function qpBar(pct, maxPct) {{
            return '<div class="qp-diag-bar-wrap"><div class="qp-diag-bar" style="width:' + (maxPct ? Math.min(100, pct / maxPct * 100) : 0) + '%"></div></div>';
        }}

        function qpRow(name, value, pct, maxPct, note, isTop) {{
            return '<div class="qp-diag-row' + (isTop ? ' top' : '') + '">' +
                '<div class="qp-diag-name">' + name + '</div>' +
                '<div class="qp-diag-val">' + value + '</div>' +
                qpBar(pct, maxPct) +
                '<div class="qp-diag-pct">' + note + '</div></div>';
        }}

        function renderQpResult(m) {{
            const f = qpFeatures(m);
            const hot = qpHotNumbers();
            document.getElementById('qp-balls').innerHTML = m.map(n =>
                '<div class="qp-ball' + (hot.indexOf(n) >= 0 ? ' hot' : '') +
                (qpNumState[n] === 'keep' ? ' keep' : '') + '">' + n + '</div>').join('');

            const bandKey = String(Math.floor(f.sum / QP_STATS.sumBand) * QP_STATS.sumBand);
            const bandPct = QP_STATS.sumBands[bandKey] || 0;
            const maxBand = Math.max.apply(null, Object.keys(QP_STATS.sumBands).map(k => QP_STATS.sumBands[k]));
            const maxOf = arr => Math.max.apply(null, arr);
            const isTop = (arr, i) => arr[i] === maxOf(arr);

            const rows = [
                qpRow('合計値', String(f.sum),
                    bandPct, maxBand,
                    bandPct.toFixed(1) + '%',
                    bandPct === maxBand),
                qpRow('奇数:偶数', f.odd + ' : ' + (6 - f.odd),
                    QP_STATS.odd[f.odd], maxOf(QP_STATS.odd),
                    QP_STATS.odd[f.odd].toFixed(1) + '%',
                    isTop(QP_STATS.odd, f.odd)),
                qpRow('低位:高位', f.low + ' : ' + (6 - f.low),
                    QP_STATS.low[f.low], maxOf(QP_STATS.low),
                    QP_STATS.low[f.low].toFixed(1) + '%',
                    isTop(QP_STATS.low, f.low)),
                qpRow('連続数字', f.pairs ? f.runNums.join(' ') : 'なし',
                    QP_STATS.maxRun[f.maxRun], maxOf(QP_STATS.maxRun),
                    QP_STATS.maxRun[f.maxRun].toFixed(1) + '%',
                    isTop(QP_STATS.maxRun, f.maxRun)),
                qpRow('下一桁', f.dup >= 2 ? f.dupGroups.join(' / ') : '被りなし',
                    QP_STATS.lastDigit[f.dup], maxOf(QP_STATS.lastDigit),
                    QP_STATS.lastDigit[f.dup].toFixed(1) + '%',
                    isTop(QP_STATS.lastDigit, f.dup)),
                qpRow('1〜31', f.birthday + ' 個',
                    QP_STATS.birthday[f.birthday], maxOf(QP_STATS.birthday),
                    f.birthday >= 6 ? '人気 高' : (f.birthday === 5 ? '人気 中' : '人気 低'),
                    false),
                qpRow('ホット', f.hotCount + ' 個', 0, 0, '直近' + QP_HOT_WINDOW + '回', false)
            ];

            // 「過去の出目らしさ」= 各項目の実測割合が、その項目の最頻値に対して何割かの平均。
            // 最頻の形ばかりなら100点、珍しい形が混ざるほど下がる。
            const ratios = [
                bandPct / maxBand,
                QP_STATS.odd[f.odd] / maxOf(QP_STATS.odd),
                QP_STATS.low[f.low] / maxOf(QP_STATS.low),
                QP_STATS.maxRun[f.maxRun] / maxOf(QP_STATS.maxRun),
                QP_STATS.lastDigit[f.dup] / maxOf(QP_STATS.lastDigit)
            ];
            const score = Math.round(ratios.reduce((a, b) => a + b, 0) / ratios.length * 100);
            const comment = score >= 80 ? 'ど真ん中。過去にいちばんよくある形です'
                : score >= 55 ? 'ありふれた形の範囲内です'
                : score >= 30 ? 'やや珍しい形です'
                : 'かなり珍しい形。誰とも被らないかもしれません';

            document.getElementById('qp-diagnosis').innerHTML =
                '<div class="qp-diag-head">この目の診断（全' + QP_STATS.n + '回との比較）</div>' +
                '<div class="qp-diag-note">％＝過去に同じ形だった回の割合（合計値は10刻みの帯で判定）。★はその項目でいちばん多い形。オレンジのボールは直近' + QP_HOT_WINDOW + '回のホット番号、白い二重枠は自分で指定した番号です。</div>' +
                rows.join('') +
                '<div class="qp-score"><span class="qp-score-num">' + score + '</span>' +
                '<span class="qp-score-label">点／過去の出目らしさ・' + comment + '</span></div>';
        }}

        function switchTab(name) {{
            activeTab = name;
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-' + name).classList.add('active');
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-btn-' + name).classList.add('active');
            if (name === 'freq') renderFreqTab();
            if (name === 'pair') renderPairTab();
            if (name === 'tier') renderTierTab();
            if (name === 'qp') renderQuickPickTab();
        }}

        function setFreqWindow(v) {{
            freqWindowSize = parseInt(v, 10);
            renderFreqTab();
        }}

        function setFreqWindowAll() {{
            freqWindowSize = currentIndex + 1;
            renderFreqTab();
        }}

        function computeFrequency(windowSize) {{
            const counts = {{}};
            for (let i = 1; i <= 43; i++) counts[i] = 0;
            const start = Math.max(0, currentIndex - windowSize + 1);
            for (let i = start; i <= currentIndex; i++) {{
                fullData[i].main.forEach(n => counts[n]++);
            }}
            return {{ counts, start }};
        }}

        function renderFreqList(counts) {{
            const entries = Object.keys(counts).map(n => ({{ num: parseInt(n), count: counts[n] }}));
            entries.sort((a, b) => b.count - a.count || a.num - b.num);
            const max = entries.length ? entries[0].count : 1;

            const list = document.getElementById('freq-list');
            list.innerHTML = '';
            entries.forEach((e, rank) => {{
                const row = document.createElement('div');
                row.className = 'freq-row';

                const rankEl = document.createElement('div');
                rankEl.className = 'freq-rank'; rankEl.innerText = (rank + 1) + '.';

                const badge = document.createElement('div');
                badge.className = 'freq-badge'; badge.innerText = e.num;

                const barWrap = document.createElement('div');
                barWrap.className = 'freq-bar-wrap';
                const bar = document.createElement('div');
                bar.className = 'freq-bar';
                bar.style.width = (max > 0 ? (e.count / max * 100) : 0) + '%';
                barWrap.appendChild(bar);

                const countEl = document.createElement('div');
                countEl.className = 'freq-count'; countEl.innerText = e.count;

                const chip = document.createElement('div');
                chip.className = 'freq-chip';
                if (rank < 3) {{ chip.classList.add('hot'); chip.innerText = 'HOT'; }}
                else if (rank >= entries.length - 3) {{ chip.classList.add('cold'); chip.innerText = 'COLD'; }}

                row.appendChild(rankEl); row.appendChild(badge); row.appendChild(barWrap);
                row.appendChild(countEl); row.appendChild(chip);
                list.appendChild(row);
            }});
        }}

        function renderFreqTab() {{
            if (fullData.length === 0) return;

            const totalDraws = currentIndex + 1;
            const sliderEl = document.getElementById('freq-window-slider');
            sliderEl.min = Math.min(10, totalDraws);
            sliderEl.max = totalDraws;
            if (freqWindowSize > totalDraws) freqWindowSize = totalDraws;
            sliderEl.value = freqWindowSize;
            document.getElementById('freq-window-value').innerText = freqWindowSize;

            const {{ counts, start }} = computeFrequency(freqWindowSize);

            renderFreqList(counts);

            const caption = document.getElementById('freq-caption');
            const drawCount = currentIndex - start + 1;
            caption.innerText = (freqWindowSize >= totalDraws)
                ? `全期間（第${{fullData[start].id}}回〜第${{fullData[currentIndex].id}}回、${{drawCount}}回分）`
                : `直近${{drawCount}}回（第${{fullData[start].id}}回〜第${{fullData[currentIndex].id}}回）`;
        }}

        function setPairMode(mode) {{
            pairMode = mode;
            document.getElementById('pair-mode-top20').classList.toggle('active-toggle', mode === 'top20');
            document.getElementById('pair-mode-zscore').classList.toggle('active-toggle', mode === 'zscore');
            document.getElementById('pair-mode-bynum').classList.toggle('active-toggle', mode === 'bynum');
            document.getElementById('pair-top20-section').classList.toggle('active', mode === 'top20');
            document.getElementById('pair-zscore-section').classList.toggle('active', mode === 'zscore');
            document.getElementById('pair-bynum-section').classList.toggle('active', mode === 'bynum');
            renderPairTab();
        }}

        function selectPairNum(n) {{
            selectedPairNum = n;
            renderPairTab();
        }}

        function computePairCounts() {{
            const counts = {{}};
            for (let i = 0; i <= currentIndex; i++) {{
                const m = fullData[i].main;
                for (let a = 0; a < m.length; a++) {{
                    for (let b = a + 1; b < m.length; b++) {{
                        const lo = Math.min(m[a], m[b]), hi = Math.max(m[a], m[b]);
                        const key = lo + '-' + hi;
                        counts[key] = (counts[key] || 0) + 1;
                    }}
                }}
            }}
            return counts;
        }}

        function makeRankRow(rank, badgeNode, count, max, opts) {{
            opts = opts || {{}};
            const row = document.createElement('div');
            row.className = 'freq-row';
            const rankEl = document.createElement('div'); rankEl.className = 'freq-rank'; rankEl.innerText = (rank + 1) + '.';
            const barWrap = document.createElement('div'); barWrap.className = 'freq-bar-wrap';
            const bar = document.createElement('div'); bar.className = 'freq-bar' + (opts.barClass ? ' ' + opts.barClass : '');
            bar.style.width = (max > 0 ? (Math.abs(opts.barValue !== undefined ? opts.barValue : count) / max * 100) : 0) + '%';
            barWrap.appendChild(bar);
            const countEl = document.createElement('div'); countEl.className = 'freq-count'; countEl.innerText = opts.label !== undefined ? opts.label : count;
            row.appendChild(rankEl); row.appendChild(badgeNode); row.appendChild(barWrap); row.appendChild(countEl);
            return row;
        }}

        // 43番号から2つ選ぶ組み合わせが「どちらもその回に含まれる」確率(理論値、抽選回数によらず一定)
        const PAIR_HIT_PROB = 101270 / 6096454; // C(41,4) / C(43,6)

        function computePairZScores(pairCounts) {{
            const N = currentIndex + 1;
            const expected = N * PAIR_HIT_PROB;
            const std = Math.sqrt(N * PAIR_HIT_PROB * (1 - PAIR_HIT_PROB));
            const list = [];
            for (let a = 1; a <= 43; a++) {{
                for (let b = a + 1; b <= 43; b++) {{
                    const count = pairCounts[a + '-' + b] || 0;
                    const z = std > 0 ? (count - expected) / std : 0;
                    list.push({{ a, b, count, z }});
                }}
            }}
            return {{ list, expected, N }};
        }}

        function makePairBadgeGroup(a, b) {{
            const group = document.createElement('div'); group.className = 'pair-badge-group';
            const b1 = document.createElement('div'); b1.className = 'pair-badge'; b1.innerText = a;
            const dash = document.createElement('span'); dash.className = 'pair-dash'; dash.innerText = '-';
            const b2 = document.createElement('div'); b2.className = 'pair-badge'; b2.innerText = b;
            group.appendChild(b1); group.appendChild(dash); group.appendChild(b2);
            return group;
        }}

        function renderPairTab() {{
            if (fullData.length === 0) return;
            const pairCounts = computePairCounts();

            if (pairMode === 'top20') {{
                const entries = Object.keys(pairCounts).map(k => {{
                    const parts = k.split('-').map(Number);
                    return {{ a: parts[0], b: parts[1], count: pairCounts[k] }};
                }});
                entries.sort((x, y) => y.count - x.count || x.a - y.a || x.b - y.b);
                const top = entries.slice(0, 20);
                const max = top.length ? top[0].count : 1;
                const list = document.getElementById('pair-top20-list');
                list.innerHTML = '';
                top.forEach((e, rank) => {{
                    list.appendChild(makeRankRow(rank, makePairBadgeGroup(e.a, e.b), e.count, max));
                }});
                document.getElementById('pair-top20-caption').innerText =
                    `よく出るペア TOP20（第1回〜第${{fullData[currentIndex].id}}回）`;
            }} else if (pairMode === 'zscore') {{
                const {{ list: zlist, expected, N }} = computePairZScores(pairCounts);
                const over = zlist.filter(e => e.z > 0).sort((x, y) => y.z - x.z).slice(0, 10);
                const under = zlist.filter(e => e.z < 0).sort((x, y) => x.z - y.z).slice(0, 10);
                const maxAbsZ = Math.max(
                    over.length ? over[0].z : 0,
                    under.length ? Math.abs(under[0].z) : 0,
                    0.001
                );

                const overList = document.getElementById('pair-over-list');
                overList.innerHTML = '';
                over.forEach((e, rank) => {{
                    overList.appendChild(makeRankRow(rank, makePairBadgeGroup(e.a, e.b), e.count, maxAbsZ, {{
                        barValue: e.z, label: (e.z >= 0 ? '+' : '') + e.z.toFixed(2)
                    }}));
                }});

                const underList = document.getElementById('pair-under-list');
                underList.innerHTML = '';
                under.forEach((e, rank) => {{
                    underList.appendChild(makeRankRow(rank, makePairBadgeGroup(e.a, e.b), e.count, maxAbsZ, {{
                        barValue: e.z, label: e.z.toFixed(2), barClass: 'cold'
                    }}));
                }});

                const note = document.querySelector('#pair-zscore-section .freq-caption');
                note.innerText = `理論上の期待出現数と比べたズレの大きさ（z値）で並べています。第1回〜第${{fullData[currentIndex].id}}回・期待値${{expected.toFixed(1)}}回が基準（母数${{N}}回）。`;
            }} else {{
                if (selectedPairNum === null) selectedPairNum = fullData[currentIndex].main[0];
                document.querySelectorAll('.num-picker-item').forEach(x => x.classList.remove('selected'));
                const picked = document.getElementById('num-pick-' + selectedPairNum);
                if (picked) picked.classList.add('selected');

                const partners = [];
                for (let n = 1; n <= 43; n++) {{
                    if (n === selectedPairNum) continue;
                    const lo = Math.min(n, selectedPairNum), hi = Math.max(n, selectedPairNum);
                    partners.push({{ num: n, count: pairCounts[lo + '-' + hi] || 0 }});
                }}
                partners.sort((x, y) => y.count - x.count || x.num - y.num);
                const top = partners.slice(0, 10);
                const max = top.length ? top[0].count : 1;
                const list = document.getElementById('pair-partner-list');
                list.innerHTML = '';
                top.forEach((e, rank) => {{
                    const badge = document.createElement('div'); badge.className = 'freq-badge'; badge.innerText = e.num;
                    list.appendChild(makeRankRow(rank, badge, e.count, max));
                }});
                document.getElementById('pair-bynum-caption').innerText =
                    `「${{selectedPairNum}}」の相棒ランキング（第1回〜第${{fullData[currentIndex].id}}回）`;
            }}
        }}

        function setTierWindow(v) {{
            tierWindowSize = parseInt(v, 10);
            renderTierTab();
        }}

        function setTierWindowAll() {{
            tierWindowSize = currentIndex + 1;
            renderTierTab();
        }}

        // 盤面の実アルゴリズム(列=その回の昇順順位、段=同じ座標を最後に明け渡してからの深さ)を
        // 第1回から忠実に再生し、「(列, 段)座標で再登場が起きた回数」を集計する。
        // windowSizeを絞った場合でも、座標の状態を正しく保つため必ず第1回からシミュレートし、
        // 集計対象(タリー)だけを直近windowSize回に絞る。
        function computeTierMatrix(windowSize) {{
            const cols = [[], [], [], [], [], []];
            for (let i = 1; i <= 43; i++) cols[(i - 1) % 6].push(i);
            const seenBefore = new Set();
            const matrix = {{}};
            const windowStart = Math.max(0, currentIndex - windowSize + 1);

            for (let idx = 0; idx <= currentIndex; idx++) {{
                const m = fullData[idx].main;
                for (let pos = 0; pos < 6; pos++) {{
                    const n = m[pos];
                    if (seenBefore.has(n) && idx >= windowStart) {{
                        let tier = -1, colIdx = -1;
                        for (let ci = 0; ci < 6; ci++) {{
                            const t = cols[ci].indexOf(n);
                            if (t !== -1) {{ tier = t; colIdx = ci; break; }}
                        }}
                        const row = Math.min(tier, TIER_ROWS); // TIER_ROWS以上はまとめて最終行
                        const key = colIdx + '-' + row;
                        matrix[key] = (matrix[key] || 0) + 1;
                    }}
                    seenBefore.add(n);
                }}
                // 実アルゴリズムと同じ手順(削除してから各列の先頭に挿入)で座標を更新
                m.forEach(n => {{
                    for (let ci = 0; ci < 6; ci++) {{
                        const p = cols[ci].indexOf(n);
                        if (p !== -1) {{ cols[ci].splice(p, 1); break; }}
                    }}
                }});
                m.forEach((n, pos) => cols[pos].unshift(n));
            }}
            return matrix;
        }}

        function renderTierTab() {{
            if (fullData.length === 0) return;

            // スライダーの範囲は「今表示中の回までの総数」に追従させる。表示中の回を
            // 遡ると総数が減るので、選択中のwindowSizeがそれを超えていたら詰める。
            const totalDraws = currentIndex + 1;
            const sliderEl = document.getElementById('tier-window-slider');
            sliderEl.min = Math.min(10, totalDraws);
            sliderEl.max = totalDraws;
            if (tierWindowSize > totalDraws) tierWindowSize = totalDraws;
            sliderEl.value = tierWindowSize;
            document.getElementById('tier-window-value').innerText = tierWindowSize;

            const matrix = computeTierMatrix(tierWindowSize);

            const values = Object.values(matrix);
            const maxV = values.length ? Math.max(...values) : 1;

            // 段ごと・列ごとの合計(行/列マージン)。
            const rowTotals = new Array(TIER_ROWS + 1).fill(0);
            const colTotals = new Array(6).fill(0);
            for (let row = 0; row <= TIER_ROWS; row++) {{
                for (let c = 0; c < 6; c++) {{
                    const v = matrix[c + '-' + row] || 0;
                    rowTotals[row] += v;
                    colTotals[c] += v;
                }}
            }}

            const table = document.getElementById('tier-table');
            table.innerHTML = '';

            const headRow = document.createElement('tr');
            headRow.appendChild(document.createElement('th'));
            for (let c = 1; c <= 6; c++) {{
                const th = document.createElement('th');
                const labelDiv = document.createElement('div'); labelDiv.innerText = c + '列目';
                const totalDiv = document.createElement('div'); totalDiv.className = 'tier-total'; totalDiv.innerText = colTotals[c - 1];
                th.appendChild(labelDiv); th.appendChild(totalDiv);
                headRow.appendChild(th);
            }}
            table.appendChild(headRow);

            for (let row = 0; row <= TIER_ROWS; row++) {{
                const tr = document.createElement('tr');
                const labelTd = document.createElement('td'); labelTd.className = 'tier-label';
                const labelDiv = document.createElement('div');
                labelDiv.innerText = TIER_LABELS[row] + '段' + (row === TIER_ROWS ? '+' : '');
                const totalDiv = document.createElement('div'); totalDiv.className = 'tier-total'; totalDiv.innerText = rowTotals[row];
                labelTd.appendChild(labelDiv); labelTd.appendChild(totalDiv);
                tr.appendChild(labelTd);
                for (let c = 0; c < 6; c++) {{
                    const v = matrix[c + '-' + row] || 0;
                    const td = document.createElement('td'); td.className = 'tier-cell';
                    const alpha = maxV > 0 ? 0.12 + (v / maxV) * 0.85 : 0.12;
                    td.style.background = `rgba(212,175,55,${{alpha.toFixed(3)}})`;
                    td.innerText = v;
                    tr.appendChild(td);
                }}
                table.appendChild(tr);
            }}

            document.getElementById('tier-caption').innerText = (tierWindowSize >= totalDraws)
                ? `全期間（第1回〜第${{fullData[currentIndex].id}}回、${{totalDraws}}回分）`
                : `直近${{tierWindowSize}}回（第${{fullData[Math.max(0, currentIndex - tierWindowSize + 1)].id}}回〜第${{fullData[currentIndex].id}}回）`;
        }}

        async function stepForward() {{
            if (currentIndex >= fullData.length - 1) return;
            const next = fullData[currentIndex + 1];
            next.main.forEach(n => document.getElementById('ball-' + n).classList.add('glow-float'));
            await new Promise(r => setTimeout(r, 600));
            next.main.forEach(n => document.getElementById('ball-' + n).classList.remove('glow-float'));
            seekTo(currentIndex + 1);
        }}

        // 「次へ」の逆再生。今表示中の回の数字を軽く光らせてから1つ前の回へ戻る。
        async function stepBackward() {{
            if (currentIndex <= 0) return;
            const cur = fullData[currentIndex];
            cur.main.forEach(n => document.getElementById('ball-' + n).classList.add('glow-float'));
            await new Promise(r => setTimeout(r, 400));
            cur.main.forEach(n => document.getElementById('ball-' + n).classList.remove('glow-float'));
            seekTo(currentIndex - 1);
        }}

        function jump(s) {{ seekTo(currentIndex + s); }}

        // 自動再生の間隔(ms)。スライダーの1(遅い)〜10(速い)に対応。
        const AUTO_INTERVALS = [3000, 2600, 2200, 1800, 1500, 1200, 900, 700, 500, 350];
        let autoSpeed = 4; // 既定値(1800ms)は変更前の速度と同じ

        function startAutoTimer() {{
            if (timer) clearInterval(timer);
            timer = setInterval(() => {{ if(currentIndex < fullData.length - 1) stepForward(); else toggleAuto(); }}, AUTO_INTERVALS[autoSpeed - 1]);
        }}
        function toggleAuto() {{
            if(timer) {{ clearInterval(timer); timer = null; }}
            else {{ startAutoTimer(); }}
        }}
        function setAutoSpeed(v) {{
            autoSpeed = parseInt(v, 10);
            if (timer) startAutoTimer(); // 再生中ならその場で速度を切り替える
        }}
        setup();
        setupNumPicker();
        if(fullData.length > 0) {{
            document.getElementById('slider').max = fullData.length - 1;
            seekTo(fullData.length - 1);
        }}
    </script>
</body>
</html>
"""

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"生成完了: {OUTPUT_FILE} が作成されました。")

if __name__ == '__main__':
    main()
