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
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


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
