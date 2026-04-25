

import pyodbc
import os
import glob
import random
import uuid
import sys
from typing import List, Tuple
from dotenv import load_dotenv

# Common imports
try:
    from enums import LoaiXetNghiem
except ImportError:
    print("Warning: could not import LoaiXetNghiem from enums.py")
    LoaiXetNghiem = None

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("Warning: Vector DB dependencies not found. Ingestion step will fail if attempted.")

try:
    from argon2 import PasswordHasher
    ph = PasswordHasher()
except ImportError:
    print("Warning: argon2 not found. Account seeding will use plain text passwords.")
    ph = None

load_dotenv()

# Configuration
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "quanlibenhvien")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "210506")
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
    CONN_STR_MASTER = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        "DATABASE=master;"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )
else:
    CONN_STR = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        "TrustServerCertificate=yes;"
        "MARS_Connection=Yes;"
    )
    CONN_STR_MASTER = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        "DATABASE=master;"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )

# === DOCTORS DATA ===
HO_LIST = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Hồ", "Ngô", "Dương", "Lý"]
DEM_LIST = ["Văn", "Thị", "Hữu", "Minh", "Thu", "Ngọc", "Đức", "Thanh", "Mạnh", "Quang"]
TEN_LIST = ["Hùng", "Cường", "Dũng", "Lan", "Huệ", "Hoa", "Mai", "Tuấn", "Dat", "Khoa", "Long", "Giang", "Nhung", "Trang", "Thảo", "Vy"]
KHOA_LIST = [
    "Khoa Nội", "Khoa Ngoại", "Khoa Nhi", "Khoa Sản", 
    "Khoa Cấp Cứu", "Khoa Mắt", "Khoa Tai Mũi Họng", 
    "Khoa Răng Hàm Mặt", "Khoa Da Liễu", "Khoa Tim Mạch"
]
STREET_LIST = ["Nguyễn Huệ", "Lê Lợi", "Trần Hưng Đạo", "Hai Bà Trưng", "Lý Thường Kiệt", "Điện Biên Phủ", "Nguyễn Trãi"]
CITY_LIST = ["TP.Hồ Chí Minh", "Hà Nội", "Đà Nẵng", "Cần Thơ", "Hải Phòng"]
CHUCVU_LIST = ["Bác sĩ", "Trưởng khoa", "Phó khoa"]
TRINHDO_LIST = ["Thạc sĩ", "Tiến sĩ", "Bác sĩ CKI", "Bác sĩ CKII", "Đại học"]

# === INGEST CONFIG ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_DIR = os.path.join(BASE_DIR, "vectordb")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "knowledge_base")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120
BATCH_SIZE = 64

# === THEME CONFIG ===
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
THEME_CSS = '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'theme.css\') }}">'
THEME_JS = '<script src="{{ url_for(\'static\', filename=\'theme.js\') }}"></script>'

def get_connection(autocommit=False):
    return pyodbc.connect(CONN_STR, autocommit=autocommit)


# ============================================================
# STEP 0: Auto-create database if not exists
# ============================================================
def ensure_database():
    print("--- 0. Ensuring Database Exists ---")
    try:
        cn = pyodbc.connect(CONN_STR_MASTER, autocommit=True)
        cur = cn.cursor()
        cur.execute(f"SELECT DB_ID(N'{DB_NAME}')")
        if cur.fetchone()[0] is None:
            cur.execute(f"CREATE DATABASE [{DB_NAME}]")
            print(f"✅ Created database '{DB_NAME}'")
        else:
            print(f"✅ Database '{DB_NAME}' already exists")
        cn.close()
    except Exception as e:
        print(f"❌ Error ensuring database: {e}")
        print("   Please create the database manually and try again.")
        sys.exit(1)


