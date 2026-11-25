import re
import urllib.parse
import plotly.express as px
import requests
import streamlit as st

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="무드튠 (MOODTUNE)", page_icon="🎵", layout="centered"
)

# 1. Gemini API 키 설정 (Streamlit Secrets 활용)
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    st.error("Streamlit Secrets에 'GEMINI_API_KEY'를 추가해 주세요.")
    st.stop()

MODEL = "gemini-2.5-flash"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

# 2. 시스템 프롬프트 설정
SYSTEM_INSTRUCTION = """
너는 음악 추천 웹 서비스 '무드튠(MOODTUNE)'의 전담 AI 감성 DJ이다.
사용자가 입력한 기분, 일상 이야기, 음악 취향을 바탕으로 감정을 분석하고 맞춤형 음악을 추천해 주는 역할을 수행한다.

[기본 규칙]
1. 사용자의 이야기에 따뜻하고 위트 있게 공감하는 어조를 사용해라.
2. 분석 결과는 파이썬 프로그램이 읽어서 그래프(Plotly)와 개별 곡 링크로 변환해야 하므로, 아래 [출력 양식]을 단 1자도 틀리지 않고 정확히 지켜서 답변해라.
3. [출력 양식] 외의 인사말, 서론, 결론은 절대 추가하지 마라.

[출력 양식]
---
[감정분석]
주요감정1: 비율%
주요감정2: 비율%
주요감정3: 비율%

[추천이유]
(사용자의 기분에 공감하고 취향을 반영하여 이 곡들을 추천하는 이유를 2~3문장으로 작성)

[추천음악]
1. 가수 - 노래제목
2. 가수 - 노래제목
3. 가수 - 노래제목
---

[작성 규칙]
1. [감정분석] 섹션의 비율 합은 반드시 100%가 되도록 작성해라.
2. [추천음악]은 반드시 `번호. 가수 - 노래제목` 형식을 지켜라. (예: 1. 성시경 - 거리에서)
3. [출력 양식] 외의 인사말, 서론, 결론은 절대 포함하지 마라.
"""


# 3. API 키 없이 유튜브 검색 페이지에서 첫 번째 실제 영상 URL 추출
@st.cache_data(ttl=86400, show_spinner=False)
def get_youtube_video_url_no_api(song_query):
    """YouTube API 키 없이 검색 페이지 HTML에서 첫 번째 videoId를 파싱합니다."""
    encoded_query = urllib.parse.quote(f"{song_query} official audio")
    search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
    fallback_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(song_query)}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    try:
        response = requests.get(search_url, headers=headers, timeout=5)
        if response.status_code == 200:
            # 유튜브 검색 결과 JSON 데이터 내의 첫 번째 videoId 추출 (11자리 영문/숫자/-/_)
            match = re.search(r'"videoId":"([a-zA-Z0-9_-]{11})"', response.text)
            if match:
                video_id = match.group(1)
                return f"https://www.youtube.com/watch?v={video_id}", True
    except Exception:
        pass

    # 추출 실패 시 개별 곡 검색 링크로 안전하게 대체
    return fallback_url, False


