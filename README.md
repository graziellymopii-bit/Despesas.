# Despesas.

Controle financeiro mensal feito com [Streamlit](https://streamlit.io) e
[Supabase](https://supabase.com), com conta individual para cada pessoa.

## Funcionalidades

**Contas de usuário**
- Criar conta com nome, e-mail e senha (mínimo 8 caracteres)
- Verificação do e-mail por **código** (com botão "Reenviar código")
- Entrar com e-mail e senha; se a conta não foi verificada, o app pede o código de novo
- "Esqueci minha senha" com código por e-mail
- Botão "Sair" na barra lateral, mostrando o nome de quem está logado

**Controle financeiro**
- Lançamento de **despesas** e **receitas** (data, descrição, categoria, forma de pagamento, valor)
- Lançamentos **fixos** que se repetem automaticamente nos meses seguintes
- Navegação mês a mês com resumo: receitas, despesas, saldo e % da renda comprometida
- Edição e exclusão de lançamentos
- Gráficos: despesas por categoria, por forma de pagamento e histórico dos últimos 12 meses
- **Orçamento** mensal por categoria, com alerta ao chegar em 80% e ao estourar
- Categorias personalizáveis
- Exportação do mês para **Excel**

## Privacidade

Cada lançamento, categoria e orçamento é gravado com o `user_id` de quem criou.
O banco usa **Row Level Security (RLS)**: o próprio Postgres só deixa cada pessoa ver,
editar e apagar as próprias linhas, mesmo que alguém altere o código do app ou chame a
API do Supabase diretamente. As chaves ficam no `st.secrets`, nunca no código.

## Configuração

O passo a passo completo (feito para o celular) está em **[SUPABASE_SETUP.md](SUPABASE_SETUP.md)**:

1. Criar o projeto no Supabase
2. Rodar [`supabase/schema.sql`](supabase/schema.sql) no SQL Editor
3. Ativar a verificação de e-mail com código
4. Colocar `url` e `key` nos Secrets do Streamlit Cloud

## Rodar no computador

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # e preencha as chaves
streamlit run app.py
```
