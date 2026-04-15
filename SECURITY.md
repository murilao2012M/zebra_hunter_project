# Segurança básica (por favor não pise no rake 😅)

- **Nunca** coloque chaves de API diretamente no código.
- Use `.env` (veja `.env.example`) e carregue com `python-dotenv`.
- Se você já colou uma chave em público/chat, **rotacione** (revogue e gere outra).
- Evite salvar dumps de requests contendo headers.

## Hardening de release (Sprint 3)

- Rode scan de segredos antes de publicar:
  - `python tools/security_scan.py`
- O `release_smoke.py` ja executa `security_scan` automaticamente.
- Nao publique arquivo `.env` com chaves reais.
- Assine o executavel e instalador:
  - `.\installer\sign_release.ps1 -PfxPath <cert.pfx> -PfxPassword <senha>`
- O instalador exibe:
  - Termos de uso: `docs/LICENSE_EULA.txt`
  - Aviso de privacidade: `docs/PRIVACY_NOTICE.txt`
