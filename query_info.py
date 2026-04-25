import pyodbc

cn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=quanlibenhvien;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;"
)
cur = cn.cursor()

print("=== DICHVU data ===")
cur.execute("SELECT * FROM DBO.DICHVU")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print(f"  Columns: {cols}")
print(f"  Total: {len(rows)} rows")
for r in rows[:10]:
    print(f"  {list(r)}")

print("\n=== HOADON schema ===")
cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='HOADON' ORDER BY ORDINAL_POSITION")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

print("\n=== HOADON_CT schema ===")
cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='HOADON_CT' ORDER BY ORDINAL_POSITION")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

print("\n=== HOADON data (top 5) ===")
cur.execute("SELECT TOP 5 * FROM DBO.HOADON ORDER BY ID DESC")
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
for r in rows:
    print(f"  {dict(zip(cols, r))}")

print("\n=== LICHHEN — lịch đã đặt (top 5) ===")
cur.execute("SELECT TOP 5 * FROM DBO.LICHHEN ORDER BY ID DESC")
cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    print(f"  {dict(zip(cols, r))}")

print("\n=== PHIEUKHAM — phiếu khám (top 3) ===")
cur.execute("SELECT TOP 3 * FROM DBO.PHIEUKHAM ORDER BY MAPHIEU DESC")
cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    print(f"  {dict(zip(cols, r))}")

print("\n=== DONTHUOC schema ===")
cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='DONTHUOC' ORDER BY ORDINAL_POSITION")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

print("\n=== DONTHUOC_CT schema ===")
cur.execute("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='DONTHUOC_CT' ORDER BY ORDINAL_POSITION")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

print("\n=== LAYSO_ONLINE (today) ===")
cur.execute("SELECT * FROM DBO.LAYSO_ONLINE WHERE CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)")
cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    print(f"  {dict(zip(cols, r))}")

print("\n=== Thanh toán APIs in app.py ===")
import re
with open("app.py","r",encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if any(kw in line for kw in ['hoadon', 'pay-url', 'vnpay', 'thanh-toan']):
            if '@app.' in line:
                print(f"  L{i}: {line.strip()}")
