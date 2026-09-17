"""
cleaning.py
-----------
Script de preprocesamiento y limpieza de datos para la EA2 del proyecto integrador.

Simula un entorno de procesamiento en la nube: en lugar de leer de S3/Blob Storage,
"carga" los datos desde la base de datos SQLite generada en la EA1 (src/db/ingestion.db),
que aquí cumple el rol de la fuente de almacenamiento en la nube.

Flujo del script:
1. Carga los datos crudos desde la base de datos (simulando la nube).
2. Ejecuta un análisis exploratorio inicial (registros, duplicados, nulos, tipos).
3. Limpia y transforma los datos: duplicados, nulos, tipos, outliers y normalización.
4. Exporta una muestra de los datos limpios a Excel.
5. Genera un archivo de auditoría (.txt) que documenta cada operación y compara
   el estado de los datos antes y después de la limpieza.
"""

# --- Importación de librerías ---
import sqlite3                      # Módulo nativo para conectarse a la base de datos SQLite
import pandas as pd                 # Librería para manipular datos en DataFrames (pandas ya gestiona NaN internamente)
import os                           # Para manejar rutas y creación de carpetas
import re                           # Para limpiar texto con expresiones regulares
from datetime import datetime       # Para registrar la fecha/hora de ejecución en el reporte

# --- Rutas del proyecto (relativas a la carpeta src/) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))                       # Carpeta donde vive este script (src/)
DB_PATH = os.path.join(BASE_DIR, "db", "ingestion.db")                      # BD generada en la EA1 (simula la nube)
CLEANED_XLSX_PATH = os.path.join(BASE_DIR, "xlsx", "cleaned_data.xlsx")     # Salida: muestra de datos limpios
REPORT_PATH = os.path.join(BASE_DIR, "static", "auditoria", "cleaning_report.txt")  # Salida: reporte de auditoría

# --- Límites geográficos aproximados de Colombia, usados para detectar outliers ---
LAT_MIN, LAT_MAX = -4.3, 13.5      # Rango válido de latitud dentro del territorio colombiano
LON_MIN, LON_MAX = -82.0, -66.0    # Rango válido de longitud dentro del territorio colombiano


def cargar_datos_desde_db(ruta_db: str) -> pd.DataFrame:
    """
    Simula la carga de datos desde un entorno cloud: en este caso, lee la base de
    datos SQLite (generada en la EA1) que hace las veces de almacenamiento en la nube.
    Devuelve un DataFrame con el join de atracciones y sus ciudades.
    """
    conn = sqlite3.connect(ruta_db)          # Abre la conexión a la base de datos "cloud" simulada
    query = """
        SELECT a.id, a.nombre, a.descripcion, a.latitud, a.longitud,
               a.ciudad_id, a.imagenes,
               c.nombre AS ciudad, c.poblacion, c.departamento_id
        FROM atracciones a
        LEFT JOIN ciudades c ON a.ciudad_id = c.id
    """                                        # Consulta que combina atracciones con su ciudad
    df = pd.read_sql_query(query, conn)        # Ejecuta la consulta y carga el resultado en un DataFrame
    conn.close()                               # Cierra la conexión, ya no se necesita
    print(f"[OK] Se cargaron {len(df)} registros desde la base de datos (nube simulada).")  # Log
    return df                                  # Devuelve el DataFrame crudo, listo para analizar


def analisis_exploratorio(df: pd.DataFrame) -> dict:
    """
    Realiza un análisis exploratorio inicial del DataFrame crudo, para documentar
    el estado de los datos ANTES de aplicar cualquier limpieza.
    Devuelve un diccionario con las estadísticas encontradas.
    """
    estadisticas = {
        "registros_iniciales": len(df),                                  # Cantidad total de filas antes de limpiar
        "duplicados_por_id": int(df.duplicated(subset="id").sum()),      # Cuántas filas tienen id repetido
        "nulos_por_columna": df.isna().sum().to_dict(),                  # Diccionario columna -> cantidad de nulos
        "tipos_originales": df.dtypes.astype(str).to_dict(),             # Diccionario columna -> tipo de dato original
    }
    print("[OK] Análisis exploratorio inicial completado.")  # Log informativo
    return estadisticas                          # Devuelve el resumen para usarlo luego en el reporte


