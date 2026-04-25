
# ==== API ĐỒNG BỘ THUỐC TỪ CỤC QUẢN LÝ DƯỢC ====
@app.post("/api/sync-thuoc-dav")
def sync_thuoc_dav():
    """
    Đồng bộ dữ liệu thuốc từ Cục Quản lý Dược.
    Loop lấy dữ liệu cho đến khi hết hoặc đạt giới hạn an toàn.
    """
    if "user" not in session:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
        
    url = "https://dichvucong.dav.gov.vn/api/services/app/quanLyGiaThuoc/GetListCongBoPublicPaging"
    
    # Cấu hình SSL (bỏ qua verify)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
    }

    added_count = 0
    updated_count = 0
    total_scanned = 0
    
    # Giới hạn an toàn: Sync tối đa 50 trang (5000 thuốc) mỗi lần gọi để tránh timeout/spam
    # Nếu muốn full: user có thể bấm sync nhiều lần hoặc tăng giới hạn này.
    MAX_PAGES = 50
    PAGE_SIZE = 100 
    
    cn_internal = None
    try:
        cn_internal = pyodbc.connect(
            f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD}",
            autocommit=True
        )
        cur = cn_internal.cursor()

        for page_idx in range(MAX_PAGES):
            skip = page_idx * PAGE_SIZE
            payload = {
                "filterAll": "",
                "CongBoGiaThuoc": {"loaiGiaId": None, "parentId": None, "TenThuoc": ""},
                "KichHoat": True,
                "skipCount": skip,
                "maxResultCount": PAGE_SIZE,
                "sorting": None
            }
            data_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, headers=headers)
            
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                    res_json = json.loads(response.read().decode('utf-8'))
                    
                items = res_json.get("result", {}).get("items", [])
                if not items:
                    break # Hết dữ liệu
                
                total_scanned += len(items)
                
                for item in items:
                    # Mapping fields
                    # MATHUOC: soDangKy (nếu null thì dùng DAV-{id})
                    sdk = (item.get("soDangKy") or "").strip()
                    if not sdk:
                        sdk = f"DAV-{item.get('id')}"
                    
                    # Cắt ngắn nếu MATHUOC quá dài (db thường varchar 20-50, check schema là varchar(50)?)
                    # Giả sử MATHUOC varchar(50). SDK có thể dài, cẩn thận.
                    # SDK vd: 893114458325 -> OK.
                    mathuoc = sdk[:50]
                    
                    tenthuoc = (item.get("tenThuoc") or "").strip()
                    donvi = (item.get("donViTinh") or "").strip()
                    gia = float(item.get("giaBanBuonDuKien") or 0)
                    
                    # Logic: Check exist
                    cur.execute("SELECT TENTHUOC, DONVI, GIA FROM DBO.THUOC WHERE MATHUOC=?", mathuoc)
                    row = cur.fetchone()
                    
                    if row:
                        # Update nếu khác
                        old_ten, old_dv, old_gia = row
                        old_gia = float(old_gia or 0)
                        
                        if (old_ten != tenthuoc) or (old_dv != donvi) or (abs(old_gia - gia) > 0.1):
                            cur.execute("""
                                UPDATE DBO.THUOC 
                                SET TENTHUOC=?, DONVI=?, GIA=?
                                WHERE MATHUOC=?
                            """, tenthuoc, donvi, gia, mathuoc)
                            updated_count += 1
                    else:
                        # Insert mới
                        # HANSUDUNG không có -> NULL
                        # TONTOITHIEU -> 100 (Cho test)
                        # TONKHO -> (1000) (mặc định trong DB hoặc set 0)
                        # IS_ACTIVE -> 1 (mặc định trong DB hoặc set 1)
                        cur.execute("""
                            INSERT INTO DBO.THUOC (MATHUOC, TENTHUOC, DONVI, GIA, HANSUDUNG, TONKHO, TONTOITHIEU, IS_ACTIVE)
                            VALUES (?, ?, ?, ?, NULL, 100, 1000, 1)
                        """, mathuoc, tenthuoc, donvi, gia)
                        added_count += 1
                        
            except Exception as e:
                print(f"Error syncing page {page_idx}: {e}")
                break

    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if cn_internal:
            cn_internal.close()
            
    return jsonify({
        "ok": True,
        "added": added_count,
        "updated": updated_count,
        "scanned": total_scanned
    })
