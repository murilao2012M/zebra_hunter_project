# Zebra Hunter - Sistema de Licenças ✅

## Status
- **Funciona**: Trial 30 dias auto, full via admin, bloqueio expiry.
- **Robustez**: Machine ID (WMI/uuid) - único por PC.
- **Arquivos**:
  - `generate_license.py`: Admin (full license).
  - `desktop_app.py`: App com license (indent OK após fixes).
  - Docs: USO.md/TODO.md.

## Uso
1. **Trial**:
```
cd _backup/cleanup_20260320/legacy_tools
python desktop_app.py
```
Cria `license.json` → app abre.

2. **Full** (admin):
```
python generate_license.py
# Expiry: 2025-12-31 ou PERM
# Copie license.json para %LOCALAPPDATA%/ZebraHunter
```

3. **Teste bloqueio**:
Edite license.json `expiry`: "2020-01-01" → erro + fecha.

## Fixes aplicados
- Indentação Ruff.
- wmi instalado (`pip install wmi`).
- Imports try-except (zebra_hunter opcional).
- Scope license_data fix.

## Produção
```
pip install pyinstaller
pyinstaller --onefile --windowed _backup/cleanup_20260320/legacy_tools/desktop_app.py
```

**Pronto para distribuição!** 🦓