# ============================================================
# STEP 1: Create ALL tables (idempotent - IF NOT EXISTS)
# ============================================================
def ensure_all_tables():
    print("\n--- 1. Ensuring All Tables Exist ---")
    try:
        cn = get_connection(autocommit=True)
        cur = cn.cursor()

        # Helper
        def table_exists(name):
            cur.execute(f"SELECT OBJECT_ID(N'DBO.{name}', N'U')")
            return cur.fetchone()[0] is not None

        def col_exists(table, col):
            cur.execute(f"""
                SELECT 1 FROM sys.columns
                WHERE Name=N'{col}' AND Object_ID=OBJECT_ID(N'DBO.{table}')
            """)
            return cur.fetchone() is not None

        # 1. QUANLINHANVIEN
        if not table_exists("QUANLINHANVIEN"):
            cur.execute("""
                CREATE TABLE DBO.QUANLINHANVIEN (
                    MANHANVIEN NVARCHAR(100) NOT NULL PRIMARY KEY,
                    HOVATEN    NVARCHAR(1000) NOT NULL,
                    CHUYENMON  NVARCHAR(100) NULL,
                    KHOA       NVARCHAR(100) NULL,
                    NGAYSINH   DATE NULL,
                    DIACHI     NVARCHAR(1000) NULL,
                    SOCCCD     NVARCHAR(100) NULL,
                    CHUCVU     NVARCHAR(100) NULL,
                    SDT        NVARCHAR(20) NULL,
                    TRINHDO    NVARCHAR(100) NULL,
                    EMAIL      NVARCHAR(200) NULL
                )
            """)
            print("  ✅ QUANLINHANVIEN")

        # 2. HOSOBENHNHAN
        if not table_exists("HOSOBENHNHAN"):
            cur.execute("""
                CREATE TABLE DBO.HOSOBENHNHAN (
                    MABENHNHAN   NVARCHAR(1000) NOT NULL PRIMARY KEY,
                    HOVATEN      NVARCHAR(1000) NOT NULL,
                    NGAYSINH     DATE,
                    SODIENTHOAI  NVARCHAR(20),
                    EMAIL        NVARCHAR(200),
                    DIACHI       NVARCHAR(1000),
                    QUEQUAN      NVARCHAR(1000),
                    DAXOA        BIT DEFAULT 0,
                    SO_THU_TU    INT
                )
            """)
            print("  ✅ HOSOBENHNHAN")
        else:
            if not col_exists("HOSOBENHNHAN", "SO_THU_TU"):
                cur.execute("ALTER TABLE DBO.HOSOBENHNHAN ADD SO_THU_TU INT")
                print("  ✅ Added SO_THU_TU to HOSOBENHNHAN")

        # 3. DANGNHAP
        if not table_exists("DANGNHAP"):
            cur.execute("""
                CREATE TABLE DBO.DANGNHAP (
                    TAIKHOAN     NVARCHAR(100) NOT NULL PRIMARY KEY,
                    MATKHAU      NVARCHAR(255),
                    MATKHAU_HASH NVARCHAR(500),
                    ROLE         NVARCHAR(20) DEFAULT 'patient',
                    MANHANVIEN   NVARCHAR(100),
                    MABENHNHAN   NVARCHAR(1000),
                    EMAIL        NVARCHAR(200),
                    TOTP_SECRET  NVARCHAR(200),
                    TOTP_ENABLED BIT DEFAULT 0
                )
            """)
            print("  ✅ DANGNHAP")
        else:
            # Ensure columns exist for older schemas
            for col, dtype in [("MANHANVIEN","NVARCHAR(100)"), ("MABENHNHAN","NVARCHAR(1000)"), ("MATKHAU_HASH","NVARCHAR(500)"), ("EMAIL","NVARCHAR(200)"), ("TOTP_SECRET","NVARCHAR(200)"), ("TOTP_ENABLED","BIT DEFAULT 0")]:
                if not col_exists("DANGNHAP", col):
                    cur.execute(f"ALTER TABLE DBO.DANGNHAP ADD {col} {dtype}")
                    print(f"  ✅ Added {col} to DANGNHAP")

        # 4. DICHVU
        if not table_exists("DICHVU"):
            cur.execute("""
                CREATE TABLE DBO.DICHVU (
                    ID        INT IDENTITY(1,1) PRIMARY KEY,
                    TENDICHVU NVARCHAR(200) NOT NULL,
                    GIA       DECIMAL(18,2) DEFAULT 0,
                    MOTA      NVARCHAR(500),
                    KHOA_NUM  INT NULL
                )
            """)
            print("  ✅ DICHVU")

        # 5. PHIEUKHAM
        if not table_exists("PHIEUKHAM"):
            cur.execute("""
                CREATE TABLE DBO.PHIEUKHAM (
                    MAPHIEU     INT IDENTITY(1,1) PRIMARY KEY,
                    MABENHNHAN  NVARCHAR(1000),
                    MANHANVIEN  NVARCHAR(100),
                    NGAYKHAM    DATETIME DEFAULT GETDATE(),
                    KHOA        NVARCHAR(100),
                    LYDOKHAM    NVARCHAR(500),
                    CHANDOAN    NVARCHAR(1000),
                    GHICHU      NVARCHAR(1000),
                    PHIKHAM     DECIMAL(18,2) DEFAULT 0
                )
            """)
            print("  ✅ PHIEUKHAM")

        # 6. CHANDOANCT
        if not table_exists("CHANDOANCT"):
            cur.execute("""
                CREATE TABLE DBO.CHANDOANCT (
                    ID       INT IDENTITY(1,1) PRIMARY KEY,
                    MAPHIEU  INT REFERENCES DBO.PHIEUKHAM(MAPHIEU) ON DELETE CASCADE,
                    ICD10    NVARCHAR(20),
                    MOTA     NVARCHAR(500),
                    LACHINH  BIT DEFAULT 0
                )
            """)
            print("  ✅ CHANDOANCT")

        # 7. XETNGHIEM
        if not table_exists("XETNGHIEM"):
            cur.execute("""
                CREATE TABLE DBO.XETNGHIEM (
                    MAXN         INT IDENTITY(1,1) PRIMARY KEY,
                    MAPHIEU      INT REFERENCES DBO.PHIEUKHAM(MAPHIEU) ON DELETE CASCADE,
                    LOAIXN       NVARCHAR(100),
                    CHIDINH      NVARCHAR(500),
                    NGAYCHIDINH  DATETIME DEFAULT GETDATE(),
                    TRANGTHAI    NVARCHAR(50) DEFAULT N'Chờ kết quả',
                    GIA          DECIMAL(18,2) DEFAULT 0
                )
            """)
            print("  ✅ XETNGHIEM")

        # 8. KETQUAXN
        if not table_exists("KETQUAXN"):
            cur.execute("""
                CREATE TABLE DBO.KETQUAXN (
                    ID           INT IDENTITY(1,1) PRIMARY KEY,
                    MAXN         INT REFERENCES DBO.XETNGHIEM(MAXN) ON DELETE CASCADE,
                    CHISO        NVARCHAR(200),
                    GIATRI       NVARCHAR(200),
                    DONVI        NVARCHAR(50),
                    MOCTHAMCHIEU NVARCHAR(200),
                    DANHGIA      NVARCHAR(200),
                    FILEURL      NVARCHAR(500)
                )
            """)
            print("  ✅ KETQUAXN")

        # 9. NHOMTHUOC
        if not table_exists("NHOMTHUOC"):
            cur.execute("""
                CREATE TABLE DBO.NHOMTHUOC (
                    ID   INT IDENTITY(1,1) PRIMARY KEY,
                    TEN  NVARCHAR(255) NOT NULL,
                    MOTA NVARCHAR(MAX) NULL
                )
            """)
            print("  ✅ NHOMTHUOC")

        # 10. THUOC
        if not table_exists("THUOC"):
            cur.execute("""
                CREATE TABLE DBO.THUOC (
                    MATHUOC     NVARCHAR(50) NOT NULL PRIMARY KEY,
                    TENTHUOC    NVARCHAR(500) NOT NULL,
                    DONVI       NVARCHAR(50),
                    HANSUDUNG   DATE,
                    GIA         DECIMAL(18,2) DEFAULT 0,
                    TONKHO      INT DEFAULT 0,
                    TONTOITHIEU INT DEFAULT 0,
                    NHOM_ID     INT NULL,
                    IS_ACTIVE   BIT DEFAULT 1
                )
            """)
            print("  ✅ THUOC")

        # 11. DONTHUOC
        if not table_exists("DONTHUOC"):
            cur.execute("""
                CREATE TABLE DBO.DONTHUOC (
                    MADON       INT IDENTITY(1,1) PRIMARY KEY,
                    MAPHIEU     INT REFERENCES DBO.PHIEUKHAM(MAPHIEU) ON DELETE CASCADE,
                    MABENHNHAN  NVARCHAR(1000),
                    NGAYKE      DATETIME DEFAULT GETDATE(),
                    BACSI       NVARCHAR(200),
                    GHICHU      NVARCHAR(1000)
                )
            """)
            print("  ✅ DONTHUOC")

        # 12. DONTHUOC_CT
        if not table_exists("DONTHUOC_CT"):
            cur.execute("""
                CREATE TABLE DBO.DONTHUOC_CT (
                    ID        INT IDENTITY(1,1) PRIMARY KEY,
                    MADON     INT REFERENCES DBO.DONTHUOC(MADON) ON DELETE CASCADE,
                    MATHUOC   NVARCHAR(50),
                    TENTHUOC  NVARCHAR(500),
                    HAMLUONG  NVARCHAR(200),
                    LIEUDUNG  NVARCHAR(500),
                    SOLUONG   DECIMAL(18,2) DEFAULT 0,
                    DONVI     NVARCHAR(50),
                    GHICHU    NVARCHAR(500)
                )
            """)
            print("  ✅ DONTHUOC_CT")

        # 13. HOADON
        if not table_exists("HOADON"):
            cur.execute("""
                CREATE TABLE DBO.HOADON (
                    ID              INT IDENTITY(1,1) PRIMARY KEY,
                    PHIEUKHAM_ID    INT,
                    NGAYLAP         DATETIME DEFAULT GETDATE(),
                    TONGTIEN        DECIMAL(18,2) DEFAULT 0,
                    DATHANHTOAN     BIT DEFAULT 0,
                    HINHTHUC        NVARCHAR(50) DEFAULT 'CASH',
                    VNPAY_TMN_CODE       NVARCHAR(50),
                    VNPAY_TXNREF         NVARCHAR(100),
                    VNPAY_TRANSACTIONNO  NVARCHAR(100),
                    VNPAY_BANKCODE       NVARCHAR(50),
                    VNPAY_CARDTYPE       NVARCHAR(50),
                    VNPAY_PAYDATE        NVARCHAR(50),
                    VNPAY_RESPONSECODE   NVARCHAR(10),
                    VNPAY_SECUREHASH     NVARCHAR(500),
                    VNPAY_STATUS         NVARCHAR(20)
                )
            """)
            print("  ✅ HOADON")

        # 14. HOADON_CT
        if not table_exists("HOADON_CT"):
            cur.execute("""
                CREATE TABLE DBO.HOADON_CT (
                    ID        INT IDENTITY(1,1) PRIMARY KEY,
                    HOADON_ID INT REFERENCES DBO.HOADON(ID) ON DELETE CASCADE,
                    LOAI      NVARCHAR(50),
                    MOTA      NVARCHAR(500),
                    SOLUONG   INT DEFAULT 1,
                    DONGIA    DECIMAL(18,2) DEFAULT 0,
                    REF_ID    NVARCHAR(100)
                )
            """)
            print("  ✅ HOADON_CT")

        # 15. HOSODINHKEM
        if not table_exists("HOSODINHKEM"):
            cur.execute("""
                CREATE TABLE DBO.HOSODINHKEM (
                    ID          INT IDENTITY(1,1) PRIMARY KEY,
                    MABENHNHAN  NVARCHAR(1000),
                    MAPHIEU     INT,
                    TENTEP      NVARCHAR(500),
                    LOAITEP     NVARCHAR(100),
                    URL         NVARCHAR(1000),
                    GHICHU      NVARCHAR(500),
                    NGAYTAI     DATETIME DEFAULT GETDATE()
                )
            """)
            print("  ✅ HOSODINHKEM")

        # 16. LAYSO_ONLINE
        if not table_exists("LAYSO_ONLINE"):
            cur.execute("""
                CREATE TABLE DBO.LAYSO_ONLINE (
                    ID          INT IDENTITY(1,1) PRIMARY KEY,
                    KHOA        NVARCHAR(100),
                    SO_THU_TU   INT,
                    MABENHNHAN  NVARCHAR(1000),
                    HOVATEN     NVARCHAR(200),
                    STATUS      NVARCHAR(20) DEFAULT 'WAITING',
                    CREATED_AT  DATETIME DEFAULT GETDATE()
                )
            """)
            print("  ✅ LAYSO_ONLINE")

        # 17. LICH_LAM_VIEC
        if not table_exists("LICH_LAM_VIEC"):
            cur.execute("""
                CREATE TABLE DBO.LICH_LAM_VIEC (
                    ID          INT IDENTITY(1,1) PRIMARY KEY,
                    MANHANVIEN  NVARCHAR(100),
                    NGAY        DATE,
                    BUOI        NVARCHAR(20),
                    GIO_BAT_DAU NVARCHAR(10),
                    GIO_KET_THUC NVARCHAR(10),
                    TRANGTHAI   NVARCHAR(20) DEFAULT 'ACTIVE'
                )
            """)
            print("  ✅ LICH_LAM_VIEC")

        # 18. LICHHEN
        if not table_exists("LICHHEN"):
            cur.execute("""
                CREATE TABLE DBO.LICHHEN (
                    ID          INT IDENTITY(1,1) PRIMARY KEY,
                    MABENHNHAN  NVARCHAR(1000),
                    MANHANVIEN  NVARCHAR(100),
                    TGBATDAU    DATETIME,
                    TGKETTHUC   DATETIME,
                    TRANGTHAI   NVARCHAR(20) DEFAULT 'PENDING',
                    GHICHU      NVARCHAR(500),
                    STT         INT,
                    NGAY AS CAST(TGBATDAU AS DATE)
                )
            """)
            print("  ✅ LICHHEN")

        # 19. KHOA
        if not table_exists("KHOA"):
            cur.execute("""
                CREATE TABLE DBO.KHOA (
                    ID        INT IDENTITY(1,1) PRIMARY KEY,
                    TEN_KHOA  NVARCHAR(200) NOT NULL,
                    MO_TA     NVARCHAR(500),
                    TRANG_THAI BIT DEFAULT 1
                )
            """)
            print("  ✅ KHOA")

        # 20. PHONGBENH
        if not table_exists("PHONGBENH"):
            cur.execute("""
                CREATE TABLE DBO.PHONGBENH (
                    ID        INT IDENTITY(1,1) PRIMARY KEY,
                    TENPHONG  NVARCHAR(100) NOT NULL,
                    KHOA      NVARCHAR(200),
                    LOAI      NVARCHAR(50),
                    SUCCHUA   INT DEFAULT 0,
                    TRANGTHAI NVARCHAR(20) DEFAULT 'AVAILABLE'
                )
            """)
            print("  ✅ PHONGBENH")

        # 21. GIUONGBENH
        if not table_exists("GIUONGBENH"):
            cur.execute("""
                CREATE TABLE DBO.GIUONGBENH (
                    ID          INT IDENTITY(1,1) PRIMARY KEY,
                    PHONG_ID    INT REFERENCES DBO.PHONGBENH(ID),
                    TENGIUONG   NVARCHAR(50),
                    MABENHNHAN  NVARCHAR(1000),
                    NGAYVAO     DATETIME,
                    NGAYRA      DATETIME,
                    TRANGTHAI   NVARCHAR(20) DEFAULT 'AVAILABLE'
                )
            """)
            print("  ✅ GIUONGBENH")

        # 22. XUATNHAP_KHO
        if not table_exists("XUATNHAP_KHO"):
            cur.execute("""
                CREATE TABLE DBO.XUATNHAP_KHO (
                    ID        INT IDENTITY(1,1) PRIMARY KEY,
                    MATHUOC   NVARCHAR(50),
                    LOAI      NVARCHAR(10),
                    SOLUONG   INT DEFAULT 0,
                    NGAYGD    DATETIME DEFAULT GETDATE(),
                    THAMCHIEU NVARCHAR(200),
                    GHICHU    NVARCHAR(500)
                )
            """)
            print("  ✅ XUATNHAP_KHO")

        # 23-24. LOAI_XET_NGHIEM + CHI_DINH_XET_NGHIEM
        if not table_exists("LOAI_XET_NGHIEM"):
            cur.execute("""
                CREATE TABLE DBO.LOAI_XET_NGHIEM (
                    ID       INT IDENTITY(1,1) PRIMARY KEY,
                    TEN_LOAI NVARCHAR(100) NOT NULL UNIQUE,
                    MO_TA    NVARCHAR(255)
                )
            """)
            print("  ✅ LOAI_XET_NGHIEM")

        if not table_exists("CHI_DINH_XET_NGHIEM"):
            cur.execute("""
                CREATE TABLE DBO.CHI_DINH_XET_NGHIEM (
                    ID             INT IDENTITY(1,1) PRIMARY KEY,
                    LOAI_ID        INT NOT NULL REFERENCES DBO.LOAI_XET_NGHIEM(ID) ON DELETE CASCADE,
                    TEN_CHI_DINH   NVARCHAR(200) NOT NULL,
                    GIA_THAM_KHAO  DECIMAL(18,2) DEFAULT 0,
                    DON_VI         NVARCHAR(50)
                )
            """)
            print("  ✅ CHI_DINH_XET_NGHIEM")

        # Ensure KHOA_NUM column on DICHVU
        if table_exists("DICHVU") and not col_exists("DICHVU", "KHOA_NUM"):
            cur.execute("ALTER TABLE DBO.DICHVU ADD KHOA_NUM INT NULL")
            print("  ✅ Added KHOA_NUM to DICHVU")

        # Ensure NHOM_ID column on THUOC
        if table_exists("THUOC") and not col_exists("THUOC", "NHOM_ID"):
            cur.execute("ALTER TABLE DBO.THUOC ADD NHOM_ID INT NULL")
            print("  ✅ Added NHOM_ID to THUOC")

        # Count
        cur.execute("SELECT COUNT(*) FROM sys.tables")
        print(f"\n  📊 Total tables: {cur.fetchone()[0]}")
        cn.close()
    except Exception as e:
        print(f"❌ Error ensuring tables: {e}")


