# Trabajo con archivos Excel (.xlsx)

## Regla crítica: nunca usar un load→save completo (openpyxl u otra librería similar) en un .xlsx con Power Query, Tablas o conexiones

Este proyecto usa archivos Excel grandes con conexiones de Power Query, `queryTables`, y decenas de Tablas con nombre (ListObjects) — por ejemplo `CONSOLIDADO 06_2026_V.0.xlsx`. Un `.xlsx` es un .zip con varias partes XML internas (worksheets, tablas, conexiones, calcChain, etc.).

**Herramientas como openpyxl, al hacer `load_workbook()` + `.save()`, pueden eliminar silenciosamente partes que no soportan del todo** (conexiones de Power Query, `queryTables`, algunas Tablas). Esto no da ningún error en Python — el archivo se guarda "bien" — pero al abrirlo en Excel aparece:

> "Hemos encontrado un problema con el contenido de '...'. ¿Desea que intentemos recuperar el máximo de contenido posible?"

Ejemplo real de este proyecto: el archivo original tenía 224 partes internas (incluía `xl/connections.xml` y varias `xl/queryTables/*.xml`). Tras un ciclo openpyxl load→save, quedó en 129 partes — perdió las conexiones y varias tablas — y Excel no podía abrirlo limpiamente.

### Cómo editar fórmulas/valores de forma segura (técnica correcta)

En vez de reescribir el libro completo, editar **solo el XML de la hoja concreta**, dejando cada una de las demás partes del zip byte a byte idéntica:

1. Localizar qué `sheetN.xml` corresponde a la pestaña objetivo: buscar `<sheet name="..." r:id="rIdX">` en `xl/workbook.xml`, y resolver `rIdX` → `worksheets/sheetN.xml` en `xl/_rels/workbook.xml.rels`.
2. Con `zipfile`, leer solo esa parte como texto (`zin.read(path).decode('utf-8')`).
3. Hacer sustituciones con regex directamente sobre el texto XML de las celdas (`<c r="D9" ...><f>...</f><v>...</v></c>`). Las fórmulas no necesitan escapar `$`, comillas simples, paréntesis — solo `<`, `>`, `&` necesitarían escape (raro en fórmulas).
4. El contenido de `<f>` **no debe incluir el "=" inicial** (Excel lo añade implícitamente). Si se guarda con un "=" de más dentro de `<f>`, Excel no recalcula esa celda y se queda congelada en el valor en caché, sin mostrar ningún error visible — es un bug silencioso y difícil de detectar solo mirando el valor de la celda.
5. Volver a empaquetar el zip copiando cada entrada original tal cual (bytes idénticos), reemplazando únicamente la(s) parte(s) modificada(s).
6. Si se cambian fórmulas, añadir `fullCalcOnLoad="1"` al elemento `<calcPr>` en `xl/workbook.xml` para forzar que Excel recalcule todo al abrir, en vez de confiar en valores cacheados desactualizados.

### Checklist de validación antes de entregar un archivo con fórmulas modificadas

1. `zipfile.namelist()` del archivo nuevo == el original (mismo número y nombres de partes). Si baja el conteo, algo se perdió.
2. Cada parte `.xml`/`.rels` parsea sin error con `xml.etree.ElementTree.fromstring` (bien formado).
3. Diff celda por celda (vía openpyxl en modo lectura) contra el original: solo deben cambiar las celdas que se pretendía tocar.
4. Revisar el XML crudo (`<f>...</f>`) de varias celdas de muestra para descartar el bug del "=" doble.
5. Si es posible, forzar recálculo real (COM de Excel) en vez de confiar en el valor cacheado — aunque abrir Excel vía automatización COM puede colgarse si el libro tiene un aviso de "vínculo no actualizable" (ver más abajo), así que no insistir mucho tiempo con eso; confiar en `fullCalcOnLoad` + que el usuario lo abra normalmente.

### Automatización de Excel vía COM (PowerShell) en este entorno

- Si el archivo tiene vínculos externos rotos (p. ej. el origen de una conexión de Power Query no accesible), abrirlo vía `New-Object -ComObject Excel.Application` puede colgarse indefinidamente esperando una respuesta a un diálogo modal invisible, aunque se pongan `DisplayAlerts=$false` / `AskToUpdateLinks=$false`. Si ocurre, matar el proceso `EXCEL.EXE` huérfano (`taskkill /PID <pid> /F`) y no reintentar automatización COM en ese archivo — mejor dejar que el usuario lo abra interactivamente.
- Antes de tocar cualquier archivo `.xlsx`, comprobar si existe su lock file `~$nombre.xlsx` en la misma carpeta — indica que está abierto en Excel (posiblemente por el usuario). No sobrescribirlo mientras el lock exista.

## Contexto del proyecto: estructura de la consolidación EPTISA

- `clientes/Nueva carpeta/CONSOLIDADO 06_2026_V.0.xlsx` es el consolidado con más empresas (~50), agregando datos vía Power Query en las pestañas `CFS_ES_Epígrafe_PIVOT` (balance España) y `CFS_INT_Epigrafe_PIVOT` (balance internacional/sucursales).
- La pestaña `BS_PL_EPTISA` tiene, en la fila 1 de cada columna de empresa, un **número de índice fijo** que identifica a la empresa (coincide con la columna `Nº` de la pestaña `SOCIEDADES`, que es la fuente de verdad de códigos de empresa).
- Las fórmulas de línea (`INDEX/MATCH` anidado en `IFERROR`) buscan ese número de índice en la fila de encabezado de **ambas** pestañas PIVOT (ES e INT) — primero ES, si falla prueba INT — así no importa en cuál de las dos tablas de origen esté realmente cargada la empresa. Si el año que viene Power Query agrega/quita/reordena columnas, o una empresa pasa de reportar por una tabla a la otra, la fórmula la sigue encontrando sin tocar nada, salvo asignar el número de índice correcto en la fila 1 cuando entra una empresa nueva.
