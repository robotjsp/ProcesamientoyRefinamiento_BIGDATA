"""
ingestion.py
------------
Script de ingesta de datos para el proyecto integrador de Big Data.

Flujo del script:
1. Extrae datos desde la API de Colombia (atracciones turísticas).
2. Crea/actualiza una base de datos SQLite con dos tablas: ciudades y atracciones.
3. Genera un archivo Excel con una muestra de los datos usando Pandas.
4. Genera un archivo de auditoría .txt comparando lo extraído del API vs lo guardado en la BD.
"""

# --- Importación de librerías ---
import requests            # Librería para hacer peticiones HTTP al API
import sqlite3              # Librería nativa de Python para trabajar con bases de datos SQLite
import pandas as pd         # Librería para manipular datos en forma de tablas (DataFrames)
import os                   # Librería para manejar rutas y carpetas del sistema operativo
from datetime import datetime  # Para registrar la fecha y hora de ejecución en la auditoría

# --- Constantes de configuración ---
API_URL = "https://api-colombia.com/api/v1/TouristicAttraction"  # Endpoint del API que vamos a consumir

# Rutas de salida, relativas a la carpeta donde vive este script (src/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))            # Carpeta donde está este archivo (src/)
DB_PATH = os.path.join(BASE_DIR, "db", "ingestion.db")            # Ruta del archivo de la base de datos
XLSX_PATH = os.path.join(BASE_DIR, "xlsx", "ingestion.xlsx")      # Ruta del archivo Excel de muestra
AUDIT_PATH = os.path.join(BASE_DIR, "static", "auditoria", "ingestion.txt")  # Ruta del archivo de auditoría


def extraer_datos(url: str) -> list:
    """
    Se conecta al API y extrae la lista de atracciones turísticas.
    Devuelve una lista de diccionarios (uno por atracción) en caso de éxito.
    """
    try:
        respuesta = requests.get(url, timeout=30)   # Hace la petición GET al API con un timeout de 30s
        respuesta.raise_for_status()                # Lanza una excepción si el status code indica error (4xx o 5xx)
        datos = respuesta.json()                    # Convierte la respuesta (texto JSON) en una lista de Python
        print(f"[OK] Se extrajeron {len(datos)} registros del API.")  # Mensaje informativo en consola
        return datos                                # Devuelve la lista de atracciones ya parseada
    except requests.exceptions.RequestException as error:  # Captura cualquier error de red o HTTP
        print(f"[ERROR] Falló la conexión con el API: {error}")  # Informa el error por consola
        raise                                        # Vuelve a lanzar el error para detener la ejecución


def crear_bd(ruta_db: str) -> sqlite3.Connection:
    """
    Crea (si no existe) el archivo de base de datos SQLite y las tablas necesarias.
    Devuelve el objeto de conexión abierto para seguir trabajando con él.
    """
    os.makedirs(os.path.dirname(ruta_db), exist_ok=True)  # Crea la carpeta db/ si todavía no existe
    conn = sqlite3.connect(ruta_db)                        # Abre (o crea) el archivo .db y devuelve la conexión
    cursor = conn.cursor()                                 # Crea un cursor para ejecutar sentencias SQL

    # Tabla de ciudades: guarda la info anidada que trae cada atracción en el campo "city"
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ciudades (
            id INTEGER PRIMARY KEY,        -- id de la ciudad, viene del API
            nombre TEXT,                   -- nombre de la ciudad
            poblacion INTEGER,             -- población de la ciudad (puede ser NULL)
            departamento_id INTEGER        -- id del departamento al que pertenece
        )
    """)  # Ejecuta la sentencia que crea la tabla ciudades solo si no existe

    # Tabla de atracciones turísticas: guarda los datos principales del API
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS atracciones (
            id INTEGER PRIMARY KEY,        -- id de la atracción, viene del API
            nombre TEXT,                   -- nombre de la atracción turística
            descripcion TEXT,              -- descripción larga de la atracción
            latitud REAL,                  -- coordenada de latitud
            longitud REAL,                 -- coordenada de longitud
            ciudad_id INTEGER,             -- id de la ciudad asociada (llave foránea)
            imagenes TEXT,                 -- URLs de imágenes, unidas con "|" como separador
            FOREIGN KEY (ciudad_id) REFERENCES ciudades(id)  -- relación con la tabla ciudades
        )
    """)  # Ejecuta la sentencia que crea la tabla atracciones solo si no existe

    conn.commit()          # Guarda los cambios (creación de tablas) en el archivo .db
    print("[OK] Base de datos y tablas verificadas/creadas.")  # Mensaje informativo
    return conn             # Devuelve la conexión abierta para reutilizarla en otras funciones


