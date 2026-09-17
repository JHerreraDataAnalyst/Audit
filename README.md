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

## Flujo recomendado

1. En el dashboard: **Nuevo informe desde DOCX** (CCAA del año anterior)
2. El sistema importa portada, memoria, tablas, **Balance** y **PyG** tipados
3. Marca **Preparar ejercicio siguiente** (rollover) si quieres N→N-1
4. Completa o ajusta cifras en **Datos** / vista previa
5. Revisa **Validaciones** → **Vista previa** → **PDF** / **Word**

Orden del informe: portada → Balance → PyG → Memoria (flujo dinámico).

El PDF es dinámico: al acortar o alargar texto, el documento se recompacta solo (mismo motor que la preview).
El Word se genera desde los mismos datos (`GET /projects/{id}/docx`) para entregar o archivar sin editar el DOCX a mano.

## Layout dinámico

El informe no usa páginas fijas ni coordenadas absolutas. El contenido fluye:

`modelo → HTML de flujo → layout.js (páginas A4) → preview / PDF`

Si acortas, eliminas o alargas un párrafo, el documento se recompacta solo.

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
