import urllib.request
import csv
import json
import io
import os

# mk-mode SITE が公開している第1回からの全回データCSV
# （旧ソース loto6.the-luck.jp は名前解決できなくなったため差し替え）
DATA_URL = "https://www.mk-mode.com/rails/loto/LOTO6_ALL.csv"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loto6_history.json")


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
    for row in reader:
        if not row or len(row) < 9:
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
            continue

    # 時系列（古い順）に並べ替え
    history.sort(key=lambda x: x["id"])
    return history


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
        .main-board {{ position: relative; width: 260px; height: 440px; background: rgba(0,0,0,0.85); padding: 10px; border-radius: 25px 25px 0 0; border: 2.5px solid #d4af37; border-bottom: none; box-shadow: 0 -10px 30px rgba(0,0,0,0.8); }}
        .ball {{ position: absolute; width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 14px; border: 1.1px solid rgba(255, 255, 255, 0.4); box-shadow: 0 4px 8px rgba(0,0,0,0.5), inset -1px -1px 3px rgba(0,0,0,0.3); transition: left 0.8s cubic-bezier(0.34, 1.56, 0.64, 1), top 0.8s cubic-bezier(0.34, 1.56, 0.64, 1), background-color 0.6s; z-index: 10; }}
        .ball.glow-float {{ z-index: 100; transform: scale(1.6) translateY(-25px) !important; background-color: #ffffff !important; color: #000 !important; box-shadow: 0 0 30px #fff, 0 0 50px #ffd700; border-color: #fff; transition: transform 0.4s ease-out, background-color 0.3s !important; }}
        .ball.active {{ border-color: #fff; box-shadow: 0 0 12px rgba(255,215,0,0.7); }}
        .bonus-section {{ display: flex; flex-direction: column; align-items: center; gap: 5px; min-width: 50px; }}
        .bonus-box {{ display: flex; flex-direction: column; gap: 8px; background: rgba(255, 255, 255, 0.08); padding: 10px; border-radius: 15px; border: 1.5px solid rgba(212, 175, 55, 0.3); align-items: center; }}
        .bonus-ball {{ width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; background: #222; border: 1px solid #d4af37; font-size: 11px; color: #ffd700; }}
        .bonus-ball.latest {{ width: 44px; height: 44px; font-size: 18px; box-shadow: 0 0 15px #d4af37; background: radial-gradient(circle, #ffd700, #b8860b); color: #1a120b; margin-bottom: 3px; }}
        .controls {{ position: fixed; bottom: 0; width: 100%; max-width: 480px; background: rgba(15, 10, 7, 0.98); padding: 15px 0 25px 0; display: flex; flex-direction: column; align-items: center; gap: 10px; border-top: 2.5px solid #d4af37; box-shadow: 0 -5px 20px rgba(0,0,0,0.6); }}
        .info-display {{ font-size: 16px; color: #ffd700; font-weight: 900; }}
        .slider-row {{ width: 95%; display: flex; align-items: center; justify-content: center; gap: 4px; }}
        input[type=range] {{ flex-grow: 1; accent-color: #ffd700; height: 10px; cursor: pointer; }}
        .btn {{ background: linear-gradient(180deg, #3d2b1f, #1a100a); color: #ffd700; border: 1px solid #ffd700; padding: 7px 12px; border-radius: 12px; font-size: 11px; font-weight: bold; cursor: pointer; min-width: 45px; transition: transform 0.1s; }}
        .btn:active {{ transform: scale(0.92); filter: brightness(0.8); }}
        .btn-main {{ background: linear-gradient(180deg, #d4af37, #b8860b); color: #1a120b; border: none; padding: 10px 40px; border-radius: 20px; font-size: 14px; }}

        /* --- タブ切り替え --- */
        .tab-bar {{ display: flex; gap: 6px; width: 100%; max-width: 280px; justify-content: center; margin-bottom: 12px; }}
        .tab-btn {{ flex: 1; background: transparent; color: #8a7a5c; border: 1px solid rgba(212,175,55,0.35); padding: 8px 0; border-radius: 14px; font-size: 13px; font-weight: bold; cursor: pointer; transition: all 0.2s; }}
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
        .freq-view {{ display: none; width: 100%; flex-direction: column; align-items: center; }}
        .freq-view.active {{ display: flex; }}

        /* --- 座標マップ(固定グリッド・ヒートマップ) --- */
        .freq-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; width: 100%; max-width: 380px; padding: 0 15px; box-sizing: border-box; }}
        .freq-cell {{ aspect-ratio: 1; border-radius: 8px; border: 1px solid rgba(212,175,55,0.25); display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .freq-cell .cell-num {{ font-size: 13px; font-weight: 900; color: #fff; }}
        .freq-cell .cell-cnt {{ font-size: 9px; color: rgba(255,255,255,0.75); font-variant-numeric: tabular-nums; }}
        .col-totals {{ display: flex; gap: 4px; width: 100%; max-width: 380px; padding: 0 15px; box-sizing: border-box; margin-bottom: 190px; }}
        .col-total-item {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }}
        .col-total-bar-wrap {{ width: 100%; height: 60px; background: rgba(212,175,55,0.1); border-radius: 4px; display: flex; align-items: flex-end; overflow: hidden; }}
        .col-total-bar {{ width: 100%; background: linear-gradient(180deg, #ffd700, #b8860b); border-radius: 3px 3px 0 0; transition: height 0.4s ease; }}
        .col-total-label {{ font-size: 10px; color: #8a7a5c; }}
        .col-total-value {{ font-size: 11px; color: #ccc; font-variant-numeric: tabular-nums; }}

        /* --- 段 x 列マトリクス --- */
        .tier-table-wrap {{ width: 100%; max-width: 400px; padding: 4px 15px 190px 15px; box-sizing: border-box; overflow-x: auto; }}
        .tier-table {{ border-collapse: separate; border-spacing: 3px; margin: 0 auto; }}
        .tier-table th {{ font-size: 10px; color: #8a7a5c; font-weight: bold; padding: 2px; }}
        .tier-table td.tier-label {{ font-size: 10px; color: #8a7a5c; text-align: right; padding-right: 4px; white-space: nowrap; }}
        .tier-cell {{ width: 40px; height: 32px; border-radius: 6px; border: 1px solid rgba(212,175,55,0.25); text-align: center; font-size: 11px; color: #fff; font-variant-numeric: tabular-nums; }}

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
            <button id="tab-btn-pair" class="tab-btn" onclick="switchTab('pair')">ペア</button>
            <button id="tab-btn-tier" class="tab-btn" onclick="switchTab('tier')">段</button>
        </div>
        <div id="panel-board" class="tab-panel active">
            <div class="board-wrapper">
                <div id="main-board" class="main-board"></div>
                <div class="bonus-section"><div class="bonus-box" id="bonus-history"></div></div>
            </div>
        </div>
        <div id="panel-freq" class="tab-panel">
            <div class="freq-toggle">
                <button id="freq-mode-all" class="btn active-toggle" onclick="setFreqMode('all')">全期間</button>
                <button id="freq-mode-recent100" class="btn" onclick="setFreqMode('recent100')">直近100回</button>
            </div>
            <div class="freq-toggle">
                <button id="freq-view-list" class="btn active-toggle" onclick="setFreqView('list')">リスト表示</button>
                <button id="freq-view-grid" class="btn" onclick="setFreqView('grid')">座標マップ</button>
            </div>
            <p class="freq-caption" id="freq-caption"></p>
            <div id="freq-list-section" class="freq-view active">
                <div class="freq-list" id="freq-list"></div>
            </div>
            <div id="freq-grid-section" class="freq-view">
                <div class="freq-grid" id="freq-grid"></div>
                <p class="freq-subheading hot">列平均（1番号あたりの平均出現回数）</p>
                <div class="col-totals" id="col-totals"></div>
            </div>
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
            <div class="freq-toggle">
                <button id="tier-mode-all" class="btn active-toggle" onclick="setTierMode('all')">全期間</button>
                <button id="tier-mode-recent100" class="btn" onclick="setTierMode('recent100')">直近100回</button>
            </div>
            <p class="freq-caption">列(その回の何番目に小さい数字か)×段(何個前の"別の数字"以来この位置にいるか)ごとに、再登場した回数です。</p>
            <p class="freq-caption" id="tier-caption"></p>
            <div class="tier-table-wrap">
                <table class="tier-table" id="tier-table"></table>
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
            <button id="auto-btn" class="btn btn-main" onclick="toggleAuto()">自動再生 / 停止</button>
            <button class="btn" style="background:#2a1a12" onclick="stepForward()">次へ</button>
        </div>
    </div>
    <script>
        const fullData = {data_json};
        const colorsRecent = ['#FFD700', '#FF0033', '#FF6600', '#FFCC00', '#CCFF00', '#66FF00', '#00FFCC', '#00CCFF', '#0066FF', '#6600FF'];
        const colorsOld = ['#FFFFFF', '#F5F5F7', '#E5E5E7', '#D5D5D7', '#C5C5C7', '#B5B5B7', '#A5A5A7', '#959597', '#858587', '#757577'];
        let ballElements = {{}}; let currentIndex = 0; let lastDrawnAt = {{}}; let columns = [[], [], [], [], [], []]; let timer = null;
        let activeTab = 'board'; let freqMode = 'all'; let freqView = 'list';
        let pairMode = 'top20'; let selectedPairNum = null;
        let tierMode = 'all';

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
                    el.style.left = (cIdx * 41 + 10) + 'px'; el.style.top = (rank * 41 + 10) + 'px';
                    const freshness = (lastDrawnAt[num] !== -1) ? currentIndex - lastDrawnAt[num] : -1;
                    if (freshness >= 0 && freshness < 10) {{
                        el.style.backgroundColor = colorsRecent[freshness]; el.style.color = (freshness===0 || freshness===3 || freshness===4) ? '#1a120b' : 'white';
                    }} else if (freshness >= 10) {{
                        const oIdx = Math.min(freshness - 10, colorsOld.length - 1);
                        el.style.backgroundColor = colorsOld[oIdx]; el.style.color = '#333';
                    }} else {{ el.style.backgroundColor = '#FFFFFF'; el.style.color = '#333'; }}
                    if (draw.main.includes(num)) el.classList.add('active'); else el.classList.remove('active');
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

        function setFreqMode(mode) {{
            freqMode = mode;
            document.getElementById('freq-mode-all').classList.toggle('active-toggle', mode === 'all');
            document.getElementById('freq-mode-recent100').classList.toggle('active-toggle', mode === 'recent100');
            renderFreqTab();
        }}

        function setFreqView(view) {{
            freqView = view;
            document.getElementById('freq-view-list').classList.toggle('active-toggle', view === 'list');
            document.getElementById('freq-view-grid').classList.toggle('active-toggle', view === 'grid');
            document.getElementById('freq-list-section').classList.toggle('active', view === 'list');
            document.getElementById('freq-grid-section').classList.toggle('active', view === 'grid');
            renderFreqTab();
        }}

        function computeFrequency(mode) {{
            const counts = {{}};
            for (let i = 1; i <= 43; i++) counts[i] = 0;
            const start = (mode === 'recent100') ? Math.max(0, currentIndex - 99) : 0;
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

        function renderFreqGrid(counts) {{
            const values = [];
            for (let i = 1; i <= 43; i++) values.push(counts[i]);
            const minC = Math.min(...values), maxC = Math.max(...values);

            const grid = document.getElementById('freq-grid');
            grid.innerHTML = '';
            for (let i = 1; i <= 43; i++) {{
                const cell = document.createElement('div');
                cell.className = 'freq-cell';
                const t = (maxC > minC) ? (counts[i] - minC) / (maxC - minC) : 0.5;
                const alpha = 0.12 + t * 0.85;
                cell.style.background = `rgba(212,175,55,${{alpha.toFixed(3)}})`;
                const numEl = document.createElement('div'); numEl.className = 'cell-num'; numEl.innerText = i;
                const cntEl = document.createElement('div'); cntEl.className = 'cell-cnt'; cntEl.innerText = counts[i];
                cell.appendChild(numEl); cell.appendChild(cntEl);
                grid.appendChild(cell);
            }}

            // 列平均: 盤面と同じ列定義 (col = (番号-1) % 6) で1〜6列目ごとに集計。
            // 1列目だけ番号が8個(他は7個)含まれ単純合計では不公平になるため、1番号あたりの平均で比較する。
            const colTotals = [0, 0, 0, 0, 0, 0];
            const colCounts = [0, 0, 0, 0, 0, 0];
            for (let i = 1; i <= 43; i++) {{
                colTotals[(i - 1) % 6] += counts[i];
                colCounts[(i - 1) % 6]++;
            }}
            const colAverages = colTotals.map((t, idx) => t / colCounts[idx]);
            const maxColAvg = Math.max(...colAverages);
            const wrap = document.getElementById('col-totals');
            wrap.innerHTML = '';
            colAverages.forEach((avg, idx) => {{
                const item = document.createElement('div'); item.className = 'col-total-item';
                const barWrap = document.createElement('div'); barWrap.className = 'col-total-bar-wrap';
                const bar = document.createElement('div'); bar.className = 'col-total-bar';
                bar.style.height = (maxColAvg > 0 ? (avg / maxColAvg * 100) : 0) + '%';
                barWrap.appendChild(bar);
                const label = document.createElement('div'); label.className = 'col-total-label'; label.innerText = (idx + 1) + '列目';
                const value = document.createElement('div'); value.className = 'col-total-value'; value.innerText = avg.toFixed(1);
                item.appendChild(barWrap); item.appendChild(label); item.appendChild(value);
                wrap.appendChild(item);
            }});
        }}

        function renderFreqTab() {{
            if (fullData.length === 0) return;
            const {{ counts, start }} = computeFrequency(freqMode);

            if (freqView === 'list') renderFreqList(counts);
            else renderFreqGrid(counts);

            const caption = document.getElementById('freq-caption');
            const drawCount = currentIndex - start + 1;
            caption.innerText = (freqMode === 'recent100')
                ? `直近${{drawCount}}回（第${{fullData[start].id}}回〜第${{fullData[currentIndex].id}}回）`
                : `全期間（第${{fullData[start].id}}回〜第${{fullData[currentIndex].id}}回、${{drawCount}}回分）`;
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

        function setTierMode(mode) {{
            tierMode = mode;
            document.getElementById('tier-mode-all').classList.toggle('active-toggle', mode === 'all');
            document.getElementById('tier-mode-recent100').classList.toggle('active-toggle', mode === 'recent100');
            renderTierTab();
        }}

        const TIER_ROWS = 10; // A段〜J段。それより深い段は最終行「K+」にまとめる
        const TIER_LABELS = ['A','B','C','D','E','F','G','H','I','J'];

        // 盤面の実アルゴリズム(列=その回の昇順順位、段=同じ座標を最後に明け渡してからの深さ)を
        // 第1回から忠実に再生し、「(列, 段)座標で再登場が起きた回数」を集計する。
        // 直近100回モードでも、座標の状態を正しく保つため必ず第1回からシミュレートし、
        // 集計対象(タリー)だけを対象期間に絞る。
        function computeTierMatrix(mode) {{
            const cols = [[], [], [], [], [], []];
            for (let i = 1; i <= 43; i++) cols[(i - 1) % 6].push(i);
            const seenBefore = new Set();
            const matrix = {{}};
            const windowStart = (mode === 'recent100') ? Math.max(0, currentIndex - 99) : 0;

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
            const matrix = computeTierMatrix(tierMode);

            const values = Object.values(matrix);
            const maxV = values.length ? Math.max(...values) : 1;

            const table = document.getElementById('tier-table');
            table.innerHTML = '';

            const headRow = document.createElement('tr');
            headRow.appendChild(document.createElement('th'));
            for (let c = 1; c <= 6; c++) {{
                const th = document.createElement('th'); th.innerText = c + '列目';
                headRow.appendChild(th);
            }}
            table.appendChild(headRow);

            for (let row = 0; row <= TIER_ROWS; row++) {{
                const tr = document.createElement('tr');
                const labelTd = document.createElement('td'); labelTd.className = 'tier-label';
                labelTd.innerText = row < TIER_ROWS ? (TIER_LABELS[row] + '段') : 'K段+';
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

            document.getElementById('tier-caption').innerText = (tierMode === 'recent100')
                ? `直近${{Math.min(currentIndex + 1, 100)}}回（第${{fullData[Math.max(0, currentIndex - 99)].id}}回〜第${{fullData[currentIndex].id}}回）`
                : `全期間（第1回〜第${{fullData[currentIndex].id}}回）`;
        }}

        async function stepForward() {{
            if (currentIndex >= fullData.length - 1) return;
            const next = fullData[currentIndex + 1];
            next.main.forEach(n => document.getElementById('ball-' + n).classList.add('glow-float'));
            await new Promise(r => setTimeout(r, 600));
            next.main.forEach(n => document.getElementById('ball-' + n).classList.remove('glow-float'));
            seekTo(currentIndex + 1);
        }}

        function jump(s) {{ seekTo(currentIndex + s); }}
        function toggleAuto() {{
            if(timer) {{ clearInterval(timer); timer = null; }}
            else {{ timer = setInterval(() => {{ if(currentIndex < fullData.length - 1) stepForward(); else toggleAuto(); }}, 1800); }}
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

    with open('loto_analysis.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("生成完了: loto_analysis.html が作成されました。")

if __name__ == '__main__':
    main()
