import threading
import time
import uuid
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# 内部モジュールのインポート
import english_db as edb
import english_ai as eai

# ページ基本設定
st.set_page_config(
    page_title="English Growth Log",
    page_icon="🗣️",
    layout="wide"
)

# Streamlit Community Cloud のサーバーは UTC のため、日付は日本時間で判定する
JST = ZoneInfo("Asia/Tokyo")

def today_jst():
    return datetime.now(JST).date()

def week_start(d):
    """その週の月曜日"""
    return d - timedelta(days=d.weekday())

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# 学習の目的に応じて1つだけ選ぶ技能（合計時間が総学習時間と一致するように単一選択）
SKILLS = ["リスニング", "スピーキング", "リーディング", "ライティング", "語彙", "文法", "発音"]
# 技能ごとの固定色（検証済みカテゴリ配色。並び順＝割り当て順で固定）
SKILL_COLORS = {
    "リスニング": "#2a78d6",
    "スピーキング": "#eb6834",
    "リーディング": "#1baf7a",
    "ライティング": "#eda100",
    "語彙": "#e87ba4",
    "文法": "#008300",
    "発音": "#4a3aa7",
}

SCORE_LABELS = {
    "total": "総合",
    "grammar": "文法",
    "vocabulary": "語彙",
    "fluency": "流暢さ",
    "content": "内容の伝わりやすさ",
    "pronunciation": "発音",
}

# アップロード可能な音声形式（拡張子 → Content-Type）
AUDIO_TYPES = {
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "aac": "audio/aac",
}

# ------------------------------------------------------------------------------
# セッション状態の初期化
# ------------------------------------------------------------------------------
if "en_selected_date" not in st.session_state:
    st.session_state["en_selected_date"] = today_jst()
if "en_speech_date" not in st.session_state:
    st.session_state["en_speech_date"] = today_jst()
# file_uploader は session_state でクリアできないため、key を変えて作り直す
if "en_uploader_ver" not in st.session_state:
    st.session_state["en_uploader_ver"] = 0

# 登録成功後にクリアする入力ウィジェットの key と初期値
# （keyを削除するだけでは画面上に前の入力が残るため、ウィジェット生成前に初期値を代入する。
#   初期値は session_state で与え、ウィジェット側には value/index を渡さない）
STUDY_INPUT_DEFAULTS = {"en_minutes": 30, "en_skill": None, "en_content": ""}

def reset_inputs(flag_key, defaults):
    clear = st.session_state.pop(flag_key, False)
    for k, v in defaults.items():
        if clear or k not in st.session_state:
            st.session_state[k] = v

