"""
seed_data.py — Seed dữ liệu mẫu cho Hospital Mobile App
Chạy: python seed_data.py  (cùng folder với app.py)
Idempotent: chạy nhiều lần không lỗi (IF NOT EXISTS)
"""

import pyodbc
import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

# ── DB Connection (copy logic từ setup.py) ──
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "quanlibenhvien")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_USE_WIN_AUTH = os.getenv("DB_USE_WIN_AUTH", "1")

if DB_USE_WIN_AUTH == "1":
    CONN_STR = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
        "MARS_Connection=Yes;"
    )
else:
    DB_USER = os.getenv("DB_USER", "")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "210506")
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
    from argon2 import PasswordHasher
    ph = PasswordHasher()
except ImportError:
    ph = None
    print("⚠️  argon2 not found, passwords saved as plain text")

DEFAULT_EMAIL = "lamkhoi.dev@gmail.com"
DEFAULT_PWD = "123456"
TODAY = date.today()
TODAY_STR = TODAY.strftime("%Y%m%d")
NOW = datetime.now()


def run():
    cn = pyodbc.connect(CONN_STR, autocommit=True)
    cur = cn.cursor()
    print("=" * 60)
    print("🌱 HOSPITAL SEED DATA")
    print("=" * 60)

    # ────────────────────────────────────────────────────
    # STEP 1: NHOMTHUOC + THUOC
    # ────────────────────────────────────────────────────
    print("\n── Step 1: NHOMTHUOC + THUOC ──")

    nhom_map = {}
    nhom_list = [
        "Kháng sinh", "Giảm đau - Hạ sốt", "Tim mạch",
        "Tiêu hóa", "Vitamin & Bổ sung", "Hô hấp"
    ]
    for ten in nhom_list:
        cur.execute("SELECT ID FROM DBO.NHOMTHUOC WHERE TEN=?", ten)
        row = cur.fetchone()
        if row:
            nhom_map[ten] = row[0]
        else:
            cur.execute("INSERT INTO DBO.NHOMTHUOC (TEN) VALUES (?)", ten)
            cur.execute("SELECT @@IDENTITY")
            nhom_map[ten] = int(cur.fetchone()[0])
            print(f"  + Nhóm: {ten}")

    thuoc_data = [
        ("TH001", "Amoxicillin 500mg",      "Viên",  3000,  200, "Kháng sinh"),
        ("TH002", "Cefixime 200mg",          "Viên",  8000,  150, "Kháng sinh"),
        ("TH003", "Azithromycin 250mg",      "Viên",  12000, 100, "Kháng sinh"),
        ("TH004", "Paracetamol 500mg",       "Viên",  1500,  500, "Giảm đau - Hạ sốt"),
        ("TH005", "Ibuprofen 400mg",         "Viên",  2500,  300, "Giảm đau - Hạ sốt"),
        ("TH006", "Amlodipine 5mg",          "Viên",  5000,  200, "Tim mạch"),
        ("TH007", "Losartan 50mg",           "Viên",  6000,  200, "Tim mạch"),
        ("TH008", "Omeprazole 20mg",         "Viên",  4000,  300, "Tiêu hóa"),
        ("TH009", "Domperidone 10mg",        "Viên",  3500,  250, "Tiêu hóa"),
        ("TH010", "Vitamin C 500mg",         "Viên",  1000,  500, "Vitamin & Bổ sung"),
        ("TH011", "Vitamin B Complex",       "Viên",  2000,  400, "Vitamin & Bổ sung"),
        ("TH012", "Salbutamol 4mg",          "Viên",  3000,  200, "Hô hấp"),
        ("TH013", "Dextromethorphan 15mg",   "Viên",  2500,  200, "Hô hấp"),
        ("TH014", "Metformin 500mg",         "Viên",  2000,  300, "Tim mạch"),
        ("TH015", "Cetirizine 10mg",         "Viên",  3000,  250, "Hô hấp"),
        ("TH016", "Diclofenac 50mg",         "Viên",  3500,  200, "Giảm đau - Hạ sốt"),
        ("TH017", "Loperamide 2mg",          "Viên",  4000,  150, "Tiêu hóa"),
        ("TH018", "Calcium + D3",            "Viên",  5000,  300, "Vitamin & Bổ sung"),
        ("TH019", "Ciprofloxacin 500mg",     "Viên",  7000,  150, "Kháng sinh"),
        ("TH020", "Prednisolone 5mg",        "Viên",  2000,  200, "Kháng sinh"),
    ]

    thuoc_count = 0
    for ma, ten, dv, gia, tonkho, nhom_ten in thuoc_data:
        cur.execute("SELECT 1 FROM DBO.THUOC WHERE MATHUOC=?", ma)
        if not cur.fetchone():
            nhom_id = nhom_map.get(nhom_ten)
            hsd = (TODAY + timedelta(days=365)).strftime("%Y-%m-%d")
            cur.execute("""
                INSERT INTO DBO.THUOC (MATHUOC, TENTHUOC, DONVI, GIA, TONKHO, TONTOITHIEU, IS_ACTIVE, HANSUDUNG, NHOM_ID)
                VALUES (?, ?, ?, ?, ?, 10, 1, ?, ?)
            """, ma, ten, dv, gia, tonkho, hsd, nhom_id)
            thuoc_count += 1
    print(f"  ✅ Thuốc: {thuoc_count} mới / {len(thuoc_data)} tổng")

    # ────────────────────────────────────────────────────
    # STEP 2: DICHVU
    # ────────────────────────────────────────────────────
    print("\n── Step 2: DICHVU ──")

    dichvu_data = [
        ("Khám tổng quát",              200000),
        ("Khám chuyên khoa",            350000),
        ("Siêu âm tổng quát",           250000),
        ("Chụp X-quang",                300000),
        ("Xét nghiệm máu tổng quát",    150000),
        ("Xét nghiệm nước tiểu",         80000),
        ("Điện tâm đồ (ECG)",           200000),
        ("Nội soi dạ dày",              800000),
        ("Chụp CT Scanner",            1500000),
        ("Chụp MRI",                   3000000),
    ]

    dv_count = 0
    for ten, gia in dichvu_data:
        cur.execute("SELECT 1 FROM DBO.DICHVU WHERE TEN_CHI_PHI=?", ten)
        if not cur.fetchone():
            cur.execute("INSERT INTO DBO.DICHVU (TEN_CHI_PHI, DON_GIA) VALUES (?, ?)", ten, gia)
            dv_count += 1
    print(f"  ✅ Dịch vụ: {dv_count} mới / {len(dichvu_data)} tổng")

    # ────────────────────────────────────────────────────
    # STEP 3: HOSOBENHNHAN + DANGNHAP (Patient accounts)
    # ────────────────────────────────────────────────────
    print("\n── Step 3: Bệnh nhân test ──")

    pw_hash = ph.hash(DEFAULT_PWD) if ph else None

    # Generate BN codes with today's date format
    bn_data = [
        (f"BN{TODAY_STR}0101", "Nguyễn Văn Minh",  "1990-05-15", "0901234567", "123 Nguyễn Huệ, TP.HCM",     "TP.Hồ Chí Minh", "benhnhan1"),
        (f"BN{TODAY_STR}0102", "Trần Thị Hương",    "1985-08-20", "0912345678", "456 Lê Lợi, Hà Nội",         "Hà Nội",          "benhnhan2"),
        (f"BN{TODAY_STR}0103", "Lê Hoàng Nam",      "2000-12-01", "0923456789", "789 Trần Hưng Đạo, Đà Nẵng", "Đà Nẵng",         "benhnhan3"),
    ]

    mabn_list = []
    for mabn, hoten, ngaysinh, sdt, diachi, quequan, taikhoan in bn_data:
        # Insert HOSOBENHNHAN
        cur.execute("SELECT 1 FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?", mabn)
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO DBO.HOSOBENHNHAN (MABENHNHAN, HOVATEN, NGAYSINH, SODIENTHOAI, EMAIL, DIACHI, QUEQUAN)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, mabn, hoten, ngaysinh, sdt, DEFAULT_EMAIL, diachi, quequan)
            print(f"  + BN: {mabn} ({hoten})")

        # Insert DANGNHAP
        cur.execute("SELECT 1 FROM DBO.DANGNHAP WHERE TAIKHOAN=?", taikhoan)
        if not cur.fetchone():
            if pw_hash:
                cur.execute("""
                    INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, MATKHAU_HASH, ROLE, MABENHNHAN, EMAIL)
                    VALUES (?, ?, ?, 'patient', ?, ?)
                """, taikhoan, DEFAULT_PWD, pw_hash, mabn, DEFAULT_EMAIL)
            else:
                cur.execute("""
                    INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, ROLE, MABENHNHAN, EMAIL)
                    VALUES (?, ?, 'patient', ?, ?)
                """, taikhoan, DEFAULT_PWD, mabn, DEFAULT_EMAIL)
            print(f"  + Account: {taikhoan}/{DEFAULT_PWD} → {mabn}")
        else:
            # Update mabn link if needed
            cur.execute("UPDATE DBO.DANGNHAP SET MABENHNHAN=?, EMAIL=COALESCE(NULLIF(EMAIL,''),?) WHERE TAIKHOAN=?",
                        mabn, DEFAULT_EMAIL, taikhoan)

        mabn_list.append(mabn)

    BN1, BN2, BN3 = mabn_list

    # Ensure BS001 exists
    cur.execute("SELECT 1 FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN='BS001'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO DBO.QUANLINHANVIEN (MANHANVIEN, HOVATEN, KHOA, CHUYENMON, CHUCVU, TRINHDO)
            VALUES ('BS001', N'BS. Nguyễn Văn A', N'Khoa Nội', N'Nội tổng quát', N'Bác sĩ', N'Thạc sĩ')
        """)
        print("  + BS001 created")

    # ────────────────────────────────────────────────────
    # STEP 4: LICHHEN (5 lịch hẹn)
    # ────────────────────────────────────────────────────
    print("\n── Step 4: Lịch hẹn ──")

    # Check KHOA exists for reference
    cur.execute("SELECT TOP 1 TEN_KHOA FROM DBO.KHOA WHERE TRANG_THAI=1")
    khoa_row = cur.fetchone()
    khoa_name = khoa_row[0] if khoa_row else "Khoa Nội"

    lichhen_data = [
        (BN1, "BS001", TODAY,                  "08:00", "09:00", "PENDING",  "Khám tổng quát lần đầu"),
        (BN1, "BS001", TODAY + timedelta(1),   "09:00", "10:00", "APPROVED", "Tái khám theo lịch"),
        (BN2, "BS001", TODAY,                  "10:00", "11:00", "APPROVED", "Đau bụng, cần khám"),
        (BN2, "BS001", TODAY + timedelta(3),   "14:00", "15:00", "PENDING",  "Lấy kết quả xét nghiệm"),
        (BN3, "BS001", TODAY - timedelta(1),   "08:00", "09:00", "DONE",     "Khám hoàn tất - viêm họng"),
    ]

    # Count existing appointments for today to avoid duplicates
    cur.execute("SELECT COUNT(*) FROM DBO.LICHHEN WHERE MABENHNHAN IN (?,?,?)", BN1, BN2, BN3)
    existing_lh = cur.fetchone()[0]
    if existing_lh == 0:
        for mabn, manv, ngay, tg_bat, tg_ket, trangthai, ghichu in lichhen_data:
            tg_start = datetime.combine(ngay, datetime.strptime(tg_bat, "%H:%M").time())
            tg_end = datetime.combine(ngay, datetime.strptime(tg_ket, "%H:%M").time())
            # NGAY is a computed column (CAST(TGBATDAU AS DATE)), do NOT insert it
            cur.execute("""
                INSERT INTO DBO.LICHHEN (MABENHNHAN, MANHANVIEN, TGBATDAU, TGKETTHUC, TRANGTHAI, GHICHU)
                VALUES (?, ?, ?, ?, ?, ?)
            """, mabn, manv, tg_start, tg_end, trangthai, ghichu)
        print(f"  ✅ {len(lichhen_data)} lịch hẹn đã tạo")
    else:
        print(f"  ℹ️  Đã có {existing_lh} lịch hẹn cho BN test, skip")

    # ────────────────────────────────────────────────────
    # STEP 5: LAYSO_ONLINE (3 vé hôm nay)
    # ────────────────────────────────────────────────────
    print("\n── Step 5: Lấy số online ──")

    cur.execute("""
        SELECT COUNT(*) FROM DBO.LAYSO_ONLINE 
        WHERE MABENHNHAN IN (?,?,?) AND CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)
    """, BN1, BN2, BN3)
    existing_ls = cur.fetchone()[0]

    if existing_ls == 0:
        layso_data = [
            ("Khoa Nội", 1, BN1, "Nguyễn Văn Minh",  "WAITING"),
            ("Khoa Nội", 2, BN2, "Trần Thị Hương",    "WAITING"),
            ("Khoa Nhi", 1, BN3, "Lê Hoàng Nam",      "CALLED"),
        ]
        for khoa, stt, mabn, hoten, status in layso_data:
            cur.execute("""
                INSERT INTO DBO.LAYSO_ONLINE (KHOA, SO_THU_TU, MABENHNHAN, HOVATEN, CREATED_AT, STATUS)
                VALUES (?, ?, ?, ?, SYSDATETIME(), ?)
            """, khoa, stt, mabn, hoten, status)
        print(f"  ✅ {len(layso_data)} vé lấy số đã tạo")
    else:
        print(f"  ℹ️  Đã có {existing_ls} vé hôm nay, skip")

    # ────────────────────────────────────────────────────
    # STEP 6: PHIEUKHAM + CHANDOANCT + DONTHUOC + XETNGHIEM
    # ────────────────────────────────────────────────────
    print("\n── Step 6: Phiếu khám ──")

    # ── Phiếu 1: BN3, hôm qua, viêm họng ──
    cur.execute("SELECT COUNT(*) FROM DBO.PHIEUKHAM WHERE MABENHNHAN=? AND MANHANVIEN='BS001'", BN3)
    if cur.fetchone()[0] == 0:
        ngay_kham_1 = datetime.combine(TODAY - timedelta(1), datetime.strptime("08:30", "%H:%M").time())
        cur.execute("""
            INSERT INTO DBO.PHIEUKHAM (MABENHNHAN, MANHANVIEN, NGAYKHAM, KHOA, LYDOKHAM, CHANDOAN, PHIKHAM)
            OUTPUT INSERTED.MAPHIEU
            VALUES (?, 'BS001', ?, N'Khoa Nội', N'Đau họng, sốt nhẹ 2 ngày', N'Viêm họng cấp', 200000)
        """, BN3, ngay_kham_1)
        mp1 = int(cur.fetchone()[0])
        print(f"  + Phiếu #{mp1}: BN3 - Viêm họng")

        # Chẩn đoán
        cur.execute("""
            INSERT INTO DBO.CHANDOANCT (MAPHIEU, ICD10, MOTA, LACHINH)
            VALUES (?, 'J06.9', N'Viêm đường hô hấp trên cấp, không đặc hiệu', 1)
        """, mp1)
        cur.execute("""
            INSERT INTO DBO.CHANDOANCT (MAPHIEU, ICD10, MOTA, LACHINH)
            VALUES (?, 'R50.9', N'Sốt không rõ nguyên nhân', 0)
        """, mp1)

        # Đơn thuốc
        cur.execute("""
            INSERT INTO DBO.DONTHUOC (MAPHIEU, NGAYKE, BACSI, GHICHU)
            OUTPUT INSERTED.MADON
            VALUES (?, ?, 'BS001', N'Uống sau ăn, đủ liệu trình 7 ngày')
        """, mp1, ngay_kham_1)
        madon1 = int(cur.fetchone()[0])

        don1_ct = [
            ("TH001", "Amoxicillin 500mg", "500mg", "Ngày 3 lần, mỗi lần 1 viên", 21, "Viên"),
            ("TH004", "Paracetamol 500mg", "500mg", "Khi sốt > 38.5°C, cách 6h", 10, "Viên"),
            ("TH010", "Vitamin C 500mg",   "500mg", "Ngày 1 viên, uống sáng",       7,  "Viên"),
        ]
        for mathuoc, tenthuoc, hamluong, lieudung, sl, donvi in don1_ct:
            cur.execute("""
                INSERT INTO DBO.DONTHUOC_CT (MADON, MATHUOC, TENTHUOC, HAMLUONG, LIEUDUNG, SOLUONG, DONVI)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, madon1, mathuoc, tenthuoc, hamluong, lieudung, sl, donvi)

        # Xét nghiệm
        cur.execute("""
            INSERT INTO DBO.XETNGHIEM (MAPHIEU, LOAIXN, CHIDINH, GIA, NGAYCHIDINH, TRANGTHAI)
            VALUES (?, N'Xét nghiệm máu tổng quát', N'Kiểm tra bạch cầu, CRP', 150000, ?, N'DONE')
        """, mp1, ngay_kham_1)
        print(f"    ✅ Chẩn đoán (2) + Đơn thuốc (3 thuốc) + XN (1)")
    else:
        # Retrieve existing MAPHIEU for HĐ step
        cur.execute("SELECT TOP 1 MAPHIEU FROM DBO.PHIEUKHAM WHERE MABENHNHAN=? AND MANHANVIEN='BS001' ORDER BY MAPHIEU", BN3)
        mp1 = int(cur.fetchone()[0])
        print(f"  ℹ️  Phiếu #{mp1} đã tồn tại")

    # ── Phiếu 2: BN1, hôm nay, đau dạ dày ──
    cur.execute("SELECT COUNT(*) FROM DBO.PHIEUKHAM WHERE MABENHNHAN=? AND MANHANVIEN='BS001'", BN1)
    if cur.fetchone()[0] == 0:
        ngay_kham_2 = datetime.combine(TODAY, datetime.strptime("09:00", "%H:%M").time())
        cur.execute("""
            INSERT INTO DBO.PHIEUKHAM (MABENHNHAN, MANHANVIEN, NGAYKHAM, KHOA, LYDOKHAM, CHANDOAN, PHIKHAM)
            OUTPUT INSERTED.MAPHIEU
            VALUES (?, 'BS001', ?, N'Khoa Nội', N'Đau thượng vị, ợ chua 1 tuần', N'Viêm dạ dày', 350000)
        """, BN1, ngay_kham_2)
        mp2 = int(cur.fetchone()[0])
        print(f"  + Phiếu #{mp2}: BN1 - Viêm dạ dày")

        # Chẩn đoán
        cur.execute("""
            INSERT INTO DBO.CHANDOANCT (MAPHIEU, ICD10, MOTA, LACHINH)
            VALUES (?, 'K29.7', N'Viêm dạ dày, không đặc hiệu', 1)
        """, mp2)

        # Đơn thuốc
        cur.execute("""
            INSERT INTO DBO.DONTHUOC (MAPHIEU, NGAYKE, BACSI, GHICHU)
            OUTPUT INSERTED.MADON
            VALUES (?, ?, 'BS001', N'Uống trước ăn 30 phút, kiêng cay nóng')
        """, mp2, ngay_kham_2)
        madon2 = int(cur.fetchone()[0])

        don2_ct = [
            ("TH008", "Omeprazole 20mg",  "20mg",  "Ngày 2 lần, sáng chiều trước ăn", 30, "Viên"),
            ("TH009", "Domperidone 10mg",  "10mg",  "Ngày 3 lần, trước ăn 30 phút",    20, "Viên"),
            ("TH011", "Vitamin B Complex", "",       "Ngày 1 viên sau ăn",               14, "Viên"),
        ]
        for mathuoc, tenthuoc, hamluong, lieudung, sl, donvi in don2_ct:
            cur.execute("""
                INSERT INTO DBO.DONTHUOC_CT (MADON, MATHUOC, TENTHUOC, HAMLUONG, LIEUDUNG, SOLUONG, DONVI)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, madon2, mathuoc, tenthuoc, hamluong, lieudung, sl, donvi)

        # Xét nghiệm
        cur.execute("""
            INSERT INTO DBO.XETNGHIEM (MAPHIEU, LOAIXN, CHIDINH, GIA, NGAYCHIDINH, TRANGTHAI)
            VALUES (?, N'Siêu âm tổng quát', N'Siêu âm bụng kiểm tra dạ dày', 250000, ?, N'PENDING')
        """, mp2, ngay_kham_2)
        print(f"    ✅ Chẩn đoán (1) + Đơn thuốc (3 thuốc) + XN (1)")
    else:
        cur.execute("SELECT TOP 1 MAPHIEU FROM DBO.PHIEUKHAM WHERE MABENHNHAN=? AND MANHANVIEN='BS001' ORDER BY MAPHIEU", BN1)
        mp2 = int(cur.fetchone()[0])
        print(f"  ℹ️  Phiếu #{mp2} đã tồn tại")

    # ────────────────────────────────────────────────────
    # STEP 7: HOADON + HOADON_CT
    # ────────────────────────────────────────────────────
    print("\n── Step 7: Hóa đơn ──")

    # HĐ 1: Phiếu 1 (BN3) — ĐÃ THANH TOÁN
    cur.execute("SELECT 1 FROM DBO.HOADON WHERE PHIEUKHAM_ID=?", mp1)
    if not cur.fetchone():
        ngay_hd1 = datetime.combine(TODAY - timedelta(1), datetime.strptime("10:00", "%H:%M").time())
        cur.execute("""
            INSERT INTO DBO.HOADON (PHIEUKHAM_ID, NGAYLAP, TONGTIEN, DATHANHTOAN, HINHTHUC)
            OUTPUT INSERTED.ID
            VALUES (?, ?, 0, 1, 'CASH')
        """, mp1, ngay_hd1)
        hd1_id = int(cur.fetchone()[0])

        # Chi tiết HĐ1
        hd1_items = [
            ("SERVICE", "Phí khám tổng quát",                      1, 200000, str(mp1)),
            ("DRUG",    "Amoxicillin 500mg (Viên)",                21,   3000, "TH001"),
            ("DRUG",    "Paracetamol 500mg (Viên)",                10,   1500, "TH004"),
            ("DRUG",    "Vitamin C 500mg (Viên)",                   7,   1000, "TH010"),
            ("XN",      "Xét nghiệm máu tổng quát",                1, 150000, None),
        ]
        tong1 = 0
        for loai, mota, sl, gia, ref in hd1_items:
            cur.execute("""
                INSERT INTO DBO.HOADON_CT (HOADON_ID, LOAI, MOTA, SOLUONG, DONGIA, REF_ID)
                VALUES (?, ?, ?, ?, ?, ?)
            """, hd1_id, loai, mota, sl, gia, ref)
            tong1 += sl * gia

        cur.execute("UPDATE DBO.HOADON SET TONGTIEN=? WHERE ID=?", tong1, hd1_id)
        print(f"  + HĐ #{hd1_id}: {tong1:,.0f}đ — ĐÃ TT (CASH)")
    else:
        print(f"  ℹ️  HĐ cho phiếu #{mp1} đã tồn tại")

    # HĐ 2: Phiếu 2 (BN1) — CHƯA THANH TOÁN
    cur.execute("SELECT 1 FROM DBO.HOADON WHERE PHIEUKHAM_ID=?", mp2)
    if not cur.fetchone():
        ngay_hd2 = datetime.combine(TODAY, datetime.strptime("11:00", "%H:%M").time())
        cur.execute("""
            INSERT INTO DBO.HOADON (PHIEUKHAM_ID, NGAYLAP, TONGTIEN, DATHANHTOAN, HINHTHUC)
            OUTPUT INSERTED.ID
            VALUES (?, ?, 0, 0, NULL)
        """, mp2, ngay_hd2)
        hd2_id = int(cur.fetchone()[0])

        hd2_items = [
            ("SERVICE", "Phí khám chuyên khoa",                     1, 350000, str(mp2)),
            ("DRUG",    "Omeprazole 20mg (Viên)",                  30,   4000, "TH008"),
            ("DRUG",    "Domperidone 10mg (Viên)",                 20,   3500, "TH009"),
            ("DRUG",    "Vitamin B Complex (Viên)",                14,   2000, "TH011"),
            ("XN",      "Siêu âm tổng quát",                       1, 250000, None),
        ]
        tong2 = 0
        for loai, mota, sl, gia, ref in hd2_items:
            cur.execute("""
                INSERT INTO DBO.HOADON_CT (HOADON_ID, LOAI, MOTA, SOLUONG, DONGIA, REF_ID)
                VALUES (?, ?, ?, ?, ?, ?)
            """, hd2_id, loai, mota, sl, gia, ref)
            tong2 += sl * gia

        cur.execute("UPDATE DBO.HOADON SET TONGTIEN=? WHERE ID=?", tong2, hd2_id)
        print(f"  + HĐ #{hd2_id}: {tong2:,.0f}đ — CHƯA TT")
    else:
        print(f"  ℹ️  HĐ cho phiếu #{mp2} đã tồn tại")

    # ────────────────────────────────────────────────────
    # STEP 8: LICH_LAM_VIEC (BS001)
    # ────────────────────────────────────────────────────
    print("\n── Step 8: Lịch làm việc BS001 ──")

    lich_data = [
        (TODAY,                "Sáng",   "07:30", "11:30", "P101"),
        (TODAY + timedelta(1), "Chiều",  "13:30", "17:00", "P102"),
        (TODAY + timedelta(2), "Sáng",   "07:30", "11:30", "P101"),
        (TODAY + timedelta(3), "Sáng",   "07:30", "11:30", "P103"),
        (TODAY + timedelta(4), "Chiều",  "13:30", "17:00", "P102"),
    ]

    lich_count = 0
    for ngay, ca, tg_bat, tg_ket, phong in lich_data:
        cur.execute("""
            SELECT 1 FROM DBO.LICH_LAM_VIEC WHERE MANHANVIEN='BS001' AND NGAY=? AND CA=?
        """, ngay, ca)
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO DBO.LICH_LAM_VIEC (MANHANVIEN, NGAY, CA, TGBATDAU, TGKETTHUC, PHONG)
                VALUES ('BS001', ?, ?, ?, ?, ?)
            """, ngay, ca, tg_bat, tg_ket, phong)
            lich_count += 1
    print(f"  ✅ Lịch LV: {lich_count} mới / {len(lich_data)} tổng")

    # ────────────────────────────────────────────────────
    # STEP 9: PHONGBENH + GIUONGBENH
    # ────────────────────────────────────────────────────
    print("\n── Step 9: Phòng bệnh + Giường ──")

    phong_data = [
        ("P.Nội-01", "Khoa Nội",  "Điều trị", 4, "Hoạt động"),
        ("P.Nội-02", "Khoa Nội",  "Lưu viện", 2, "Hoạt động"),
        ("P.Nhi-01", "Khoa Nhi",  "Điều trị", 4, "Hoạt động"),
    ]

    for tenphong, khoa, loai, succhua, trangthai in phong_data:
        cur.execute("SELECT ID FROM DBO.PHONGBENH WHERE TENPHONG=?", tenphong)
        row = cur.fetchone()
        if not row:
            cur.execute("""
                INSERT INTO DBO.PHONGBENH (TENPHONG, KHOA, LOAI, SUCCHUA, TRANGTHAI)
                VALUES (?, ?, ?, ?, ?)
            """, tenphong, khoa, loai, succhua, trangthai)
            cur.execute("SELECT @@IDENTITY")
            phong_id = int(cur.fetchone()[0])
            print(f"  + Phòng: {tenphong} (ID={phong_id})")
        else:
            phong_id = row[0]

        # Giường cho phòng
        if tenphong == "P.Nội-01":
            giuong_list = [
                ("G-NỘI01-A", BN3,  NOW - timedelta(1), None,  "OCCUPIED"),
                ("G-NỘI01-B", None, None,                None,  "AVAILABLE"),
                ("G-NỘI01-C", None, None,                None,  "AVAILABLE"),
                ("G-NỘI01-D", None, None,                None,  "MAINTENANCE"),
            ]
        elif tenphong == "P.Nội-02":
            giuong_list = [
                ("G-NỘI02-A", None, None, None, "AVAILABLE"),
                ("G-NỘI02-B", None, None, None, "AVAILABLE"),
            ]
        else:
            giuong_list = [
                ("G-NHI01-A", None, None, None, "AVAILABLE"),
                ("G-NHI01-B", None, None, None, "AVAILABLE"),
                ("G-NHI01-C", None, None, None, "AVAILABLE"),
                ("G-NHI01-D", None, None, None, "AVAILABLE"),
            ]

        for tengiuong, mabn, ngayvao, ngayra, tt in giuong_list:
            cur.execute("SELECT 1 FROM DBO.GIUONGBENH WHERE TENGIUONG=? AND PHONG_ID=?", tengiuong, phong_id)
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO DBO.GIUONGBENH (PHONG_ID, TENGIUONG, MABENHNHAN, NGAYVAO, NGAYRA, TRANGTHAI)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, phong_id, tengiuong, mabn, ngayvao, ngayra, tt)

    print(f"  ✅ Phòng bệnh + giường đã seed")

    # ────────────────────────────────────────────────────
    # SUMMARY
    # ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🎉 SEED HOÀN TẤT!")
    print("=" * 60)
    print(f"""
📋 Tài khoản test:
  ┌──────────────────────────────────────────────────┐
  │  Role      │  Username   │  Password  │  Linked  │
  ├──────────────────────────────────────────────────┤
  │  Admin     │  admin      │  123456    │  -       │
  │  Doctor    │  bacsi1     │  123456    │  BS001   │
  │  Patient   │  benhnhan1  │  123456    │  {BN1}   │
  │  Patient   │  benhnhan2  │  123456    │  {BN2}   │
  │  Patient   │  benhnhan3  │  123456    │  {BN3}   │
  └──────────────────────────────────────────────────┘

📊 Dữ liệu seed:
  • Thuốc: 20 (6 nhóm)     • Dịch vụ: 10
  • Bệnh nhân: 3           • Lịch hẹn: 5
  • Lấy số: 3              • Phiếu khám: 2
  • Hóa đơn: 2 (1 đã TT + 1 chưa TT)
  • Lịch LV: 5 ca          • Phòng: 3 (10 giường)

🔑 Email OTP chung: {DEFAULT_EMAIL}
    """)

    cn.close()


if __name__ == "__main__":
    run()