def eliminar_duplicados(df: pd.DataFrame, reporte: dict) -> pd.DataFrame:
    """
    Elimina registros duplicados: primero por id exacto, luego por combinación
    lógica de nombre + ciudad (para atrapar duplicados que llegaron con distinto id).
    Registra en 'reporte' cuántas filas se eliminaron en cada paso.
    """
    filas_antes = len(df)                                    # Cantidad de filas antes de esta operación

    df = df.drop_duplicates(subset="id", keep="first")       # Elimina duplicados exactos por id, conserva el primero
    duplicados_id = filas_antes - len(df)                    # Calcula cuántas filas se quitaron por id duplicado

    filas_antes_logico = len(df)                             # Cantidad de filas antes del segundo filtro
    clave_logica = (                                          # Construye una clave normalizada nombre+ciudad
        df["nombre"].str.strip().str.lower() + "|" + df["ciudad"].str.strip().str.lower()
    )
    df = df.loc[~clave_logica.duplicated(keep="first")]      # Conserva solo la primera aparición de cada clave lógica
    duplicados_logicos = filas_antes_logico - len(df)         # Calcula cuántas filas se quitaron por duplicado lógico

    reporte["duplicados_id_eliminados"] = duplicados_id           # Guarda el conteo en el reporte
    reporte["duplicados_logicos_eliminados"] = duplicados_logicos  # Guarda el conteo en el reporte
    print(f"[OK] Duplicados eliminados: {duplicados_id} por id, {duplicados_logicos} lógicos.")  # Log
    return df                                                  # Devuelve el DataFrame sin duplicados


def corregir_tipos(df: pd.DataFrame, reporte: dict) -> pd.DataFrame:
    """
    Corrige los tipos de datos de las columnas que vienen mal tipadas desde el API/BD
    (por ejemplo, coordenadas como texto). Registra cuántos valores no se pudieron convertir.
    """
    antes_lat_validas = df["latitud"].notna().sum()             # Cuenta valores no nulos de latitud antes de convertir
    df["latitud"] = pd.to_numeric(df["latitud"], errors="coerce")   # Convierte a número; lo inválido pasa a NaN
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")  # Igual para longitud

    df["poblacion"] = pd.to_numeric(df["poblacion"], errors="coerce").astype("Int64")  # Convierte población a entero nullable

    despues_lat_validas = df["latitud"].notna().sum()           # Cuenta valores no nulos de latitud después de convertir
    perdidos_por_conversion = int(antes_lat_validas - despues_lat_validas)  # Cuántos valores dejaron de ser válidos

    reporte["tipos_corregidos"] = ["latitud -> float", "longitud -> float", "poblacion -> Int64"]  # Detalle de la operación
    reporte["valores_invalidos_en_conversion"] = perdidos_por_conversion    # Cuántos se volvieron NaN al convertir
    print("[OK] Tipos de datos corregidos (latitud, longitud, población).")  # Log
    return df                                                     # Devuelve el DataFrame con tipos corregidos


def manejar_nulos(df: pd.DataFrame, reporte: dict) -> pd.DataFrame:
    """
    Aplica una estrategia distinta de manejo de nulos según la columna:
    - descripcion vacía -> se reemplaza con texto por defecto (no se pierde el registro).
    - poblacion nula -> se imputa con la mediana de las poblaciones conocidas.
    - lat/lon nulas -> se eliminan esas filas, porque sin ubicación el registro no es útil.
    """
    nulos_descripcion = int(df["descripcion"].isna().sum())         # Cuenta cuántas descripciones son nulas
    df["descripcion"] = df["descripcion"].fillna("Sin descripción disponible")  # Rellena con un texto por defecto

    nulos_poblacion = int(df["poblacion"].isna().sum())              # Cuenta cuántas poblaciones son nulas
    mediana_poblacion = df["poblacion"].median()                     # Calcula la mediana de las poblaciones conocidas
    df["poblacion"] = df["poblacion"].fillna(mediana_poblacion)      # Imputa los nulos con esa mediana

    filas_antes = len(df)                                            # Cantidad de filas antes de eliminar por coordenadas nulas
    df = df.dropna(subset=["latitud", "longitud"])                   # Elimina filas sin coordenadas válidas
    eliminados_por_coordenadas = filas_antes - len(df)                # Cuántas filas se perdieron por esta razón

    reporte["nulos_descripcion_rellenados"] = nulos_descripcion       # Guarda el conteo en el reporte
    reporte["nulos_poblacion_imputados"] = nulos_poblacion            # Guarda el conteo en el reporte
    reporte["mediana_poblacion_usada"] = float(mediana_poblacion) if pd.notna(mediana_poblacion) else None  # Guarda el valor usado
    reporte["filas_eliminadas_por_coordenadas_nulas"] = int(eliminados_por_coordenadas)  # Guarda el conteo en el reporte
    print("[OK] Valores nulos gestionados (descripción, población, coordenadas).")  # Log
    return df                                                          # Devuelve el DataFrame sin nulos críticos