# ------------------------------------------------------------------------------
# スマホ向けのコンパクト表示（Body Make アプリと同じスタイル）
# ------------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container { padding-top: 2.5rem; }
    .app-title { font-size: 1.4rem; font-weight: 700; margin: 0 0 0.25rem 0; line-height: 1.3; }
    .block-container h2 { font-size: 1.2rem !important; padding: 0.4rem 0 0.2rem 0 !important; }
    .block-container h3 { font-size: 1.05rem !important; padding: 0.3rem 0 0.1rem 0 !important; }
    .block-container h4 { font-size: 0.95rem !important; padding: 0.2rem 0 0.1rem 0 !important; }
    [data-testid="stRadio"] div[role="radiogroup"][aria-orientation="horizontal"] { gap: 0.1rem 0.6rem !important; }
    [data-testid="stRadio"] div[role="radiogroup"] label > div { gap: 0.25rem !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown('<p class="app-title">🗣️ English Growth Log</p>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 共通: スピーチ分析結果の表示
# ------------------------------------------------------------------------------
def render_speech_result(sp):
    scores = sp.get("scores", {}) or {}
    st.metric("総合", f"{scores.get('total', 0)} 点")
    # スマホで縦に長くならないよう、観点別の点数は1行にまとめる
    sub_keys = ["grammar", "vocabulary", "fluency", "content", "pronunciation"]
    st.markdown("　".join(f"{SCORE_LABELS[k]} **{scores.get(k, 0)}**" for k in sub_keys))

    if sp.get("growth_comment"):
        st.success(f"📈 成長メモ: {sp['growth_comment']}")
    if sp.get("overall_comment"):
        st.info(sp["overall_comment"])

    st.markdown("#### 📝 文字起こし")
    st.write(sp.get("transcript", ""))

    suggestions = sp.get("suggestions") or []
    if suggestions:
        st.markdown("#### 💡 より自然な言い回し")
        for s in suggestions:
            st.markdown(f"- ~~{s.get('original', '')}~~ → **{s.get('better', '')}**  \n  {s.get('reason', '')}")

    if sp.get("natural_version"):
        with st.expander("✨ 自然な英語に直したスピーチ全文"):
            st.write(sp["natural_version"])

def process_speech(audio_bytes, filename, speech_date_str, past_speeches):
    """変換→分析→音声アップロード→Firestore保存を行い、保存したレコードを返す。

    バックグラウンドスレッドで実行するため、この関数内では Streamlit の表示関数を呼ばない。
    失敗時は RuntimeError を送出する。
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    content_type = AUDIO_TYPES.get(ext, "application/octet-stream")
    wav_bytes = eai.convert_to_wav(audio_bytes, ext)
    result = eai.analyze_speech(wav_bytes, past_speeches)
    audio_path = edb.upload_audio(speech_date_str, audio_bytes, ext, content_type)
    speech_record = {
        "date": speech_date_str,
        "audio_path": audio_path,
        "audio_content_type": content_type,
        "original_filename": filename,
        "transcript": result.get("transcript", ""),
        "natural_version": result.get("natural_version", ""),
        "suggestions": result.get("suggestions", []),
        "scores": result.get("scores", {}),
        "overall_comment": result.get("overall_comment", ""),
        "growth_comment": result.get("growth_comment", ""),
    }
    try:
        edb.save_speech(speech_record)
    except RuntimeError:
        # 分析結果を保存できなかった場合は、アップロード済みの音声を残さない
        try:
            edb.bucket.blob(audio_path).delete()
        except Exception:
            pass
        raise
    return speech_record

# ------------------------------------------------------------------------------
# スピーチ分析のバックグラウンド実行
# 分析には1分ほどかかり、その間にスマホの画面スリープ・再接続などで画面の再実行が割り込むと、
# 通常の処理では結果の保存・表示が失われる。そこで分析はスレッドで実行し、画面は結果を数秒ごとに確認する。
# ------------------------------------------------------------------------------
@st.cache_resource
def speech_jobs():
    """実行中・完了したスピーチ分析ジョブ（プロセス全体で共有）: job_id -> 状態dict"""
    return {}

JOB_TIMEOUT_SEC = 600

def start_speech_job(audio_bytes, filename, speech_date_str, past_speeches):
    jobs = speech_jobs()
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "started": time.time(), "date": speech_date_str}

    def run():
        try:
            jobs[job_id]["record"] = process_speech(audio_bytes, filename, speech_date_str, past_speeches)
            jobs[job_id]["status"] = "done"
        except Exception as e:
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["status"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return job_id

def running_job_id():
    """このセッションのジョブ、なければ（画面の再読み込み等でセッションが変わった場合に備え）実行中の最新ジョブ"""
    jobs = speech_jobs()
    # 結果を受け取られないまま残った古いジョブを片付ける
    for jid in [jid for jid, j in jobs.items() if time.time() - j["started"] > JOB_TIMEOUT_SEC and j["status"] != "running"]:
        jobs.pop(jid, None)
    job_id = st.session_state.get("speech_job")
    if job_id in jobs:
        return job_id
    running = [(j["started"], jid) for jid, j in jobs.items()
               if j["status"] == "running" and time.time() - j["started"] < JOB_TIMEOUT_SEC]
    return max(running)[1] if running else None

@st.fragment(run_every=3)
def speech_job_status(job_id):
    """実行中のジョブの進み具合を3秒ごとに確認し、終わったら画面全体を更新する"""
    job = speech_jobs().get(job_id)
    if not job:
        return
    if job["status"] == "running":
        elapsed = int(time.time() - job["started"])
        st.info(f"⏳ Geminiがスピーチを分析・保存中...（{elapsed}秒経過。1分ほどかかります）")
        return
    # 完了・失敗: 結果をセッションに移して画面全体を更新
    speech_jobs().pop(job_id, None)
    st.session_state.pop("speech_job", None)
    if job["status"] == "done":
        st.session_state["latest_speech"] = job["record"]
        st.session_state["en_uploader_ver"] += 1
    else:
        st.session_state["speech_job_error"] = job.get("error", "不明なエラー")
    st.rerun(scope="app")

def pick_past_speeches(speeches, speech_date_str):
    """比較用の過去スピーチ: 直近4回＋約3か月前に最も近い1回"""
    past = [s for s in speeches if s.get("date", "") < speech_date_str]
    recent = past[-4:]
    older = [s for s in past if s not in recent]
    if older:
        target = (datetime.strptime(speech_date_str, "%Y-%m-%d") - timedelta(days=90)).date()
        closest = min(older, key=lambda s: abs((datetime.strptime(s["date"], "%Y-%m-%d").date() - target).days))
        return [closest] + recent
    return recent

tab1, tab2, tab3, tab4 = st.tabs([
    "📝 勉強ログ",
    "🎤 1分スピーチ",
    "📈 積み上げ",
    "🎧 スピーチ履歴"
])

# ==============================================================================
# TAB 1: 勉強ログ
# ==============================================================================
with tab1:
    st.subheader("📝 勉強ログの入力")

    # key で session_state と直接連動させる（value指定だと2回目以降の日付変更が無視される）
    target_date = st.date_input("記録対象日", key="en_selected_date")
    date_str = target_date.strftime("%Y-%m-%d")
    st.info(f"選択中: {date_str} ({WEEKDAYS[target_date.weekday()]})")

    # 前回の保存が成功していれば入力欄を初期状態に戻す
    reset_inputs("clear_study_inputs", STUDY_INPUT_DEFAULTS)

    minutes = st.number_input("勉強時間 (分)", min_value=1, max_value=600, step=5, key="en_minutes")
    skill = st.radio("技能（学習の目的で1つ選択）", SKILLS, horizontal=True, key="en_skill")
    content = st.text_input("勉強内容", placeholder="例: Podcastをシャドーイング、オンライン英会話 など", key="en_content")

    if st.button("勉強ログを保存"):
        if not skill:
            st.warning("技能を1つ選択してください。")
        else:
            edb.save_study_log({
                "date": date_str,
                "minutes": float(minutes),
                "skill": skill,
                "content": content,
            })
            st.session_state["study_saved_msg"] = True
            st.session_state["clear_study_inputs"] = True
            st.rerun()

    if st.session_state.pop("study_saved_msg", False):
        st.success("勉強ログを保存しました！")

    st.markdown("---")
    day_logs = edb.fetch_study_logs(date_str)
    day_total = sum(float(l.get("minutes") or 0) for l in day_logs)
    st.markdown(f"### この日の記録（合計 {day_total:.0f} 分）")

    if day_logs:
        for log in day_logs:
            col_l1, col_l2, col_l3 = st.columns([6, 2, 2])
            log_min = float(log.get("minutes") or 0)
            log_skill = log.get("skill", "")
            col_l1.write(f"**[{log_skill}]** {log_min:.0f} 分  {log.get('content', '')}")

            log_id = log.get("doc_id")
            with col_l2:
                with st.popover("編集"):
                    with st.form(f"edit_log_{log_id}"):
                        edit_min = st.number_input("勉強時間 (分)", min_value=1.0, max_value=600.0, value=max(log_min, 1.0), step=5.0)
                        edit_skill = st.selectbox("技能", SKILLS, index=SKILLS.index(log_skill) if log_skill in SKILLS else 0)
                        edit_content = st.text_input("勉強内容", value=log.get("content", ""))
                        if st.form_submit_button("保存"):
                            edb.update_study_log(log_id, {
                                "minutes": float(edit_min),
                                "skill": edit_skill,
                                "content": edit_content,
                            })
                            st.success("更新しました。")
                            st.rerun()
            with col_l3:
                if st.button("削除", key=f"del_log_{log_id}"):
                    edb.delete_study_log(log_id)
                    st.success("削除しました。")
                    st.rerun()
    else:
        st.caption("この日の勉強ログはありません。")

# ==============================================================================
# TAB 2: 1分スピーチ
# ==============================================================================
with tab2:
    st.subheader("🎤 1分スピーチ")

    speeches = edb.fetch_all_speeches()
    this_week = week_start(today_jst())
    done_this_week = any(
        s.get("date", "") >= this_week.strftime("%Y-%m-%d") for s in speeches
    )
    if done_this_week:
        st.success("✅ 今週のスピーチは録音済みです。")
    else:
        st.warning("🎙️ 今週はまだ録音していません。")

    speech_date = st.date_input("スピーチ日", key="en_speech_date")
    speech_date_str = speech_date.strftime("%Y-%m-%d")

    uploaded = st.file_uploader(
        "ボイスメモの音声ファイル（m4a / mp3 / wav など）",
        type=list(AUDIO_TYPES.keys()),
        key=f"en_audio_{st.session_state['en_uploader_ver']}"
    )
    if uploaded:
        st.audio(uploaded)

    job_id = running_job_id()
    if st.button("AIで分析して保存", disabled=uploaded is None or job_id is not None):
        st.session_state.pop("latest_speech", None)
        st.session_state["speech_job"] = start_speech_job(
            uploaded.getvalue(), uploaded.name, speech_date_str, pick_past_speeches(speeches, speech_date_str)
        )
        st.rerun()

    if job_id:
        speech_job_status(job_id)
    if "speech_job_error" in st.session_state:
        st.error(st.session_state.pop("speech_job_error"))

    # 直前の分析結果。画面の再読み込み等でセッションの結果が失われた場合は、今週保存済みの最新スピーチを表示する
    latest = st.session_state.get("latest_speech")
    if not latest:
        this_week_speeches = [s for s in speeches if s.get("date", "") >= this_week.strftime("%Y-%m-%d")]
        latest = this_week_speeches[-1] if this_week_speeches else None
    if latest:
        st.markdown("---")
        st.markdown(f"### 分析結果（{latest['date']}）")
        render_speech_result(latest)

# ==============================================================================
# TAB 3: 積み上げ
# ==============================================================================
with tab3:
    st.subheader("📈 積み上げ")

    all_logs = edb.fetch_all_study_logs()
    if not all_logs:
        st.caption("まだ勉強ログがありません。")
    else:
        df = pd.DataFrame(all_logs)
        df["minutes"] = pd.to_numeric(df.get("minutes"), errors="coerce").fillna(0.0)
        df["skill"] = df.get("skill").fillna("不明") if "skill" in df else "不明"
        df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date_dt"])

        today = today_jst()
        daily = df.groupby(df["date_dt"].dt.date)["minutes"].sum()

        # 連続記録日数（今日 or 昨日から遡って途切れるまで）
        study_days = set(d for d, m in daily.items() if m > 0)
        streak = 0
        cursor = today if today in study_days else today - timedelta(days=1)
        while cursor in study_days:
            streak += 1
            cursor -= timedelta(days=1)

        month_min = daily[[d for d in daily.index if d.year == today.year and d.month == today.month]].sum()
        week_min = daily[[d for d in daily.index if d >= week_start(today)]].sum()

        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        col_s1.metric("累計", f"{daily.sum() / 60:.1f} 時間")
        col_s2.metric("今月", f"{month_min / 60:.1f} 時間")
        col_s3.metric("今週", f"{week_min / 60:.1f} 時間")
        col_s4.metric("連続記録", f"{streak} 日")

        # --- 日別ヒートマップ（過去16週・月曜始まり） ---
        st.markdown("---")
        st.markdown("### 日別の勉強時間（過去16週）")
        n_weeks = 16
        start = week_start(today) - timedelta(weeks=n_weeks - 1)
        z, text, x_labels = [[None] * n_weeks for _ in range(7)], [[""] * n_weeks for _ in range(7)], []
        for w in range(n_weeks):
            ws = start + timedelta(weeks=w)
            x_labels.append(ws.strftime("%m/%d"))
            for wd in range(7):
                d = ws + timedelta(days=wd)
                if d > today:
                    continue
                m = float(daily.get(d, 0.0))
                z[wd][w] = m
                text[wd][w] = f"{d.strftime('%Y-%m-%d')} ({WEEKDAYS[wd]})<br>{m:.0f} 分"
        fig_hm = go.Figure(go.Heatmap(
            z=z, x=x_labels, y=WEEKDAYS, text=text, hoverinfo="text",
            colorscale=[[0, "#ebedf0"], [0.001, "#cde2fb"], [0.35, "#86b6ef"], [0.7, "#2a78d6"], [1, "#104281"]],
            zmin=0, zmax=max(90.0, float(daily.max())), xgap=3, ygap=3,
            colorbar=dict(title="分", thickness=10)
        ))
        fig_hm.update_layout(
            height=240, margin=dict(l=10, r=10, t=10, b=10),
            yaxis=dict(autorange="reversed", scaleanchor="x"), xaxis=dict(type="category", side="top"),
            plot_bgcolor="rgba(0,0,0,0)"
        )
        st.plotly_chart(fig_hm, width="stretch")

        # --- 累計時間の推移 ---
        st.markdown("---")
        st.markdown("### 累計勉強時間の推移")
        df_cum = daily.sort_index().cumsum().div(60).reset_index()
        df_cum.columns = ["date", "hours"]
        fig_cum = px.line(df_cum, x="date", y="hours")
        fig_cum.update_traces(line=dict(width=2, color="#2a78d6"),
                              hovertemplate="%{x|%Y-%m-%d}<br>累計 %{y:.1f} 時間<extra></extra>")
        fig_cum.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                              xaxis_title=None, yaxis_title="時間", yaxis_rangemode="tozero")
        st.plotly_chart(fig_cum, width="stretch")

        # --- 週ごとの技能別時間（過去12週） ---
        st.markdown("---")
        st.markdown("### 週ごとの技能別時間（過去12週）")
        df["week"] = df["date_dt"].dt.date.map(lambda d: week_start(d).strftime("%m/%d~"))
        recent_start = week_start(today) - timedelta(weeks=11)
        df_recent = df[df["date_dt"].dt.date >= recent_start]
        week_order = [(recent_start + timedelta(weeks=i)).strftime("%m/%d~") for i in range(12)]
        df_week = df_recent.groupby(["week", "skill"], as_index=False)["minutes"].sum()
        df_week["hours"] = df_week["minutes"] / 60
        fig_week = px.bar(
            df_week, x="week", y="hours", color="skill",
            category_orders={"week": week_order, "skill": SKILLS},
            color_discrete_map=SKILL_COLORS,
        )
        fig_week.update_traces(marker_line_color="white", marker_line_width=1,
                               hovertemplate="%{x}<br>%{fullData.name}: %{y:.1f} 時間<extra></extra>")
        fig_week.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10),
                               xaxis_title=None, yaxis_title="時間", legend_title_text=None,
                               legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_week, width="stretch")

        # --- 技能別の累計 ---
        st.markdown("### 技能別の累計時間")
        df_skill = df.groupby("skill", as_index=False)["minutes"].sum()
        df_skill["hours"] = df_skill["minutes"] / 60
        df_skill["order"] = df_skill["skill"].map(lambda s: SKILLS.index(s) if s in SKILLS else 99)
        df_skill = df_skill.sort_values("order")
        fig_skill = px.bar(df_skill, x="hours", y="skill", orientation="h", color="skill",
                           color_discrete_map=SKILL_COLORS, text=df_skill["hours"].map(lambda h: f"{h:.1f}h"))
        fig_skill.update_traces(textposition="outside", cliponaxis=False, showlegend=False,
                                hovertemplate="%{y}: %{x:.1f} 時間<extra></extra>")
        fig_skill.update_layout(height=300, margin=dict(l=10, r=30, t=10, b=10),
                                xaxis_title="時間", yaxis_title=None, xaxis_range=[0, max(float(df_skill["hours"].max()), 0.1) * 1.25],
                                yaxis=dict(categoryorder="array", categoryarray=list(reversed(SKILLS))))
        st.plotly_chart(fig_skill, width="stretch")

# ==============================================================================
# TAB 4: スピーチ履歴
# ==============================================================================
with tab4:
    st.subheader("🎧 スピーチ履歴")

    speeches = edb.fetch_all_speeches()
    if not speeches:
        st.caption("まだスピーチの記録がありません。")
    else:
        # --- 点数の推移 ---
        rows = []
        for s in speeches:
            for k, label in SCORE_LABELS.items():
                if k in (s.get("scores") or {}):
                    rows.append({"date": s["date"], "項目": label, "点数": s["scores"][k]})
        df_score = pd.DataFrame(rows)
        if not df_score.empty:
            st.markdown("### 点数の推移")
            show_items = st.multiselect("表示する項目", list(SCORE_LABELS.values()), default=["総合"], key="en_score_items")
            df_show = df_score[df_score["項目"].isin(show_items)]
            fig_score = px.line(df_show, x="date", y="点数", color="項目", markers=True,
                                category_orders={"項目": list(SCORE_LABELS.values())},
                                color_discrete_sequence=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"])
            fig_score.update_traces(line=dict(width=2), marker=dict(size=8))
            fig_score.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                    xaxis_title=None, yaxis=dict(range=[0, 100]), legend_title_text=None,
                                    xaxis=dict(type="category"), legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fig_score, width="stretch")

        st.markdown("---")
        st.markdown("### 過去のスピーチ")
        for sp in reversed(speeches):
            total = (sp.get("scores") or {}).get("total", "-")
            with st.expander(f"{sp.get('date')}（総合 {total} 点）"):
                audio = edb.download_audio(sp.get("audio_path"))
                if audio:
                    st.audio(audio, format=sp.get("audio_content_type", "audio/mp4"))
                    st.download_button(
                        "⬇️ 音声をダウンロード", data=audio,
                        file_name=sp.get("original_filename") or f"speech_{sp.get('date')}.m4a",
                        mime=sp.get("audio_content_type", "audio/mp4"),
                        key=f"dl_{sp['doc_id']}"
                    )
                render_speech_result(sp)

                st.markdown("---")
                if st.checkbox("このスピーチを削除する", key=f"del_chk_{sp['doc_id']}"):
                    if st.button("削除を実行（音声も削除されます）", key=f"del_sp_{sp['doc_id']}"):
                        edb.delete_speech(sp["doc_id"], sp.get("audio_path"))
                        st.session_state.pop("latest_speech", None)
                        st.success("削除しました。")
                        st.rerun()