# 4. Gemini API 호출 함수
def get_gemini_recommendation(user_input, chat_history):
    contents = []
    for message in chat_history:
        contents.append(
            {"role": message["role"], "parts": [{"text": message["content"]}]}
        )
    contents.append({"role": "user", "parts": [{"text": str(user_input)}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
    }

    try:
        response = requests.post(GEMINI_API_URL, json=payload, timeout=15)
        res = response.json()

        if "error" in res:
            return (
                f"구글 API 오류 ({res['error'].get('code')}): {res['error'].get('message')}",
                False,
            )

        return res["candidates"][0]["content"]["parts"][0]["text"], True
    except Exception as e:
        return f"오류 발생: {str(e)}", False


# 5. 텍스트 파싱 및 시각화/개별 곡 링크 출력 함수
def parse_and_display_response(response_text):
    try:
        # 감정 분석 파싱
        emotions = {}
        emotion_section = re.search(
            r"\[감정분석\](.*?)\[추천이유\]", response_text, re.DOTALL
        )
        if emotion_section:
            matches = re.findall(
                r"([가-힣a-zA-A\s]+):\s*(\d+)%", emotion_section.group(1)
            )
            for emotion, percent in matches:
                emotions[emotion.strip()] = int(percent)

        # 추천 이유 파싱
        reason_section = re.search(
            r"\[추천이유\](.*?)\[추천음악\]", response_text, re.DOTALL
        )
        reason = (
            reason_section.group(1).strip()
            if reason_section
            else "공감 메시지를 불러올 수 없습니다."
        )

        # 추천 음악 리스트 개별 파싱
        music_section = re.search(
            r"\[추천음악\](.*?)(---|$\n?)", response_text, re.DOTALL
        )
        songs = []
        if music_section:
            lines = music_section.group(1).strip().split("\n")
            for line in lines:
                cleaned = re.sub(r"^\d+\.\s*", "", line.strip())
                if cleaned:
                    songs.append(cleaned)

        # UI 출력: 추천 이유
        st.info(f"💡 **DJ 무드튠의 한마디**\n\n{reason}")

        # UI 출력: Plotly 감정 차트
        if emotions:
            fig = px.pie(
                names=list(emotions.keys()),
                values=list(emotions.values()),
                title="📊 당신의 감정 분석 그래프",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig.update_traces(
                textposition="inside", textinfo="percent+label"
            )
            st.plotly_chart(fig, use_container_width=True)

        # UI 출력: 추천 음악별 개별 유튜브 링크 카드
        if songs:
            st.subheader("🎧 추천 플레이리스트")
            for idx, song in enumerate(songs, 1):
                yt_url, is_direct = get_youtube_video_url_no_api(song)
                col1, col2 = st.columns([3, 1.2])
                with col1:
                    st.markdown(f"**{idx}. {song}**")
                with col2:
                    btn_label = "▶️ 바로 듣기" if is_direct else "🔍 곡 검색"
                    st.link_button(btn_label, yt_url, use_container_width=True)

    except Exception:
        st.warning("응답 양식이 정규 규격과 달라 텍스트 원문으로 표시합니다.")
        st.write(response_text)


# 6. UI 화면 구성
st.title("🎵 무드튠 (MOODTUNE)")
st.caption(
    "오늘 당신의 기분이나 들었던 생각을 적어주세요. 감정을 분석해 어울리는 음악을 추천해드립니다."
)

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            parse_and_display_response(msg["content"])

st.write("---")
example_col1, example_col2 = st.columns(2)
example_input = None

if example_col1.button("🌧️ 비 오고 잔잔한 팝송 추천"):
    example_input = "오늘 비가 오는데 괜히 울적해지고 잔잔한 음악이 듣고 싶네.. 잔잔한 팝송 위주로 추천해줘!"

if example_col2.button("🎉 시험 끝나서 신나는 K-POP"):
    example_input = "시험 끝나서 기분이 너무 날아갈 것 같아! 신나는 케이팝 노래 추천해줘"

user_prompt = st.chat_input("오늘 기분이 어떠신가요?")
final_input = user_prompt or example_input

if final_input:
    st.session_state.messages.append({"role": "user", "content": final_input})
    with st.chat_message("user"):
        st.write(final_input)

    with st.chat_message("assistant"):
        with st.spinner("감정을 분석하고 어울리는 노래를 찾는 중입니다..."):
            response_text, success = get_gemini_recommendation(
                final_input, st.session_state.messages[:-1]
            )

            if success:
                parse_and_display_response(response_text)
                st.session_state.messages.append(
                    {"role": "model", "content": response_text}
                )
            else:
                st.error(response_text)
