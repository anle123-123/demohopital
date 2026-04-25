
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

def apply_schema_changes():
    try:
        cn = pyodbc.connect(CONN_STR, autocommit=True)
        cursor = cn.cursor()

        # Add EMAIL to HOSOBENHNHAN
        print("Checking EMAIL in HOSOBENHNHAN...")
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'HOSOBENHNHAN' AND COLUMN_NAME = 'EMAIL'")
        if not cursor.fetchone():
            print("Adding EMAIL column to HOSOBENHNHAN...")
            cursor.execute("ALTER TABLE DBO.HOSOBENHNHAN ADD EMAIL NVARCHAR(100)")
        else:
            print("EMAIL column already exists in HOSOBENHNHAN.")

        # Add MABENHNHAN to DANGNHAP
        print("Checking MABENHNHAN in DANGNHAP...")
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'DANGNHAP' AND COLUMN_NAME = 'MABENHNHAN'")
        if not cursor.fetchone():
            print("Adding MABENHNHAN column to DANGNHAP...")
            cursor.execute("ALTER TABLE DBO.DANGNHAP ADD MABENHNHAN VARCHAR(20)")
        else:
            print("MABENHNHAN column already exists in DANGNHAP.")
            
        print("Schema changes applied successfully.")

    except Exception as e:
        print(f"Error applying schema changes: {e}")

if __name__ == "__main__":
    apply_schema_changes()