def insertar_datos(conn: sqlite3.Connection, datos: list) -> None:
    """
    Recorre la lista de atracciones extraídas del API e inserta/actualiza
    los registros correspondientes en las tablas ciudades y atracciones.
    """
    cursor = conn.cursor()          # Crea un cursor para ejecutar los INSERT
    insertados = 0                  # Contador de registros insertados, útil para el log

    for atraccion in datos:                       # Itera sobre cada atracción devuelta por el API
        ciudad = atraccion.get("city") or {}       # Obtiene el diccionario de ciudad (o vacío si viene null)

        # --- Insertar/actualizar la ciudad asociada ---
        cursor.execute("""
            INSERT OR REPLACE INTO ciudades (id, nombre, poblacion, departamento_id)
            VALUES (?, ?, ?, ?)
        """, (
            ciudad.get("id"),              # id de la ciudad
            ciudad.get("name"),            # nombre de la ciudad
            ciudad.get("population"),      # población (puede ser None)
            ciudad.get("departmentId"),    # id del departamento
        ))  # INSERT OR REPLACE evita duplicados si el script se corre varias veces

        # --- Preparar la lista de imágenes como un solo string ---
        imagenes = atraccion.get("images") or []          # Lista de URLs de imágenes (o vacía)
        imagenes_str = "|".join([img for img in imagenes if img])  # Une las URLs válidas con "|"

        # --- Insertar/actualizar la atracción turística ---
        cursor.execute("""
            INSERT OR REPLACE INTO atracciones
                (id, nombre, descripcion, latitud, longitud, ciudad_id, imagenes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            atraccion.get("id"),              # id de la atracción
            atraccion.get("name"),            # nombre de la atracción
            atraccion.get("description"),     # descripción
            atraccion.get("latitude"),        # latitud
            atraccion.get("longitude"),       # longitud
            atraccion.get("cityId"),          # id de la ciudad (FK)
            imagenes_str,                     # imágenes concatenadas
        ))  # INSERT OR REPLACE actualiza el registro si ya existía el mismo id

        insertados += 1              # Incrementa el contador por cada atracción procesada

    conn.commit()                    # Guarda todos los cambios (inserciones) en la base de datos
    print(f"[OK] {insertados} atracciones insertadas/actualizadas en la BD.")  # Log informativo


def generar_muestra_excel(conn: sqlite3.Connection, ruta_salida: str, n: int = 15) -> None:
    """
    Lee los datos ya almacenados en la base de datos y genera un archivo Excel
    con una muestra representativa de los registros (join entre atracciones y ciudades).
    """
    os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)  # Crea la carpeta xlsx/ si no existe

    # Consulta SQL que combina atracciones con el nombre de su ciudad
    query = """
        SELECT a.id, a.nombre, a.descripcion, a.latitud, a.longitud,
               c.nombre AS ciudad, c.poblacion
        FROM atracciones a
        LEFT JOIN ciudades c ON a.ciudad_id = c.id
    """
    df = pd.read_sql_query(query, conn)          # Ejecuta la consulta y carga el resultado en un DataFrame

    tamano_muestra = min(n, len(df))             # Evita pedir más filas de las que existen
    muestra = df.sample(n=tamano_muestra, random_state=42) if tamano_muestra > 0 else df  # Toma una muestra aleatoria

    muestra.to_excel(ruta_salida, index=False)   # Exporta la muestra a un archivo .xlsx sin la columna de índice
    print(f"[OK] Archivo de muestra generado en: {ruta_salida}")  # Log informativo


def generar_auditoria(datos_api: list, conn: sqlite3.Connection, ruta_txt: str) -> None:
    """
    Compara los datos obtenidos directamente del API con los datos almacenados
    en la base de datos, y escribe un reporte de auditoría en un archivo .txt.
    """
    os.makedirs(os.path.dirname(ruta_txt), exist_ok=True)  # Crea la carpeta static/auditoria/ si no existe

    df_bd = pd.read_sql_query("SELECT * FROM atracciones", conn)  # Carga todo lo almacenado en la BD

    ids_api = {atraccion.get("id") for atraccion in datos_api}    # Conjunto de ids que vinieron del API
    ids_bd = set(df_bd["id"].tolist())                            # Conjunto de ids que quedaron en la BD

    faltantes_en_bd = ids_api - ids_bd     # ids que están en el API pero no se guardaron en la BD
    sobrantes_en_bd = ids_bd - ids_api     # ids que están en la BD pero ya no vienen en el API

    # Construye el contenido del reporte como una lista de líneas de texto
    lineas = [
        "REPORTE DE AUDITORÍA - INGESTA DE DATOS",                       # Título del reporte
        f"Fecha y hora de ejecución: {datetime.now().isoformat()}",      # Marca de tiempo de la corrida
        f"API consultada: {API_URL}",                                    # URL del API usado
        "-" * 60,                                                        # Línea separadora visual
        f"Registros extraídos del API: {len(datos_api)}",                # Total extraído del API
        f"Registros almacenados en la BD: {len(df_bd)}",                 # Total almacenado en la BD
        f"¿Coinciden las cantidades?: {len(datos_api) == len(df_bd)}",   # Verificación simple de conteo
        f"IDs en API pero ausentes en BD: {sorted(faltantes_en_bd) if faltantes_en_bd else 'Ninguno'}",  # Diferencias
        f"IDs en BD pero ausentes en API: {sorted(sobrantes_en_bd) if sobrantes_en_bd else 'Ninguno'}",  # Diferencias
        "-" * 60,
        "Conclusión: " + (
            "La ingesta fue exitosa y los datos son consistentes."       # Mensaje si todo coincide
            if not faltantes_en_bd and not sobrantes_en_bd
            else "Se encontraron inconsistencias entre el API y la BD. Revisar detalle arriba."  # Mensaje si hay diferencias
        ),
    ]

    with open(ruta_txt, "w", encoding="utf-8") as archivo:  # Abre el archivo .txt en modo escritura
        archivo.write("\n".join(lineas))                    # Escribe todas las líneas separadas por saltos de línea

    print(f"[OK] Archivo de auditoría generado en: {ruta_txt}")  # Log informativo


def main():
    """
    Función principal que orquesta todo el pipeline de ingesta:
    extraer -> crear BD -> insertar -> generar muestra -> generar auditoría.
    """
    datos = extraer_datos(API_URL)                    # Paso 1: extrae los datos del API
    conn = crear_bd(DB_PATH)                           # Paso 2: crea/abre la base de datos y sus tablas

    try:
        insertar_datos(conn, datos)                    # Paso 3: inserta los datos extraídos en la BD
        generar_muestra_excel(conn, XLSX_PATH, n=15)    # Paso 4: genera el Excel de muestra
        generar_auditoria(datos, conn, AUDIT_PATH)      # Paso 5: genera el archivo de auditoría
    finally:
        conn.close()                                    # Cierra la conexión a la BD pase lo que pase
        print("[OK] Conexión a la base de datos cerrada.")  # Log informativo final


if __name__ == "__main__":     # Verifica que el script se esté ejecutando directamente (no importado)
    main()                      # Llama a la función principal para correr todo el pipeline