# ============================================================
# STEP 2: Create ALL stored procedures (inline, no SQL files)
# ============================================================
def ensure_stored_procedures():
    print("\n--- 2. Ensuring Stored Procedures ---")
    try:
        cn = get_connection(autocommit=True)
        cur = cn.cursor()

        def sp_exists(name):
            cur.execute(f"SELECT OBJECT_ID(N'DBO.{name}', N'P')")
            return cur.fetchone()[0] is not None

        # SP 1: sp_LaySo_ListToday
        if not sp_exists("sp_LaySo_ListToday"):
            cur.execute("""
                CREATE PROCEDURE DBO.sp_LaySo_ListToday
                    @Khoa NVARCHAR(100) = NULL
                AS
                BEGIN
                    SET NOCOUNT ON;
                    SELECT ID, KHOA, SO_THU_TU, HOVATEN, STATUS, CREATED_AT
                    FROM DBO.LAYSO_ONLINE
                    WHERE CAST(CREATED_AT AS DATE) = CAST(GETDATE() AS DATE)
                      AND (@Khoa IS NULL OR KHOA = @Khoa)
                    ORDER BY SO_THU_TU ASC;
                END
            """)
            print("  ✅ sp_LaySo_ListToday")

        # SP 2: sp_LaySo_GetCurrent
        if not sp_exists("sp_LaySo_GetCurrent"):
            cur.execute("""
                CREATE PROCEDURE DBO.sp_LaySo_GetCurrent
                    @Khoa NVARCHAR(100)
                AS
                BEGIN
                    SET NOCOUNT ON;
                    SELECT TOP 1 ID, KHOA, SO_THU_TU, HOVATEN, STATUS, CREATED_AT
                    FROM DBO.LAYSO_ONLINE
                    WHERE KHOA = @Khoa
                      AND CAST(CREATED_AT AS DATE) = CAST(GETDATE() AS DATE)
                      AND STATUS = 'CALLING'
                    ORDER BY SO_THU_TU DESC;
                END
            """)
            print("  ✅ sp_LaySo_GetCurrent")

        # SP 3: sp_LaySo_Next
        if not sp_exists("sp_LaySo_Next"):
            cur.execute("""
                CREATE PROCEDURE DBO.sp_LaySo_Next
                    @Khoa NVARCHAR(100)
                AS
                BEGIN
                    SET NOCOUNT ON;
                    DECLARE @NextID INT;

                    UPDATE DBO.LAYSO_ONLINE SET STATUS = 'DONE'
                    WHERE KHOA = @Khoa AND STATUS = 'CALLING'
                      AND CAST(CREATED_AT AS DATE) = CAST(GETDATE() AS DATE);

                    SELECT TOP 1 @NextID = ID
                    FROM DBO.LAYSO_ONLINE
                    WHERE KHOA = @Khoa AND STATUS = 'WAITING'
                      AND CAST(CREATED_AT AS DATE) = CAST(GETDATE() AS DATE)
                    ORDER BY SO_THU_TU ASC;

                    IF @NextID IS NOT NULL
                    BEGIN
                        UPDATE DBO.LAYSO_ONLINE SET STATUS = 'CALLING' WHERE ID = @NextID;
                        SELECT * FROM DBO.LAYSO_ONLINE WHERE ID = @NextID;
                    END
                END
            """)
            print("  ✅ sp_LaySo_Next")

        # SP 4: sp_LaySo_SetStatus
        if not sp_exists("sp_LaySo_SetStatus"):
            cur.execute("""
                CREATE PROCEDURE DBO.sp_LaySo_SetStatus
                    @Id INT,
                    @Status NVARCHAR(20)
                AS
                BEGIN
                    UPDATE DBO.LAYSO_ONLINE SET STATUS = @Status WHERE ID = @Id;
                    SELECT @@ROWCOUNT AS affected;
                END
            """)
            print("  ✅ sp_LaySo_SetStatus")

        # SP 5: sp_PhieuKham_TongHop
        if not sp_exists("sp_PhieuKham_TongHop"):
            cur.execute("""
                CREATE PROCEDURE DBO.sp_PhieuKham_TongHop
                    @MaPhieu INT
                AS
                BEGIN
                    SET NOCOUNT ON;
                    SELECT pk.MAPHIEU, pk.MABENHNHAN, bn.HOVATEN,
                           CONVERT(VARCHAR(10), bn.NGAYSINH, 23) AS NGAYSINH,
                           bn.SODIENTHOAI, bn.DIACHI,
                           CONVERT(VARCHAR(16), pk.NGAYKHAM, 120) AS NGAYKHAM,
                           pk.KHOA, pk.LYDOKHAM, pk.CHANDOAN, pk.GHICHU,
                           nv.HOVATEN AS TENBACSI
                    FROM DBO.PHIEUKHAM pk
                    LEFT JOIN DBO.HOSOBENHNHAN bn ON pk.MABENHNHAN = bn.MABENHNHAN
                    LEFT JOIN DBO.QUANLINHANVIEN nv ON pk.MANHANVIEN = nv.MANHANVIEN
                    WHERE pk.MAPHIEU = @MaPhieu;

                    SELECT N'Xét nghiệm' AS LOAI, LOAIXN AS MOTA, 1 AS SOLUONG,
                           ISNULL(GIA,0) AS DONGIA, ISNULL(GIA,0) AS THANHTIEN
                    FROM DBO.XETNGHIEM WHERE MAPHIEU = @MaPhieu AND ISNULL(GIA,0) > 0
                    UNION ALL
                    SELECT N'Thuốc', ct.TENTHUOC + N' (' + ISNULL(ct.DONVI,N'') + N')',
                           ISNULL(ct.SOLUONG,0), ISNULL(t.GIA,0),
                           ISNULL(ct.SOLUONG,0) * ISNULL(t.GIA,0)
                    FROM DBO.DONTHUOC d
                    JOIN DBO.DONTHUOC_CT ct ON ct.MADON = d.MADON
                    LEFT JOIN DBO.THUOC t ON t.MATHUOC = ct.MATHUOC
                    WHERE d.MAPHIEU = @MaPhieu;
                END
            """)
            print("  ✅ sp_PhieuKham_TongHop")

        cn.close()
    except Exception as e:
        print(f"❌ Error ensuring SPs: {e}")


