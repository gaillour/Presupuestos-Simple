# Backend (`back/`) — Presupuestos Simple

API REST en FastAPI (`api.py`) desacoplada con motor de cálculo y persistencia Supabase (`core.py`).

## Comandos y Entorno
```bash
# Servidor local con virtualenv
./venv/bin/uvicorn api:app --reload --host 0.0.0.0 --port 8000
# Deploy (manual si no corre GitHub Actions)
flyctl deploy --remote-only
```
- Dependencias: `requirements.txt` (FastAPI, Uvicorn, Supabase, FPDF2, Pydantic, PyJWT).

## Reglas Inviolables
1. **`app.py` legacy:** Monolito Streamlit deprecado. Prohibido editarlo, extenderlo o importar código de él.
2. **`core.py` estable:** Contiene consultas SQL y lógica matemática validada. Solo retocar si cambia el modelo de negocio.
3. **Persistencia & Fly.io efímero:** Filesystem efímero; persistir en Supabase (`configuracion`, `tipo_estampado`), no en `.config_extra.json`.
4. **Supabase `multiplicador`:** Es `bigint` en tabla `presupuestos`; conservar fallbacks de conversión float en `core.py`.
5. **Contratos:** Modelos Pydantic en `api.py` deben reflejarse exactamente en `front/lib/types.ts`.

## Autenticación y Variables
- **Auth dual:** Admin local con JWT (`Simple2026`/`admin`) o Supabase Auth vía `db.client.auth.get_user`.
- **PDF:** `/api/presupuestos/{id}/pdf` acepta auth por header `Bearer` o query `?token=`.
- **Variables (`.env` / Fly):** `SUPABASE_URL`, `SUPABASE_KEY`, `JWT_SECRET`, `ALLOWED_ORIGINS`, `FRONTEND_URL`.
