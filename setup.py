"""
setup.py
--------
Define el proyecto como un paquete instalable y declara sus dependencias.
No ejecuta la lógica de ingesta (eso lo hace src/ingestion.py); su función
es dejar claro qué librerías necesita el proyecto para funcionar, tanto
en instalación local como dentro del workflow de GitHub Actions.
"""

from setuptools import setup, find_packages  # setup: función que registra el proyecto / find_packages: detecta paquetes automáticamente

setup(
    name="ingestion-bigdata",           # Nombre del proyecto/paquete
    version="1.0.0",                    # Versión del proyecto
    description="Ingesta de datos desde el API de Colombia hacia SQLite, con evidencias en Excel y auditoría en TXT",  # Descripción corta
    packages=find_packages(where="src"),  # Busca automáticamente subpaquetes dentro de src/ (si los hubiera)
    package_dir={"": "src"},              # Indica que el código fuente vive dentro de la carpeta src/
    install_requires=[                    # Lista de dependencias necesarias para correr el proyecto
        "requests>=2.31.0",              # Para hacer las peticiones HTTP al API
        "pandas>=2.0.0",                 # Para procesar los datos y generar el Excel
        "openpyxl>=3.1.0",               # Motor que usa Pandas para escribir archivos .xlsx
    ],
    python_requires=">=3.10",             # Versión mínima de Python requerida
)