# ============================================================
# STEP 3: Seed accounts (admin + bacsi1) + link schema
# ============================================================
def seed_accounts():
    print("\n--- 3. Seeding Accounts ---")
    try:
        cn = get_connection(autocommit=True)
        cur = cn.cursor()

        # Ensure BS001 exists in QUANLINHANVIEN
        cur.execute("SELECT 1 FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN='BS001'")
        if not cur.fetchone():
            cur.execute("INSERT INTO DBO.QUANLINHANVIEN (MANHANVIEN, HOVATEN, KHOA) VALUES ('BS001', N'Nguyễn Văn A', N'Khoa Nội')")
            print("  ✅ Created doctor BS001")

        # Hash password
        pwd = "123456"
        default_email = "lamkhoi.dev@gmail.com"
        hashed = ph.hash(pwd) if ph else None

        # Admin account
        cur.execute("SELECT 1 FROM DBO.DANGNHAP WHERE TAIKHOAN='admin'")
        if not cur.fetchone():
            if hashed:
                cur.execute("INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, MATKHAU_HASH, ROLE, EMAIL) VALUES ('admin', ?, ?, 'admin', ?)", pwd, hashed, default_email)
            else:
                cur.execute("INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, ROLE, EMAIL) VALUES ('admin', ?, 'admin', ?)", pwd, default_email)
            print("  ✅ Admin account created (admin/123456)")
        else:
            cur.execute("UPDATE DBO.DANGNHAP SET EMAIL=? WHERE TAIKHOAN='admin' AND (EMAIL IS NULL OR EMAIL='')", default_email)
            print("  ℹ️  Admin account already exists")

        # Doctor account
        cur.execute("SELECT 1 FROM DBO.DANGNHAP WHERE TAIKHOAN='bacsi1'")
        if not cur.fetchone():
            if hashed:
                cur.execute("INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, MATKHAU_HASH, ROLE, MANHANVIEN, EMAIL) VALUES ('bacsi1', ?, ?, 'doctor', 'BS001', ?)", pwd, hashed, default_email)
            else:
                cur.execute("INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, ROLE, MANHANVIEN, EMAIL) VALUES ('bacsi1', ?, 'doctor', 'BS001', ?)", pwd, default_email)
            print("  ✅ Doctor account created (bacsi1/123456)")
        else:
            cur.execute("UPDATE DBO.DANGNHAP SET MANHANVIEN='BS001', EMAIL=COALESCE(NULLIF(EMAIL,''), ?) WHERE TAIKHOAN='bacsi1'", default_email)
            print("  ℹ️  bacsi1 already exists, linked to BS001")

        cn.close()
    except Exception as e:
        print(f"❌ Error seeding accounts: {e}")


