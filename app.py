"""
Monthly expense tracker (Streamlit + Supabase)

Each person has their own account (Supabase Auth, verified by an e-mail code)
and their data lives in Supabase Postgres, protected by Row Level Security.

Run locally:  pip install -r requirements.txt
              create .streamlit/secrets.toml (see .streamlit/secrets.toml.example)
              streamlit run app.py
"""

import re
from calendar import monthrange
from datetime import date
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st
from postgrest.exceptions import APIError
from supabase import AuthApiError, AuthError, Client, create_client

DEFAULT_CATEGORIES = ["Moradia", "Alimentação", "Transporte", "Saúde",
                      "Educação", "Lazer", "Investimentos", "Outros"]
INCOME_CATEGORIES = ["Salário", "Renda extra"]
PAYMENT_METHODS = ["Pix", "Débito", "Crédito", "Dinheiro"]
MONTHS_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
MIN_PASSWORD = 8
ENTRY_COLUMNS = ["id", "type", "date", "description", "category", "method", "amount", "fixed"]
PAGE_SIZE = 1000  # Supabase returns at most 1000 rows per request

st.set_page_config(page_title="Despesas", page_icon="💰", layout="wide")


# ============================================================
# SUPABASE CLIENT (one per browser session, never shared)
# ============================================================
def get_client() -> Client:
    """Each visitor gets their own client, so one person's login is never
    used for another person's requests."""
    if "sb" not in st.session_state:
        try:
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
        except Exception:
            st.error("As chaves do Supabase não foram configuradas. "
                     "Adicione a seção [supabase] com url e key nos secrets do app.")
            st.stop()
        st.session_state.sb = create_client(url, key)
    return st.session_state.sb


sb = get_client()


# ============================================================
# HELPERS
# ============================================================
def brl(value):
    """Formats a number as R$ 1.234,56"""
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {text}" if value < 0 else f"R$ {text}"


def br_date(iso):
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def shift_month(year, month, delta):
    total = year * 12 + (month - 1) + delta
    return total // 12, total % 12 + 1


def to_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False, sheet_name="Lançamentos")
    return buffer.getvalue()


def valid_email(email):
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) is not None


# ============================================================
# AUTH
# ============================================================
AUTH_MESSAGES = {
    "invalid_credentials": "E-mail ou senha incorretos.",
    "email_not_confirmed": "Sua conta ainda não foi verificada.",
    "user_already_exists": "Este e-mail já tem uma conta. Use \"Entrar\".",
    "email_exists": "Este e-mail já tem uma conta. Use \"Entrar\".",
    "otp_expired": "Código inválido ou expirado. Confira o código ou peça um novo.",
    "weak_password": f"Senha fraca. Use pelo menos {MIN_PASSWORD} caracteres.",
    "same_password": "A nova senha precisa ser diferente da anterior.",
    "email_address_invalid": "E-mail inválido.",
    "over_email_send_rate_limit": "Muitos e-mails enviados. Aguarde alguns minutos e tente de novo.",
    "over_request_rate_limit": "Muitas tentativas. Aguarde alguns minutos e tente de novo.",
    "signup_disabled": "A criação de contas está desativada no momento.",
}


def auth_message(err):
    code = getattr(err, "code", None)
    if code in AUTH_MESSAGES:
        return AUTH_MESSAGES[code]
    text = str(getattr(err, "message", err))
    if "Invalid login credentials" in text:
        return AUTH_MESSAGES["invalid_credentials"]
    if "Email not confirmed" in text:
        return AUTH_MESSAGES["email_not_confirmed"]
    if "expired" in text or ("invalid" in text.lower() and "token" in text.lower()):
        return AUTH_MESSAGES["otp_expired"]
    if "security purposes" in text or "rate limit" in text:
        return "Aguarde alguns segundos antes de pedir outro código."
    return f"Não foi possível concluir: {text}"


def is_not_confirmed(err):
    return (getattr(err, "code", None) == "email_not_confirmed"
            or "Email not confirmed" in str(getattr(err, "message", err)))


def go(screen):
    st.session_state.screen = screen
    st.session_state.pop("recovery_ok", None)


def log_in(user):
    meta = user.user_metadata or {}
    st.session_state.user = {
        "id": user.id,
        "email": user.email,
        "name": meta.get("name") or user.email.split("@")[0],
    }
    st.session_state.screen = "app"


