
import pyodbc
import os

DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "quanlibenhvien")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "0966288650aA@")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

CONN_STR = (
    f"DRIVER={{{DB_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASSWORD};"
    "TrustServerCertificate=yes;"
    "MARS_Connection=Yes;"
)

try:
    cn = pyodbc.connect(CONN_STR, autocommit=True)
    cursor = cn.cursor()
    cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'HOSOBENHNHAN'")
    columns = [row[0] for row in cursor.fetchall()]
    print(f"Columns in HOSOBENHNHAN: {columns}")
except Exception as e:
    print(f"Error: {e}")
