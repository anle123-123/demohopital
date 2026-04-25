
import pyodbc
import os
from datetime import datetime, timedelta

# Database configuration (matching app.py)
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "quanlibenhvien")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "0966288650aA@")

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};DATABASE={DB_NAME};"
    f"UID={DB_USER};PWD={DB_PASSWORD};"
    "Encrypt=no;TrustServerCertificate=yes;"
)

def init_db():
    print(f"Connecting to {DB_SERVER}/{DB_NAME}...")
    try:
        cn = pyodbc.connect(CONN_STR)
        cur = cn.cursor()
        
        # 1. Create Table LICH_LAM_VIEC
        print("Creating table LICH_LAM_VIEC...")
        cur.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[LICH_LAM_VIEC]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [dbo].[LICH_LAM_VIEC](
                    [ID] [int] IDENTITY(1,1) NOT NULL,
                    [MANHANVIEN] [varchar](50) NULL,
                    [NGAY] [date] NOT NULL,
                    [CA] [nvarchar](50) NULL,
                    [TGBATDAU] [time](7) NULL,
                    [TGKETTHUC] [time](7) NULL,
                    [PHONG] [nvarchar](50) NULL,
                    PRIMARY KEY CLUSTERED ([ID] ASC)
                )
            END
        """)
        
        # 2. Seed Data
        print("Seeding sample data...")
        
        # Get some doctors
        cur.execute("SELECT TOP 5 MANHANVIEN FROM QUANLINHANVIEN ORDER BY NEWID()")
        doctors = [row[0] for row in cur.fetchall()]
        
        if not doctors:
            print("No doctors found in QUANLINHANVIEN. Please add some staff first.")
        else:
            today = datetime.now().date()
            # Shifts
            shifts = [
                ("Sáng", "07:00", "11:00", "P101"),
                ("Chiều", "13:00", "17:00", "P102"),
                ("Sáng", "08:00", "12:00", "P201"),
            ]
            
            # Add schedule for today and yesterday (to test filter)
            dates = [today, today - timedelta(days=1)]
            
            for d in dates:
                for i, doc in enumerate(doctors):
                    shift = shifts[i % len(shifts)]
                    # Check duplicate
                    cur.execute("SELECT 1 FROM LICH_LAM_VIEC WHERE MANHANVIEN=? AND NGAY=? AND CA=?", doc, d, shift[0])
                    if not cur.fetchone():
                        cur.execute("""
                            INSERT INTO LICH_LAM_VIEC (MANHANVIEN, NGAY, CA, TGBATDAU, TGKETTHUC, PHONG)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, doc, d, shift[0], shift[1], shift[2], shift[3])
                        
        cn.commit()
        print("Done!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    init_db()
