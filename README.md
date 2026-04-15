# ðŸ¦“ Zebra Hunter â€” projeto completo (2010 â†’ hoje) com visÃ£o cientÃ­fica + prÃ¡tica

Este repositÃ³rio Ã© um **kit â€œdo mundo realâ€** pra vocÃª:
1) **baixar e padronizar** resultados + odds histÃ³ricas (Football-Data),  
2) **definir zebra de forma operacional** com probabilidades vig-free,  
3) **medir % de zebras por perÃ­odo** (2010â€“2014 / 2015â€“2019 / 2020â€“2024 / 2025â†’hoje) com **IC95%**,  
4) **treinar modelos preditivos** (baseline forte e honesto) sem leakage,  
5) **rodar um scanner ao vivo** (API-Sports) pra gerar shortlist com **edge vs mercado** (EV + Kelly fracionado).

> âš ï¸ SeguranÃ§a: **NUNCA** comite sua chave da API (eu vi vocÃª colando uma chave no chat).  
> Troque/rotacione a chave na plataforma e use `.env`.

---

## 0) Setup rÃ¡pido

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# ou
cp .env.example .env     # Linux/Mac
```

---

## 1) Baixar histÃ³rico (Football-Data)

O template clÃ¡ssico de download Ã©:

`https://www.football-data.co.uk/mmz4281/{SEASON}/{DIV}.csv`

Exemplos:
- `.../1011/E0.csv` (Premier League 2010/11)
- `.../2324/E0.csv` (Premier League 2023/24)

### Download (exemplo)
```bash
python -m zebra_hunter.cli download \
  --seasons 1011 1112 1213 1314 1415 1516 1617 1718 1819 1920 2021 2122 2223 2324 2425 2526 \
  --divs E0 E1 SP1 D1 I1 F1 \
  --out data/raw/football_data
```

---

## 2) Construir dataset padronizado + zebra labels

```bash
python -m zebra_hunter.cli build-dataset \
  --raw data/raw/football_data \
  --out data/processed/matches.parquet \
  --odds-pref closing_avg
```

**odds-pref**:
- `closing_avg` tenta usar `AvgCH/AvgCD/AvgCA` quando existir; senÃ£o cai em `AvgH/AvgD/AvgA`
- `opening_avg` usa `AvgH/AvgD/AvgA`
- `max` usa `MaxH/MaxD/MaxA` (bom pra â€œmelhor preÃ§oâ€, mas NÃƒO Ã© â€œprobabilidade de mercadoâ€)

---

## 3) Calcular % de zebras por perÃ­odo (com IC95%)

```bash
python -m zebra_hunter.cli zebra-rates \
  --data data/processed/matches.parquet \
  --out reports/zebra_rates.csv
```

Ele gera:
- global + por divisÃ£o,
- zebra(â‰¤30%), zebra(â‰¤25%), zebra(â‰¤20%),
- **Wilson 95% CI**.

---

## 4) Treinar modelo (com validaÃ§Ã£o temporal)

```bash
python -m zebra_hunter.cli train \
  --data data/processed/matches.parquet \
  --target underdog_win \
  --train-end 2019-12-31 \
  --test-start 2020-01-01 \
  --out models/zebra_model.joblib
```

Targets:
- `underdog_win` (melhor base; threshold vira regra depois)
- `zebra_30`, `zebra_25`, `zebra_20`

---

## 5) Scanner ao vivo (API-Sports)

```bash
python -m zebra_hunter.cli scan \
  --days 7 \
  --thr 0.25 \
  --min-odd 3.0 --max-odd 7.0 \
  --mode rich \
  --top 20
```

SaÃ­da: tabela bonita + JSON em `reports/scan_live.json`.

---

## Filosofia (sem misticismo ðŸ§ )
- **Odds jÃ¡ agregam muita informaÃ§Ã£o.** Seu edge vem de:
  - mercado menos eficiente,
  - features de contexto que o mercado precifica mal,
  - disciplina (calibraÃ§Ã£o, CLV quando tiver closing, e gestÃ£o de risco).
- **Zebra â‰  aposta boa.** Aposta boa Ã© `P_model > P_mercado` o suficiente pra compensar risco/margem.

---

## 6) MongoDB (persistencia profissional, sem Excel)

Para usar banco de dados no fluxo do Zebra Hunter:

