# Licenciamento Server-Side

## O que entrou

- Trial local de 30 dias no desktop continua existindo.
- Backend Django agora registra dispositivo, trial, licenca e eventos de pagamento.
- Desktop passa a preferir o backend server-side quando `LICENSE_API_BASE` estiver configurado.
- Checkout do Mercado Pago pode ser criado pelo backend.
- Webhook do Mercado Pago pode ativar automaticamente a instancia paga.

## Endpoints novos

- `POST /api/public/license/status/`
- `POST /api/public/license/checkout/`
- `POST /api/public/payments/mercadopago/webhook/`

## Payload esperado do desktop

O desktop envia automaticamente:

- `device_id`
- `install_id`
- `license_key`
- `app_name`
- `app_version`
- `hostname`
- `platform`

## Variaveis de ambiente principais

No `.env` da raiz:

```env
LICENSE_REQUIRED=1
LICENSE_TRIAL_DAYS=30
LICENSE_API_BASE=http://127.0.0.1:8000
LICENSE_API_TIMEOUT_SEC=8
LICENSE_API_VERIFY_SSL=1
LICENSE_PAYMENT_URL=
LICENSE_PLAN_CODE=pro-monthly
LICENSE_PRODUCT_NAME=Zebra Hunter Quantum Pro
LICENSE_PRICE_BRL=29.00
LICENSE_BILLING_DAYS=30
LICENSE_MAX_DEVICES=1
LICENSE_CURRENCY=BRL

DJANGO_PUBLIC_BASE_URL=https://seudominio.com

MERCADO_PAGO_ACCESS_TOKEN=
MERCADO_PAGO_WEBHOOK_TOKEN=
MERCADO_PAGO_SUCCESS_URL=
MERCADO_PAGO_PENDING_URL=
MERCADO_PAGO_FAILURE_URL=
```

## Fluxo

1. Sem `LICENSE_KEY`, o desktop consulta `license/status`.
2. O backend cria ou continua o trial por dispositivo.
3. Quando o trial expira, o desktop chama `license/checkout` e abre o checkout.
4. O Mercado Pago chama o webhook.
5. O webhook consulta o pagamento, ativa a licenca e vincula o dispositivo.
6. O desktop revalida e passa a receber `status=active` mesmo sem chave manual, desde que o dispositivo ja esteja vinculado.

## Comandos locais

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver
```

Desktop em modo dev:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH=".;src"
python tools\desktop_app_pro.py
```

## Observacoes

- Sem `MERCADO_PAGO_ACCESS_TOKEN`, o backend usa `LICENSE_PAYMENT_URL` como fallback.
- O webhook usa `MERCADO_PAGO_WEBHOOK_TOKEN` como protecao simples via query string/header.
- Para producao publica, o ideal e publicar o Django sob HTTPS e preencher `DJANGO_PUBLIC_BASE_URL`.
