# Instruções de desenvolvimento

## Contexto e stack

API Django de um aplicativo mobile de organização pessoal com gamificação:
tarefas, hábitos, registro de conclusões, XP, níveis e acompanhamento da evolução.
O frontend futuro será React Native; o foco atual é exclusivamente a API.

- Python 3.13.5 no ambiente local inspecionado; Django exige Python >= 3.12.
- Django 6.0.1 e Django REST Framework 3.16.1, conforme `requirements.txt`.
- Banco atual: SQLite (`db.sqlite3`).
- Autenticação da API: SimpleJWT 5.5.1, login por username, access de 5 minutos,
  refresh de 1 dia e `Authorization: Bearer <access>`. Login em `/accounts/login/`
  e refresh em `/accounts/token/refresh/`; sem rotação automática.
  Logout em `/accounts/logout/` exige JWT e revoga somente o refresh do usuário
  autenticado pela blacklist oficial. Logout não invalida access tokens;
  não implementar revogação individual de access tokens.
  O admin mantém sessões Django; a API usa somente JWTAuthentication.
  `CHECK_REVOKE_TOKEN=True`: alterar a senha invalida a autenticação dos access
  anteriores. Como o refresh do SimpleJWT 5.5.1 não aplica essa checagem sozinho,
  `RefreshSerializer` usa `JWTAuthentication.get_user()` para aplicar a mesma
  proteção oficial antes de emitir access. Não criar mecanismo próprio de revogação.
  Tokens sem a claim oficial de revogação exigem novo login. Mudanças nessa
  política exigem decisão explícita e testes.

## Arquitetura

- `accounts.User` é o User model oficial, baseado em AbstractUser.
- Nunca importar `django.contrib.auth.models.User`. Em código Python, usar
  `get_user_model()` quando apropriado; em relacionamentos, `settings.AUTH_USER_MODEL`.
- Separar autenticação de gamificação. Não adicionar XP, level, streaks, atributos
  ou informações similares diretamente ao User sem decisão arquitetural explícita.
- Não espalhar regras de negócio importantes pelas views. Evitar abstrações
  prematuras e arquitetura excessivamente complexa.

## API e segurança

- Usar DRF, códigos HTTP apropriados e serializers para validar payloads quando
  apropriado. Erros esperados de entrada nunca devem resultar em HTTP 500.
- Serializers de entrada de accounts rejeitam campos extras e campos somente
  de leitura com HTTP 400; preservar essa convenção nos contratos existentes.
- Nunca confiar em campos sensíveis enviados pelo cliente. Cadastro público nunca
  pode definir is_staff, is_superuser, grupos ou permissões.
- Endpoints privados devem exigir autenticação explicitamente. Um usuário nunca
  pode acessar ou alterar recursos pertencentes a outro usuário.
- Nunca retornar senhas nem seus hashes. Armazenar senhas apenas pelos mecanismos
  seguros do Django e aplicar seus password validators nos fluxos de definição de senha.
- Não adicionar segredos diretamente ao código, nem credenciais, tokens ou dados
  sensíveis ao repositório. Dados sintéticos de teste não devem ser credenciais reais.
- Configurações de ambiente usam `os.environ`, sem carregamento automático de arquivo.
  `DJANGO_SECRET_KEY` é obrigatória; usar `.env.local` ignorado pelo Git no desenvolvimento,
  conforme README.md. Preservar o virtualenv `../.env`; nunca usá-lo como arquivo dotenv.

## Testes

- Novas regras de negócio devem possuir testes; bugs corrigidos devem receber
  testes de regressão sempre que possível. Executar testes específicos quando necessário.
- Antes de finalizar qualquer task, executar no mínimo:

  ```bash
  python manage.py check
  python manage.py test
  ```

- Quando houver mudanças em models, executar também:

  ```bash
  python manage.py makemigrations --check
  ```

- O ambiente virtual local existente está em `../.env`; ativá-lo ou utilizar seu Python.
- Antes dos comandos Django locais, exportar `.env.local` com `set -a`,
  `source .env.local`, `set +a`. Usar `DJANGO_DEBUG=true` para testes HTTP locais.

## Escopo e entrega

- Não implementar funcionalidades não solicitadas nem realizar grandes refatorações
  sem necessidade. Preservar o comportamento fora do escopo e preferir alterações
  pequenas e revisáveis.
- Registrar melhorias fora do escopo como pendências, sem implementá-las automaticamente.
- Ao finalizar, informar: arquivos criados/modificados, comportamento implementado,
  testes executados e resultados, decisões relevantes e pendências encontradas.
