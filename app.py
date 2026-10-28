import re
import urllib.parse
import plotly.express as px
import requests
import streamlit as st

# Streamlit 페이지 기본 설정
st.set_page_config(
    page_title="무드튠 (MOODTUNE)", page_icon="🎵", layout="centered"
)

# 1. API 키 및 모델 설정 (Streamlit Secrets 활용)
# Streamlit Cloud 배포 시 Secrets 설정 창에 GEMINI_API_KEY를 지정해야 합니다.
if "GEMINI_API_KEY" in st.secrets:
    API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    st.error(
        "API 키가 설정되지 않았습니다. Streamlit Secrets에 'GEMINI_API_KEY'를 추가해 주세요."
    )
    st.stop()

MODEL = "gemini-1.5-flash"  # 안정적으로 지원되는 Gemini 모델 지정
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

# 2. 시스템 프롬프트 설정
SYSTEM_INSTRUCTION = """
너는 음악 추천 웹 서비스 '무드튠(MOODTUNE)'의 전담 AI 감성 DJ이다.
사용자가 입력한 기분, 일상 이야기, 음악 취향을 바탕으로 감정을 분석하고 맞춤형 음악을 추천해 주는 역할을 수행한다.

[기본 규칙]
1. 사용자의 이야기에 따뜻하고 위트 있게 공감하는 어조를 사용해라.
2. 분석 결과는 파이썬 프로그램이 읽어서 그래프(Plotly)와 링크 버튼으로 변환해야 하므로, 아래 [출력 양식]을 단 1자도 틀리지 않고 정확히 지켜서 답변해라.
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

[검색키워드]
유튜브에서 해당 감정과 분위기로 바로 검색할 수 있는 통합 검색어 1개
---

[작성 규칙]
1. [감정분석] 섹션의 비율 합은 반드시 100%가 되도록 작성해라. (예: 우울함: 60%, 센치함: 40%)
2. [출력 양식] 외의 인사말, 서론, 결론은 절대 포함하지 마라.
"""


# 3. Gemini API 호출 함수
def get_gemini_recommendation(user_input, chat_history):
    contents = []

    # 이전 대화 기록 누적
    for message in chat_history:
        contents.append(
            {"role": message["role"], "parts": [{"text": message["content"]}]}
        )

    # 현재 메시지 추가
    contents.append({"role": "user", "parts": [{"text": str(user_input)}]})

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": contents,
    }

    try:
        response = requests.post(API_URL, json=payload, timeout=15)
        res = response.json()

        if "error" in res:
            return (
                f"구글 API 오류 ({res['error'].get('code')}): {res['error'].get('message')}",
                False,
            )

        return res["candidates"][0]["content"]["parts"][0]["text"], True

    except Exception as e:
        return f"오류 발생: {str(e)}", False


# 4. 텍스트 파싱 및 시각화 함수
def parse_and_display_response(response_text):
    try:
        # 감정 분석 섹션 파싱
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

        # 추천 음악 파싱
        music_section = re.search(
            r"\[추천음악\](.*?)\[검색키워드\]", response_text, re.DOTALL
        )
        music_list = (
            music_section.group(1).strip() if music_section else ""
        )

        # 검색 키워드 파싱
        keyword_section = re.search(
            r"\[검색키워드\](.*?)(---|$\n?)", response_text, re.DOTALL
        )
        keyword = (
            keyword_section.group(1).strip() if keyword_section else ""
        )

        # UI 출력: 추천 이유
        st.info(f"💡 **DJ 무드튠의 한마디**\n\n{reason}")

        # UI 출력: Plotly 파이 차트 시각화
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

        # UI 출력: 추천 음악 목록
        if music_list:
            st.subheader("🎧 추천 플레이리스트")
            st.markdown(music_list)

        # UI 출력: 유튜브 검색 버튼
        if keyword:
            encoded_keyword = urllib.parse.quote(keyword)
            yt_url = f"https://www.youtube.com/results?search_query={encoded_keyword}"
            st.link_button(
                f"🔍 유튜브에서 '{keyword}' 듣기", yt_url, use_container_width=True
            )

    except Exception as e:
        # 파싱 오류 발생 시 원문 출력 fallback
        st.warning("응답 양식이 정규 규격과 달라 텍스트 원문으로 표시합니다.")
        st.write(response_text)


# 5. UI 화면 구성 (Streamlit 앱 Main)
st.title("🎵 무드튠 (MOODTUNE)")
st.caption(
    "오늘 당신의 기분이나 들었던 생각을 적어주세요. 감정을 분석해 어울리는 음악을 추천해드립니다."
)

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 이전 대화 내용 출력
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            parse_and_display_response(msg["content"])

# 예시 질문 버튼 제공
st.write("---")
example_col1, example_col2 = st.columns(2)
example_input = None

if example_col1.button("🌧️ 비 오고 잔잔한 팝송 추천"):
    example_input = "오늘 비가 오는데 괜히 울적해지고 잔잔한 음악이 듣고 싶네.. 잔잔한 팝송 위주로 추천해줘!"

if example_col2.button("🎉 시험 끝나서 신나는 K-POP"):
    example_input = "시험 끝나서 기분이 너무 날아갈 것 같아! 신나는 케이팝 노래 추천해줘"

# 사용자 입력 처리
user_prompt = st.chat_input("오늘 기분이 어떠신가요?")

# 예시 버튼 입력 또는 채팅 입력 적용
final_input = user_prompt or example_input

if final_input:
    # 1. 사용자 메시지 화면 표시 및 세션 저장
    st.session_state.messages.append({"role": "user", "content": final_input})
    with st.chat_message("user"):
        st.write(final_input)

    # 2. AI 응답 생성
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
