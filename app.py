import streamlit as st
import pandas as pd
import io
import datetime

st.set_page_config(layout="wide")

st.title("라인·교대별 생산 실적 대시보드")

# 파일 업로더 (여러 파일 허용, 확장자 .csv만 허용)
uploaded_files = st.file_uploader(
    "생산 실적 CSV 업로드 (여러 날짜 파일 동시 선택 가능)",
    type=["csv"],
    accept_multiple_files=True
)

required_cols = ['날짜', '라인', '교대', '생산수량', '불량수량', '목표수량']

valid_dfs = []
invalid_warnings = []

if uploaded_files:
    for uploaded_file in uploaded_files:
        content = uploaded_file.read()
        df = None
        # UTF-8로 먼저 읽고, 실패하면 CP949로 다시 읽는다
        try:
            df = pd.read_csv(io.BytesIO(content), encoding='utf-8')
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(content), encoding='cp949')
            except Exception as e:
                invalid_warnings.append(f"⚠️ {uploaded_file.name} — 파일 읽기 실패 (인코딩 오류)")
                continue
        
        if df is not None:
            # 필수 컬럼 검증
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                missing_str = ", ".join(missing_cols)
                invalid_warnings.append(f"⚠️ {uploaded_file.name} — {missing_str} 컬럼 누락으로 제외됨")
            else:
                # 정상 파일 데이터 저장
                # 컬럼 타입 정제 (생산수량, 불량수량, 목표수량은 숫자로 변환)
                try:
                    df['생산수량'] = pd.to_numeric(df['생산수량'], errors='coerce').fillna(0).astype(int)
                    df['불량수량'] = pd.to_numeric(df['불량수량'], errors='coerce').fillna(0).astype(int)
                    df['목표수량'] = pd.to_numeric(df['목표수량'], errors='coerce').fillna(0).astype(int)
                    
                    # 날짜 형식 파싱
                    df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce').dt.date
                    df = df.dropna(subset=['날짜'])
                    
                    df['라인'] = df['라인'].astype(str).str.strip()
                    df['교대'] = df['교대'].astype(str).str.strip()
                    
                    valid_dfs.append(df)
                except Exception as e:
                    invalid_warnings.append(f"⚠️ {uploaded_file.name} — 데이터 타입 변환 실패")
                    continue

# 화면 상단에 경고 표시
for warning in invalid_warnings:
    st.warning(warning)

# 정상 파일이 0개인 경우 안내문만 표시하고 중단
if not valid_dfs:
    st.info("일자별 생산 실적 CSV를 업로드하세요")
    st.markdown("""
    **필수 컬럼 6개 목록:**
    - **날짜** — 텍스트, YYYY-MM-DD 형식
    - **라인** — 텍스트 (예: A라인/B라인/C라인)
    - **교대** — 텍스트, 값은 주간/야간 두 가지
    - **생산수량** — 숫자 (콤마 없음)
    - **불량수량** — 숫자 (콤마 없음)
    - **목표수량** — 숫자 (콤마 없음)
    """)
    st.stop()

# 병합
merged_df = pd.concat(valid_dfs, ignore_index=True)

# 중복 처리: 날짜+라인+교대가 완전히 동일한 중복 행은 첫 번째만 남기고 제거
initial_len = len(merged_df)
merged_df = merged_df.drop_duplicates(subset=['날짜', '라인', '교대'], keep='first')
removed_count = initial_len - len(merged_df)
if removed_count > 0:
    st.warning(f"중복 데이터 {removed_count}건이 제거되었습니다")

# 사이드바 필터 구성
st.sidebar.header("필터 설정")

min_date = merged_df['날짜'].min()
max_date = merged_df['날짜'].max()

