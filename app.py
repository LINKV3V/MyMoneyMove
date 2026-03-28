import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_gsheets import GSheetsConnection
import hashlib
from datetime import datetime
import calendar

st.set_page_config(page_title="My Money Move (Web)", layout="wide")

# ==========================================
# 🛠️ 데이터베이스 관리 (구글 시트 연동)
# ==========================================
# Streamlit Secrets에 저장된 구글 시트 주소를 통해 연결합니다.
conn = st.connection("gsheets", type=GSheetsConnection)

def make_hashes(password): 
    return hashlib.sha256(str.encode(password)).hexdigest()

# 안전하게 구글 시트를 읽어오는 함수
def read_sheet_safe(sheet_name, default_cols):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0) # ttl=0: 실시간 동기화
        if df.empty or len(df.columns) == 0:
            return pd.DataFrame(columns=default_cols)
        return df
    except Exception:
        return pd.DataFrame(columns=default_cols)

# 1. 사용자 정보 (users 탭)
def load_users():
    return read_sheet_safe("users", ["username", "password"])

def save_users(df):
    conn.update(worksheet="users", data=df)
    st.cache_data.clear()

# 2. 카테고리 정보 (categories 탭)
def load_categories(username):
    df = read_sheet_safe("categories", ["username", "분류", "세부분류"])
    user_df = df[df['username'] == username].copy()
    
    # 첫 사용자일 경우 기본 카테고리 세팅
    if user_df.empty:
        temp = {
            "username": [username]*19,
            "분류": ["수입"]*5 + ["지출"]*9 + ["투자(저축)"]*5,
            "세부분류": [
                "용돈", "급여", "상여금", "성과급", "부수입",
                "고정비(통신비)", "고정비(관리비)", "생활비(식비)", "생활비(교통)", "생활비(의료)", "생활비(교육)", "생활비(잡화)", "생활비(자유)", "생활비(관리)",
                "해외주식", "국내주식", "적금", "원자재", "코인"
            ]
        }
        return pd.DataFrame(temp)
    return user_df

def save_categories(username, user_df):
    df = read_sheet_safe("categories", ["username", "분류", "세부분류"])
    df = df[df['username'] != username] # 기존 유저 정보 삭제
    user_df['username'] = username # 새 정보에 유저명 추가
    df = pd.concat([df, user_df], ignore_index=True)
    conn.update(worksheet="categories", data=df)
    st.cache_data.clear()

# 3. 가계부 내역 정보 (ledger 탭)
def load_ledger(username):
    df = read_sheet_safe("ledger", ["username", "날짜", "분류", "세부분류", "항목", "금액"])
    user_df = df[df['username'] == username].copy()
    
    if "세부분류" not in user_df.columns: user_df["세부분류"] = "기타"
    user_df['세부분류'] = user_df['세부분류'].fillna('기타').astype(str)
    user_df['항목'] = user_df['항목'].fillna('내용없음').astype(str)
    return user_df

def save_ledger(username, new_data=None, overwrite_df=None):
    df = read_sheet_safe("ledger", ["username", "날짜", "분류", "세부분류", "항목", "금액"])
    
    if overwrite_df is not None:
        # 수정/삭제: 현재 유저의 기록을 모두 지우고 덮어쓰기
        overwrite_df['username'] = username
        df = df[df['username'] != username]
        df = pd.concat([df, overwrite_df], ignore_index=True)
    else:
        # 신규 추가: 기존 기록 맨 아래에 추가
        if new_data is not None:
            new_data['username'] = username
            df = pd.concat([df, new_data], ignore_index=True)
            
    conn.update(worksheet="ledger", data=df)
    st.cache_data.clear()

# ==========================================
# ➕ 팝업창 모음
# ==========================================
@st.dialog("⚙️ 카테고리 관리")
def manage_categories_dialog(current_user):
    cats = load_categories(current_user)
    t1, t2, t3 = st.tabs(["🔵 수입", "🔴 지출", "🟢 투자"])
    with t1: e_inc = st.data_editor(cats[cats['분류']=='수입'][['세부분류']].reset_index(drop=True), num_rows="dynamic", use_container_width=True)
    with t2: e_exp = st.data_editor(cats[cats['분류']=='지출'][['세부분류']].reset_index(drop=True), num_rows="dynamic", use_container_width=True)
    with t3: e_inv = st.data_editor(cats[cats['분류']=='투자(저축)'][['세부분류']].reset_index(drop=True), num_rows="dynamic", use_container_width=True)
        
    if st.button("💾 카테고리 저장", use_container_width=True):
        e_inc['분류'] = '수입'; e_exp['분류'] = '지출'; e_inv['분류'] = '투자(저축)'
        new_cats = pd.concat([e_inc, e_exp, e_inv], ignore_index=True)[['분류', '세부분류']]
        new_cats.dropna(subset=['세부분류'], inplace=True)
        save_categories(current_user, new_cats[new_cats['세부분류'].str.strip() != ""])
        st.success("저장 완료!"); st.rerun()

