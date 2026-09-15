# Motor local de informes financieros (MVP)

Sistema local para preparar CCAA: datos estructurados → modelo → HTML tipográfico → PDF.

## Requisitos

- Python 3.11+
- Windows (Arial Narrow del sistema; fallback Arial)

## Instalación

```powershell
cd "C:\Users\Jose Herrera\Documents\Jose\Audit"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

## Arranque

```powershell
cd "C:\Users\Jose Herrera\Documents\Jose\Audit"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000

## Flujo MVP

1. Abrir el informe demo HH Print
2. Editar cifras / añadir fila en **Datos**
3. Editar párrafos en **Contenido**
4. Revisar **Validaciones**
5. **Vista previa** → **Generar PDF**

## Estructura

- `app/` — API, dominio, servicios, plantillas
- `data/projects/` — JSON por informe (fuente de verdad)
- `reference/` — DOCX gold standard (solo diseño)
- `outputs/` — PDFs generados
- `samples/` — Excel de ejemplo para importación

## Nota tipográfica

El informe usa `Arial Narrow` si está instalada; si no, cae a `Arial`.

## Control de versiones (Git)

El historial vive en Git local. Así puedes ver cambios y volver atrás si algo se rompe.

```powershell
cd "C:\Users\Jose Herrera\Documents\Jose\Audit"

# Ver estado
git status

# Guardar un punto estable
git add -A
git commit -m "Descripción breve del cambio"

# Ver historial
git log --oneline

# Deshacer el último commit manteniendo los archivos (si aún no has subido nada)
git reset --soft HEAD~1
```

No se versionan: `.venv/`, `outputs/`, PDFs generados, `.env`.

### GitHub (recomendado, repo privado)

Cuando quieras copia remota y backup:

1. Instala [GitHub CLI](https://cli.github.com/) y autentica: `gh auth login`
2. Crea el remoto privado desde esta carpeta:

```powershell
cd "C:\Users\Jose Herrera\Documents\Jose\Audit"
gh repo create audit-informes --private --source=. --remote=origin --push
```

Si prefieres la web: crea un repo **privado** vacío en GitHub y luego:

```powershell
git remote add origin https://github.com/TU_USUARIO/audit-informes.git
git push -u origin main
```
