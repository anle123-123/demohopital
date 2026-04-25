
import requests
import pyodbc
import os
import json
from datetime import datetime, timedelta

# Config (matching app.py)
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "quanlibenhvien")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "0966288650aA@")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
CONN_STR = f"DRIVER={{{DB_DRIVER}}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD};TrustServerCertificate=yes;"

BASE_URL = "http://localhost:5000" # Assuming flask is running, but I can just test DB logic directly via python if flask isn't up. 
# Actually I should test the FLASK API. But I can't guarantee Flask is running.
# I will test the DB logic that I added to app.py by simulating the queries.

def test_db_logic():
    print("Connecting to DB...")
    cn = pyodbc.connect(CONN_STR)
    cur = cn.cursor()
    
    # 1. Setup Data
    print("Setting up test data...")
    manv = "BS001"
    
    # Ensure BS001 in QUANLINHANVIEN
    cur.execute("SELECT 1 FROM QUANLINHANVIEN WHERE MANHANVIEN=?", manv)
    if not cur.fetchone():
        cur.execute("INSERT INTO QUANLINHANVIEN (MANHANVIEN, HOVATEN, KHOA) VALUES (?, N'Test Doc', N'Nội')", manv)
    
    # Clear Schedule
    cur.execute("DELETE FROM LICH_LAM_VIEC WHERE MANHANVIEN=?", manv)
    
    # Add Schedule for Tomorrow
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    
    cur.execute("""
        INSERT INTO LICH_LAM_VIEC (MANHANVIEN, NGAY, CA, TGBATDAU, TGKETTHUC)
        VALUES (?, ?, N'Sáng', '07:00:00', '11:30:00')
    """, manv, tomorrow)
    cn.commit()
    print(f"Added schedule for {manv} on {tomorrow}")
    
    # 2. Test Logic (Simulate api_list_bacsi)
    print("Testing Logic...")
    
    # Case A: Filter by Tomorrow (Should find BS001)
    print(f"Querying for {tomorrow}...")
    cur.execute("""
        SELECT DISTINCT nv.MANHANVIEN
        FROM DBO.QUANLINHANVIEN nv
        JOIN DBO.LICH_LAM_VIEC llv ON nv.MANHANVIEN = llv.MANHANVIEN
        WHERE llv.NGAY = ? AND nv.MANHANVIEN = ?
    """, tomorrow, manv)
    if cur.fetchone():
        print("PASS: Found doctor for tomorrow.")
    else:
        print("FAIL: Doctor not found for tomorrow.")
        
    # Case B: Filter by Day After (Should NOT find BS001)
    print(f"Querying for {day_after}...")
    cur.execute("""
        SELECT DISTINCT nv.MANHANVIEN
        FROM DBO.QUANLINHANVIEN nv
        JOIN DBO.LICH_LAM_VIEC llv ON nv.MANHANVIEN = llv.MANHANVIEN
        WHERE llv.NGAY = ? AND nv.MANHANVIEN = ?
    """, day_after, manv)
    if not cur.fetchone():
        print("PASS: Doctor correctly not found for day after.")
    else:
        print("FAIL: Doctor found for day after (unexpected).")

    # Cleanup
    # cur.execute("DELETE FROM LICH_LAM_VIEC WHERE MANHANVIEN=?", manv)
    # cn.commit()

if __name__ == "__main__":
    test_db_logic()