1. Suba seu MongoDB (local ou Atlas).
2. Configure no `.env`:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=zebra_hunter
MONGO_COLLECTION_PICKS=picks_log
MONGO_COLLECTION_ALERT_RUNS=alerts_analysis_runs
MONGO_COLLECTION_ALERT_TABLES=alerts_analysis_tables
```

3. Sincronize historico do `picks_log.csv` para MongoDB:

```bash
python -m zebra_hunter.cli mongo-sync --log reports/picks_log.csv --dedup
```

4. A partir dai:
- novos picks escritos no CSV ja fazem `upsert` no Mongo;
- `tools/update_results.py` sincroniza em lote apos atualizar resultados;
- `zebra_hunter.analisar_alertas` gera `relatorio_alerts.json` e pode salvar no Mongo com `--mongo-sync`.
- artefatos de `data/`, `models/` e `reports/` podem ser sincronizados em lote com:

```bash
python -m zebra_hunter.cli mongo-sync-all --root . --include-dirs data models reports
```

Exemplo de analise sem Excel:

```bash
python -m zebra_hunter.analisar_alertas \
  --csv reports/picks_log.csv \
  --out reports/relatorio_alerts.json \
  --mongo-sync
```

### Engine API (FastAPI + Pydantic + APScheduler)

Suba a API interna para integrar desktop, automacoes e futuros clientes web/mobile:

```bash
python -m zebra_hunter.cli api-serve --host 127.0.0.1 --port 8765
```

Endpoints principais:
- `GET /health`
- `POST /scan`
- `POST /performance`
- `POST /mongo-sync`
- `POST /operations/update-results`
- `POST /operations/analyze-alerts`

### Django Web API (Fase 2)

Com o Django rodando e usuario autenticado, endpoints web disponiveis:

- `GET /api/health/`
- `POST /api/scanner/run/`
- `POST /api/performance/run/`
- `POST /api/operations/update-results/`
- `POST /api/operations/analyze-alerts/`

Exemplo rapido (PowerShell, com sessao autenticada):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/scanner/run/ `
  -ContentType "application/json" `
  -Body '{"days":1,"top":5,"thr":0.45,"min_books":8,"min_conf":0.55,"min_edge":0.01,"min_ev":0.01}'
```

### Django + Celery (Fase 3: filas assíncronas e agendamentos)

Suba os processos em 3 terminais separados:

```powershell
# terminal 1
.\.venv\Scripts\python manage.py runserver 127.0.0.1:8000

# terminal 2
.\.venv\Scripts\python -m celery -A webapp worker -l info --pool=solo

# terminal 3
.\.venv\Scripts\python -m celery -A webapp beat -l info
```

Endpoints assíncronos (enfileiram jobs e retornam `task_id`):

- `POST /api/scanner/enqueue/`
- `POST /api/performance/enqueue/`
- `POST /api/operations/update-results/enqueue/`
- `POST /api/operations/analyze-alerts/enqueue/`
- `POST /api/mongo-sync/enqueue/`
- `GET /api/jobs/<task_id>/` (status do job)

Exemplo (PowerShell) para enfileirar scanner:

```powershell
$body = @{
  days = 1
  top = 5
  thr = 0.45
  min_books = 8
  min_conf = 0.55
  min_edge = 0.01
  min_ev = 0.01
  only_future = $true
} | ConvertTo-Json

$res = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/scanner/enqueue/ `
  -ContentType "application/json" `
  -Body $body

$taskId = $res.data.task_id
Invoke-RestMethod -Method Get -Uri ("http://127.0.0.1:8000/api/jobs/" + $taskId + "/")
```

### Fase 4: Dashboard web profissional com graficos

O dashboard Django (`/`) agora entrega:

- KPIs operacionais (scans, oportunidades, picks, hit rate, ROI, banca, drawdown)
- Curva de banca (linha)
- Lucro diario (barras)
- ROI por liga (barras horizontais)
- Distribuicao de status G/P/E/V (rosca)
- Tabelas de top ligas, oportunidades recentes, scans e filas assincronas

Endpoint de refresh parcial do dashboard:

- `GET /api/dashboard/summary/` (autenticado)

O front web atualiza os graficos em lote pelo botao **Atualizar dados** e tambem via auto-refresh (60s).

### Fase 5: Hardening de producao

Entregas implementadas:

- Security hardening no Django (`settings.py`) com cookies secure, SSL redirect, HSTS, CSRF trusted origins e policy de headers.
- Logging de producao (texto ou JSON) com arquivo rotativo em `reports/webapp/django_app.log`.
- Backup operacional completo:
  - script: `python tools/backup_runtime.py`
  - task assíncrona: `POST /api/operations/backup/enqueue/`
  - agendamento via Celery Beat: `DJANGO_SCHED_BACKUP_HOURS`.
- Monitoramento operacional:
  - `GET /api/ops/healthz/` (autenticado ou token)
  - `GET /api/ops/metrics/` (autenticado)
- Deploy package:
  - `deploy/Dockerfile`
  - `deploy/docker-compose.prod.yml`
  - `deploy/nginx.conf`
  - `deploy/entrypoint-web.sh`
- Preflight de producao:
  - `python tools/deploy_preflight.py`