# 날짜 범위
date_range = st.sidebar.date_input(
    "날짜 범위",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

# 라인 다중 선택
unique_lines = sorted(merged_df['라인'].unique())
selected_lines = st.sidebar.multiselect(
    "라인 선택",
    options=unique_lines,
    default=unique_lines
)

# 교대 선택
selected_shift = st.sidebar.selectbox(
    "교대 선택",
    options=["전체", "주간", "야간"],
    index=0
)

# 필터링 적용
filtered_df = merged_df.copy()

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered_df = filtered_df[(filtered_df['날짜'] >= start_date) & (filtered_df['날짜'] <= end_date)]
elif isinstance(date_range, tuple) and len(date_range) == 1:
    start_date = date_range[0]
    filtered_df = filtered_df[filtered_df['날짜'] == start_date]
elif isinstance(date_range, datetime.date):
    filtered_df = filtered_df[filtered_df['날짜'] == date_range]

filtered_df = filtered_df[filtered_df['라인'].isin(selected_lines)]

if selected_shift != "전체":
    filtered_df = filtered_df[filtered_df['교대'] == selected_shift]

# 계산 처리
total_prod = int(filtered_df['생산수량'].sum())
total_defect = int(filtered_df['불량수량'].sum())
total_target = int(filtered_df['목표수량'].sum())

avg_achievement = (total_prod / total_target * 100) if total_target > 0 else 0.0
avg_defect = (total_defect / total_prod * 100) if total_prod > 0 else 0.0

# 문제 라인 계산
problem_line_str = "없음"
if not filtered_df.empty:
    line_group = filtered_df.groupby('라인').agg({
        '생산수량': 'sum',
        '불량수량': 'sum'
    }).reset_index()
    line_group['불량률'] = line_group.apply(
        lambda r: (r['불량수량'] / r['생산수량'] * 100) if r['생산수량'] > 0 else 0.0,
        axis=1
    )
    if not line_group.empty and line_group['생산수량'].sum() > 0:
        idx_max = line_group['불량률'].idxmax()
        max_row = line_group.loc[idx_max]
        problem_line_str = f"{max_row['라인']} ({max_row['불량률']:.2f}%)"

# ④ 출력 (위→아래 순서, 색상 경고 없이 숫자만 표시)

# 상단 KPI 카드 4개(st.metric)
kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
kpi_col1.metric("총 생산수량", f"{total_prod:,}")
kpi_col2.metric("평균 달성률(%)", f"{avg_achievement:.2f}%")
kpi_col3.metric("평균 불량률(%)", f"{avg_defect:.2f}%")
kpi_col4.metric("문제 라인", problem_line_str)

st.markdown("---")

# 차트 1 — 라인별 생산수량 vs 목표수량 비교 막대차트
st.subheader("라인별 생산수량 vs 목표수량 비교")
if not filtered_df.empty:
    chart1_data = filtered_df.groupby('라인')[['생산수량', '목표수량']].sum()
    st.bar_chart(chart1_data)
else:
    st.info("필터링된 데이터가 없습니다.")

# 차트 2 — 라인×교대별 불량률 막대차트 (라인별로 주간/야간 나란히)
st.subheader("라인×교대별 불량률 (%)")
if not filtered_df.empty:
    chart2_group = filtered_df.groupby(['라인', '교대']).agg({
        '생산수량': 'sum',
        '불량수량': 'sum'
    }).reset_index()
    chart2_group['불량률'] = chart2_group.apply(
        lambda r: (r['불량수량'] / r['생산수량'] * 100) if r['생산수량'] > 0 else 0.0,
        axis=1
    )
    chart2_pivot = chart2_group.pivot(index='라인', columns='교대', values='불량률')
    for col in ['주간', '야간']:
        if col not in chart2_pivot.columns:
            chart2_pivot[col] = 0.0
    chart2_pivot = chart2_pivot[['주간', '야간']].fillna(0.0)
    st.bar_chart(chart2_pivot)
else:
    st.info("필터링된 데이터가 없습니다.")

# 차트 3 — 일자별 총 생산수량 추이 꺾은선 차트
st.subheader("일자별 총 생산수량 추이")
if not filtered_df.empty:
    chart3_data = filtered_df.groupby('날짜')[['생산수량']].sum().sort_index()
    st.line_chart(chart3_data)
else:
    st.info("필터링된 데이터가 없습니다.")

st.markdown("---")

# 하단 — 라인별 집계표(생산·불량·목표·달성률·불량률)
st.subheader("라인별 집계표")
if not filtered_df.empty:
    line_table = filtered_df.groupby('라인').agg({
        '생산수량': 'sum',
        '불량수량': 'sum',
        '목표수량': 'sum'
    }).reset_index()
    line_table['달성률(%)'] = line_table.apply(
        lambda r: (r['생산수량'] / r['목표수량'] * 100) if r['목표수량'] > 0 else 0.0,
        axis=1
    )
    line_table['불량률(%)'] = line_table.apply(
        lambda r: (r['불량수량'] / r['생산수량'] * 100) if r['생산수량'] > 0 else 0.0,
        axis=1
    )
    
    st.dataframe(
        line_table,
        column_config={
            "라인": st.column_config.TextColumn("라인"),
            "생산수량": st.column_config.NumberColumn("생산수량", format="%d"),
            "불량수량": st.column_config.NumberColumn("불량수량", format="%d"),
            "목표수량": st.column_config.NumberColumn("목표수량", format="%d"),
            "달성률(%)": st.column_config.NumberColumn("달성률(%)", format="%.2f%%"),
            "불량률(%)": st.column_config.NumberColumn("불량률(%)", format="%.2f%%")
        },
        hide_index=True,
        use_container_width=True
    )
else:
    st.info("필터링된 데이터가 없습니다.")

# 그 아래 필터 반영된 원본 데이터 표
st.subheader("상세 원본 데이터")
if not filtered_df.empty:
    display_df = filtered_df.copy()
    display_df['날짜'] = display_df['날짜'].apply(lambda x: x.strftime("%Y-%m-%d") if hasattr(x, 'strftime') else str(x))
    st.dataframe(
        display_df,
        column_config={
            "날짜": st.column_config.TextColumn("날짜"),
            "라인": st.column_config.TextColumn("라인"),
            "교대": st.column_config.TextColumn("교대"),
            "생산수량": st.column_config.NumberColumn("생산수량", format="%d"),
            "불량수량": st.column_config.NumberColumn("불량수량", format="%d"),
            "목표수량": st.column_config.NumberColumn("목표수량", format="%d")
        },
        hide_index=True,
        use_container_width=True
    )
else:
    st.info("필터링된 데이터가 없습니다.")