@st.dialog("📝 상세 수정 및 연속 추가")
def show_daily_detail_dialog(current_user, date_str):
    def edit_cb(idx):
        amt_str = str(st.session_state.get(f"a_{idx}", "0")).replace(',', '')
        try: amt = int(amt_str)
        except: amt = 0
        if amt <= 0: st.session_state[f"msg_{idx}"] = ("error", "❌ 금액을 1원 이상 입력해주세요!")
        else:
            df_cur = load_ledger(current_user)
            df_cur.at[idx, '날짜'] = st.session_state[f"d_{idx}"].strftime('%Y-%m-%d')
            df_cur.at[idx, '분류'] = st.session_state[f"t_{idx}"]
            df_cur.at[idx, '세부분류'] = st.session_state[f"s_{idx}"]
            df_cur.at[idx, '항목'] = st.session_state[f"n_{idx}"]
            df_cur.at[idx, '금액'] = amt
            save_ledger(current_user, overwrite_df=df_cur)
            st.session_state[f"msg_{idx}"] = ("success", "✅ 수정 완료!")

    def del_cb(idx):
        df_cur = load_ledger(current_user)
        save_ledger(current_user, overwrite_df=df_cur.drop(idx))
        st.session_state[f"msg_top"] = ("success", "🗑️ 삭제 완료!")

    def add_cb():
        amt_str = str(st.session_state.get("new_a", "0")).replace(',', '')
        try: amt = int(amt_str)
        except: amt = 0
        if amt <= 0: st.session_state["msg_new"] = ("error", "❌ 금액을 1원 이상 입력해주세요!")
        else:
            new_rec = pd.DataFrame([[
                date_str, st.session_state["new_t"], st.session_state["new_s"],
                st.session_state["new_n"], amt
            ]], columns=["날짜", "분류", "세부분류", "항목", "금액"])
            save_ledger(current_user, new_data=new_rec)
            st.session_state["msg_new"] = ("success", "✅ 기록 추가 완료!")

    df = load_ledger(current_user)
    cats = load_categories(current_user)
    day_idx = df[df['날짜'] == date_str].index
    
    st.markdown(f"### 🗓️ {date_str} 기록")
    if st.session_state.get("msg_top"):
        st.success(st.session_state["msg_top"][1])
        st.session_state["msg_top"] = None

    if len(day_idx) == 0: st.info("기록이 없습니다.")
    else:
        for idx in day_idx:
            row = df.loc[idx]
            with st.expander(f"[{row['분류']}-{row['세부분류']}] {row['항목']} : {int(row['금액']):,}원"):
                c_date = st.date_input("날짜 이동", datetime.strptime(row['날짜'], '%Y-%m-%d'), key=f"d_{idx}")
                c_type = st.selectbox("분류 변경", ["수입", "지출", "투자(저축)"], index=["수입", "지출", "투자(저축)"].index(row['분류']), key=f"t_{idx}")
                s_opts = cats[cats['분류'] == c_type]['세부분류'].tolist()
                if row['세부분류'] not in s_opts: s_opts.append(row['세부분류'])
                c_sub = st.selectbox("세부분류 변경", s_opts, index=s_opts.index(row['세부분류']), key=f"s_{idx}")

                with st.form(key=f"edit_form_{idx}", clear_on_submit=False):
                    st.text_input("내용 수정 (TAB 이동 지원)", value=row['항목'], key=f"n_{idx}")
                    st.text_input("금액 수정 (원)", value=f"{int(row['금액'])}", key=f"a_{idx}")

                    msg = st.session_state.get(f"msg_{idx}")
                    if msg:
                        if msg[0] == "error": st.error(msg[1])
                        else: st.success(msg[1])
                        st.session_state[f"msg_{idx}"] = None

                    col1, col2 = st.columns(2)
                    col1.form_submit_button("✅ 수정 완료", on_click=edit_cb, args=(idx,), use_container_width=True)
                    col2.form_submit_button("🗑️ 삭제", on_click=del_cb, args=(idx,), use_container_width=True)

    st.markdown("---")
    st.markdown(f"#### ➕ {date_str}에 연속 추가")
    new_type = st.selectbox("분류", ["수입", "지출", "투자(저축)"], key="new_t")
    new_s_opts = cats[cats['분류'] == new_type]['세부분류'].tolist()
    st.selectbox("세부분류", new_s_opts if new_s_opts else ["기타"], key="new_s")

    with st.form("new_daily_form", clear_on_submit=True):
        st.text_input("내용 (입력 후 TAB 누르면 이동)", placeholder="예: 커피", key="new_n")
        st.text_input("금액 (원) (엔터 누르면 저장)", placeholder="1원 이상 숫자 입력", key="new_a")

        msg = st.session_state.get("msg_new")
        if msg:
            if msg[0] == "error": st.error(msg[1])
            else: st.success(msg[1])
            st.session_state["msg_new"] = None

        st.form_submit_button("🚀 이 날짜로 기록 추가 (엔터)", on_click=add_cb, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("닫기 및 달력 새로고침", type="primary", use_container_width=True):
        st.rerun()

# ==========================================
# 🔐 1단계: 로그인
# ==========================================
if "logged_in" not in st.session_state: st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    st.title("🔐 My Money Move (Web)")
    tab1, tab2 = st.tabs(["로그인", "회원가입"])
    with tab1:
        with st.form("login_form"):
            u = st.text_input("아이디")
            p = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인 (엔터)", use_container_width=True):
                users = load_users()
                if not users.empty and u in users['username'].values and make_hashes(p) == users.loc[users['username'] == u, 'password'].values[0]:
                    st.session_state["logged_in"] = True; st.session_state["username"] = u; st.rerun()
                else: st.error("정보 불일치")
    with tab2:
        with st.form("signup_form"):
            nu = st.text_input("새 아이디"); np = st.text_input("새 비밀번호", type="password")
            if st.form_submit_button("회원가입 (엔터)", use_container_width=True):
                users = load_users()
                if not users.empty and nu in users['username'].values:
                    st.error("이미 존재하는 아이디입니다.")
                else:
                    new_user = pd.DataFrame([[nu, make_hashes(np)]], columns=["username", "password"])
                    save_users_df = pd.concat([users, new_user], ignore_index=True)
                    save_users(save_users_df)
                    st.success("가입 성공! 로그인 탭에서 로그인해주세요.")

# ==========================================
# 📱 2단계: 메인 어플리케이션
# ==========================================
else:
    current_user = st.session_state["username"]
    df_ledger = load_ledger(current_user)
    
    today = datetime.today()
    if 'sync_month_idx' not in st.session_state:
        st.session_state.sync_month_idx = today.month - 1
        st.session_state.sync_year = today.year

    def sync(key):
        selected = st.session_state[key]
        st.session_state.sync_year = int(selected.split("년")[0])
        st.session_state.sync_month_idx = int(selected.split("년")[1].replace("월", "")) - 1
        st.session_state.month_selector = selected; st.session_state.month_selector_analysis = selected

    c1, c2 = st.columns([9, 1])
    c1.markdown(f"### **{current_user}**님의 지출/수입 대시보드")
    if c2.button("로그아웃"): st.session_state["logged_in"] = False; st.rerun()
    st.markdown("---")
    
    tab_calendar, tab_analysis = st.tabs(["🗓️ 가계부 달력", "📊 디테일 흐름 분석 (생키)"])

    sel_year = st.session_state.sync_year
    sel_month = st.session_state.sync_month_idx + 1
    monthly_df = pd.DataFrame()
    if not df_ledger.empty:
        df_ledger['날짜'] = pd.to_datetime(df_ledger['날짜'])
        monthly_df = df_ledger[(df_ledger['날짜'].dt.year == sel_year) & (df_ledger['날짜'].dt.month == sel_month)]
        
    t_inc = monthly_df[monthly_df['분류'] == '수입']['금액'].sum() if not monthly_df.empty else 0
    t_exp = monthly_df[monthly_df['분류'] == '지출']['금액'].sum() if not monthly_df.empty else 0
    t_inv = monthly_df[monthly_df['분류'] == '투자(저축)']['금액'].sum() if not monthly_df.empty else 0
    net_savings = t_inc - t_exp
    month_options = [f"{sel_year}년 {m}월" for m in range(1, 13)]

    # ----------------------------------------
    # 탭 1: 가계부 달력
    # ----------------------------------------
    with tab_calendar:
        hc1, hc2, hc3 = st.columns([2, 1, 1])
        with hc1: st.selectbox("조회", month_options, index=st.session_state.sync_month_idx, key="month_selector", on_change=sync, args=("month_selector",), label_visibility="collapsed")
        with hc2:
            if st.button("➕ 오늘 거래 추가", use_container_width=True): show_daily_detail_dialog(current_user, datetime.today().strftime('%Y-%m-%d'))
        with hc3:
            if st.button("⚙️ 카테고리 관리", use_container_width=True): manage_categories_dialog(current_user)
            
        c1, c2, c3 = st.columns(3)
        c1.metric("수입", f"{t_inc:,} 원"); c2.metric("지출", f"{t_exp:,} 원"); c3.metric("투자", f"{t_inv:,} 원")
        st.markdown(f"<h3 style='text-align:center; color:#22c55e;'>이번 달 모은 돈: {net_savings:,} 원</h3><br>", unsafe_allow_html=True)
        
        calendar.setfirstweekday(calendar.SUNDAY)
        cal_matrix = calendar.monthcalendar(sel_year, sel_month)
        cols = st.columns(7)
        for i, dn in enumerate(["일", "월", "화", "수", "목", "금", "토"]):
            cols[i].markdown(f"<div style='text-align:center; color:{'red' if i==0 else 'blue' if i==6 else 'black'}; font-weight:bold;'>{dn}</div>", unsafe_allow_html=True)
        st.markdown("<hr style='margin-top: 5px; margin-bottom: 10px;'>", unsafe_allow_html=True)
        for week in cal_matrix:
            cols = st.columns(7)
            for i, day in enumerate(week):
                if day != 0:
                    ds = f"{sel_year}-{sel_month:02d}-{day:02d}"
                    d_i = d_e = d_v = 0
                    if not monthly_df.empty:
                        dd = monthly_df[monthly_df['날짜'] == pd.to_datetime(ds)]
                        d_i = dd[dd['분류'] == '수입']['금액'].sum()
                        d_e = dd[dd['분류'] == '지출']['금액'].sum()
                        d_v = dd[dd['분류'] == '투자(저축)']['금액'].sum()
                    with cols[i]:
                        if st.button(str(day), key=f"btn_{ds}", use_container_width=True): show_daily_detail_dialog(current_user, ds)
                        if d_i > 0: st.markdown(f"<div style='text-align:center; color:#3b82f6; font-size:12px; margin-top:-8px;'>+{d_i:,}</div>", unsafe_allow_html=True)
                        if d_e > 0: st.markdown(f"<div style='text-align:center; color:#4b5563; font-size:12px; margin-top:-3px;'>-{d_e:,}</div>", unsafe_allow_html=True)
                        if d_v > 0: st.markdown(f"<div style='text-align:center; color:#22c55e; font-size:12px; margin-top:-3px;'>={d_v:,}</div>", unsafe_allow_html=True)

    # ----------------------------------------
    # 탭 2: 디테일 흐름 분석 (폭포수 절대 정렬 완벽 적용)
    # ----------------------------------------
    with tab_analysis:
        st.selectbox("조회 (분석)", month_options, index=st.session_state.sync_month_idx, key="month_selector_analysis", on_change=sync, args=("month_selector_analysis",), label_visibility="collapsed")
        if monthly_df.empty or (t_inc == 0 and t_exp == 0 and t_inv == 0): st.info("데이터 부족")
        else:
            df_sorted = monthly_df.sort_values(by="날짜", ascending=True)
            df_sorted['날짜_str'] = df_sorted['날짜'].dt.strftime('%m-%d')
            
            nodes_set = set()
            node_col = {}
            link_dict = {} 
            node_details = {} 
            parent_of_c3 = {} 
            parent_of_c4 = {} 
            
            def add_node(name, col):
                if name not in nodes_set:
                    nodes_set.add(name)
                    node_col[name] = col
                    node_details[name] = []

            def add_link(s_name, s_col, t_name, t_col, val, det):
                add_node(s_name, s_col)
                add_node(t_name, t_col)
                if (s_name, t_name) not in link_dict: link_dict[(s_name, t_name)] = 0
                link_dict[(s_name, t_name)] += val
                if det: node_details[t_name].append(det)

            layer0_in = []
            for _, r in df_sorted[df_sorted['분류'] == '수입'].iterrows():
                sub = str(r['세부분류']).strip()
                if sub not in layer0_in: layer0_in.append(sub)
                amt, det = r['금액'], f"{r['날짜_str']} | {r['항목']} | {r['금액']:,}원"
                add_link(sub, 0, "총 수입", 1, amt, det)
                
            layer3_grp = []
            for typ, t_name in [('지출', "총 지출"), ('투자(저축)', "총 투자")]:
                for _, r in df_sorted[df_sorted['분류'] == typ].iterrows():
                    sub = str(r['세부분류']).strip()
                    amt, det = r['금액'], f"{r['날짜_str']} | {r['항목']} | {r['금액']:,}원"
                    
                    if '(' in sub and ')' in sub:
                        grp = sub.split('(')[0].strip()
                        dtl = sub.split('(')[1].replace(')', '').strip()
                        if dtl == grp: dtl += " " 
                        if grp not in layer3_grp: layer3_grp.append(grp)
                        parent_of_c3[grp] = t_name
                        parent_of_c4[dtl] = grp
                        add_link(t_name, 2, grp, 3, amt, None) 
                        add_link(grp, 3, dtl, 4, amt, det)
                    else:
                        parent_of_c4[sub] = t_name
                        add_link(t_name, 2, sub, 4, amt, det)
            
            if t_exp > 0: add_link("총 수입", 1, "총 지출", 2, t_exp, None)
            if t_inv > 0: add_link("총 수입", 1, "총 투자", 2, t_inv, None)
            cash_s = max(0, t_inc - t_exp - t_inv)
            if cash_s > 0: add_link("총 수입", 1, "현금 잉여(보유)", 4, cash_s, "이번 달 남은 잉여 자금") 

            nodes = list(nodes_set)
            node_money = {n: 0 for n in nodes_set}
            for (s, t), v in link_dict.items():
                node_money[t] += v
                if node_col[s] == 0: node_money[s] += v

            right_leaves = []
            
            fixed_c = [n for n in nodes_set if parent_of_c4.get(n) == "고정비"]
            fixed_c.sort(key=lambda x: -node_money[x])
            right_leaves.extend(fixed_c)
            
            living_c = [n for n in nodes_set if parent_of_c4.get(n) == "생활비"]
            living_c.sort(key=lambda x: -node_money[x])
            right_leaves.extend(living_c)
            
            other_grp = [g for g in layer3_grp if parent_of_c3.get(g) == "총 지출" and g not in ["고정비", "생활비"]]
            other_grp.sort(key=lambda x: -node_money[x])
            for g in other_grp:
                g_c = [n for n in nodes_set if parent_of_c4.get(n) == g]
                g_c.sort(key=lambda x: -node_money[x])
                right_leaves.extend(g_c)
                
            solo_exp = [n for n in nodes_set if parent_of_c4.get(n) == "총 지출"]
            solo_exp.sort(key=lambda x: -node_money[x])
            right_leaves.extend(solo_exp)
            
            inv_grp = [g for g in layer3_grp if parent_of_c3.get(g) == "총 투자"]
            inv_grp.sort(key=lambda x: -node_money[x])
            for g in inv_grp:
                g_c = [n for n in nodes_set if parent_of_c4.get(n) == g]
                g_c.sort(key=lambda x: -node_money[x])
                right_leaves.extend(g_c)
                
            solo_inv = [n for n in nodes_set if parent_of_c4.get(n) == "총 투자"]
            solo_inv.sort(key=lambda x: -node_money[x])
            right_leaves.extend(solo_inv)
            
            if "현금 잉여(보유)" in nodes_set: right_leaves.append("현금 잉여(보유)")
            
            y_coords = {}
            tot_right = sum(node_money[n] for n in right_leaves)
            if tot_right == 0: tot_right = 1
            curr_y = 0.02
            pad = 0.02
            usable = max(0.1, 1.0 - (pad * (len(right_leaves) - 1)))
            for n in right_leaves:
                h = (node_money[n] / tot_right) * usable
                y_coords[n] = curr_y + (h / 2.0)
                curr_y += h + pad
                
            for g in layer3_grp:
                g_c = [n for n in nodes_set if parent_of_c4.get(n) == g]
                if g_c:
                    w_sum = sum(y_coords[c] * node_money[c] for c in g_c)
                    tot = sum(node_money[c] for c in g_c)
                    y_coords[g] = w_sum / tot if tot > 0 else 0.5
                else: y_coords[g] = 0.5
                    
            for m in ["총 지출", "총 투자"]:
                if m not in nodes_set: continue
                c_g = [g for g in layer3_grp if parent_of_c3.get(g) == m] 
                c_s = [n for n in nodes_set if parent_of_c4.get(n) == m] 
                w_sum = sum(y_coords[g] * node_money[g] for g in c_g) + sum(y_coords[s] * node_money[s] for s in c_s)
                tot = sum(node_money[g] for g in c_g) + sum(node_money[s] for s in c_s)
                y_coords[m] = w_sum / tot if tot > 0 else 0.5
                
            mains = [m for m in ["총 지출", "총 투자", "현금 잉여(보유)"] if m in nodes_set]
            if mains:
                w_sum = sum(y_coords[m] * node_money[m] for m in mains)
                tot = sum(node_money[m] for m in mains)
                y_coords["총 수입"] = w_sum / tot if tot > 0 else 0.5
            
            layer0_in.sort(key=lambda x: -node_money[x])
            tot_in = sum(node_money[n] for n in layer0_in)
            if tot_in == 0: tot_in = 1
            curr_y = 0.02
            usable_in = max(0.1, 1.0 - (pad * (len(layer0_in) - 1)))
            for n in layer0_in:
                h = (node_money[n] / tot_in) * usable_in
                y_coords[n] = curr_y + (h / 2.0)
                curr_y += h + pad
                
            nodes = list(nodes_set)
            final_x, final_y = [], []
            x_map = {0: 0.01, 1: 0.25, 2: 0.50, 3: 0.75, 4: 0.99}
            
            for n in nodes:
                final_y.append(y_coords.get(n, 0.5))
                if n in layer0_in: final_x.append(x_map[0])
                elif n == "총 수입": final_x.append(x_map[1])
                elif n in ["총 지출", "총 투자"]: final_x.append(x_map[2])
                elif n in layer3_grp: final_x.append(x_map[3])
                else: final_x.append(x_map[4])

            customdata = []
            for n in nodes:
                dets = node_details.get(n, [])
                if not dets: customdata.append("세부 내역 없음")
                else: customdata.append("<br>".join(dets[:15]) + (f"<br>...외 {len(dets)-15}건" if len(dets)>15 else ""))

            colors = []
            for n in nodes:
                if n == "총 수입": colors.append("#1d4ed8")
                elif n == "총 지출": colors.append("#b91c1c")
                elif n == "총 투자": colors.append("#15803d")
                elif n == "고정비": colors.append("#ef4444")
                elif n == "생활비": colors.append("#f87171")
                elif n == "현금 잉여(보유)": colors.append("gray")
                elif node_col[n] == 0: colors.append("#60a5fa")
                elif node_col[n] == 4:
                    p = parent_of_c4.get(n, "")
                    if p in ["고정비", "생활비", "총 지출"] or parent_of_c3.get(p) == "총 지출": colors.append("#fca5a5")
                    else: colors.append("#86efac")
                else: colors.append("#d1d5db")

            source_idx = [nodes.index(s) for (s, t) in link_dict.keys()]
            target_idx = [nodes.index(t) for (s, t) in link_dict.keys()]
            link_vals = list(link_dict.values())

            fig = go.Figure(data=[go.Sankey(
                arrangement="freeform", 
                node = dict(
                    pad=15, thickness=20, line=dict(color="black", width=0.5),
                    label=nodes, color=colors, x=final_x, y=final_y,
                    customdata=customdata,
                    hovertemplate="<b>%{label}</b><br>총액: %{value:,.0f}원<br><br><b>[상세 내역]</b><br>%{customdata}<extra></extra>"
                ),
                link = dict(source=source_idx, target=target_idx, value=link_vals, hoverinfo="none")
            )])
            fig.update_layout(height=800, font=dict(size=14, color="black"))
            st.plotly_chart(fig, use_container_width=True)