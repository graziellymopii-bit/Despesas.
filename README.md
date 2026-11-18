# Despesas.

Controle financeiro mensal feito com [Streamlit](https://streamlit.io).

## Funcionalidades

- Lançamento de **despesas** e **receitas** (data, descrição, categoria, forma de pagamento, valor)
- Lançamentos **fixos** que se repetem automaticamente nos meses seguintes
- Navegação mês a mês com resumo: receitas, despesas, saldo e % da renda comprometida
- Edição e exclusão de lançamentos
- Gráficos: despesas por categoria, por forma de pagamento e histórico dos últimos 12 meses
- **Orçamento** mensal por categoria, com alerta ao chegar em 80% e ao estourar
- Categorias personalizáveis
- Exportação do mês para **Excel**

Os dados ficam em um banco SQLite local (`expenses.db`).

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```
