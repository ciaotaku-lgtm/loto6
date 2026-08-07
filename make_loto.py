import urllib.request
import csv
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
            history.append({
                "id": int(row[0]),
                "date": row[1],
                "main": main_nums,
                "bonus": int(row[8])
            })
        except ValueError:
            skipped += 1
            continue

    if skipped:
        print(f"⚠ CSVの{skipped}行を解析できずスキップしました。データ提供元のCSV形式が変わっていないか確認してください。")

    # 時系列（古い順）に並べ替え
    history.sort(key=lambda x: x["id"])
    return history


def compute_tier_distribution(history):
    """盤面・座標タブと同じアルゴリズム(列=昇順順位・段=move-to-front方式)で、
    (列,段)ごとの再登場回数を全期間で集計し、段ごとの再登場回数と総数を返す。"""
    tier_rows = 11
    cols = [[] for _ in range(6)]
    for i in range(1, 44):
        cols[(i - 1) % 6].append(i)
    seen = set()
    tier_counts = [0] * (tier_rows + 1)
    total = 0
    for d in history:
        m = d["main"]
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
    return tier_counts, total


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


def build_trivia_html(history):
    """座標分布の形・連続未出記録・ボーナス俗説の検証を、トリビアタブ用のHTMLカードにする。"""
    tier_counts, tier_total = compute_tier_distribution(history)
    tier_pct = [c / tier_total * 100 for c in tier_counts] if tier_total else [0] * len(tier_counts)
    top4_min, top4_max = min(tier_pct[:4]), max(tier_pct[:4])
    tail_pct = sum(tier_pct[9:])

    droughts = compute_droughts(history)
    end = droughts["longest_end"]
    end_text = f"第{end['id']}回（{end['date']}）でようやく再登場しました" if end else "まだ再登場していません"
    current_top_text = "、".join(f"{num}番（{gap}回）" for num, gap in droughts["current_top"])

    bonus = compute_bonus_trivia(history)

    cards = [
        f'''<div class="trivia-card">
            <h3 class="trivia-title">座標(段)の分布は「なだらか→崖」の形</h3>
            <p class="trivia-body">全<span class="num">{len(history)}</span>回・のべ<span class="num">{tier_total:,}</span>回の再登場を集計すると、1〜4段目は<span class="num">{top4_min:.1f}〜{top4_max:.1f}%</span>でほぼ横並び、5段目あたりから急に減っていきます（10段目以降は合計<span class="num">{tail_pct:.1f}%</span>）。これは「直近に出た数字が列の先頭に来る」しくみ（move-to-front方式の自己組織化リストと同じ構造）による形で、抽選そのものの偏りではありません。</p>
        </div>''',
        f'''<div class="trivia-card">
            <h3 class="trivia-title">連続未出（干上がり）記録</h3>
            <p class="trivia-body">過去最長の連続未出は<span class="num">{droughts['longest_num']}番</span>の<span class="num">{droughts['longest_gap']}回</span>連続。{end_text}。現時点で連続未出が長いのは{current_top_text}です。</p>
        </div>''',
        f'''<div class="trivia-card">
            <h3 class="trivia-title">ボーナス数字の都市伝説を検証</h3>
            <p class="trivia-body">「前回のボーナス数字は次回、本数字として出やすい」という説を検証すると<span class="num">{bonus['bonus_to_next_main_rate']:.2f}%</span>（基準値{bonus['baseline_rate']:.2f}%）、逆に「前回の本数字は次回ボーナスになりやすい」も<span class="num">{bonus['main_to_next_bonus_rate']:.2f}%</span>で、どちらも俗説は成立しませんでした。ちなみにボーナス数字が本数字の最小〜最大の範囲内に収まる確率は<span class="num">{bonus['within_range_rate']:.1f}%</span>ですが、これは6個の数字が散らばれば7個目がその間に入りやすいという組み合わせ論の話で、特別な偏りではありません。</p>
        </div>''',
    ]
    return "\n".join(cards)


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

    data_json = json.dumps(history)
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
        .tab-bar {{ display: flex; flex-wrap: wrap; gap: 6px; width: 100%; max-width: 340px; justify-content: center; margin-bottom: 12px; }}
        .tab-btn {{ flex: 1; min-width: 56px; background: transparent; color: #8a7a5c; border: 1px solid rgba(212,175,55,0.35); padding: 8px 4px; border-radius: 14px; font-size: 13px; font-weight: bold; cursor: pointer; transition: all 0.2s; }}
        .tab-btn.active {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border-color: #d4af37; box-shadow: 0 0 12px rgba(212,175,55,0.4); }}
        .tab-panel {{ display: none; width: 100%; flex-direction: column; align-items: center; }}
        .tab-panel.active {{ display: flex; }}

        /* --- 出現頻度ランキング --- */
        .freq-toggle {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 8px; }}
        .freq-toggle .btn.active-toggle {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border-color: #d4af37; }}
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

        function switchTab(name) {{
            activeTab = name;
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.getElementById('panel-' + name).classList.add('active');
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById('tab-btn-' + name).classList.add('active');
            if (name === 'freq') renderFreqTab();
            if (name === 'pair') renderPairTab();
            if (name === 'tier') renderTierTab();
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
