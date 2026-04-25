import pyodbc

CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;"
    "DATABASE=quanlibenhvien;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)
cn = pyodbc.connect(CONN_STR)
cur = cn.cursor()

# Find UNIQUE constraints on DANGNHAP
cur.execute("""
    SELECT name FROM sys.key_constraints 
    WHERE parent_object_id = OBJECT_ID('DBO.DANGNHAP') AND type = 'UQ'
""")
rows = cur.fetchall()
print("UNIQUE constraints:", [r[0] for r in rows])

for r in rows:
    name = r[0]
    print(f"Dropping {name}...")
    cur.execute(f"ALTER TABLE DBO.DANGNHAP DROP CONSTRAINT [{name}]")
    cn.commit()
    print(f"  Dropped {name}")

print("Done!")
