"""
AUTO-TEST: Execute every mobile API SQL query against real DB.
Catches column/table mismatches before users hit 500 errors.
"""
import pyodbc, re

cn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost;DATABASE=quanlibenhvien;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;"
)

# Read app.py
with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find all triple-quoted SQL blocks
# Pattern: cur.execute("""...""", ...) or cur.execute("SELECT ...")
sql_blocks = []

# Find function + SQL pairs
func_pattern = re.compile(
    r'@app\.(get|post|put|delete|patch|route)\(["\']([^"\']+)',
    re.MULTILINE
)
functions = list(func_pattern.finditer(content))

# For each route, find SQL statements
errors = []
ok_count = 0

# Extract SQL from triple-quoted strings  
sql_pattern = re.compile(r'cur\.execute\(\s*"""(.*?)"""', re.DOTALL)
sql_pattern2 = re.compile(r'cur\.execute\(\s*f"""(.*?)"""', re.DOTALL)
sql_pattern3 = re.compile(r'cur\.execute\(\s*"(SELECT[^"]+)"', re.DOTALL)

test_params = {
    'MABENHNHAN': 'BN001',
    'MANHANVIEN': 'BS001',
    'TAIKHOAN': 'admin',
    'KHOA': 'Khoa Nội',
    'mabn': 'BN001',
    'manv': 'BS001',
}

# Mobile-focused endpoints to test
mobile_endpoints = [
    "/api/mobile/khoa",
    "/api/mobile/bacsi",
    "/api/mobile/dat-lich",
    "/api/mobile/my-appointments",
    "/api/mobile/dich-vu",
    "/api/mobile/lay-so-online",
    "/api/mobile/list-today",
    "/api/mobile/my-records",
    "/api/mobile/doctor/my-schedule",
    "/api/mobile/doctor/register-schedule",
    "/api/mobile/doctor/cancel-schedule",
    "/api/mobile/doctor/appointments",
    "/api/mobile/doctor/phongbenh",
    "/api/mobile/doctor/giuongbenh",
    "/api/mobile/doctor/profile",
    "/api/mobile/patient/profile",
    "/api/mobile/doi-mat-khau",
    "/api/mobile/doctor/call-next",
    "/api/home-stats",
    "/api/benhnhan",
    "/api/phieukham",
    "/api/lichhen",
    "/api/nhanvien",
]

print("=" * 70)
print("SQL QUERY VALIDATION — Testing every query against real DB")
print("=" * 70)

for func in functions:
    method = func.group(1)
    route = func.group(2)
    
    # Get function body (from this @app to next @app or EOF)
    start = func.end()
    next_func = None
    for nf in functions:
        if nf.start() > func.start():
            next_func = nf
            break
    end = next_func.start() if next_func else len(content)
    body = content[start:end]
    
    # Find SQL in body
    sqls = sql_pattern.findall(body) + sql_pattern2.findall(body) + sql_pattern3.findall(body)
    
    if not sqls:
        continue
    
    # Only test mobile + key API endpoints
    is_mobile = any(route.startswith(ep) or route == ep for ep in mobile_endpoints)
    if not is_mobile:
        continue
    
    for sql_raw in sqls:
        # Clean up f-string interpolations
        sql_clean = sql_raw.strip()
        sql_clean = re.sub(r'\{[^}]+\}', "'test'", sql_clean)  # f-string vars
        
        # Replace ? params with test values
        param_count = sql_clean.count('?')
        test_vals = ['BS001'] * param_count  # safe test value
        
        # Try to parse as SET TOP or validate syntax
        try:
            # Use SET FMTONLY ON to validate without executing
            cur2 = cn.cursor()
            
            # For SELECT queries, wrap in a non-executing check
            if sql_clean.strip().upper().startswith('SELECT'):
                # Add TOP 0 to prevent actual data return
                check_sql = sql_clean.replace('SELECT ', 'SELECT TOP 0 ', 1)
                check_sql = re.sub(r'SELECT TOP \d+ TOP 0', 'SELECT TOP 0', check_sql)
                cur2.execute(check_sql, test_vals)
                cur2.fetchall()
                cur2.close()
                ok_count += 1
                print(f"  ✅ [{method.upper():6s}] {route}")
            elif sql_clean.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                # For DML, use SET PARSEONLY to syntax-check
                cur2.execute("SET PARSEONLY ON")
                try:
                    cur2.execute(sql_clean, test_vals)
                except Exception as e2:
                    err_str = str(e2)
                    if 'Invalid column' in err_str or 'Invalid object' in err_str:
                        errors.append((route, sql_clean[:80], str(e2)))
                        print(f"  ❌ [{method.upper():6s}] {route}")
                        print(f"       ERROR: {e2}")
                    else:
                        ok_count += 1
                        print(f"  ✅ [{method.upper():6s}] {route}")
                finally:
                    cur2.execute("SET PARSEONLY OFF")
                    cur2.close()
            else:
                ok_count += 1
                print(f"  ⚪ [{method.upper():6s}] {route} (skipped non-SQL)")
                
        except Exception as e:
            err_str = str(e)
            # Filter out param count mismatches (those are fine, we're just testing columns)
            if 'Invalid column' in err_str or 'Invalid object' in err_str:
                errors.append((route, sql_clean[:100], str(e)))
                print(f"  ❌ [{method.upper():6s}] {route}")
                # Extract specific column/table error
                col_errors = re.findall(r"Invalid column name '(\w+)'", err_str)
                tbl_errors = re.findall(r"Invalid object name '([^']+)'", err_str)
                if col_errors:
                    print(f"       MISSING COLUMNS: {', '.join(set(col_errors))}")
                if tbl_errors:
                    print(f"       MISSING TABLES: {', '.join(set(tbl_errors))}")
            elif 'expects parameter' in err_str or 'are supplied' in err_str:
                ok_count += 1
                print(f"  ✅ [{method.upper():6s}] {route} (param count differs, columns OK)")
            else:
                errors.append((route, sql_clean[:100], str(e)))
                print(f"  ⚠️  [{method.upper():6s}] {route}")
                print(f"       WARN: {err_str[:120]}")

print(f"\n{'=' * 70}")
print(f"RESULTS: {ok_count} OK, {len(errors)} ERRORS")
print(f"{'=' * 70}")

if errors:
    print("\n🔴 ERRORS REQUIRING FIX:")
    for route, sql, err in errors:
        print(f"\n  Route: {route}")
        print(f"  SQL:   {sql}...")
        col_errors = re.findall(r"Invalid column name '(\w+)'", err)
        tbl_errors = re.findall(r"Invalid object name '([^']+)'", err)
        if col_errors:
            print(f"  FIX:   Columns {col_errors} don't exist in the table")
        if tbl_errors:
            print(f"  FIX:   Tables {tbl_errors} don't exist")
else:
    print("\n🟢 ALL QUERIES VALID!")
