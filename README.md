# EA1 + EA2 - Ingestión y Preprocesamiento de Datos

## Descripción breve de la solución

Este proyecto implementa las etapas de **ingesta (EA1)** y **preprocesamiento/limpieza (EA2)** del proyecto integrador de Big Data.

### EA1 - Ingesta (`src/ingestion.py`)

1. Se conecta al API público de **[API Colombia](https://api-colombia.com/)**, específicamente al endpoint `TouristicAttraction`, y extrae la lista de atracciones turísticas del país.
2. Almacena la información en una base de datos **SQLite** (`src/db/ingestion.db`), en dos tablas relacionadas: `ciudades` y `atracciones`.
3. Genera un archivo **Excel** (`src/xlsx/ingestion.xlsx`) con una muestra representativa de los registros almacenados, usando **Pandas**.
4. Genera un archivo de **auditoría** (`src/static/auditoria/ingestion.txt`) que compara la cantidad e identificadores de los registros extraídos del API contra los almacenados en la base de datos.

### EA2 - Preprocesamiento y limpieza (`src/cleaning.py`)

Simula un entorno de procesamiento en la nube: en lugar de conectarse a un servicio real (S3, Azure Blob Storage, GCS), el script **lee la base de datos SQLite generada en la EA1** (`src/db/ingestion.db`), la cual cumple aquí el rol de almacenamiento en la nube. Sobre esos datos:

1. Ejecuta un **análisis exploratorio inicial**: cantidad de registros, duplicados por id, nulos por columna y tipos de datos originales.
2. Aplica **limpieza y transformación**:
   - Elimina duplicados exactos (por `id`) y duplicados lógicos (mismo nombre + ciudad).
   - Corrige tipos de datos: `latitud`/`longitud` a `float`, `poblacion` a entero.
   - Maneja valores nulos: rellena descripciones vacías, imputa población faltante con la mediana, y elimina registros sin coordenadas válidas.
   - Elimina **outliers geográficos** (coordenadas fuera del territorio colombiano).
   - Aplica transformaciones adicionales: normalización de texto, cálculo de `num_imagenes`, y escalado min-max de la población (`poblacion_normalizada`).
3. Exporta una muestra de los datos limpios a **Excel** (`src/xlsx/cleaned_data.xlsx`).
4. Genera un archivo de **auditoría** (`src/static/auditoria/cleaning_report.txt`) que documenta cada operación realizada y compara el estado de los datos **antes y después** de la limpieza.

> **Nota sobre PySpark:** el enunciado permite usar PySpark o Pandas. Dado el volumen de datos del API (unos pocos cientos de registros) y para mantener el workflow de GitHub Actions simple y confiable, se optó por **Pandas**, que cumple el mismo propósito de análisis y transformación distribuida a esta escala.

Todo el proceso está automatizado mediante **GitHub Actions**, que ejecuta el pipeline completo (ingesta + limpieza) y deja evidencia tanto como artefactos descargables como directamente commiteados en el repositorio.

## Estructura del proyecto

```
├── setup.py                              # Declara el paquete y sus dependencias
├── README.md                             # Este archivo
├── .github/workflows/bigdata.yml         # Workflow de automatización (EA1 + EA2)
└── src/
    ├── ingestion.py                      # EA1: script de ingesta desde el API
    ├── cleaning.py                       # EA2: script de limpieza y preprocesamiento
    ├── db/ingestion.db                   # Base de datos SQLite (salida EA1 / entrada EA2, simula la nube)
    ├── xlsx/
    │   ├── ingestion.xlsx                # EA1: muestra de datos crudos
    │   └── cleaned_data.xlsx             # EA2: muestra de datos limpios
    └── static/auditoria/
        ├── ingestion.txt                 # EA1: reporte de auditoría de ingesta
        └── cleaning_report.txt           # EA2: reporte de auditoría de limpieza
```

## Instrucciones para clonar y ejecutar localmente

```bash
# 1. Clonar el repositorio
git clone https://github.com/<tu-usuario>/<tu-repo>.git
cd <tu-repo>

# 2. Instalar dependencias (usa setup.py)
pip install -e .

# 3. Ejecutar el script de ingesta (EA1)
python src/ingestion.py

# 4. Ejecutar el script de limpieza (EA2), usando la BD generada en el paso anterior
python src/cleaning.py
```

Al finalizar, se generarán/actualizarán automáticamente:
- `src/db/ingestion.db` (EA1)
- `src/xlsx/ingestion.xlsx` (EA1)
- `src/static/auditoria/ingestion.txt` (EA1)
- `src/xlsx/cleaned_data.xlsx` (EA2)
- `src/static/auditoria/cleaning_report.txt` (EA2)

## Automatización con GitHub Actions

El archivo `.github/workflows/bigdata.yml` define un workflow que:

1. Se dispara manualmente (`workflow_dispatch`), en cada `push` a `main`, o de forma programada (`cron` diario).
2. Instala Python 3.11 y las dependencias del proyecto (`requests`, `pandas`, `openpyxl`) vía `pip install -e .`.
3. Ejecuta `python src/ingestion.py` (EA1: crea/actualiza la base de datos).
4. Ejecuta `python src/cleaning.py` (EA2: lee esa base de datos, simula la nube, y genera los datos limpios).
5. Verifica que los cinco archivos de evidencia existan y muestra el contenido del reporte de limpieza en el log.
6. Sube los archivos generados como **artefacto descargable** (`evidencias-proyecto`) desde la pestaña **Actions**.
7. Hace commit y push de los archivos generados directamente al repositorio, dejando evidencia permanente del proceso.

### Cómo verificar la ejecución

1. Ir a la pestaña **Actions** del repositorio.
2. Seleccionar la ejecución más reciente del workflow "Ingesta y Limpieza de Datos - Proyecto Big Data".
3. Revisar los logs de cada paso (extracción, limpieza, verificación de archivos).
4. Descargar el artefacto **evidencias-proyecto** para inspeccionar la base de datos, ambos Excel y ambos reportes.
5. Alternativamente, revisar directamente en el repositorio las rutas `src/db/`, `src/xlsx/` y `src/static/auditoria/`, actualizadas automáticamente por el workflow.