# ============================================================
# STEP 3b: Seed KHOA (departments)
# ============================================================
def seed_khoa():
    print("\n--- 3b. Seeding Departments (KHOA) ---")
    try:
        cn = get_connection(autocommit=True)
        cur = cn.cursor()
        cur.execute("SELECT COUNT(*) FROM DBO.KHOA")
        if cur.fetchone()[0] > 0:
            print("  ✅ KHOA already has data. Skipping.")
            cn.close()
            return

        khoas = [
            "Khoa Nội", "Khoa Ngoại", "Khoa Nhi", "Khoa Sản",
            "Khoa Cấp Cứu", "Khoa Mắt", "Khoa Tai Mũi Họng",
            "Khoa Răng Hàm Mặt", "Khoa Da Liễu", "Khoa Tim Mạch"
        ]
        for k in khoas:
            cur.execute("INSERT INTO DBO.KHOA (TEN_KHOA, TRANG_THAI) VALUES (?, 1)", k)
        print(f"  ✅ Seeded {len(khoas)} departments")
        cn.close()
    except Exception as e:
        print(f"❌ Error seeding KHOA: {e}")

# ============================================================
# STEP 4: Seed doctors
# ============================================================
def generate_name():
    ho = random.choice(HO_LIST)
    dem = random.choice(DEM_LIST)
    ten = random.choice(TEN_LIST)
    if random.random() < 0.2:
        dem2 = random.choice(DEM_LIST)
        return f"BS. {ho} {dem} {dem2} {ten}"
    return f"BS. {ho} {dem} {ten}"