def log_out():
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    st.session_state.clear()


def send_signup_code(email):
    try:
        sb.auth.resend({"type": "signup", "email": email})
        return True
    except AuthError as err:
        st.error(auth_message(err))
        return False


def verify_signup_code(email, code):
    """Supabase accepts sign-up codes as type "email" (current) or "signup" (older projects)."""
    try:
        return sb.auth.verify_otp({"email": email, "token": code, "type": "email"})
    except AuthApiError:
        return sb.auth.verify_otp({"email": email, "token": code, "type": "signup"})


def auth_header(subtitle):
    st.markdown("<h1 style='text-align:center'>💰 Despesas</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;opacity:.75'>{subtitle}</p>", unsafe_allow_html=True)


def screen_home():
    auth_header("Controle suas receitas e despesas mês a mês.")
    st.write("")
    st.button("Entrar", type="primary", width="stretch", on_click=go, args=("login",))
    st.button("Criar conta", width="stretch", on_click=go, args=("signup",))


def screen_signup():
    auth_header("Criar conta")
    with st.form("signup"):
        name = st.text_input("Nome")
        email = st.text_input("E-mail")
        password = st.text_input(f"Senha (mínimo {MIN_PASSWORD} caracteres)", type="password")
        confirm = st.text_input("Confirmar senha", type="password")
        submitted = st.form_submit_button("Criar conta", type="primary", width="stretch")
    if submitted:
        email = email.strip().lower()
        if not name.strip():
            st.error("Informe seu nome.")
        elif not valid_email(email):
            st.error("Informe um e-mail válido.")
        elif len(password) < MIN_PASSWORD:
            st.error(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
        elif password != confirm:
            st.error("As senhas não conferem.")
        else:
            try:
                resp = sb.auth.sign_up({"email": email, "password": password,
                                        "options": {"data": {"name": name.strip()}}})
            except AuthError as err:
                st.error(auth_message(err))
            else:
                if resp.user is not None and resp.user.identities == []:
                    # Supabase's answer when the e-mail is already registered
                    st.error(AUTH_MESSAGES["user_already_exists"])
                elif resp.session is not None:
                    # E-mail confirmation is turned off in Supabase: already logged in
                    log_in(resp.user)
                    st.rerun()
                else:
                    st.session_state.pending_email = email
                    st.session_state.notice = f"Enviamos um código de verificação para {email}."
                    go("verify")
                    st.rerun()
    st.button("Já tenho conta", width="stretch", on_click=go, args=("login",))


def screen_verify():
    email = st.session_state.get("pending_email", "")
    auth_header("Verificar e-mail")
    if notice := st.session_state.pop("notice", None):
        st.success(notice)
    st.write(f"Digite o código que enviamos para **{email}**.")
    with st.form("verify"):
        code = st.text_input("Código de verificação", max_chars=10)
        submitted = st.form_submit_button("Confirmar", type="primary", width="stretch")
    if submitted:
        code = re.sub(r"\s", "", code)
        if not code:
            st.error("Digite o código.")
        else:
            try:
                resp = verify_signup_code(email, code)
            except AuthError as err:
                st.error(auth_message(err))
            else:
                log_in(resp.user)
                st.rerun()
    if st.button("Reenviar código", width="stretch") and send_signup_code(email):
        st.success("Código reenviado. Confira também a caixa de spam.")
    st.button("Voltar", width="stretch", on_click=go, args=("home",))


def screen_login():
    auth_header("Entrar")
    with st.form("login"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", type="primary", width="stretch")
    if submitted:
        email = email.strip().lower()
        if not email or not password:
            st.error("Informe e-mail e senha.")
        else:
            try:
                resp = sb.auth.sign_in_with_password({"email": email, "password": password})
            except AuthError as err:
                if is_not_confirmed(err):
                    st.session_state.pending_email = email
                    if send_signup_code(email):
                        st.session_state.notice = (
                            f"Sua conta ainda não foi verificada. Enviamos um novo código para {email}.")
                        go("verify")
                        st.rerun()
                else:
                    st.error(auth_message(err))
            else:
                log_in(resp.user)
                st.rerun()
    st.button("Esqueci minha senha", width="stretch", on_click=go, args=("forgot",))
    st.button("Criar conta", width="stretch", on_click=go, args=("signup",))


def screen_forgot():
    auth_header("Esqueci minha senha")
    st.write("Informe seu e-mail. Vamos enviar um código para você criar uma nova senha.")
    with st.form("forgot"):
        email = st.text_input("E-mail")
        submitted = st.form_submit_button("Enviar código", type="primary", width="stretch")
    if submitted:
        email = email.strip().lower()
        if not valid_email(email):
            st.error("Informe um e-mail válido.")
        else:
            try:
                sb.auth.reset_password_for_email(email)
            except AuthError as err:
                st.error(auth_message(err))
            else:
                st.session_state.pending_email = email
                st.session_state.notice = f"Se houver uma conta com {email}, enviamos um código para lá."
                go("reset")
                st.rerun()
    st.button("Voltar", width="stretch", on_click=go, args=("login",))


def screen_reset():
    email = st.session_state.get("pending_email", "")
    code_ok = st.session_state.get("recovery_ok", False)
    auth_header("Criar nova senha")
    if notice := st.session_state.pop("notice", None):
        st.success(notice)
    with st.form("reset"):
        code = st.text_input("Código recebido por e-mail", max_chars=10, disabled=code_ok,
                             placeholder="Código já confirmado" if code_ok else "")
        password = st.text_input(f"Nova senha (mínimo {MIN_PASSWORD} caracteres)", type="password")
        confirm = st.text_input("Confirmar nova senha", type="password")
        submitted = st.form_submit_button("Salvar nova senha", type="primary", width="stretch")
    if submitted:
        code = re.sub(r"\s", "", code or "")
        if not code_ok and not code:
            st.error("Digite o código.")
        elif len(password) < MIN_PASSWORD:
            st.error(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
        elif password != confirm:
            st.error("As senhas não conferem.")
        else:
            try:
                if not code_ok:
                    sb.auth.verify_otp({"email": email, "token": code, "type": "recovery"})
                    st.session_state.recovery_ok = True
                resp = sb.auth.update_user({"password": password})
            except AuthError as err:
                st.error(auth_message(err))
            else:
                log_in(resp.user)
                st.session_state.welcome = "Senha alterada com sucesso!"
                st.rerun()
    if not code_ok and st.button("Reenviar código", width="stretch"):
        try:
            sb.auth.reset_password_for_email(email)
            st.success("Código reenviado. Confira também a caixa de spam.")
        except AuthError as err:
            st.error(auth_message(err))
    if code_ok:
        st.button("Cancelar", width="stretch", on_click=log_out)
    else:
        st.button("Voltar", width="stretch", on_click=go, args=("login",))


AUTH_SCREENS = {"home": screen_home, "signup": screen_signup, "verify": screen_verify,
                "login": screen_login, "forgot": screen_forgot, "reset": screen_reset}

if "user" not in st.session_state:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        AUTH_SCREENS.get(st.session_state.get("screen", "home"), screen_home)()
    st.stop()

user = st.session_state.user
uid = user["id"]


# ============================================================
# DATABASE (Supabase; RLS guarantees each user only sees their own rows)
# ============================================================
def get_categories():
    rows = sb.table("categories").select("name").order("id").execute().data
    if not rows:
        sb.table("categories").upsert(
            [{"user_id": uid, "name": c} for c in DEFAULT_CATEGORIES],
            on_conflict="user_id,name", ignore_duplicates=True).execute()
        return DEFAULT_CATEGORIES.copy()
    return [r["name"] for r in rows]


def add_category(name):
    sb.table("categories").upsert({"user_id": uid, "name": name},
                                  on_conflict="user_id,name", ignore_duplicates=True).execute()


def remove_category(name):
    sb.table("categories").delete().eq("user_id", uid).eq("name", name).execute()
    sb.table("budgets").delete().eq("user_id", uid).eq("category", name).execute()


def get_budgets():
    rows = sb.table("budgets").select("category, amount").execute().data
    return {r["category"]: float(r["amount"]) for r in rows}


def save_budgets(values):
    sb.table("budgets").delete().eq("user_id", uid).execute()
    rows = [{"user_id": uid, "category": c, "amount": v} for c, v in values.items() if v > 0]
    if rows:
        sb.table("budgets").insert(rows).execute()


def entry_payload(entry_date, desc, category, method, amount, fixed):
    return {"date": entry_date.isoformat(), "description": desc, "category": category,
            "method": method, "amount": round(float(amount), 2), "fixed": bool(fixed)}


def add_entry(entry_type, entry_date, desc, category, method, amount, fixed):
    payload = entry_payload(entry_date, desc, category, method, amount, fixed)
    sb.table("entries").insert({"user_id": uid, "type": entry_type, **payload}).execute()


def update_entry(entry_id, entry_date, desc, category, method, amount, fixed):
    payload = entry_payload(entry_date, desc, category, method, amount, fixed)
    sb.table("entries").update(payload).eq("id", entry_id).execute()


def delete_entry(entry_id):
    sb.table("entries").delete().eq("id", entry_id).execute()


def fetch_entries(start, end):
    """Entries dated in [start, end) plus every fixed entry dated before end."""
    rows, offset = [], 0
    while True:
        page = (sb.table("entries").select(",".join(ENTRY_COLUMNS))
                .lt("date", end.isoformat())
                .or_(f"date.gte.{start.isoformat()},fixed.is.true")
                .order("date").order("id")
                .range(offset, offset + PAGE_SIZE - 1).execute().data)
        rows += page
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    df = pd.DataFrame(rows, columns=ENTRY_COLUMNS)
    df["amount"] = df["amount"].astype(float)
    df["fixed"] = df["fixed"].astype(bool).astype(int)
    df["description"] = df["description"].fillna("")
    return df


def entries_for_month(all_entries, year, month):
    """Entries of the month + fixed entries from earlier months (repeat automatically)."""
    ym = f"{year:04d}-{month:02d}"
    start = f"{ym}-01"
    end = "%04d-%02d-01" % shift_month(year, month, 1)
    df = all_entries
    current = df[(df["date"] >= start) & (df["date"] < end)].copy()
    current["repeated"] = False
    current["orig_date"] = current["date"]

    fixed = df[(df["fixed"] == 1) & (df["date"] < start)].copy()
    fixed["repeated"] = True
    fixed["orig_date"] = fixed["date"]
    if not fixed.empty:
        last_day = monthrange(year, month)[1]
        fixed["date"] = fixed["date"].map(lambda d: f"{ym}-{min(int(d[8:10]), last_day):02d}")

    result = pd.concat([current, fixed], ignore_index=True)
    return result.sort_values(["date", "id"]).reset_index(drop=True)


# ============================================================
# PAGE SETUP + SIDEBAR
# ============================================================
today = date.today()
if "year" not in st.session_state:
    st.session_state.year, st.session_state.month = today.year, today.month


def go_to_month(delta):
    st.session_state.year, st.session_state.month = shift_month(
        st.session_state.year, st.session_state.month, delta)


with st.sidebar:
    st.markdown(f"### 👤 {user['name']}")
    st.caption(user["email"])
    st.button("Sair", on_click=log_out, width="stretch")
    st.divider()

    st.header("📅 Mês")
    col_prev, col_label, col_next = st.columns([1, 2, 1])
    col_prev.button("◀", on_click=go_to_month, args=(-1,), width="stretch")
    col_next.button("▶", on_click=go_to_month, args=(1,), width="stretch")
    col_label.markdown(
        f"<div style='text-align:center;font-weight:600;padding-top:6px'>"
        f"{MONTHS_PT[st.session_state.month - 1]}/{st.session_state.year}</div>",
        unsafe_allow_html=True)
    if st.button("Ir para o mês atual", width="stretch"):
        st.session_state.year, st.session_state.month = today.year, today.month
        st.rerun()

year, month = st.session_state.year, st.session_state.month
month_label = f"{MONTHS_PT[month - 1]}/{year}"

try:
    history_start = date(*shift_month(year, month, -11), 1)
    history_end = date(*shift_month(year, month, 1), 1)
    all_entries = fetch_entries(history_start, history_end)
    categories = get_categories()
    budgets = get_budgets()
except APIError as err:
    if "JWT" in str(err) or getattr(err, "code", "") in ("PGRST301", "PGRST303"):
        # Session expired: send the person back to the login screen
        log_out()
        st.session_state.screen = "login"
        st.rerun()
    raise

df_month = entries_for_month(all_entries, year, month)

if welcome := st.session_state.pop("welcome", None):
    st.success(welcome)

with st.sidebar:
    st.divider()
    st.header("⬇️ Exportar")
    if df_month.empty:
        st.caption("Nenhum lançamento neste mês.")
    else:
        export = df_month.rename(columns={
            "type": "Tipo", "date": "Data", "description": "Descrição", "category": "Categoria",
            "method": "Forma de pagamento", "amount": "Valor", "fixed": "Fixo",
            "repeated": "Repetido"}).drop(columns=["id", "orig_date"])
        export["Data"] = export["Data"].map(br_date)
        export["Fixo"] = export["Fixo"].map({1: "Sim", 0: "Não"})
        export["Repetido"] = export["Repetido"].map({True: "Sim", False: "Não"})
        st.download_button("Baixar Excel do mês", to_excel(export),
                           file_name=f"despesas_{year}-{month:02d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")

    st.divider()
    st.header("🏷️ Categorias")
    with st.form("new_category", clear_on_submit=True):
        new_cat = st.text_input("Nova categoria")
        if st.form_submit_button("Adicionar") and new_cat.strip():
            add_category(new_cat.strip())
            st.rerun()
    to_remove = st.selectbox("Remover categoria", ["—"] + categories)
    if st.button("Remover", disabled=to_remove == "—"):
        remove_category(to_remove)
        st.rerun()

# ============================================================
# SUMMARY
# ============================================================
st.title(f"💰 Despesas — {month_label}")

expenses = df_month[df_month["type"] == "Despesa"]
incomes = df_month[df_month["type"] == "Receita"]
total_exp = float(expenses["amount"].sum())
total_inc = float(incomes["amount"].sum())
balance = total_inc - total_exp

m1, m2, m3, m4 = st.columns(4)
m1.metric("Receitas", brl(total_inc))
m2.metric("Despesas", brl(total_exp))
m3.metric("Saldo", brl(balance))
m4.metric("Comprometido da renda", f"{total_exp / total_inc * 100:.0f}%" if total_inc else "—")

tab_new, tab_list, tab_charts, tab_budget = st.tabs(
    ["➕ Novo lançamento", "📋 Lançamentos", "📊 Gráficos", "🎯 Orçamento"])

# ============================================================
# NEW ENTRY
# ============================================================
with tab_new:
    entry_type = st.radio("Tipo", ["Despesa", "Receita"], horizontal=True)
    cat_options = categories if entry_type == "Despesa" else INCOME_CATEGORIES
    default_day = today if (today.year, today.month) == (year, month) else date(year, month, 1)
    with st.form("new_entry", clear_on_submit=True):
        c1, c2 = st.columns(2)
        entry_date = c1.date_input("Data", value=default_day, format="DD/MM/YYYY")
        amount = c2.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
        desc = st.text_input("Descrição")
        c3, c4 = st.columns(2)
        category = c3.selectbox("Categoria", cat_options)
        method = c4.selectbox("Forma de pagamento", PAYMENT_METHODS)
        fixed = st.checkbox("Fixo (repete todo mês)")
        if st.form_submit_button("Salvar", type="primary"):
            if amount <= 0:
                st.error("Informe um valor maior que zero.")
            elif not category:
                st.error("Crie uma categoria na barra lateral antes de lançar.")
            else:
                add_entry(entry_type, entry_date, desc.strip(), category, method, amount, fixed)
                st.success("Lançamento salvo!")
                st.rerun()

# ============================================================
# ENTRY LIST + EDIT / DELETE
# ============================================================
with tab_list:
    if df_month.empty:
        st.info("Nenhum lançamento neste mês.")
    else:
        filter_type = st.radio("Mostrar", ["Todos", "Despesa", "Receita"], horizontal=True)
        view = df_month if filter_type == "Todos" else df_month[df_month["type"] == filter_type]
        table = pd.DataFrame({
            "Data": view["date"].map(br_date),
            "Tipo": view["type"],
            "Descrição": view["description"],
            "Categoria": view["category"],
            "Pagamento": view["method"],
            "Valor": view["amount"].map(brl),
            "Fixo": view.apply(lambda r: "🔁 repetido" if r["repeated"]
                               else ("📌 sim" if r["fixed"] else ""), axis=1),
        })
        st.dataframe(table, hide_index=True, width="stretch")

        st.subheader("Editar ou excluir")
        originals = df_month.drop_duplicates("id").set_index("id")
        chosen = st.selectbox(
            "Lançamento", originals.index,
            format_func=lambda i: (f"{br_date(originals.at[i, 'date'])} · {originals.at[i, 'type']} · "
                                   f"{originals.at[i, 'description'] or originals.at[i, 'category']} · "
                                   f"{brl(originals.at[i, 'amount'])}"))
        row = originals.loc[chosen]
        if bool(row["repeated"]):
            st.caption(f"Lançamento fixo criado em {br_date(row['orig_date'])}: "
                       "alterações valem para todos os meses.")
        edit_cats = categories if row["type"] == "Despesa" else INCOME_CATEGORIES
        if row["category"] not in edit_cats:
            edit_cats = edit_cats + [row["category"]]
        with st.form(f"edit_{chosen}"):
            c1, c2 = st.columns(2)
            e_date = c1.date_input("Data", value=date.fromisoformat(row["orig_date"]),
                                   format="DD/MM/YYYY")
            e_amount = c2.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f",
                                       value=float(row["amount"]))
            e_desc = st.text_input("Descrição", value=row["description"] or "")
            c3, c4 = st.columns(2)
            e_cat = c3.selectbox("Categoria", edit_cats, index=edit_cats.index(row["category"]))
            e_method = c4.selectbox("Forma de pagamento", PAYMENT_METHODS,
                                    index=PAYMENT_METHODS.index(row["method"])
                                    if row["method"] in PAYMENT_METHODS else 0)
            e_fixed = st.checkbox("Fixo (repete todo mês)", value=bool(row["fixed"]))
            b1, b2 = st.columns(2)
            if b1.form_submit_button("Salvar alterações", type="primary"):
                if e_amount <= 0:
                    st.error("Informe um valor maior que zero.")
                else:
                    update_entry(int(chosen), e_date, e_desc.strip(), e_cat, e_method, e_amount, e_fixed)
                    st.rerun()
            if b2.form_submit_button("Excluir"):
                delete_entry(int(chosen))
                st.rerun()

# ============================================================
# CHARTS
# ============================================================
with tab_charts:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Despesas por categoria")
        if expenses.empty:
            st.info("Sem despesas neste mês.")
        else:
            by_cat = expenses.groupby("category", as_index=False)["amount"].sum()
            fig = px.pie(by_cat, names="category", values="amount", hole=0.45)
            fig.update_traces(textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, width="stretch")
    with col_b:
        st.subheader("Por forma de pagamento")
        if expenses.empty:
            st.info("Sem despesas neste mês.")
        else:
            by_method = expenses.groupby("method", as_index=False)["amount"].sum()
            fig = px.bar(by_method, x="method", y="amount",
                         labels={"method": "", "amount": "R$"})
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, width="stretch")

    st.subheader("Últimos 12 meses")
    history = []
    for delta in range(-11, 1):
        y, m = shift_month(year, month, delta)
        d = entries_for_month(all_entries, y, m)
        label = f"{MONTHS_PT[m - 1]}/{str(y)[2:]}"
        for kind in ("Receita", "Despesa"):
            history.append({"Mês": label, "Tipo": kind,
                            "Valor": float(d.loc[d["type"] == kind, "amount"].sum())})
    fig = px.bar(pd.DataFrame(history), x="Mês", y="Valor", color="Tipo", barmode="group",
                 color_discrete_map={"Receita": "#2e9e5b", "Despesa": "#d64545"},
                 labels={"Valor": "R$", "Mês": ""})
    fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")

# ============================================================
# BUDGET
# ============================================================
with tab_budget:
    st.caption("Defina um limite mensal por categoria (0 = sem limite).")
    spent = expenses.groupby("category")["amount"].sum()
    for cat in categories:
        limit = budgets.get(cat, 0.0)
        value = float(spent.get(cat, 0.0))
        if limit:
            ratio = value / limit
            icon = "🔴" if ratio > 1 else ("🟡" if ratio >= 0.8 else "🟢")
            st.write(f"{icon} **{cat}** — {brl(value)} de {brl(limit)} ({ratio * 100:.0f}%)")
            st.progress(min(ratio, 1.0))
        elif value:
            st.write(f"⚪ **{cat}** — {brl(value)} (sem limite)")

    with st.form("budgets"):
        new_budgets = {}
        cols = st.columns(2)
        for i, cat in enumerate(categories):
            new_budgets[cat] = cols[i % 2].number_input(
                cat, min_value=0.0, step=50.0, format="%.2f",
                value=float(budgets.get(cat, 0.0)), key=f"budget_{cat}")
        if st.form_submit_button("Salvar orçamento", type="primary"):
            save_budgets(new_budgets)
            st.rerun()