def tratar_outliers(df: pd.DataFrame, reporte: dict) -> pd.DataFrame:
    """
    Detecta y elimina registros cuyas coordenadas caen fuera del territorio
    colombiano (posibles errores de carga o atracciones mal geolocalizadas).
    """
    dentro_de_colombia = (                                    # Condición booleana: coordenadas dentro de los rangos válidos
        df["latitud"].between(LAT_MIN, LAT_MAX) &
        df["longitud"].between(LON_MIN, LON_MAX)
    )
    outliers = int((~dentro_de_colombia).sum())               # Cuenta cuántas filas NO cumplen la condición (outliers)
    df = df.loc[dentro_de_colombia]                           # Conserva solo las filas dentro del rango válido

    reporte["outliers_geograficos_eliminados"] = outliers      # Guarda el conteo en el reporte
    print(f"[OK] Outliers geográficos eliminados: {outliers}.")  # Log informativo
    return df                                                  # Devuelve el DataFrame sin outliers geográficos


def transformaciones_adicionales(df: pd.DataFrame, reporte: dict) -> pd.DataFrame:
    """
    Aplica transformaciones de normalización y enriquecimiento ligero:
    - Limpia espacios y capitalización en texto (nombre, ciudad).
    - Calcula el número de imágenes por atracción a partir del campo 'imagenes'.
    - Normaliza la población con escalado min-max (0 a 1) en una columna nueva.
    """
    df["nombre"] = df["nombre"].str.strip()                            # Quita espacios sobrantes al inicio/fin del nombre
    df["nombre"] = df["nombre"].apply(lambda x: re.sub(r"\s+", " ", x))  # Colapsa espacios múltiples internos en uno solo
    df["ciudad"] = df["ciudad"].str.strip().str.title()                 # Limpia y capitaliza el nombre de la ciudad

    df["num_imagenes"] = df["imagenes"].apply(                          # Crea columna nueva con el conteo de imágenes
        lambda x: len(x.split("|")) if isinstance(x, str) and x else 0  # Cuenta elementos separados por "|", o 0 si está vacío
    )

    poblacion_min = df["poblacion"].min()                                # Valor mínimo de población, para el escalado
    poblacion_max = df["poblacion"].max()                                # Valor máximo de población, para el escalado
    rango = (poblacion_max - poblacion_min) if poblacion_max != poblacion_min else 1  # Evita división entre cero
    df["poblacion_normalizada"] = (df["poblacion"] - poblacion_min) / rango  # Escala la población entre 0 y 1

    reporte["transformaciones_aplicadas"] = [                            # Detalla las transformaciones para el reporte
        "Normalización de texto en nombre y ciudad",
        "Cálculo de num_imagenes a partir del campo imagenes",
        "Escalado min-max de poblacion -> poblacion_normalizada",
    ]
    print("[OK] Transformaciones adicionales aplicadas (texto, imágenes, escalado).")  # Log
    return df                                                             # Devuelve el DataFrame ya transformado


def exportar_datos_limpios(df: pd.DataFrame, ruta_salida: str, n: int = 50) -> None:
    """
    Exporta una muestra representativa del DataFrame limpio a un archivo Excel.
    """
    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)   # Crea la carpeta xlsx/ si no existe
    tamano_muestra = min(n, len(df))                            # Evita pedir más filas de las que hay disponibles
    muestra = df.sample(n=tamano_muestra, random_state=42) if tamano_muestra > 0 else df  # Toma muestra aleatoria reproducible
    muestra.to_excel(ruta_salida, index=False)                  # Exporta la muestra a Excel sin la columna de índice
    print(f"[OK] Datos limpios exportados a: {ruta_salida}")     # Log informativo