def seed_doctors():
    print("\n--- 4. Seeding Doctors ---")
    try:
        cn = get_connection()
        cur = cn.cursor()

        cur.execute("SELECT COUNT(*) FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN LIKE 'BS%'")
        count = cur.fetchone()[0]

        if count >= 10:
            print(f"  ✅ Already has {count} doctors. Skipping.")
        else:
            cur.execute("SELECT MAX(MANHANVIEN) FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN LIKE 'BS%'")
            row = cur.fetchone()
            start_num = 1
            if row and row[0]:
                try:
                    start_num = int(row[0][2:]) + 1
                except ValueError:
                    pass

            limit = 30
            print(f"  Adding {limit} doctors starting from ID {start_num}...")

            for i in range(limit):
                current_num = start_num + i
                manv = f"BS{current_num:03d}"
                hoten = generate_name()
                khoa = random.choice(KHOA_LIST)
                ngaysinh = f"{random.randint(1970, 1995)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
                diachi = f"{random.randint(1, 999)} {random.choice(STREET_LIST)}, {random.choice(CITY_LIST)}"
                socccd = f"0{random.randint(10000000000, 99999999999)}"
                chucvu = random.choices(CHUCVU_LIST, weights=[80, 10, 10], k=1)[0]
                sdt = f"09{random.randint(10000000, 99999999)}"
                trinhdo = random.choice(TRINHDO_LIST)

                cur.execute("""
                    INSERT INTO DBO.QUANLINHANVIEN
                    (MANHANVIEN, HOVATEN, KHOA, CHUYENMON, NGAYSINH, DIACHI, SOCCCD, CHUCVU, SDT, TRINHDO)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (manv, hoten, khoa, khoa, ngaysinh, diachi, socccd, chucvu, sdt, trinhdo))

            cn.commit()
            print(f"  ✅ Added {limit} doctors.")
        cn.close()
    except Exception as e:
        print(f"❌ Error seeding doctors: {e}")


# ============================================================
# STEP 5: Seed lab test types
# ============================================================
def seed_xetnghiem():
    print("\n--- 5. Seeding Lab Test Types ---")
    if LoaiXetNghiem is None:
        print("  Skipping (missing enums.py)")
        return

    try:
        cn = get_connection()
        cur = cn.cursor()

        sample_indications = {
            LoaiXetNghiem.TONG_QUAT: [("Tổng phân tích tế bào máu", 50000, "Lần"), ("Xét nghiệm nước tiểu 10 thông số", 40000, "Lần")],
            LoaiXetNghiem.HUYET_HOC: [("Công thức máu (CBC)", 60000, "Lần"), ("Nhóm máu (ABO, Rh)", 80000, "Lần"), ("Tốc độ máu lắng (VS)", 30000, "mm/h")],
            LoaiXetNghiem.SINH_HOA: [("Glucose (Đường huyết lúc đói)", 35000, "mmol/L"), ("Urea", 35000, "mmol/L"), ("Creatinine", 40000, "µmol/L"), ("AST (GOT)", 40000, "U/L"), ("ALT (GPT)", 40000, "U/L"), ("Cholesterol toàn phần", 50000, "mmol/L"), ("Triglyceride", 50000, "mmol/L")],
            LoaiXetNghiem.VI_SINH: [("Nuôi cấy vi khuẩn", 150000, "Lần"), ("Soi tươi dịch âm đạo", 60000, "Lần")],
            LoaiXetNghiem.MIEN_DICH: [("HBsAg (Test nhanh)", 80000, "Lần"), ("HCV Ab (Test nhanh)", 100000, "Lần")],
            LoaiXetNghiem.NUOC_TIEU: [("Tổng phân tích nước tiểu", 40000, "Lần"), ("Cặn Addis", 30000, "Lần")],
            LoaiXetNghiem.CHUC_NANG_GAN: [("Bilirubin T.P/T.T/G.T", 45000, "µmol/L"), ("GGT", 50000, "U/L"), ("Albumin", 40000, "g/dL")],
            LoaiXetNghiem.CHUC_NANG_THAN: [("Điện giải đồ (Na, K, Cl)", 60000, "mmol/L"), ("Acid Uric", 40000, "µmol/L")],
            LoaiXetNghiem.TUYEN_GIAP: [("TSH", 120000, "µU/mL"), ("T3", 100000, "nmol/L"), ("FT4", 100000, "pmol/L")]
        }

        for xn in LoaiXetNghiem:
            ten_loai = xn.value
            cur.execute("SELECT ID FROM DBO.LOAI_XET_NGHIEM WHERE TEN_LOAI = ?", ten_loai)
            row = cur.fetchone()
            if not row:
                cur.execute("INSERT INTO DBO.LOAI_XET_NGHIEM (TEN_LOAI) VALUES (?)", ten_loai)
                cn.commit()
                cur.execute("SELECT @@IDENTITY")
                loai_id = cur.fetchone()[0]
                print(f"  Inserted: {ten_loai}")
            else:
                loai_id = row[0]

            if xn in sample_indications:
                for ten_cd, gia, don_vi in sample_indications[xn]:
                    cur.execute("SELECT 1 FROM DBO.CHI_DINH_XET_NGHIEM WHERE LOAI_ID=? AND TEN_CHI_DINH=?", loai_id, ten_cd)
                    if not cur.fetchone():
                        cur.execute("INSERT INTO DBO.CHI_DINH_XET_NGHIEM (LOAI_ID, TEN_CHI_DINH, GIA_THAM_KHAO, DON_VI) VALUES (?,?,?,?)", loai_id, ten_cd, gia, don_vi)
                        print(f"    + {ten_cd}")

        cn.commit()
        print("  ✅ Lab test seeding completed.")
        cn.close()
    except Exception as e:
        print(f"❌ Error seeding lab tests: {e}")


# ============================================================
# STEP 6: Theme injection
# ============================================================
def inject_theme():
    print("\n--- 6. Injecting Theme ---")
    if not os.path.exists(TEMPLATE_DIR):
        print(f"  Template directory not found: {TEMPLATE_DIR}")
        return

    files = glob.glob(os.path.join(TEMPLATE_DIR, '*.html'))
    for filepath in files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            modified = False
            if 'filename=\'theme.css\'' not in content and 'filename="theme.css"' not in content:
                lower_content = content.lower()
                idx_link = lower_content.find('<link rel="stylesheet"')
                if idx_link == -1: idx_link = lower_content.find("<link rel='stylesheet'")
                idx_head_close = lower_content.find('</head>')
                insert_pos = idx_link if idx_link != -1 else idx_head_close
                if insert_pos != -1:
                    content = content[:insert_pos] + THEME_CSS + '\n  ' + content[insert_pos:]
                    print(f"  Inserted CSS into {os.path.basename(filepath)}")
                    modified = True

            if 'filename=\'theme.js\'' not in content and 'filename="theme.js"' not in content:
                idx_body_close = content.lower().rfind('</body>')
                if idx_body_close != -1:
                    content = content[:idx_body_close] + THEME_JS + '\n' + content[idx_body_close:]
                    print(f"  Inserted JS into {os.path.basename(filepath)}")
                    modified = True

            if modified:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
        except Exception as e:
            print(f"  Error: {os.path.basename(filepath)}: {e}")
    print("  ✅ Theme injection completed.")


# ============================================================
# STEP 7: Vector DB ingestion (ChromaDB)
# ============================================================
def read_all_texts() -> List[Tuple[str, str]]:
    texts = []
    for p in glob.glob(os.path.join(DATA_DIR, "**", "*.txt"), recursive=True):
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                texts.append((p, f.read()))
        except Exception:
            pass
    return texts

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    text = " ".join(text.split())
    chunks, start, n = [], 0, len(text)
    step = max(1, size - overlap)
    while start < n:
        end = min(start + size, n)
        chunks.append(text[start:end])
        start += step
    return chunks

def ingest_knowledge():
    print("\n--- 7. Ingesting Knowledge Base ---")
    try:
        client = chromadb.PersistentClient(path=DB_DIR)
        colls = [c.name for c in client.list_collections()]

        if COLLECTION_NAME in colls:
            coll = client.get_collection(COLLECTION_NAME)
            if coll.count() > 0:
                print(f"  ✅ Collection '{COLLECTION_NAME}' already has data. Skipping.")
                return

        print("  Starting ingestion...")
        model = SentenceTransformer("intfloat/multilingual-e5-small")
        coll = client.get_or_create_collection(COLLECTION_NAME)
        docs = read_all_texts()

        if not docs:
            print(f"  ⚠️  No .txt files found in {DATA_DIR}")
            return

        ids, metas, contents = [], [], []
        for path, fulltext in docs:
            for ch in chunk_text(fulltext):
                ids.append(str(uuid.uuid4()))
                contents.append(ch)
                metas.append({"source": os.path.relpath(path, BASE_DIR)})

        embeddings = []
        for i in range(0, len(contents), BATCH_SIZE):
            batch = contents[i : i + BATCH_SIZE]
            vec = model.encode(batch, convert_to_numpy=True, normalize_embeddings=True, batch_size=min(BATCH_SIZE, len(batch)), show_progress_bar=False)
            embeddings.extend(vec)

        coll.add(ids=ids, metadatas=metas, documents=contents, embeddings=embeddings)
        print(f"  ✅ Ingested {len(contents)} chunks from {len(docs)} files.")

    except Exception as e:
        print(f"❌ Error in ingestion: {e}")


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 50)
    print("   HOSPITAL MANAGEMENT - FULL SETUP SCRIPT")
    print("=" * 50)

    ensure_database()          # 0. Create DB if not exists
    ensure_all_tables()        # 1. Create all 24 tables
    ensure_stored_procedures() # 2. Create all 5 SPs
    seed_accounts()            # 3. Admin + bacsi1 accounts
    seed_khoa()                # 3b. Departments
    seed_doctors()             # 4. 30 sample doctors
    seed_xetnghiem()           # 5. Lab test types + indications
    inject_theme()             # 6. CSS/JS injection
    ingest_knowledge()         # 7. ChromaDB ingestion

    print("\n" + "=" * 50)
    print("   ✅ SETUP COMPLETED SUCCESSFULLY")
    print("=" * 50)
    print("\nCredentials:")
    print("  Admin:  admin / 123456")
    print("  Doctor: bacsi1 / 123456")
    print("\nRun: python app.py")
    print("Open: http://localhost:5000")

if __name__ == "__main__":
    main()
