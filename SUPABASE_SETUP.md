# Passo a passo: Supabase + Streamlit (pelo celular)

São 6 etapas. Dá para fazer tudo pelo navegador do celular (Chrome ou Safari).
Dica: se alguma tela do Supabase ficar apertada, use a opção **"Versão para computador"**
do navegador.

---

## 1. Criar a conta e o projeto no Supabase

1. Abra **supabase.com** e toque em **Start your project**.
2. Entre com sua conta do **GitHub** (é o mais rápido).
3. Toque em **New project**.
4. Preencha:
   - **Name:** `despesas`
   - **Database Password:** toque em **Generate a password** e guarde essa senha
     (o app não usa essa senha, mas é bom ter).
   - **Region:** escolha **South America (São Paulo)**.
5. Toque em **Create new project** e espere 1 ou 2 minutos até o projeto ficar pronto.

---

## 2. Criar as tabelas (rodar o SQL)

1. Em outra aba, abra o arquivo
   **github.com/graziellymopii-bit/Despesas./blob/main/supabase/schema.sql**.
2. Toque no ícone de **copiar** (dois quadradinhos, "Copy raw file") no topo do arquivo.
3. Volte ao Supabase. No menu (☰), toque em **SQL Editor**.
4. Toque em **New query** (ou no **+**), apague o que estiver escrito e **cole** o SQL.
5. Toque em **Run**. Deve aparecer **"Success. No rows returned"**.
6. Para conferir: menu (☰) → **Table Editor**. Devem aparecer as tabelas
   `entries`, `categories` e `budgets`, cada uma com a etiqueta **RLS enabled**.

> Pode rodar o SQL de novo sem problema: ele não apaga nada.

---

## 3. Ativar a verificação de e-mail com código

### 3.1 Exigir confirmação e senha mínima
1. Menu (☰) → **Authentication** → **Sign In / Providers** (em alguns projetos aparece
   como **Providers**).
2. Toque em **Email** e confira:
   - **Enable Email provider:** ligado
   - **Confirm email:** **ligado** (é isso que obriga o código)
   - **Minimum password length:** `8`
3. Toque em **Save**.

### 3.2 Trocar o link do e-mail por um código
Por padrão o Supabase manda um **link**. O app usa **código**, então é preciso trocar
o texto dos e-mails.

1. Menu (☰) → **Authentication** → **Emails** (em alguns projetos: **Email Templates**).
2. Abra o modelo **Confirm signup**.
   - **Subject:** `Seu código de verificação`
   - **Body:** apague tudo e cole:
     ```html
     <h2>Bem-vindo(a) ao Despesas!</h2>
     <p>Seu código de verificação é:</p>
     <h1>{{ .Token }}</h1>
     <p>Digite esse código no app para ativar sua conta.</p>
     ```
   - Toque em **Save**.
3. Abra o modelo **Reset Password**.
   - **Subject:** `Código para criar nova senha`
   - **Body:** apague tudo e cole:
     ```html
     <h2>Criar nova senha</h2>
     <p>Seu código é:</p>
     <h1>{{ .Token }}</h1>
     <p>Se não foi você que pediu, ignore este e-mail.</p>
     ```
   - Toque em **Save**.

> O `{{ .Token }}` é onde o Supabase coloca o código. Não mude essa parte.

### 3.3 (Importante se outras pessoas forem usar) Configurar envio de e-mail
O envio de e-mail que já vem no Supabase é só para testes: ele manda **poucos e-mails por hora**
e, em projetos novos, **só para e-mails da sua equipe no Supabase**. Para você mesma testar,
ele basta. Para outras pessoas criarem conta, configure um serviço de e-mail gratuito,
como o **Brevo** (300 e-mails por dia grátis):

1. Crie uma conta em **brevo.com** e confirme o e-mail que vai aparecer como remetente.
2. No Brevo: menu do seu perfil → **SMTP & API** → aba **SMTP**. Anote o **Login** e
   toque em **Generate a new SMTP key** (anote a chave).
3. No Supabase: **Authentication** → **Emails** → aba **SMTP Settings** →
   ligue **Enable Custom SMTP** e preencha:
   - **Sender email:** o e-mail que você confirmou no Brevo
   - **Sender name:** `Despesas`
   - **Host:** `smtp-relay.brevo.com`
   - **Port:** `587`
   - **Username:** o Login do Brevo
   - **Password:** a SMTP key do Brevo
4. Toque em **Save**.

---

## 4. Pegar as chaves do Supabase

1. No Supabase, abra o projeto e toque no botão **Connect** no topo
   (ou menu ☰ → **Project Settings** → **API Keys** / **Data API**).
2. Copie e guarde:
   - **Project URL**: algo como `https://abcdefgh.supabase.co`
   - **Publishable key** (começa com `sb_publishable_...`).
     Se seu projeto mostrar só as chaves antigas, use a **anon public**.

> ⚠️ **Nunca** use a chave **secret** / **service_role**. Ela passa por cima do RLS e
> daria acesso aos dados de todo mundo.

---

## 5. Colocar as chaves no Streamlit Cloud

1. Abra **share.streamlit.io** e entre na sua conta.
2. No seu app, toque nos **⋮** → **Settings** → **Secrets**.
   (Se ainda não publicou: **Create app**, escolha o repositório, a branch `main` e o
   arquivo `app.py`, toque em **Advanced settings** e use o campo **Secrets** de lá.)
3. Cole, trocando pelos seus valores:
   ```toml
   [supabase]
   url = "https://abcdefgh.supabase.co"
   key = "sb_publishable_xxxxxxxxxxxxxxxx"
   ```
4. Toque em **Save**. O app reinicia sozinho em alguns segundos.

---

## 6. Testar

1. Abra o app e toque em **Criar conta**.
2. Preencha nome, e-mail e senha (8 caracteres ou mais) e toque em **Criar conta**.
3. Veja o e-mail (confira o **spam**) e digite o código no app.
4. Pronto: você está dentro. Lance uma despesa para conferir.
5. Para ver se os dados chegaram: Supabase → **Table Editor** → `entries`.

### Se algo der errado
| O que aparece | O que fazer |
|---|---|
| "As chaves do Supabase não foram configuradas" | Revise a etapa 5 (o texto precisa ter `[supabase]`, `url` e `key`). |
| O e-mail chega com um **link** em vez de código | Revise a etapa 3.2. |
| O e-mail não chega | Olhe o spam. Se for outra pessoa, faça a etapa 3.3. |
| "Muitos e-mails enviados" | Limite do e-mail de teste do Supabase: faça a etapa 3.3 ou espere 1 hora. |
| Erro dizendo que a tabela não existe | Rode o SQL de novo (etapa 2). |
