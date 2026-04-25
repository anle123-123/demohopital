
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
    # Add MANHANVIEN column
    try:
        cursor.execute("ALTER TABLE DANGNHAP ADD MANHANVIEN VARCHAR(50)")
        print("Added MANHANVIEN column to DANGNHAP")
    except Exception as e:
        print(f"Error adding column (might already exist): {e}")

    # Map existing 'doctor' accounts to a sample doctor if available, or just leave null
    # For testing, let's try to update 'bacsi1' to 'BS001' if it exists
    try:
        cursor.execute("UPDATE DANGNHAP SET MANHANVIEN = 'BS001' WHERE TAIKHOAN = 'bacsi1'")
        print("Updated bacsi1 -> BS001")
    except Exception as e:
        print(f"Error updating sample data: {e}")

except Exception as e:
    print(f"Connection error: {e}")
