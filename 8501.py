import streamlit as st
import time
from datetime import datetime

# 1. 페이지 설정 (자비스 대시보드 테마)
st.set_page_config(page_title="JARVIS - Oracle 8501", layout="wide", initial_sidebar_state="expanded")

# 2. 커스텀 스타일 (사령부 느낌)
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #00ff00; }
    .stMetric { background-color: #1e2130; border-radius: 10px; padding: 15px; border: 1px solid #00ffff; }
    </style>
    """, unsafe_allow_html=True)

# 3. 사이드바 - 사령부 상태창
with st.sidebar:
    st.title("⚓ 춘천 사령부")
    st.subheader("지휘관: David")
    st.info(f"📍 작전 개시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if st.button("🔄 시스템 리부트"):
        st.rerun()

# 4. 메인 대시보드
st.title("🎻 JARVIS: Oracle 8501 공성 대시보드")
st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="🎯 목표 OCPU", value="2 / 3 / 4", delta="순환 타격 중")

with col2:
    st.metric(label="💾 목표 RAM", value="24 GB", delta="고정")

with col3:
    st.metric(label="⚡ 작전 상태", value="공성 중", delta="Active")

# 5. 작전 상황판 (수동 클릭 가이드 겸용)
st.subheader("📝 사령관 전용 작전 지침")
st.warning("""
1. 브라우저의 오라클 창에서 **OCPU 2 / RAM 24**를 수동 입력한다.
2. 하단의 **[Save changes]** 버튼을 5초 간격으로 타격한다.
3. 성공하여 창이 닫히면 자비스가 즉시 서버 점령 절차를 시작한다.
""")

# 6. 실시간 로그 (가상 시뮬레이션)
st.subheader("🕵️ 자비스 실시간 분석 로그")
log_box = st.empty()
now = datetime.now().strftime('%H:%M:%S')
log_box.code(f"[{now}] 자비스 시스템 온라인.\n[{now}] 춘천 사령부 통신 대기 중...\n[{now}] 사령관님의 수동 타격을 감지하기 위해 대기 중.", language="bash")

st.divider()
st.caption("“Everything is achievable with enough caffeine and a reliable AI.” - JARVIS")
