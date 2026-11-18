"""
Monthly expense tracker (Streamlit)
Run locally:  pip install -r requirements.txt
              streamlit run app.py
"""

import sqlite3
from datetime import date
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

DB_FILE = "expenses.db"
DEFAULT_CATEGORIES = ["Moradia", "Alimentação", "Transporte", "Saúde",
                      "Educação", "Lazer", "Investimentos", "Outros"]
INCOME_CATEGORIES = ["Salário", "Renda extra"]
PAYMENT_METHODS = ["Pix", "Débito", "Crédito", "Dinheiro"]
MONTHS_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


# ============================================================
# DATABASE
# ============================================================
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, date TEXT, description TEXT, category TEXT,
        method TEXT, amount REAL, fixed INTEGER DEFAULT 0)""")
    conn.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS budgets (category TEXT PRIMARY KEY, amount REAL)")
    if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
        conn.executemany("INSERT INTO categories VALUES (?)", [(c,) for c in DEFAULT_CATEGORIES])
    conn.commit()
    return conn


conn = get_conn()


def get_categories():
    return [r[0] for r in conn.execute("SELECT name FROM categories ORDER BY rowid")]


def get_budgets():
    return dict(conn.execute("SELECT category, amount FROM budgets").fetchall())


def add_entry(entry_type, entry_date, desc, category, method, amount, fixed):
    conn.execute("""INSERT INTO entries (type, date, description, category, method, amount, fixed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                 (entry_type, entry_date.isoformat(), desc, category, method, amount, int(fixed)))
    conn.commit()


def update_entry(entry_id, entry_date, desc, category, method, amount, fixed):
    conn.execute("""UPDATE entries SET date=?, description=?, category=?, method=?, amount=?, fixed=?
                    WHERE id=?""",
                 (entry_date.isoformat(), desc, category, method, amount, int(fixed), entry_id))
    conn.commit()


def delete_entry(entry_id):
    conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    conn.commit()


def entries_for_month(year, month):
    """Entries of the month + fixed entries from earlier months (repeat automatically)."""
    ym = f"{year:04d}-{month:02d}"
    df = pd.read_sql("SELECT * FROM entries", conn)
    if df.empty:
        return df.assign(repeated=False)

    df["ym"] = df["date"].str[:7]
    current = df[df["ym"] == ym].copy()
    current["repeated"] = False

    fixed = df[(df["fixed"] == 1) & (df["ym"] < ym)].copy()
    if not fixed.empty:
        fixed["date"] = ym + "-" + fixed["date"].str[8:10]
        fixed["repeated"] = True

    result = pd.concat([current, fixed], ignore_index=True)
    return result.sort_values("date").drop(columns="ym")


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


# ============================================================
# PAGE SETUP + SIDEBAR
# ===================================================
st.set_page_config(page_title="Despesas", page_icon="💰", layout="wide")

today = date.today()
if "year" not in st.session_state:
    st.session_state.year, st.session_state.month = today.year, today.month


def go_to_month(delta):
    st.session_state.year, st.session_state.month = shift_month(
        st.session_state.year, st.session_state.month, delta)


with st.sidebar:
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
df_month = entries_for_month(year, month)
categories = get_categories()
budgets = get_budgets()

with st.sidebar:
    st.divider()
    st.header("⬇️ Exportar")
    if df_month.empty:
        st.caption("Nenhum lançamento neste mês.")
    else:
        export = df_month.rename(columns={
            "type": "Tipo", "date": "Data", "description": "Descrição", "category": "Categoria",
            "method": "Forma de pagamento", "amount": "Valor", "fixed": "Fixo",
            "repeated": "Repetido"}).drop(columns="id")
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
            conn.execute("INSERT OR IGNORE INTO categories VALUES (?)", (new_cat.strip(),))
            conn.commit()
            st.rerun()
    to_remove = st.selectbox("Remover categoria", ["—"] + categories)
    if st.button("Remover", disabled=to_remove == "—"):
        conn.execute("DELETE FROM categories WHERE name=?", (to_remove,))
        conn.execute("DELETE FROM budgets WHERE category=?", (to_remove,))
        conn.commit()
        st.rerun()

# ============================================================
# SUMMARY
# ============================================================
st.title(f"💰 Despesas — {month_label}")

expenses = df_month[df_month["type"] == "Despesa"] if not df_month.empty else df_month
incomes = df_month[df_month["type"] == "Receita"] if not df_month.empty else df_month
total_exp = float(expenses["amount"].sum()) if not expenses.empty else 0.0
total_inc = float(incomes["amount"].sum()) if not incomes.empty else 0.0
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
        row = pd.read_sql("SELECT * FROM entries WHERE id=?", conn, params=(int(chosen),)).iloc[0]
        if bool(originals.at[chosen, "repeated"]):
            st.caption(f"Lançamento fixo criado em {br_date(row['date'])}: "
                       "alterações valem para todos os meses.")
        edit_cats = categories if row["type"] == "Despesa" else INCOME_CATEGORIES
        if row["category"] not in edit_cats:
            edit_cats = edit_cats + [row["category"]]
        with st.form(f"edit_{chosen}"):
            c1, c2 = st.columns(2)
            e_date = c1.date_input("Data", value=date.fromisoformat(row["date"]), format="DD/MM/YYYY")
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
        d = entries_for_month(y, m)
        label = f"{MONTHS_PT[m - 1]}/{str(y)[2:]}"
        for kind in ("Receita", "Despesa"):
            total = float(d.loc[d["type"] == kind, "amount"].sum()) if not d.empty else 0.0
            history.append({"Mês": label, "Tipo": kind, "Valor": total})
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
    spent = expenses.groupby("category")["amount"].sum() if not expenses.empty else pd.Series(dtype=float)
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
            conn.execute("DELETE FROM budgets")
            conn.executemany("INSERT INTO budgets VALUES (?, ?)",
                             [(c, v) for c, v in new_budgets.items() if v > 0])
            conn.commit()
            st.rerun()