Runbook completo: `docs/PRODUCTION_HARDENING.md`

Exemplo rapido (health):

```bash
curl http://127.0.0.1:8765/health
```

Scheduler interno (opcional, via `.env`):

```env
ZEBRA_API_SCHEDULER_ENABLED=1
ZEBRA_API_SCAN_INTERVAL_MIN=60
ZEBRA_API_SYNC_INTERVAL_MIN=30
ZEBRA_API_UPDATE_RESULTS_INTERVAL_MIN=20
```

Observabilidade profissional (opcional):

```env
LOG_LEVEL=INFO
LOG_JSON=1
SENTRY_DSN=
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.10
SENTRY_PROFILES_SAMPLE_RATE=0.0
```

---
## Estrutura
```
src/zebra_hunter/
  cli.py
  config.py
  logging_config.py
  data_sources/
    football_data.py
    apisports.py
    open_meteo.py
  features/
    market.py
    form.py
    poisson.py
    context.py
  analytics/
    zebra_rates.py
    stats.py
  models/
    train.py
    infer.py
tests/
```

Boa caÃ§ada â€” mas com cinto de seguranÃ§a estatÃ­stico. ðŸ¦“ðŸ“ˆ

---

## MVP Desktop (Executavel + Instalador)

### Rodar interface desktop (dev)
`bash
tools\\run_desktop_pro.bat
`

Ou diretamente:

`bash
python tools/desktop_app_pro.py
`

### Build do instalador/release
`powershell
powershell -ExecutionPolicy Bypass -File .\\installer\\build_release.ps1 -Mode client -Version 1.0.0
`

Guia completo de release: `docs/MVP_RELEASE.md`

---

## Pro Desktop Architecture

- Entrypoint: `python tools/desktop_app_pro.py`
- UI layer: `tools/pro_ui/main_window.py`
- Design system: `tools/pro_ui/design_system.py`
- Services: `tools/pro_ui/services.py`
- Runner: `tools/pro_ui/runner.py`
- State: `tools/pro_ui/state.py`

## CI and Tests

- CI workflow: `.github/workflows/ci.yml`
- Local tests:
`bash
pytest -q
`

## Release Smoke (Sprint 1)

- Rodar smoke manual:
`bash
python tools/release_smoke.py --json-out reports/release_smoke_manual.json
`

- Build com smoke automÃƒÂ¡tico:
`powershell
.\installer\build_release.ps1 -Mode both -Version 1.0.8-mvp
`

- Build sem smoke (somente emergÃƒÂªncia):
`powershell
.\installer\build_release.ps1 -Mode both -Version 1.0.8-mvp -SkipSmoke
`

## Operacional (Sprint 2)

- Logs estruturados com `session_id` e `app_version`:
  - `reports/app/audit.jsonl`
  - `reports/app/metrics.jsonl`
- BotÃƒÂ£o rÃƒÂ¡pido de suporte no desktop: **Exportar Suporte**
  - Gera `reports/support_YYYYMMDD_HHMMSS.zip` e copia caminho.
- Health check de runtime no header do app:
  - `Runtime: saudavel` / `Runtime: atencao`

## Seguranca e Compliance (Sprint 3)

- Scan de segredos no projeto:
`bash
python tools/security_scan.py
`

- O `release_smoke.py` ja valida segredos automaticamente.
- Instalador com Termos e Aviso de Privacidade:
  - `docs/LICENSE_EULA.txt`
  - `docs/PRIVACY_NOTICE.txt`

- Assinatura digital (apos build):
`powershell
.\installer\sign_release.ps1 -PfxPath <cert.pfx> -PfxPassword <senha>
`

## UX de Onboarding (Sprint 4)

- Primeira execucao exibe guia de setup em 3 passos (API -> Pipeline -> Scanner).
- Botao **Guia 5 Min** no topo da tela para reabrir instrucoes.
- Estados vazios com dicas operacionais no feed.

## Go-Live (Sprint 5)

- Gerar bundle de release:
`bash
python tools/create_release_bundle.py --version 1.0.9-mvp
`
- Arquivos gerados:
  - `release/<versao>/manifest.json`
  - `release/<versao>/checksums.txt`
  - `release/<versao>/CHANGELOG.md`
  - `release/<versao>/RELEASE_NOTES.md`
- Checklist final: `docs/GO_LIVE_CHECKLIST.md`
- Template de feedback beta: `docs/BETA_FEEDBACK_TEMPLATE.csv`

### Limpeza de instalacao antiga (Windows)

`powershell
.\tools\CLEAN_OLD_INSTALL.ps1
`

Para manter dados de runtime (`%LOCALAPPDATA%\ZebraHunter`):

`powershell
.\tools\CLEAN_OLD_INSTALL.ps1 -KeepRuntimeData
`


