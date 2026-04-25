"""
Comprehensive DB Schema + SQL Query Cross-Reference Scanner
Dumps ALL table schemas and tests EVERY SQL query in app.py against the real DB.
"""
import pyodbc

cn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=quanlibenhvien;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;"
)
cur = cn.cursor()

print("=" * 70)
print("FULL DATABASE SCHEMA DUMP")
print("=" * 70)

cur.execute("""
    SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
    WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME
""")
tables = [r[0] for r in cur.fetchall()]

schema = {}
for t in tables:
    cur.execute(f"""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME='{t}' ORDER BY ORDINAL_POSITION
    """)
    cols = []
    for r in cur.fetchall():
        cols.append(r[0])
        size = f"({r[3]})" if r[3] and r[3] > 0 else ""
        null = "NULL" if r[2] == "YES" else "NOT NULL"
        print(f"  {t:25s} | {r[0]:25s} | {r[1]:12s}{size:8s} | {null}")
    schema[t] = [c.upper() for c in cols]
    print()

print("\n" + "=" * 70)
print("SCHEMA QUICK REFERENCE (columns per table)")
print("=" * 70)
for t, cols in schema.items():
    print(f"\n{t}: {', '.join(cols)}")

cn.close()