def generar_reporte_limpieza(reporte: dict, registros_finales: int, ruta_txt: str) -> None:
    """
    Escribe el archivo de auditoría .txt documentando todas las operaciones
    realizadas y comparando el estado de los datos antes y después de la limpieza.
    """
    os.makedirs(os.path.dirname(ruta_txt), exist_ok=True)      # Crea la carpeta static/auditoria/ si no existe

    lineas = [                                                  # Construye el contenido del reporte línea por línea
        "REPORTE DE AUDITORÍA - LIMPIEZA Y PREPROCESAMIENTO DE DATOS",
        f"Fecha y hora de ejecución: {datetime.now().isoformat()}",
        "=" * 70,
        "ESTADO INICIAL (antes de limpiar)",
        f"  Registros iniciales: {reporte['registros_iniciales']}",
        f"  Duplicados por id detectados: {reporte['duplicados_por_id']}",
        f"  Nulos por columna: {reporte['nulos_por_columna']}",
        f"  Tipos de datos originales: {reporte['tipos_originales']}",
        "=" * 70,
        "OPERACIONES DE LIMPIEZA REALIZADAS",
        f"  Duplicados eliminados por id: {reporte['duplicados_id_eliminados']}",
        f"  Duplicados lógicos eliminados (nombre+ciudad): {reporte['duplicados_logicos_eliminados']}",
        f"  Tipos corregidos: {reporte['tipos_corregidos']}",
        f"  Valores inválidos detectados al convertir tipos: {reporte['valores_invalidos_en_conversion']}",
        f"  Nulos en descripción rellenados: {reporte['nulos_descripcion_rellenados']}",
        f"  Nulos en población imputados (mediana={reporte['mediana_poblacion_usada']}): {reporte['nulos_poblacion_imputados']}",
        f"  Filas eliminadas por coordenadas nulas: {reporte['filas_eliminadas_por_coordenadas_nulas']}",
        f"  Outliers geográficos eliminados: {reporte['outliers_geograficos_eliminados']}",
        f"  Transformaciones adicionales aplicadas: {reporte['transformaciones_aplicadas']}",
        "=" * 70,
        "ESTADO FINAL (después de limpiar)",
        f"  Registros finales: {registros_finales}",
        f"  Registros eliminados en total: {reporte['registros_iniciales'] - registros_finales}",
        "=" * 70,
        "Conclusión: El proceso de limpieza se ejecutó correctamente y el conjunto "
        "de datos resultante está libre de duplicados, con tipos de datos consistentes "
        "y sin valores nulos en campos críticos.",
    ]

    with open(ruta_txt, "w", encoding="utf-8") as archivo:      # Abre el archivo de auditoría en modo escritura
        archivo.write("\n".join(lineas))                        # Escribe todas las líneas separadas por saltos de línea

    print(f"[OK] Reporte de limpieza generado en: {ruta_txt}")   # Log informativo


def main():
    """
    Orquesta el pipeline completo de preprocesamiento:
    cargar -> analizar -> limpiar (duplicados, tipos, nulos, outliers, transformar)
    -> exportar -> generar reporte de auditoría.
    """
    df_crudo = cargar_datos_desde_db(DB_PATH)          # Paso 1: carga los datos desde la BD (simula la nube)

    reporte = analisis_exploratorio(df_crudo)          # Paso 2: analiza y guarda estadísticas iniciales

    df = eliminar_duplicados(df_crudo, reporte)        # Paso 3: elimina duplicados exactos y lógicos
    df = corregir_tipos(df, reporte)                   # Paso 4: corrige tipos de datos (lat/lon/población)
    df = manejar_nulos(df, reporte)                    # Paso 5: gestiona valores nulos según la columna
    df = tratar_outliers(df, reporte)                  # Paso 6: elimina outliers geográficos
    df = transformaciones_adicionales(df, reporte)     # Paso 7: normaliza texto y escala variables

    exportar_datos_limpios(df, CLEANED_XLSX_PATH, n=50)          # Paso 8: exporta muestra de datos limpios
    generar_reporte_limpieza(reporte, len(df), REPORT_PATH)      # Paso 9: genera el archivo de auditoría

    print(f"[OK] Pipeline de limpieza finalizado. Registros finales: {len(df)}")  # Log final


if __name__ == "__main__":   # Verifica que el script se ejecute directamente (no como import)
    main()                    # Llama a la función principal para correr todo el pipeline
