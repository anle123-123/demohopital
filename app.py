from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, send_from_directory, abort, send_file, session, g
)
import pyodbc, os, io, re, random, string
import urllib.request, ssl, json
import smtplib
from email.message import EmailMessage
from openpyxl import Workbook
from enums import Khoa, LoaiXetNghiem
from datetime import datetime, date, timedelta
from uuid import uuid4
import hmac, hashlib
from urllib.parse import urlencode, quote_plus
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from flask import send_file, jsonify, request
from flask import send_file, redirect
from datetime import datetime, timedelta
import pyodbc 
from enums import LoaiXetNghiem, Khoa, NhomThuoc
from chatbot_routes import chatbot_bp
import os
from dotenv import load_dotenv
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from datetime import date 
from setup import KHOA_LIST
from flask_cors import CORS
from jwt_auth import generate_tokens, verify_token, get_current_user, jwt_or_session


ph = PasswordHasher()

app = Flask(__name__)
app.secret_key = "super-secret-change-this"  # đổi khi deploy
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)
# ===== VNPAY DEMO CONFIG =====
VNPAY_TMN_CODE   = os.getenv("VNPAY_TMN_CODE", "2BATOUM5")   # demo
VNPAY_HASH_SECRET= os.getenv("VNPAY_HASH_SECRET", "FGC4GQAE5263172DQ04CEFKODOIMM5OK") # demo
VNPAY_PAY_URL    = os.getenv("VNPAY_PAY_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html")
VNPAY_RETURN_URL = os.getenv("VNPAY_RETURN_URL", "https://unsensuous-athena-superseraphic.ngrok-free.dev/vnpay_return")
VNPAY_IPN_URL    = os.getenv("VNPAY_IPN_URL",    "https://unsensuous-athena-superseraphic.ngrok-free.dev/vnpay_ipn")

def vnpay_hmac_sha512(key: str, data: str) -> str:
    return hmac.new(key.encode('utf-8'), data.encode('utf-8'), hashlib.sha512).hexdigest()

def vnpay_build_url(params: dict) -> str:
    # sort by key asc, urlencode theo chuẩn VNPAY
    sorted_params = dict(sorted(params.items()))
    query = "&".join([f"{k}={quote_plus(str(v))}" for k, v in sorted_params.items() if v is not None])
    secure_hash = vnpay_hmac_sha512(VNPAY_HASH_SECRET, query)
    return f"{VNPAY_PAY_URL}?{query}&vnp_SecureHash={secure_hash}", secure_hash



# ===== DATABASE CONFIG =====
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "quanlibenhvien")
DB_USER = os.getenv("DB_USER", "")  # Để trống = Windows Auth
DB_PASSWORD = os.getenv("DB_PASSWORD", "210506")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")
DB_USE_WIN_AUTH = os.getenv("DB_USE_WIN_AUTH", "1")  # 1 = Windows Auth

# ===== SMTP CONFIG =====
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "chom59072@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "zbyl qpcp kdfq ztbz")

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
    CONN_STR = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        "TrustServerCertificate=yes;"
        "MARS_Connection=Yes;"
    )

# Thử kết nối, nếu lỗi thì in ra terminal để debug
try:
    cn = pyodbc.connect(CONN_STR, autocommit=True)
    print(">>> [Database] Connected successfully!")
except Exception as e:
    print(f">>> [Database] Connection failed: {e}")
    # Không crash app ngay, để có thể xem log, nhưng các route DB sẽ lỗi
    cn = None



# CHẶN TRUY CẬP KHI CHƯA ĐĂNG NHẬP HOẶC KHÔNG ĐÚNG QUYỀN
ALLOW_ANON_ENDPOINTS = {
    "root", "trang_chu", "favicon", "static",
    "lay_so_online", "api_lay_so_online",   # bệnh nhân tự lấy số
    "api_list_today", "api_get_current", "api_call_next", "api_set_status",  # bác sĩ gọi số
    "login_page", "api_login", "api_logout", "api_session", "dat_lich_page",   # GET /dat-lich
    "api_dat_lich", "api_list_bacsi", "quansat_layso", "api/chat", "api_login_otp", "api_2fa_status",
    "vnpay_return", "vnpay_ipn", "api_get_khoa", "tracuu_hoso", "ho_so_benh_nhan", # Allow VNPAY return/IPN
    "register_page",        # Trang đăng ký
    "verify_email_page",    # Trang nhập OTP
    "public_register",      # API gửi OTP
    "confirm_registration",
    "gioi_thieu_page",
    "bac_si_page",
}

# Mapping: Route endpoint -> Allowed roles
# Nếu không có trong này => mặc định cho phép nếu đã login (hoặc logic riêng)
ROLE_ACCESS = {
    # Admin roles
    "ql_bac_si":        ["admin"],
    "ql_thuoc_kho":     ["admin"],
    "bao_cao_thong_ke": ["admin"], # Assuming route name
    "ql_lich_hen":      ["admin"], # Doctor has their own view or filtered
    "lich_lam_viec":    ["admin", "doctor"], # Managing schedule
    "admin_dichvu_page":["admin"],
    "admin_accounts_page": ["admin"], 
    
    # Doctor roles (shared with Admin mostly, but explicit checks here)
    # Doctor roles (shared with Admin mostly, but explicit checks here)
    "ql_kham_benh":     ["admin", "doctor"], 
    "benh_nhan":        ["admin", "doctor"],
    "ql_benh_nhan":     ["admin", "doctor"],
    "trang_kham_benh":  ["admin", "doctor"],
    "ql_thanh_toan":    ["admin", "doctor"],
    "ho_so_benh_nhan":  ["admin", "doctor", "patient"],
    "trang_chu":        ["admin", "doctor", "patient"],
    "goi_so":           ["admin", "doctor", "patient"],
    "xet_lich_lam":     ["admin", "doctor"],
    "ql_lich_hen":      ["admin","doctor"],
}
# =======================================================
# PUBLIC REGISTRATION (ĐĂNG KÝ TÀI KHOẢN GIỐNG VIDEO)
# =======================================================
# Route cho trang Bác sĩ
@app.route('/doi-ngu-bac-si')
def bac_si_page():
    return render_template('bacsi1.html', title='Đội ngũ bác sĩ', active='bac_si')
@app.post("/api/register")
def public_register():
    d = request.get_json(force=True) or {}
    
    # 1. Lấy dữ liệu từ Frontend gửi lên
    taikhoan = (d.get("taikhoan") or "").strip()
    hoten = (d.get("hoten") or "").strip()
    ngaysinh = d.get("ngaysinh")
    diachi = (d.get("diachi") or "").strip()
    quequan = (d.get("quequan") or "").strip()
    email = (d.get("email") or "").strip()
    sdt = (d.get("phone") or "").strip()
    matkhau = (d.get("password") or "").strip()

    # 2. Validate cơ bản
    if not taikhoan or not hoten or not email or not matkhau or not sdt:
        return jsonify({"success": False, "error": "Vui lòng điền đầy đủ thông tin bắt buộc"}), 400

    cur = cn.cursor()

    # Kiểm tra Tài khoản đã tồn tại chưa (cho phép trùng email)
    cur.execute("SELECT 1 FROM DBO.DANGNHAP WHERE TAIKHOAN=?", taikhoan)
    if cur.fetchone():
        return jsonify({"success": False, "error": "Tài khoản đã tồn tại. Vui lòng chọn tên khác."}), 409
    
    # 5. Tạo OTP và lưu tạm vào Session (chưa lưu DB)
    otp = "".join(random.choices(string.digits, k=6))
    
    session["reg_data"] = {
        "taikhoan": taikhoan,
        "hoten": hoten,
        "ngaysinh": ngaysinh,
        "diachi": diachi,
        "quequan": quequan,
        "email": email,
        "sdt": sdt,
        "matkhau": matkhau
    }
    session["reg_otp"] = otp

    # Also store in server-side dict for mobile (no session cookies)
    _pending_registrations[email] = {
        "data": {
            "taikhoan": taikhoan,
            "hoten": hoten,
            "ngaysinh": ngaysinh,
            "diachi": diachi,
            "quequan": quequan,
            "email": email,
            "sdt": sdt,
            "matkhau": matkhau
        },
        "otp": otp
    }
    
    # 6. Gửi Email OTP
    try:
        subject = "Mã xác thực đăng ký tài khoản"
        body = f"Chào {hoten},\n\nMã xác thực (OTP) của bạn là: {otp}\nMã có hiệu lực trong ít phút."
        send_email(email, subject, body)
    except Exception as e:
        print(f"Lỗi gửi mail: {e}")
        return jsonify({"success": False, "error": "Không thể gửi email xác thực"}), 500

    return jsonify({"success": True, "message": "Đã gửi OTP qua email", "email": email})
# =======================================================
# ROUTES GIAO DIỆN ĐĂNG KÝ & XÁC THỰC (Thêm đoạn này)
# =======================================================
# ==========================================
# API QUẢN LÝ KHOA (Dành cho trang admin_qlkhoa.html)
# ==========================================
# Route cho trang Giới thiệu
@app.route('/gioi-thieu')
def gioi_thieu_page():
    # Render ra file html bạn vừa lưu ở Bước 1
    # active='gioi_thieu' dùng để tô màu menu đang chọn (nếu cần)
    return render_template('gioithieu.html', title='Giới thiệu - Hopital AZC', active='gioi_thieu')
@app.get("/api/khoa-admin")
def api_khoa_admin_list():
    # Kiểm tra quyền admin
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    q = (request.args.get("q") or "").strip()
    cur = cn.cursor()
    
    # Kiểm tra xem bảng KHOA có cột MO_TA chưa, nếu chưa thì chỉ select các cột có sẵn
    # Giả sử bảng KHOA có: ID, TEN_KHOA, TRANG_THAI, MO_TA
    if q:
        sql = """
            SELECT ID, TEN_KHOA, MO_TA, TRANG_THAI 
            FROM DBO.KHOA 
            WHERE TEN_KHOA LIKE ?
            ORDER BY ID DESC
        """
        cur.execute(sql, f"%{q}%")
    else:
        sql = """
            SELECT ID, TEN_KHOA, MO_TA, TRANG_THAI 
            FROM DBO.KHOA 
            ORDER BY ID DESC
        """
        cur.execute(sql)
    
    rows = cur.fetchall()
    # Convert kết quả thành list dictionary
    data = [
        {
            "ID": r[0],
            "TEN_KHOA": r[1],
            "MO_TA": r[2] if r[2] else "",
            "TRANG_THAI": r[3]
        }
        for r in rows
    ]
    return jsonify(data)

@app.post("/api/khoa-admin/create")
def api_khoa_admin_create():
    if session.get("role") != "admin": return jsonify({"error": "Unauthorized"}), 403
    
    d = request.get_json(force=True)
    ten = (d.get("TEN_KHOA") or "").strip()
    mota = (d.get("MO_TA") or "").strip()
    trangthai = int(d.get("TRANG_THAI") or 1)
    
    if not ten:
        return jsonify({"error": "Tên khoa không được để trống"}), 400
        
    cur = cn.cursor()
    # Kiểm tra trùng tên
    cur.execute("SELECT 1 FROM DBO.KHOA WHERE TEN_KHOA = ?", ten)
    if cur.fetchone():
        return jsonify({"error": "Tên khoa đã tồn tại"}), 409
        
    cur.execute("""
        INSERT INTO DBO.KHOA (TEN_KHOA, MO_TA, TRANG_THAI)
        VALUES (?, ?, ?)
    """, ten, mota, trangthai)
    cn.commit()
    
    return jsonify({"success": True})

@app.post("/api/khoa-admin/<int:id>/update")
def api_khoa_admin_update(id):
    if session.get("role") != "admin": return jsonify({"error": "Unauthorized"}), 403
    
    d = request.get_json(force=True)
    ten = (d.get("TEN_KHOA") or "").strip()
    mota = (d.get("MO_TA") or "").strip()
    trangthai = int(d.get("TRANG_THAI") or 1)
    
    if not ten:
        return jsonify({"error": "Tên khoa không được để trống"}), 400
        
    cur = cn.cursor()
    cur.execute("""
        UPDATE DBO.KHOA 
        SET TEN_KHOA=?, MO_TA=?, TRANG_THAI=?
        WHERE ID=?
    """, ten, mota, trangthai, id)
    
    if cur.rowcount == 0:
        return jsonify({"error": "Không tìm thấy khoa"}), 404
        
    cn.commit()
    return jsonify({"success": True})

@app.post("/api/khoa-admin/<int:id>/toggle")
def api_khoa_admin_toggle(id):
    if session.get("role") != "admin": return jsonify({"error": "Unauthorized"}), 403
    
    d = request.get_json(force=True)
    # Lấy trạng thái mới từ client gửi lên (0 hoặc 1)
    new_status = int(d.get("TRANG_THAI", 1))
    
    cur = cn.cursor()
    cur.execute("UPDATE DBO.KHOA SET TRANG_THAI=? WHERE ID=?", new_status, id)
    cn.commit()
    return jsonify({"success": True})

@app.post("/api/khoa-admin/<int:id>/delete")
def api_khoa_admin_delete(id):
    if session.get("role") != "admin": return jsonify({"error": "Unauthorized"}), 403
    
    try:
        cur = cn.cursor()
        cur.execute("DELETE FROM DBO.KHOA WHERE ID=?", id)
        cn.commit()
        return jsonify({"success": True})
    except Exception as e:
        # Lỗi thường gặp: Khoa đang được tham chiếu bởi Bác sĩ hoặc Dịch vụ
        return jsonify({"error": "Không thể xóa khoa này do đã có dữ liệu liên quan. Hãy thử tắt trạng thái."}), 400
@app.route("/register")
def register_page():
    return render_template("dangky.html", title="Đăng ký tài khoản")

@app.route("/verify-email")
def verify_email_page():
    # Trang nhập OTP sau khi đăng ký
    return render_template("xacnhanotp.html", title="Xác thực Email")

@app.post("/api/confirm-registration")
def confirm_registration():
    d = request.get_json(force=True) or {}
    otp_input = (d.get("otp") or "").strip()
    
    # 1. Lấy dữ liệu từ session (web) hoặc server-side dict (mobile)
    reg_data = session.get("reg_data")
    saved_otp = session.get("reg_otp")
    
    if not reg_data or not saved_otp:
        # Fallback: mobile sends email in body
        reg_email = (d.get("email") or "").strip()
        pending = _pending_registrations.get(reg_email)
        if pending:
            reg_data = pending["data"]
            saved_otp = pending["otp"]
    
    if not reg_data or not saved_otp:
        return jsonify({"success": False, "error": "Phiên đăng ký hết hạn, vui lòng làm lại"}), 400
        
    # 2. Kiểm tra OTP
    if otp_input != saved_otp:
        return jsonify({"success": False, "error": "Mã OTP không đúng"}), 400
        
    # 3. OTP đúng -> Thực hiện lưu vào DB
    try:
        cur = cn.cursor()
        
        # 3a. Tạo mã bệnh nhân mới
        mabn = _gen_new_mabn() 
        
        # 3b. Insert vào HOSOBENHNHAN
        # Lưu ý: Cần đảm bảo bảng HOSOBENHNHAN của bạn có cột EMAIL. Nếu chưa có thì bỏ cột đó ra khỏi câu lệnh dưới.
        cur.execute("""
            INSERT INTO DBO.HOSOBENHNHAN (MABENHNHAN, HOVATEN, NGAYSINH, SODIENTHOAI, DIACHI, QUEQUAN, EMAIL)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mabn, reg_data["hoten"], reg_data["ngaysinh"], reg_data["sdt"], reg_data["diachi"], reg_data["quequan"], reg_data["email"]))
        
        # 3c. Insert vào DANGNHAP
        hashed_pw = ph.hash(reg_data["matkhau"])
        taikhoan = reg_data.get("taikhoan") or reg_data["email"]
        cur.execute("""
            INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, MATKHAU_HASH, ROLE, MABENHNHAN, MANHANVIEN, TOTP_ENABLED, EMAIL)
            VALUES (?, ?, ?, 'patient', ?, NULL, 0, ?)
        """, (taikhoan, reg_data["matkhau"], hashed_pw, mabn, reg_data["email"]))
        
        cn.commit()
        
        # 4. Xóa session + server-side dict
        session.pop("reg_data", None)
        session.pop("reg_otp", None)
        _pending_registrations.pop(reg_data.get("email", ""), None)
        
        return jsonify({"success": True, "message": "Đăng ký thành công!", "taikhoan": taikhoan})
        
    except Exception as e:
        cn.rollback()
        print(f"Lỗi DB Register: {e}")
        return jsonify({"success": False, "error": "Lỗi hệ thống khi lưu dữ liệu"}), 500
@app.before_request
def _guard_auth():
    ep = request.endpoint or ""
    
    # Bỏ qua kiểm tra đăng nhập cho các API chatbot
    if ep == "chatbot.api_chat":
        return  # Không cần kiểm tra đăng nhập cho API này
    
    if ep.startswith("static."):
        return
    if ep in ALLOW_ANON_ENDPOINTS:
        return
        
    # Check login: JWT (mobile) OR session (web)
    if not get_current_user():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized"}), 401
        return redirect(url_for("trang_chu"))
        
    # Check Role Access
    role = g.current_user.get("role", "doctor")
    if ep in ROLE_ACCESS:
        allowed = ROLE_ACCESS[ep]
        if role not in allowed:
            return render_template("403.html", msg="Bạn không có quyền truy cập trang này"), 403

    # Restriction for 'patient' role: can only view their own profile
    if role == "patient" and ep == "ho_so_benh_nhan":
        mabn_param = (request.view_args or {}).get("mabn")
        mabn_session = session.get("mabn")
        if mabn_param and mabn_param != mabn_session:
             return render_template("403.html", msg="Bạn chỉ có thể xem hồ sơ của mình"), 403

# ==============================
# ADMIN: QUẢN LÝ TÀI KHOẢN BÁC SĨ
# ==============================

@app.get("/admin/tai-khoan", endpoint="admin_accounts_page")
def admin_accounts_page():
    # Guard theo ROLE_ACCESS là đủ, nhưng có thể double-check:
    if session.get("role") != "admin":
        return render_template("403.html", msg="Bạn không có quyền truy cập trang này"), 403
    return render_template("admin_qltaikhoan.html", title="Quản lý tài khoản bác sĩ", active="ql_tai_khoan")

@app.get("/api/admin/nhanvien/<manv>")
def api_admin_get_nhanvien(manv):
    # chỉ admin dùng
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    manv = (manv or "").strip()
    if not manv:
        return jsonify({"ok": False, "error": "Thiếu mã nhân viên"}), 400

    cur = cn.cursor()
    cur.execute("""
        SELECT MANHANVIEN, HOVATEN, KHOA
        FROM DBO.QUANLINHANVIEN
        WHERE MANHANVIEN = ?
    """, (manv,))
    row = cur.fetchone()

    if not row:
        return jsonify({"ok": False, "error": "Không tìm thấy bác sĩ"}), 404

    return jsonify({
        "ok": True,
        "manhanvien": row[0],
        "hovaten": row[1] or "",
        "khoa": row[2] or ""
    })
@app.post("/api/admin/accounts/<taikhoan>/set-password")
def api_admin_set_password(taikhoan):
    """
    Admin đặt mật khẩu mới (dễ nhớ) cho tài khoản bác sĩ.
    Body JSON:
    { "new_password": "abc12345", "email": "optional@gmail.com" }
    """
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    tk = (taikhoan or "").strip()
    d = request.get_json(force=True) or {}
    new_pw = (d.get("new_password") or "").strip()
    email = (d.get("email") or "").strip() or None

    if not tk:
        return jsonify({"ok": False, "error": "Thiếu tài khoản"}), 400

    if len(new_pw) < 6:
        return jsonify({"ok": False, "error": "Mật khẩu tối thiểu 6 ký tự"}), 400

    new_hash = ph.hash(new_pw)

    cur = cn.cursor()
    # set password + tắt 2FA (khuyên dùng để bác sĩ setup lại nếu đang bật)
    cur.execute("""
        UPDATE DBO.DANGNHAP
        SET MATKHAU=?,
            MATKHAU_HASH=?,
            TOTP_ENABLED=0,
            TOTP_SECRET=NULL
        WHERE TAIKHOAN=? AND ROLE='doctor'
    """, (new_pw, new_hash, tk))

    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Không tìm thấy tài khoản bác sĩ"}), 404

    cn.commit()

    if email:
        subject = "Cập nhật mật khẩu tài khoản bác sĩ"
        body = f"""Mật khẩu của bạn đã được cập nhật:

Username: {tk}
Mật khẩu mới: {new_pw}

Vui lòng đăng nhập và đổi mật khẩu nếu cần.
"""
        send_email(email, subject, body)

    return jsonify({"ok": True})

@app.get("/admin/dich-vu")
def admin_dich_vu():
    if session.get("role") != "admin":
        return render_template("403.html", msg="Bạn không có quyền"), 403
    return render_template("admin_dichvu.html", title="Quản lý dịch vụ", active="ql_dich_vu")


@app.get("/admin/xet-nghiem")
def admin_xet_nghiem():
    if session.get("role") != "admin":
        return render_template("403.html", msg="Bạn không có quyền"), 403
    return render_template("admin_xetnghiem.html", title="Quản lý xét nghiệm", active="ql_xet_nghiem")

@app.get("/api/admin/accounts")
def api_admin_list_accounts():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    role = (request.args.get("role") or "doctor").strip()

    cur = cn.cursor()
    cur.execute("""
        SELECT dn.TAIKHOAN, dn.ROLE, dn.MANHANVIEN,
               nv.HOVATEN, nv.KHOA,
               CAST(ISNULL(dn.TOTP_ENABLED, 0) AS INT) AS TOTP_ENABLED
        FROM DBO.DANGNHAP dn
        LEFT JOIN DBO.QUANLINHANVIEN nv ON nv.MANHANVIEN = dn.MANHANVIEN
        WHERE dn.ROLE = ?
        ORDER BY dn.TAIKHOAN
    """, (role,))
    rows = cur.fetchall() or []

    items = []
    for r in rows:
        items.append({
            "taikhoan": r[0],
            "role": r[1],
            "manhanvien": r[2],
            "hovaten": r[3] or "",
            "khoa": r[4] or "",
            "totp_enabled": bool(r[5]),
        })
    return jsonify({"ok": True, "items": items})


@app.post("/api/admin/accounts")
def api_admin_create_account():
    """
    Tạo tài khoản cho bác sĩ.
    Body JSON:
    {
      "taikhoan": "bs001",            # bắt buộc
      "manhanvien": "BS001",          # bắt buộc
      "hovaten": "Nguyễn Văn A",      # optional
      "khoa": "Khoa Nội",             # optional
      "password": "123456",           # optional (trống -> auto gen)
      "email": "chom59072@gmail.com"  # optional (lưu DB + gửi thông tin TK)
    }
    """
    if session.get("role") != "admin":
        return jsonify({"ok": False, "error": "Unauthorized"}), 403

    d = request.get_json(force=True) or {}
    taikhoan = (d.get("taikhoan") or "").strip()
    manv = (d.get("manhanvien") or "").strip()
    hovaten = (d.get("hovaten") or "").strip() or None
    khoa = (d.get("khoa") or "").strip() or None
    email = (d.get("email") or "").strip() or None

    if not taikhoan or not manv:
        return jsonify({"ok": False, "error": "Thiếu taikhoan / manhanvien"}), 400

    # đảm bảo có nhân viên trong QUANLINHANVIEN
    ensure_nhanvien(manv, hovaten=hovaten, khoa=khoa)

    cur = cn.cursor()

    # check trùng username
    cur.execute("SELECT 1 FROM DBO.DANGNHAP WHERE TAIKHOAN=?", (taikhoan,))
    if cur.fetchone():
        return jsonify({"ok": False, "error": "Tài khoản đã tồn tại"}), 409

    # auto gen password nếu không nhập
    raw_pw = (d.get("password") or "").strip() or _generate_password()
    pw_hash = ph.hash(raw_pw)

    # ✅ LƯU EMAIL VÀO DB (DBO.DANGNHAP.EMAIL)
    try:
        cur.execute("""
            INSERT INTO DBO.DANGNHAP
                (TAIKHOAN, MATKHAU, MATKHAU_HASH, ROLE, MANHANVIEN, EMAIL, TOTP_ENABLED)
            VALUES
                (?, ?, ?, 'doctor', ?, ?, 0)
        """, (taikhoan, raw_pw, pw_hash, manv, email))
        cn.commit()
    except Exception as e:
        cn.rollback()
        return jsonify({"ok": False, "error": f"Lỗi tạo tài khoản: {e}"}), 500

    # (tuỳ bạn) gửi mail thông tin tài khoản
    if email:
        subject = "Tạo tài khoản bác sĩ"
        body = f"""Chào bác sĩ,

Tài khoản của bạn đã được tạo:
Username: {taikhoan}
Password: {raw_pw}

Vui lòng đăng nhập và đổi mật khẩu sau khi vào hệ thống.
"""
        try:
            send_email(email, subject, body)
        except Exception:
            # không fail request chỉ vì mail lỗi
            pass

    return jsonify({
        "ok": True,
        "taikhoan": taikhoan,
        "email": email,
        "generated_password": raw_pw
    })



@app.delete("/api/admin/accounts/<taikhoan>")
def api_admin_delete_account(taikhoan):
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    tk = (taikhoan or "").strip()
    if not tk:
        return jsonify({"ok": False, "error": "Thiếu taikhoan"}), 400

    # chặn xóa admin (an toàn)
    cur = cn.cursor()
    cur.execute("SELECT ROLE FROM DBO.DANGNHAP WHERE TAIKHOAN=?", (tk,))
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Không tìm thấy tài khoản"}), 404
    if (row[0] or "").lower() == "admin":
        return jsonify({"ok": False, "error": "Không được xóa tài khoản admin"}), 400

    cur.execute("DELETE FROM DBO.DANGNHAP WHERE TAIKHOAN=?", (tk,))
    cn.commit()
    return jsonify({"ok": True})


@app.post("/api/admin/accounts/<taikhoan>/reset-password")
def api_admin_reset_password(taikhoan):
    """
    Quên mật khẩu: reset về password mới.
    Optional JSON:
    { "email": "..." } để gửi mail, hoặc frontend tự hỏi email.
    """
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    tk = (taikhoan or "").strip()
    if not tk:
        return jsonify({"ok": False, "error": "Thiếu taikhoan"}), 400

    d = request.get_json(force=True) or {}
    email = (d.get("email") or "").strip() or None

    new_pw = _generate_password()
    new_hash = ph.hash(new_pw)

    cur = cn.cursor()
    # Reset password + (khuyến nghị) tắt 2FA để bác sĩ setup lại nếu cần
    cur.execute("""
        UPDATE DBO.DANGNHAP
        SET MATKHAU=?, MATKHAU_HASH=?, TOTP_ENABLED=0, TOTP_SECRET=NULL
        WHERE TAIKHOAN=? AND ROLE='doctor'
    """, (new_pw, new_hash, tk))

    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Không tìm thấy tài khoản bác sĩ"}), 404

    cn.commit()

    if email:
        subject = "Reset mật khẩu tài khoản bác sĩ"
        body = f"""Mật khẩu của bạn đã được reset:

Username: {tk}
Password mới: {new_pw}

Vui lòng đăng nhập và đổi mật khẩu ngay sau khi vào hệ thống.
"""
        send_email(email, subject, body)

    return jsonify({"ok": True, "taikhoan": tk, "new_password": new_pw})
@app.get("/admin/tai-khoan", endpoint="admin_accounts_page_v2")
def admin_accounts_page_v2():
    return render_template("admin_qltaikhoan.html", title="Quản lý tài khoản bác sĩ", active="ql_tai_khoan")


@app.get("/phong-benh")
def phong_benh_page():
    # chưa đăng nhập → đá về login
    if not session.get("user"):
        return redirect(url_for("login_page"))

    # chỉ cho admin & bác sĩ
    if session.get("role") not in ("admin", "doctor"):
        return redirect(url_for("trang_chu"))

    return render_template(
        "admin_phongbenh.html",
        title="Quản lý phòng bệnh",
        active="phong_benh"
    )
# ==========================================
# API QUẢN LÝ PHÒNG BỆNH & GIƯỜNG (MỚI)
# ==========================================

# 1. Lấy danh sách phòng và giường theo Khoa
@app.get("/api/phongbenh")
def api_get_phongbenh():
    khoa = request.args.get("khoa", "").strip()
    if not khoa: return jsonify([])

    cur = cn.cursor()
    # Lấy danh sách phòng
    cur.execute("SELECT ID, TENPHONG FROM DBO.PHONGBENH WHERE KHOA = ?", khoa)
    phongs = [{"id": r[0], "roomName": r[1], "beds": []} for r in cur.fetchall()]

    if not phongs: return jsonify([])

    # Lấy danh sách giường cho các phòng này
    phong_ids = ",".join(str(p["id"]) for p in phongs)
    cur.execute(f"""
        SELECT g.ID, g.PHONG_ID, g.TENGIUONG, g.MABENHNHAN, bn.HOVATEN, 
               CONVERT(VARCHAR(10), g.NGAYVAO, 23), 
               CONVERT(VARCHAR(10), g.NGAYRA, 23)
        FROM DBO.GIUONGBENH g
        LEFT JOIN DBO.HOSOBENHNHAN bn ON g.MABENHNHAN = bn.MABENHNHAN
        WHERE g.PHONG_ID IN ({phong_ids})
    """)
    
    rows = cur.fetchall()
    # Map giường vào phòng tương ứng
    for r in rows:
        bed_obj = {
            "dbId": r[0],          # ID trong DB để update
            "id": r[2],            # Tên giường hiển thị (G1, G2...)
            "patientId": r[3],
            "name": r[4],
            "admissionDate": r[5] or "",
            "dischargeDate": r[6] or ""
        }
        # Tìm phòng chứa giường này
        for p in phongs:
            if p["id"] == r[1]:
                p["beds"].append(bed_obj)
                break
    
    return jsonify(phongs)

# 2. Tạo phòng mới
@app.post("/api/phongbenh")
def api_create_phong():
    if session.get("role") != "admin": return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True)
    ten = d.get("ten")
    khoa = d.get("khoa")
    
    if not ten or not khoa: return jsonify({"error": "Thiếu thông tin"}), 400
    
    cur = cn.cursor()
    cur.execute("INSERT INTO DBO.PHONGBENH (TENPHONG, KHOA) VALUES (?, ?)", ten, khoa)
    cn.commit()
    return jsonify({"success": True})

# 3. Thêm giường mới
@app.post("/api/giuongbenh")
def api_create_giuong():
    if session.get("role") != "admin": return jsonify({"error": "Unauthorized"}), 403
    d = request.get_json(force=True)
    phong_id = d.get("phong_id")
    ten_giuong = d.get("ten_giuong") # VD: G1, G2
    
    cur = cn.cursor()
    cur.execute("INSERT INTO DBO.GIUONGBENH (PHONG_ID, TENGIUONG) VALUES (?, ?)", phong_id, ten_giuong)
    cn.commit()
    return jsonify({"success": True})

# 4. Cập nhật giường (Gán BN, Ra viện, Sửa ngày)
# 4. Cập nhật giường (Gán BN, Ra viện, Sửa ngày)
@app.put("/api/giuongbenh/<int:bed_id>")
def api_update_giuong(bed_id):
    # Cho phép cả 'admin' và 'doctor' thao tác
    if session.get("role") not in ["admin", "doctor"]: 
        return jsonify({"error": "Unauthorized"}), 403

    d = request.get_json(force=True)
    
    mabn = d.get("mabn") # Null nếu ra viện
    ngayvao = d.get("ngayvao") or None
    ngayra = d.get("ngayra") or None
    
    cur = cn.cursor()

    # === [MỚI] KIỂM TRA: 1 BỆNH NHÂN CHỈ NẰM 1 GIƯỜNG ===
    if mabn:  # Nếu đang xếp giường (không phải cho ra viện)
        # Tìm xem bệnh nhân này có đang ở giường nào KHÁC không (ID != bed_id)
        cur.execute("""
            SELECT g.TENGIUONG, p.TENPHONG 
            FROM DBO.GIUONGBENH g
            LEFT JOIN DBO.PHONGBENH p ON g.PHONG_ID = p.ID
            WHERE g.MABENHNHAN = ? AND g.ID != ?
        """, mabn, bed_id)
        
        row = cur.fetchone()
        if row:
            ten_giuong, ten_phong = row[0], row[1]
            # Trả về lỗi 400 (Bad Request) để frontend nhận biết và hiện thông báo
            return jsonify({
                "error": f"Bệnh nhân này đang nằm ở {ten_phong} - Giường {ten_giuong}. Vui lòng cho ra viện ở giường cũ trước."
            }), 400
    # ====================================================

    cur.execute("""
        UPDATE DBO.GIUONGBENH 
        SET MABENHNHAN=?, NGAYVAO=?, NGAYRA=?
        WHERE ID=?
    """, mabn, ngayvao, ngayra, bed_id)
    cn.commit()
    return jsonify({"success": True})
# LOGIN / LOGOUT

@app.get("/login")
def login_page():
    return render_template("dangnhap.html", title="Đăng nhập")

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("trang_chu"))

def _get_login_row(tk):
    cur = cn.cursor()
    cur.execute("""
            SELECT TAIKHOAN, MATKHAU, MATKHAU_HASH, TOTP_SECRET, TOTP_ENABLED, ROLE, MANHANVIEN, MABENHNHAN
        FROM DBO.DANGNHAP
        WHERE TAIKHOAN=?
    """, (tk,))
    return cur.fetchone()

import random
from datetime import datetime

# In-memory OTP storage for mobile clients (no session cookies)
_pending_otps = {}
_pending_registrations = {}

@app.post("/api/login")
def api_login():
    d = request.get_json(force=True) or {}
    tk = (d.get("taikhoan") or "").strip()
    mk = (d.get("matkhau") or "").strip()

    if not tk or not mk:
        return jsonify(success=False, error="Thiếu tài khoản hoặc mật khẩu"), 400

    row = _get_login_row(tk)
    if not row:
        print(f"[LOGIN DEBUG] User not found: '{tk}'")
        return jsonify(success=False, error="Sai tài khoản hoặc mật khẩu"), 401

    taikhoan, matkhau_plain, matkhau_hash, _, _, role, manv, mabn = row

    # Verify password
    ok_pw = False
    if matkhau_hash:
        try:
            ok_pw = ph.verify(matkhau_hash, mk)
        except VerifyMismatchError:
            ok_pw = False
    else:
        ok_pw = (matkhau_plain == mk)

    if not ok_pw:
        print(f"[LOGIN DEBUG] Wrong password for '{tk}' (has_hash={bool(matkhau_hash)}, plain_match={matkhau_plain == mk})")
        return jsonify(success=False, error="Sai tài khoản hoặc mật khẩu"), 401

    # Nâng cấp hash nếu cần
    if not matkhau_hash:
        new_hash = ph.hash(mk)
        cur = cn.cursor()
        cur.execute(
            "UPDATE DBO.DANGNHAP SET MATKHAU_HASH=? WHERE TAIKHOAN=?",
            (new_hash, tk)
        )
        cn.commit()

    # === EMAIL OTP ===
    otp = f"{random.randint(0, 999999):06d}"

    session.clear()
    session["pending_user"] = tk
    session["pending_otp"] = otp
    session["pending_at"] = datetime.utcnow().isoformat()

    # ⚠️ LẤY EMAIL THEO TÀI KHOẢN
    email = _get_email_by_taikhoan(tk)

    if not email:
        return jsonify({
            "success": False,
            "error": "Tài khoản chưa có email, không thể gửi OTP"
        }), 400

    otp = f"{random.randint(0, 999999):06d}"

    session.clear()
    session["pending_user"] = tk
    session["pending_otp"] = otp
    session["pending_at"] = datetime.utcnow().isoformat()

    # Also store in server-side dict for mobile (no session cookies)
    _pending_otps[tk] = {"otp": otp, "at": datetime.utcnow().isoformat()}

    ok = send_email(
        email,
        "Mã OTP đăng nhập",
        f"Mã OTP của bạn là: {otp}\nHiệu lực trong 5 phút."
    )

    if not ok:
        return jsonify(success=False, error="Không gửi được OTP email"), 500

    return jsonify(success=True, require_otp=True, taikhoan=tk)

@app.post("/api/login/otp")
def api_login_otp():
    d = request.get_json(force=True) or {}
    otp = (d.get("otp") or "").strip()

    # Try session first (web), then server-side dict (mobile)
    tk = session.get("pending_user")
    real_otp = session.get("pending_otp")

    if not tk or not real_otp:
        # Fallback: mobile sends taikhoan in body
        tk = (d.get("taikhoan") or "").strip()
        pending = _pending_otps.get(tk)
        if pending:
            real_otp = pending["otp"]

    if not tk or not real_otp:
        return jsonify(success=False, error="Phiên đăng nhập đã hết hạn"), 401

    if otp != real_otp:
        return jsonify(success=False, error="OTP không đúng"), 401

    # Clean up server-side OTP
    _pending_otps.pop(tk, None)

    # LOGIN THÀNH CÔNG
    row = _get_login_row(tk)
    if not row:
        return jsonify(success=False, error="Tài khoản không tồn tại"), 401

    role = row[5] or "doctor"
    manv = row[6]
    mabn = row[7]

    session.clear()
    session["user"] = tk
    session["role"] = role
    session["manv"] = manv
    session["mabn"] = mabn

    # Generate JWT for mobile clients
    access_token, refresh_token = generate_tokens(tk, role, manv, mabn)

    return jsonify(
        success=True,
        redirect=url_for("trang_chu"),
        access_token=access_token,
        refresh_token=refresh_token,
        user=tk,
        role=role,
        manv=manv,
        mabn=mabn,
    )


@app.post("/api/login/resend-otp")
def resend_login_otp():
    d = request.get_json(force=True) or {}
    tk = session.get("pending_user") or (d.get("taikhoan") or "").strip()
    if not tk:
        return jsonify(success=False, error="Phiên đăng nhập hết hạn"), 401

    otp = f"{random.randint(0, 999999):06d}"
    session["pending_otp"] = otp
    session["pending_at"] = datetime.utcnow().isoformat()

    email = _get_email_by_taikhoan(tk)
    ok = send_email(email, "Mã OTP mới", f"Mã OTP mới của bạn là: {otp}")

    if not ok:
        return jsonify(success=False, error="Không gửi được OTP"), 500

    return jsonify(success=True)
def _get_email_by_taikhoan(tk):
    cur = cn.cursor()
    cur.execute("""
        SELECT EMAIL, MANHANVIEN, MABENHNHAN
        FROM DBO.DANGNHAP
        WHERE TAIKHOAN = ?
    """, (tk,))
    r = cur.fetchone()
    if not r:
        return None

    email_dn, ma_nv, ma_bn = r
    if email_dn:
        return email_dn

    # (tuỳ chọn) nếu bạn có EMAIL ở QUANLINHANVIEN thì lấy tiếp
    if ma_nv:
        cur.execute("SELECT EMAIL FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN = ?", (ma_nv,))
        x = cur.fetchone()
        return x[0] if x else None

    if ma_bn:
        cur.execute("SELECT EMAIL FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN = ?", (ma_bn,))
        x = cur.fetchone()
        return x[0] if x else None

    return None



@app.get("/api/2fa/status")
def api_2fa_status():
    tk = session.get("pending_user") or session.get("user")
    if not tk:
        return jsonify({"logged_in": False})

    row = _get_login_row(tk)
    if not row:
        return jsonify({"logged_in": False})

    _, _, _, totp_secret, totp_enabled, _ = row
    return jsonify({
        "logged_in": ("user" in session),
        "user": session.get("user"),
        "pending_user": session.get("pending_user"),
        "totp_enabled": bool(totp_enabled and totp_secret),
    })
@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"success": True})

@app.get("/api/session")
def api_session():
    if "user" in session:
        return jsonify({"logged_in": True, "user": session["user"], "role": session.get("role")})
    return jsonify({"logged_in": False})


# HELPERS
def recompute_hoadon_total(hoadon_id: int) -> float:
    """
    Tính lại tổng tiền hóa đơn từ HOADON_CT và cập nhật HOADON.TONGTIEN.
    Trả về tổng mới.
    """
    cur = cn.cursor()

    cur.execute("""
        SELECT ISNULL(SUM(CAST(SOLUONG AS DECIMAL(18,2)) * CAST(DONGIA AS DECIMAL(18,2))), 0)
        FROM dbo.HOADON_CT
        WHERE HOADON_ID = ?
    """, hoadon_id)
    total = float((cur.fetchone() or [0])[0] or 0)

    cur.execute("UPDATE dbo.HOADON SET TONGTIEN=? WHERE ID=?", total, hoadon_id)
    cn.commit()
    return total

def ensure_nhanvien(manv: str, hovaten: str = None, khoa: str = None):
    if not manv:
        return
    manv = str(manv).strip()
    if not manv:
        return
    cur = cn.cursor()
    cur.execute(
        """
        IF NOT EXISTS (SELECT 1 FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN = ?)
        INSERT INTO DBO.QUANLINHANVIEN (MANHANVIEN, HOVATEN, KHOA)
        VALUES (?, ?, ?)
        """,
        (manv, manv, (hovaten or "Chưa cập nhật"), khoa),
    )
    cn.commit()

def send_email(to_addr, subject, body):
    if not to_addr:
        return False

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_addr

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        print(f">>> [EMAIL SENT] To: {to_addr}")
        return True
    except Exception as e:
        print(f">>> [EMAIL ERROR] {e}")
        return False


def _generate_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))



# ROUTES GIAO DIỆN

@app.route("/")
def root():
    return redirect(url_for("trang_chu"))

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/x-icon",
    )

@app.get("/__dbg")
def dbg():
    cur = cn.cursor()
    cur.execute("SELECT COUNT(*) FROM dbo.PHIEUKHAM WHERE MABENHNHAN=N'1'")
    return {"phieukham_of_1": cur.fetchone()[0]}

@app.route("/goi-so", endpoint="goi_so")
def show_goi_so():
    return render_template("giaodienquansatlayso.html", active="quản_lí_lịch_hẹn", title="Danh sách thứ tự", khoa_enum=Khoa)



import pyodbc  # đảm bảo đã import

@app.route("/home", endpoint="trang_chu")
def home_page():
   
    today = date.today()


    bn_moi = 0
    dang_dieu_tri = 0
    lich_hen = 0

    cur = cn.cursor()
    try:
        # --- 1) BN mới hôm nay (tính theo lần khám đầu tiên)
        cur.execute("""
            SELECT COUNT(*) 
            FROM (
              SELECT MABENHNHAN, MIN(CAST(NGAYKHAM AS DATE)) AS first_day
              FROM DBO.PHIEUKHAM
              GROUP BY MABENHNHAN
            ) t
            WHERE t.first_day = CAST(SYSDATETIME() AS DATE)
        """)
        bn_moi = (cur.fetchone() or [0])[0] or 0

        # --- 2) Đang điều trị (chưa thanh toán hoặc chưa có hóa đơn)
        cur.execute("""
            SELECT COUNT(*)
            FROM DBO.PHIEUKHAM pk
            LEFT JOIN DBO.HOADON h ON h.PHIEUKHAM_ID = pk.MAPHIEU
            WHERE h.ID IS NULL OR h.DATHANHTOAN = 0
        """)
        dang_dieu_tri = (cur.fetchone() or [0])[0] or 0

        # --- 3) Lịch hẹn hôm nay (dựa vào cột NGAY của LICHHEN)
        cur.execute("""
            SELECT COUNT(*) 
            FROM DBO.LICHHEN 
            WHERE NGAY = CAST(SYSDATETIME() AS DATE)
        """)
        lich_hen = (cur.fetchone() or [0])[0] or 0

    finally:
        cur.close()

    return render_template(
        "home.html",
        bn_moi=bn_moi,
        dang_dieu_tri=dang_dieu_tri,
        lich_hen=lich_hen,
        active="trang_chu",
        title="Trang chủ"
    )
# ... (Ngay sau hàm home_page của bạn) ...

@app.get("/api/home-stats")
def api_home_stats():
    """
    API endpoint để làm mới thống kê trên trang chủ (cho JavaScript).
    """
    bn_moi = 0
    dang_dieu_tri = 0
    lich_hen = 0
    cur = None
    
    try:
        cur = cn.cursor()
        
        # --- 1) BN mới hôm nay (tính theo lần khám đầu tiên)
        cur.execute("""
            SELECT COUNT(*) 
            FROM (
              SELECT MABENHNHAN, MIN(CAST(NGAYKHAM AS DATE)) AS first_day
              FROM DBO.PHIEUKHAM
              GROUP BY MABENHNHAN
            ) t
            WHERE t.first_day = CAST(SYSDATETIME() AS DATE)
        """)
        bn_moi = (cur.fetchone() or [0])[0] or 0

        # --- 2) Đang điều trị (chưa thanh toán hoặc chưa có hóa đơn)
        cur.execute("""
            SELECT COUNT(*)
            FROM DBO.PHIEUKHAM pk
            LEFT JOIN DBO.HOADON h ON h.PHIEUKHAM_ID = pk.MAPHIEU
            WHERE h.ID IS NULL OR h.DATHANHTOAN = 0
        """)
        dang_dieu_tri = (cur.fetchone() or [0])[0] or 0

        # --- 3) Lịch hẹn hôm nay (dựa vào cột NGAY của LICHHEN)
        cur.execute("""
            SELECT COUNT(*) 
            FROM DBO.LICHHEN 
            WHERE NGAY = CAST(SYSDATETIME() AS DATE)
        """)
        lich_hen = (cur.fetchone() or [0])[0] or 0

        # Trả về JSON, khớp với những gì home.html mong đợi
        return jsonify({
            "ok": True,
            "bn_moi": bn_moi,
            "dang_dieu_tri": dang_dieu_tri,
            "lich_hen": lich_hen
        })
        
    except Exception as e:
        print(f"Lỗi khi lấy home-stats: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        if cur:
            cur.close()

# ... (Phần còn lại của app.py) ...

@app.route("/ql-benh-nhan")
def ql_benh_nhan():
    return render_template("index.html", active="hồ_sơ_bệnh_nhân", title="Hồ sơ bệnh nhân",bn=None)

@app.route("/benh-nhan")
def benh_nhan():
    return render_template("index.html", active="hồ_sơ_bệnh_nhân", title="Hồ sơ bệnh nhân",bn=None)

@app.route("/ql-bac-si")
def ql_bac_si():
    return render_template("quanlibacsi.html", active="quản_lí_bác_sĩ", title="Quản lí bác sĩ", khoa_enum=Khoa)

@app.route("/ql-lich-hen")
def ql_lich_hen():
    return render_template("lichhen.html", active="ql_lich_hen", title="Quản lí lịch hẹn")

@app.route("/lich-lam-viec")
def lich_lam_viec():
    return render_template("lich_lam_viec.html", active="lịch_làm_việc", title="Lịch làm việc bác sĩ")

@app.route("/xet-lich-lam")
def xet_lich_lam():
    if "user" not in session:
        return redirect(url_for("login_page"))
    # Chỉ cho phép bác sĩ (hoặc admin) truy cập
    # role = session.get("role")
    # if role not in ["doctor", "admin"]: return ... (tuỳ logic)
    
    return render_template("xet_lich_lam.html", active="xet_lich_lam", title="Đăng ký lịch làm")

@app.get("/api/doctor/my-schedule")
def api_doctor_my_schedule():
    manv = session.get("manv") # Lấy mã NV từ session login
    if not manv:
        return jsonify({"error": "Chưa xác định nhân viên"}), 400
        
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify([])

    cur = cn.cursor()
    cur.execute("""
        SELECT ID, NGAY, CA, TGBATDAU, TGKETTHUC, PHONG
        FROM DBO.LICH_LAM_VIEC
        WHERE MANHANVIEN = ? AND NGAY BETWEEN ? AND ?
        ORDER BY NGAY, CA
    """, manv, start, end)
    
    rows = cur.fetchall()
    return jsonify([
        {
            "id": r[0],
            "ngay": r[1].strftime("%Y-%m-%d"),
            "ca": r[2],
            "batdau": str(r[3])[:5] if r[3] else "",
            "ketthuc": str(r[4])[:5] if r[4] else "",
            "phong": r[5]
        }
        for r in rows
    ])

@app.post("/api/doctor/schedule/register")
def api_doctor_register_schedule():
    manv = session.get("manv")
    if not manv: return jsonify({"error": "Unauthorized"}), 401
    
    d = request.get_json(force=True)
    ngay = d.get("ngay")
    ca = d.get("ca") # 'Sáng' hoặc 'Chiều'
    
    if not ngay or not ca:
        return jsonify({"error": "Thiếu thông tin"}), 400
        
    # Mapping giờ mặc định
    if ca == "Sáng":
        t_start, t_end = "07:00", "11:30"
    else:
        t_start, t_end = "13:30", "17:00"
        
    cur = cn.cursor()
    # Check trùng
    cur.execute("SELECT 1 FROM LICH_LAM_VIEC WHERE MANHANVIEN=? AND NGAY=? AND CA=?", manv, ngay, ca)
    if cur.fetchone():
        return jsonify({"error": "Lịch đã tồn tại"}), 409
        
    cur.execute("""
        INSERT INTO LICH_LAM_VIEC (MANHANVIEN, NGAY, CA, TGBATDAU, TGKETTHUC, PHONG)
        VALUES (?, ?, ?, ?, ?, ?)
    """, manv, ngay, ca, t_start, t_end, "P_KHAM") # Phòng mặc định hoặc admin xếp sau
    cn.commit()
    
    return jsonify({"success": True})

@app.post("/api/doctor/schedule/cancel")
def api_doctor_cancel_schedule():
    manv = session.get("manv")
    if not manv: return jsonify({"error": "Unauthorized"}), 401
    
    d = request.get_json(force=True)
    schedule_id = d.get("id")
    
    cur = cn.cursor()
    cur.execute("DELETE FROM LICH_LAM_VIEC WHERE ID=? AND MANHANVIEN=?", schedule_id, manv)
    if cur.rowcount == 0:
        return jsonify({"error": "Không tìm thấy lịch hoặc không có quyền"}), 404
        
    cn.commit()
    return jsonify({"success": True})

@app.get("/api/lich-lam-viec")
def api_get_lich_lam_viec():
    start = request.args.get("start")
    end = request.args.get("end")
    
    # Optional filtering by date if provided, otherwise empty
    if not start or not end:
        return jsonify([])

    cur = cn.cursor()
    cur.execute("""
        SELECT 
            llv.ID,
            nv.HOVATEN as TEN_BAC_SI,
            llv.CA,
            CONVERT(VARCHAR(5), llv.TGBATDAU, 108) as TGBATDAU,
            CONVERT(VARCHAR(5), llv.TGKETTHUC, 108) as TGKETTHUC,
            llv.PHONG,
            nv.KHOA,
            CONVERT(VARCHAR(10), llv.NGAY, 23) as NGAY
        FROM DBO.LICH_LAM_VIEC llv
        LEFT JOIN DBO.QUANLINHANVIEN nv ON llv.MANHANVIEN = nv.MANHANVIEN
        WHERE llv.NGAY BETWEEN ? AND ?
        ORDER BY llv.NGAY, llv.CA, llv.TGBATDAU
    """, start, end)
    rows = cur.fetchall()
    
    return jsonify([
        {
            "id": r[0],
            "ten_bac_si": r[1],
            "ca": r[2],
            "bat_dau": r[3],
            "ket_thuc": r[4],
            "phong": r[5],
            "khoa": r[6],
            "ngay": r[7]
        }
        for r in rows
    ])

@app.route("/lay-so-online", endpoint="lay_so_online")
def show_lay_so_online():
    return render_template("layso.html", active="quản_lí_lịch_hẹn", title="Lấy số online", bn=None, bs=session.get("user", ""), khoa_enum=Khoa)

@app.route("/ql-kham-benh")
def ql_kham_benh():
    maphieu = request.args.get("maphieu", type=int)
    loai_xn_list = _get_db_loaixn()
    return render_template(
        "khambenh.html",
        active="quản_lí_khám_bệnh",
        title="Quản lí khám bệnh",
        maphieu=maphieu,
        loai_xn=loai_xn_list
    )
@app.route("/kham/<mabn>", defaults={'maphieu': None})
@app.route("/kham/<mabn>/<maphieu>")
def trang_kham_benh(mabn, maphieu):
    cur = cn.cursor()
    cur.execute("""
        SELECT MABENHNHAN, HOVATEN,
               CONVERT(VARCHAR(10), NGAYSINH, 23) AS NGAYSINH,
               SODIENTHOAI, DIACHI
        FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?
    """, mabn)
    r = cur.fetchone()
    if not r:
        return redirect(url_for("ql_benh_nhan"))
    bn = dict(
        MABENHNHAN=r[0],
        HOVATEN=r[1],
        NGAYSINH=r[2],
        SODIENTHOAI=r[3],
        DIACHI=r[4]
    )
    bs = session.get("user", "")
    
    loai_xn_list = _get_db_loaixn()
    return render_template(
        "khambenh.html",
        title="Khám bệnh",
        active="quản_lí_khám_bệnh",
        bn=bn,
        bs=bs,
        role=session.get("role"),
        loai_xn=loai_xn_list,
        maphieu=maphieu  # Truyền mã phiếu (có thể None)
    )


@app.route("/ql-thuoc-kho")
def ql_thuoc_kho():
    return render_template("quanlithuoc.html", active="quản_lí_thuốc_kho", title="Quản lí thuốc & kho")

@app.route("/ql-thanh-toan")
def ql_thanh_toan():
    return render_template("thanhtoan.html", active="quản_lí_thanh_toán", title="Quản lí thanh toán")


@app.route("/tracuuhoso")
def tracuu_hoso():
    mabn = request.args.get("mabn")
    if not mabn:
        return redirect(url_for("benh_nhan"))
    return redirect(url_for("ho_so_benh_nhan", mabn=mabn))
# ==== Trang public cho bệnh nhân ====
@app.get("/dat-lich", endpoint="dat_lich_page")
def dat_lich_page():
    return render_template("datlichhenonline.html", title="Đặt lịch khám online")

# ==== API nhận đặt lịch (bắt buộc SĐT) ====
@app.post("/api/dat-lich")
def api_dat_lich():
    """
    Body JSON:
    {
      "HOVATEN": "...",            # bắt buộc
      "SODIENTHOAI": "09...",      # bắt buộc (9-11 số)
      "NGAY": "YYYY-MM-DD",        # bắt buộc
      "GIO": "HH:MM",              # bắt buộc
      "MANHANVIEN": "BS003",       # optional (NULL nếu chưa chọn bác sĩ)
      "KHOA": "Khoa Nội",          # optional (tham khảo thêm, không lưu vào LICHHEN)
      "GHICHU": "..."              # optional
    }
    """
    d = request.get_json(force=True) or {}
    hoten = (d.get("HOVATEN") or "").strip()
    sdt   = (d.get("SODIENTHOAI") or "").strip()
    ngay  = (d.get("NGAY") or "").strip()
    gio   = (d.get("GIO") or "").strip()
    manv  = (d.get("MANHANVIEN") or "").strip() or None
    ghichu= (d.get("GHICHU") or "").strip() or None
    email = (d.get("EMAIL") or "").strip() # New field

    # Nếu đang login là patient, force MABENHNHAN
    if session.get("role") == "patient":
         mabn_session = session.get("mabn")
         # Nếu muốn cho phép đặt hộ người khác thì bỏ check này, 
         # nhưng requirement bảo "Khi họ đặt lịch khám thì sẽ tự động đăng ký theo mã bệnh nhân của họ"
         # nên ta sẽ ưu tiên lấy mã bn của session.
         if mabn_session:
             # Logic tìm BN xem có khớp không? 
             # Ở đây ta sẽ ignore thông tin họ tên/sđt nhập sai, hoặc update lại?
             # Simple approach: If logged in, use current verified info or update it?
             # Let's assume we update contact info if provided, but link to the same MABENHNHAN
             pass


    # Validate
    if not hoten or not sdt or not ngay or not gio:
        return jsonify({"ok": False, "error": "Thiếu HỌ TÊN / SĐT / NGÀY / GIỜ"}), 400
    if not re.fullmatch(r"[0-9]{9,11}", sdt):
        return jsonify({"ok": False, "error": "Số điện thoại không hợp lệ"}), 400
    try:
        batdau = datetime.fromisoformat(f"{ngay}T{gio}")
    except Exception:
        return jsonify({"ok": False, "error": "Thời gian không hợp lệ"}), 400
    if batdau < datetime.now() - timedelta(minutes=1):
        return jsonify({"ok": False, "error": "Thời gian phải ở tương lai"}), 400

    # Thời lượng mặc định 30'
    ketthuc = batdau + timedelta(minutes=30)

    cur = cn.cursor()

    # 1) Tìm BN theo SĐT; không có thì tạo BN tối thiểu (điền sẵn SĐT & Họ tên)
    cur.execute("SELECT TOP 1 MABENHNHAN, HOVATEN FROM DBO.HOSOBENHNHAN WHERE SODIENTHOAI = ?", sdt)
    row = cur.fetchone()
    if row:
        mabn = row[0]
    else:
        mabn = _gen_new_mabn()
        cur.execute("""
            INSERT INTO DBO.HOSOBENHNHAN(MABENHNHAN, HOVATEN, SODIENTHOAI)
            VALUES (?,?,?)
        """, mabn, hoten, sdt)

    # 1.1) Cập nhật EMAIL nếu có (cho cả BN cũ và mới)
    if email:
        cur.execute("UPDATE DBO.HOSOBENHNHAN SET EMAIL=? WHERE MABENHNHAN=?", email, mabn)
        
    # 1.2) Nếu chưa đăng nhập: Kiểm tra xem BN này đã có account chưa? Nếu chưa -> tạo
    created_account = False
    generated_pass = None
    if not session.get("user"):
         cur.execute("SELECT TAIKHOAN FROM DBO.DANGNHAP WHERE MABENHNHAN=?", mabn)
         if not cur.fetchone():
             # Tạo account
             generated_pass = _generate_password()
             # Username = MABENHNHAN (để dễ nhớ/unique) hoặc email? Requirement: "gửi mail... kèm username, password"
             # Let's use MABENHNHAN as username.
             username = mabn
             
             # Hash password
             pw_hash = ph.hash(generated_pass)
             
             cur.execute("""
                 INSERT INTO DBO.DANGNHAP (TAIKHOAN, MATKHAU, MATKHAU_HASH, ROLE, MABENHNHAN)
                 VALUES (?, ?, ?, 'patient', ?)
             """, username, generated_pass, pw_hash, mabn)
             created_account = True
             
    # 1.3) Nếu đang login patient, đảm bảo mapping đúng (override biến mabn)
    if session.get("role") == "patient" and session.get("mabn"):
        mabn = session["mabn"] # Force booking for self


    # 2) Nếu có chọn bác sĩ, chặn trùng slot với BS đó (overlap)
    if manv:
        cur.execute("""
            SELECT 1
            FROM DBO.LICHHEN
            WHERE MANHANVIEN = ?
              AND (? < TGKETTHUC) AND (? > TGBATDAU)
        """, manv, batdau, ketthuc)
        if cur.fetchone():
            return jsonify({"ok": False, "error": "Khung giờ đã có lịch với bác sĩ này"}), 409

    # 3) Chèn vào LICHHEN (KHÔNG set STT/NGAY — trigger tự gán)
    sql = """
    DECLARE @ids TABLE (ID INT);

    INSERT INTO dbo.LICHHEN
        (MABENHNHAN, MANHANVIEN, TGBATDAU, TGKETTHUC, TRANGTHAI, GHICHU)
    OUTPUT INSERTED.ID INTO @ids
    VALUES
        (?,?,?,?,N'PENDING',?);

    SELECT ID FROM @ids;
    """
    cur.execute(sql, mabn, manv, batdau, ketthuc, ghichu)

    # Một số môi trường cần "đi tới" tập kết quả thực sự (nếu driver tạo ra tập kết quả rỗng trước)
    while cur.description is None:   # chưa đến result set có cột
        if not cur.nextset():
            break

    row = cur.fetchone()
    if not row or row[0] is None:
        # fallback cuối (gần như không cần dùng đến)
        cur.execute("SELECT TOP 1 ID FROM dbo.LICHHEN WHERE MABENHNHAN=? ORDER BY ID DESC", mabn)
        row = cur.fetchone()

    new_id = int(row[0])
    cn.commit()
    
    # Send Email asynchronously (or sync for simplicity here)
    if created_account and email:
        subject = "Thông báo tạo tài khoản - Phòng khám"
        body = f"""Chào {hoten},
        
Cảm ơn bạn đã đặt lịch khám.
Tài khoản của bạn đã được tạo tự động:
Username: {mabn}
Password: {generated_pass}

Vui lòng đăng nhập để xem hồ sơ và lịch sử khám.
"""
        send_email(email, subject, body)
    elif email:
        # Gửi mail xác nhận đặt lịch thường
        subject = "Xác nhận đặt lịch khám"
        body = f"""Chào {hoten},
        
Bạn đã đặt lịch thành công.
Mã lịch hẹn: {new_id}
Thời gian: {batdau.strftime("%H:%M %d/%m/%Y")}
"""
        send_email(email, subject, body)


    # 4) Lấy lại STT sau trigger để trả cho user (nếu cần hiển thị)
    cur.execute("SELECT STT FROM dbo.LICHHEN WHERE ID = ?", new_id)
    stt = cur.fetchone()[0]
    return jsonify({
        "ok": True,
        "lichhen_id": new_id,
        "mabn": mabn,
        "ten_bn": hoten,
        "batdau": batdau.strftime("%Y-%m-%d %H:%M"),
        "ketthuc": ketthuc.strftime("%Y-%m-%d %H:%M"),
        "stt": stt
    }), 201
# ==== Helper sinh mã bệnh nhân mới ====
def _gen_new_mabn():
    cur = cn.cursor()
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"BN{today}"
    cur.execute("""
        SELECT RIGHT(ISNULL(MAX(MABENHNHAN), ''), 4)
        FROM DBO.HOSOBENHNHAN
        WHERE MABENHNHAN LIKE ?
    """, prefix + "%")
    r = cur.fetchone()
    n = int(r[0]) + 1 if (r and r[0] and r[0].isdigit()) else 1
    return f"{prefix}{n:04d}"
# ==== API: danh sách khoa ====
@app.get("/api/khoa")
def api_get_khoa():
    cur = cn.cursor()
    cur.execute("""
        SELECT TEN_KHOA
        FROM DBO.KHOA
        WHERE TRANG_THAI = 1
        ORDER BY ID
    """)
    rows = cur.fetchall()
    return jsonify([r[0] for r in rows])


def _resolve_khoa_id_by_ten(cur, ten: str):
    """Map TEN_KHOA (DB) -> KHOA.ID; dùng cho DICHVU.KHOA_NUM."""
    ten = (ten or "").strip()
    if not ten:
        return None
    cur.execute(
        "SELECT ID FROM DBO.KHOA WHERE TEN_KHOA = ? AND TRANG_THAI = 1",
        ten,
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _khoa_id_to_name_map(cur):
    cur.execute("SELECT ID, TEN_KHOA FROM DBO.KHOA WHERE TRANG_THAI = 1")
    return {int(r[0]): r[1] for r in cur.fetchall()}


@app.get("/admin/khoa")
def admin_khoa_page():
    # Chặn nếu chưa login
    if not session.get("user"):
        return redirect(url_for("login"))

    # Chặn nếu không phải admin
    if session.get("role") != "admin":
        abort(403)

    # active dùng để highlight menu
    return render_template("admin_qlkhoa.html", active="ql_khoa")
# ==== NEW: Get LoaiXetNghiem from DB ====
def _get_db_loaixn():
    cur = cn.cursor()
    cur.execute("SELECT ID, TEN_LOAI FROM LOAI_XET_NGHIEM ORDER BY TEN_LOAI")
    return [{"id": r[0], "ten": r[1]} for r in cur.fetchall()]


# ==== API: lấy danh sách chỉ định theo loại ====
@app.get("/api/xetnghiem/chidinh")
def api_get_chidinh_xn():
    loai_id = request.args.get("loai_id")
    if not loai_id:
        return jsonify([])
    cur = cn.cursor()
    cur.execute("SELECT ID, TEN_CHI_DINH, GIA_THAM_KHAO, DON_VI FROM CHI_DINH_XET_NGHIEM WHERE LOAI_ID = ? ORDER BY TEN_CHI_DINH", loai_id)
    rows = cur.fetchall()
    return jsonify([
        {"id": r[0], "ten": r[1], "gia": float(r[2] or 0), "don_vi": r[3]} 
        for r in rows
    ])

# ==== API: danh sách khoa ====

@app.get("/api/bac-si", endpoint="api_list_bacsi")
def api_list_bacsi():
    kw = (request.args.get("khoa") or "").strip()
    cur = cn.cursor()

    if kw:
        key = kw
        if key.lower().startswith("khoa "):  # người dùng hay gõ "Khoa Nội"
            key = key[5:].strip()
        like = f"%{key}%"
        
        # Nếu có ngày, join với LICH_LAM_VIEC
        ngay = request.args.get("ngay")
        if ngay:
            cur.execute("""
                SELECT DISTINCT nv.MANHANVIEN, nv.HOVATEN, nv.KHOA
                FROM DBO.QUANLINHANVIEN nv
                JOIN DBO.LICH_LAM_VIEC llv ON nv.MANHANVIEN = llv.MANHANVIEN
                WHERE nv.KHOA COLLATE Vietnamese_CI_AI LIKE ?
                  AND llv.NGAY = ?
                ORDER BY nv.KHOA, nv.HOVATEN
            """, like, ngay)
        else:
            cur.execute("""
                SELECT MANHANVIEN, HOVATEN, KHOA
                FROM DBO.QUANLINHANVIEN
                WHERE KHOA COLLATE Vietnamese_CI_AI LIKE ?
                ORDER BY KHOA, HOVATEN
            """, like)
            
        rows = cur.fetchall() or []
    else:
        # Tương tự cho case không có khoa
        ngay = request.args.get("ngay")
        if ngay:
            cur.execute("""
                SELECT DISTINCT nv.MANHANVIEN, nv.HOVATEN, nv.KHOA
                FROM DBO.QUANLINHANVIEN nv
                JOIN DBO.LICH_LAM_VIEC llv ON nv.MANHANVIEN = llv.MANHANVIEN
                WHERE llv.NGAY = ?
                ORDER BY nv.KHOA, nv.HOVATEN
            """, ngay)
        else:
            cur.execute("""
                SELECT MANHANVIEN, HOVATEN, KHOA
                FROM DBO.QUANLINHANVIEN
                ORDER BY KHOA, HOVATEN
            """)
        rows = cur.fetchall() or []

    return jsonify({"ok": True, "items": [
        {"MANHANVIEN": r[0], "HOVATEN": r[1], "KHOA": r[2]} for r in rows
    ]})
@app.get("/api/lichhen/last", endpoint="lh_last")
def lh_last():
    since = request.args.get("since", "0")
    try:
        since_id = int(since)
    except ValueError:
        since_id = 0

    cur = cn.cursor()
    # Lưu ý: lấy KHOA từ QUANLINHANVIEN (alias nv)
    cur.execute("""
        SELECT TOP 1
            lh.ID,
            ISNULL(bn.HOVATEN, N'')           AS TENBN,
            ISNULL(bn.SODIENTHOAI, N'')       AS SDT,
            ISNULL(nv.KHOA, N'')              AS KHOA,
            CONVERT(VARCHAR(16), lh.TGBATDAU, 120) AS TGBATDAU
        FROM DBO.LICHHEN lh
        LEFT JOIN DBO.HOSOBENHNHAN   bn ON bn.MABENHNHAN  = lh.MABENHNHAN
        LEFT JOIN DBO.QUANLINHANVIEN nv ON nv.MANHANVIEN  = lh.MANHANVIEN
        ORDER BY lh.ID DESC
    """)
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": True, "has_new": False, "last_id": since_id})

    last_id = int(row[0])
    payload = {
        "id": last_id,
        "ten": row[1],
        "sdt": row[2],
        "khoa": row[3] or "Không rõ khoa",
        "batdau": row[4],
    }
    return jsonify({"ok": True, "has_new": (last_id > since_id), "last_id": last_id, "item": payload})

# ==== QUẢN LÝ DỊCH VỤ (ADMIN ONLY) ====

@app.route("/admin/dich-vu")
def admin_dichvu_page():
    if session.get("role") != "admin":
        return redirect(url_for("trang_chu"))

    return render_template(
        "admin_dichvu.html",
        title="Quản lý dịch vụ",
        active="ql_dich_vu",
    )

@app.get("/api/dich-vu")
def api_get_dichvu():
    """DICHVU.KHOA_NUM lưu ID bảng DBO.KHOA (khớp với /api/khoa)."""
    khoa_num = request.args.get("khoa_num", type=int)
    khoa_name = (request.args.get("khoa") or "").strip()

    cur = cn.cursor()
    try:
        id_to_name = _khoa_id_to_name_map(cur)

        if khoa_name and not khoa_num:
            khoa_num = _resolve_khoa_id_by_ten(cur, khoa_name)
            if khoa_num is None:
                return jsonify([])

        if khoa_num:
            cur.execute("""
                SELECT ID, TEN_CHI_PHI, DON_GIA, KHOA_NUM
                FROM DBO.DICHVU
                WHERE KHOA_NUM = ?
                ORDER BY TEN_CHI_PHI
            """, khoa_num)
        else:
            cur.execute("""
                SELECT ID, TEN_CHI_PHI, DON_GIA, KHOA_NUM
                FROM DBO.DICHVU
                ORDER BY TEN_CHI_PHI
            """)

        rows = cur.fetchall()

        return jsonify([
            {
                "id": r[0],
                "ten": r[1],
                "dongia": float(r[2] or 0),
                "khoa_num": int(r[3]) if r[3] is not None else None,
                "khoa_ten": id_to_name.get(int(r[3])) if r[3] is not None else None,
            }
            for r in rows
        ])
    finally:
        cur.close()


@app.post("/api/admin/dich-vu")
def api_create_dichvu():
    if session.get("user") != "admin":  # Lưu ý: check 'role' hay 'user' tuỳ logic login của bạn, ở đây giữ nguyên code cũ
        return jsonify({"error": "Unauthorized"}), 403

    d = request.get_json(force=True) or {}
    ten = (d.get("ten") or "").strip()
    khoa_num = d.get("khoa_num")
    khoa_ten = (d.get("khoa_ten") or "").strip()

    cur = cn.cursor()
    try:
        if khoa_num is not None:
            try:
                khoa_num = int(khoa_num)
            except (TypeError, ValueError):
                return jsonify({"error": "khoa_num không hợp lệ"}), 400
        elif khoa_ten:
            khoa_num = _resolve_khoa_id_by_ten(cur, khoa_ten)
        else:
            khoa_num = None

        if khoa_num is None:
            return jsonify({"error": "Vui lòng chọn khoa"}), 400

        ids = _khoa_id_to_name_map(cur)
        if khoa_num not in ids:
            return jsonify({"error": "Khoa không hợp lệ"}), 400

        try:
            dongia = float(d.get("dongia", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Đơn giá không hợp lệ"}), 400

        if not ten:
            return jsonify({"error": "Tên dịch vụ không được để trống"}), 400

        cur.execute(
            "INSERT INTO DBO.DICHVU (TEN_CHI_PHI, DON_GIA, KHOA_NUM) VALUES (?, ?, ?)",
            ten, dongia, khoa_num,
        )
    finally:
        cur.close()
    cn.commit()
    return jsonify({"success": True})


@app.put("/api/admin/dich-vu/<int:id>")
def api_update_dichvu(id):
    if session.get("user") != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    d = request.get_json(force=True) or {}
    ten = (d.get("ten") or "").strip()
    khoa_num = d.get("khoa_num")
    khoa_ten = (d.get("khoa_ten") or "").strip()

    cur = cn.cursor()
    try:
        if khoa_num is not None:
            try:
                khoa_num = int(khoa_num)
            except (TypeError, ValueError):
                return jsonify({"error": "khoa_num không hợp lệ"}), 400
        elif khoa_ten:
            khoa_num = _resolve_khoa_id_by_ten(cur, khoa_ten)
        else:
            khoa_num = None

        if khoa_num is None:
            return jsonify({"error": "Vui lòng chọn khoa"}), 400

        ids = _khoa_id_to_name_map(cur)
        if khoa_num not in ids:
            return jsonify({"error": "Khoa không hợp lệ"}), 400

        try:
            dongia = float(d.get("dongia", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Đơn giá không hợp lệ"}), 400

        if not ten:
            return jsonify({"error": "Tên dịch vụ không được để trống"}), 400

        cur.execute(
            "UPDATE DBO.DICHVU SET TEN_CHI_PHI=?, DON_GIA=?, KHOA_NUM=? WHERE ID=?",
            ten, dongia, khoa_num, id,
        )
    finally:
        cur.close()
    cn.commit()
    return jsonify({"success": True})

@app.delete("/api/admin/dich-vu/<int:id>")
def api_delete_dichvu(id):
    if session.get("user") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
        
    cur = cn.cursor()
    cur.execute("DELETE FROM DBO.DICHVU WHERE ID=?", id)
    cn.commit()
    return jsonify({"success": True})


# ==== QUẢN LÝ XÉT NGHIỆM (ADMIN ONLY) ====

@app.route("/admin/xet-nghiem")
def admin_xetnghiem_page():
    if session.get("user") != "admin":
        return redirect(url_for("trang_chu"))
    return render_template("admin_xetnghiem.html", title="Quản lý Xét nghiệm", active="ql_xet_nghiem")

# --- LOẠI XÉT NGHIỆM ---
@app.get("/api/admin/loai-xn")
def api_admin_get_loai_xn():
    if session.get("user") != "admin": return jsonify([]), 403
    cur = cn.cursor()
    cur.execute("SELECT ID, TEN_LOAI, MO_TA FROM LOAI_XET_NGHIEM ORDER BY ID")
    rows = cur.fetchall()
    return jsonify([{"id": r[0], "ten": r[1], "mota": r[2]} for r in rows])

@app.post("/api/admin/loai-xn")
def api_admin_create_loai_xn():
    if session.get("user") != "admin": return jsonify({"error": "Auth"}), 403
    d = request.get_json(force=True)
    ten = (d.get("ten") or "").strip()
    mota = (d.get("mota") or "").strip()
    if not ten: return jsonify({"error": "Thiếu tên loại"}), 400
    
    cur = cn.cursor()
    cur.execute("INSERT INTO LOAI_XET_NGHIEM (TEN_LOAI, MO_TA) VALUES (?, ?)", ten, mota)
    cn.commit()
    return jsonify({"success": True})

@app.put("/api/admin/loai-xn/<int:id>")
def api_admin_update_loai_xn(id):
    if session.get("user") != "admin": return jsonify({"error": "Auth"}), 403
    d = request.get_json(force=True)
    ten = (d.get("ten") or "").strip()
    mota = (d.get("mota") or "").strip()
    
    cur = cn.cursor()
    cur.execute("UPDATE LOAI_XET_NGHIEM SET TEN_LOAI=?, MO_TA=? WHERE ID=?", ten, mota, id)
    cn.commit()
    return jsonify({"success": True})

@app.delete("/api/admin/loai-xn/<int:id>")
def api_admin_delete_loai_xn(id):
    if session.get("user") != "admin": return jsonify({"error": "Auth"}), 403
    cur = cn.cursor()
    # Check constraint if needed, or cascade if DB set up (assuming simple delete for now)
    # Usually should delete children first or set Master ID to NULL. 
    # Let's clean up children manually to be safe.
    cur.execute("DELETE FROM CHI_DINH_XET_NGHIEM WHERE LOAI_ID=?", id)
    cur.execute("DELETE FROM LOAI_XET_NGHIEM WHERE ID=?", id)
    cn.commit()
    return jsonify({"success": True})

# --- CHI ĐỊNH (TEST ITEMS) ---
@app.get("/api/admin/loai-xn/<int:id>/chi-dinh")
def api_admin_get_chidinh_by_loai(id):
    if session.get("user") != "admin": return jsonify([]), 403
    cur = cn.cursor()
    cur.execute("SELECT ID, TEN_CHI_DINH, GIA_THAM_KHAO, DON_VI FROM CHI_DINH_XET_NGHIEM WHERE LOAI_ID=? ORDER BY ID", id)
    rows = cur.fetchall()
    return jsonify([
        {"id": r[0], "ten": r[1], "gia": float(r[2] or 0), "donvi": r[3]} 
        for r in rows
    ])

@app.post("/api/admin/chi-dinh-xn")
def api_admin_create_chidinh():
    if session.get("user") != "admin": return jsonify({"error": "Auth"}), 403
    d = request.get_json(force=True)
    loai_id = d.get("loai_id")
    ten = (d.get("ten") or "").strip()
    gia = float(d.get("gia") or 0)
    donvi = (d.get("donvi") or "").strip()
    
    if not loai_id or not ten: return jsonify({"error": "Thiếu thông tin"}), 400
    
    cur = cn.cursor()
    cur.execute("INSERT INTO CHI_DINH_XET_NGHIEM (LOAI_ID, TEN_CHI_DINH, GIA_THAM_KHAO, DON_VI) VALUES (?,?,?,?)", loai_id, ten, gia, donvi)
    cn.commit()
    return jsonify({"success": True})

@app.put("/api/admin/chi-dinh-xn/<int:id>")
def api_admin_update_chidinh(id):
    if session.get("user") != "admin": return jsonify({"error": "Auth"}), 403
    d = request.get_json(force=True)
    ten = (d.get("ten") or "").strip()
    gia = float(d.get("gia") or 0)
    donvi = (d.get("donvi") or "").strip()
    
    cur = cn.cursor()
    cur.execute("UPDATE CHI_DINH_XET_NGHIEM SET TEN_CHI_DINH=?, GIA_THAM_KHAO=?, DON_VI=? WHERE ID=?", ten, gia, donvi, id)
    cn.commit()
    return jsonify({"success": True})

@app.delete("/api/admin/chi-dinh-xn/<int:id>")
def api_admin_delete_chidinh(id):
    if session.get("user") != "admin": return jsonify({"error": "Auth"}), 403
    cur = cn.cursor()
    cur.execute("DELETE FROM CHI_DINH_XET_NGHIEM WHERE ID=?", id)
    cn.commit()
    return jsonify({"success": True})


# API BỆNH NHÂN (CRUD)

# [Trong app.py]

# ==========================================
# API BỆNH NHÂN (Đã sửa để lọc theo NGÀY)
# ==========================================
@app.get("/api/benhnhan")
@app.get("/api/benh-nhan")
def bn_list():
    # 1. Nhận tham số
    q = (request.args.get("q") or "").strip()
    khoa_filter = (request.args.get("khoa") or "").strip()
    date_filter = (request.args.get("date") or "").strip()
    status = (request.args.get("status") or "all").strip() # <--- MỚI: Nhận trạng thái (paid/unpaid)

    try:
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit/offset phải là số nguyên"}), 400

    # 2. SQL Cơ bản
    sql = """
        SELECT DISTINCT 
               bn.MABENHNHAN, 
               bn.HOVATEN,
               CONVERT(VARCHAR(10), bn.NGAYSINH, 23) as NGAYSINH,
               bn.SODIENTHOAI, 
               bn.DIACHI, 
               bn.QUEQUAN
        FROM DBO.HOSOBENHNHAN bn
    """
    
    params = []
    conditions = ["ISNULL(bn.DAXOA, 0) = 0"]

    # 3. Xử lý Lọc Khoa/Ngày (JOIN PHIEUKHAM nếu cần)
    if khoa_filter or date_filter:
        sql += " JOIN DBO.PHIEUKHAM pk ON pk.MABENHNHAN = bn.MABENHNHAN "
        if khoa_filter:
            conditions.append("pk.KHOA = ?")
            params.append(khoa_filter)
        if date_filter:
            conditions.append("CAST(pk.NGAYKHAM AS DATE) = ?")
            params.append(date_filter)

    # 4. Xử lý Lọc Trạng Thái Thanh Toán (LOGIC MỚI)
    # Sử dụng EXISTS để tìm trong lịch sử mà không cần join cứng
    # 4. Xử lý Lọc Trạng Thái Thanh Toán (ĐÃ SỬA THEO SCHEMA SQLQuery1.sql)
    if status == 'unpaid':
        # Logic: Tìm BN có phiếu khám mà hóa đơn chưa thanh toán (hoặc chưa tạo hóa đơn)
        # SỬA: pk2.MAPHIEU = hd2.PHIEUKHAM_ID
        conditions.append("""
            EXISTS (
                SELECT 1 FROM PHIEUKHAM pk2 
                LEFT JOIN HOADON hd2 ON pk2.MAPHIEU = hd2.PHIEUKHAM_ID 
                WHERE pk2.MABENHNHAN = bn.MABENHNHAN 
                AND (hd2.DATHANHTOAN = 0 OR hd2.DATHANHTOAN IS NULL)
            )
        """)
    elif status == 'paid':
        # Logic: Tìm BN có phiếu khám đã thanh toán
        # SỬA: pk2.MAPHIEU = hd2.PHIEUKHAM_ID
        conditions.append("""
            EXISTS (
                SELECT 1 FROM PHIEUKHAM pk2 
                JOIN HOADON hd2 ON pk2.MAPHIEU = hd2.PHIEUKHAM_ID
                WHERE pk2.MABENHNHAN = bn.MABENHNHAN 
                AND hd2.DATHANHTOAN = 1
            )
        """)

    # 5. Xử lý Tìm kiếm
    if q:
        conditions.append("(bn.MABENHNHAN LIKE ? OR bn.HOVATEN LIKE ? OR bn.SODIENTHOAI LIKE ?)")
        key = f"%{q}%"
        params.extend([key, key, key])

    # 6. Gộp điều kiện
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    # 7. Sắp xếp & Phân trang
    sql += " ORDER BY bn.MABENHNHAN OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    params.extend([offset, limit])

    # 8. Thực thi
    try:
        cur = cn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        
        data = [
            dict(
                MABENHNHAN=r[0],
                HOVATEN=r[1],
                NGAYSINH=r[2],
                SODIENTHOAI=r[3],
                DIACHI=r[4],
                QUEQUAN=r[5],
            )
            for r in rows
        ]
        return jsonify(data)
    except Exception as e:
        print("Lỗi SQL bn_list:", e)
        return jsonify({"error": str(e)}), 500

    # --- LOGIC LỌC THEO KHOA ---
    if khoa_filter:
        # Chỉ lấy bệnh nhân có phiếu khám ở KHOA này (trong ngày hôm nay hoặc tất cả tuỳ logic)
        # Ở đây ví dụ lấy tất cả bệnh nhân từng khám hoặc đang chờ ở khoa này
        sql += " JOIN DBO.PHIEUKHAM pk ON pk.MABENHNHAN = bn.MABENHNHAN "
        conditions.append("pk.KHOA = ?")
        params.append(khoa_filter)
        
        # Nếu muốn chỉ hiện bệnh nhân khám HÔM NAY tại khoa đó thì thêm dòng dưới:
        # conditions.append("CAST(pk.NGAYKHAM AS DATE) = CAST(GETDATE() AS DATE)")

    # --- LOGIC TÌM KIẾM ---
    if q:
        conditions.append("(bn.MABENHNHAN LIKE ? OR bn.HOVATEN LIKE ? OR bn.SODIENTHOAI LIKE ?)")
        key = f"%{q}%"
        params.extend([key, key, key])

    # Gộp điều kiện WHERE
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    # Sắp xếp và phân trang
    sql += " ORDER BY bn.MABENHNHAN OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    params.extend([offset, limit])

    cur = cn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    
    data = [
        dict(
            MABENHNHAN=r[0],
            HOVATEN=r[1],
            NGAYSINH=r[2],
            SODIENTHOAI=r[3],
            DIACHI=r[4],
            QUEQUAN=r[5],
        )
        for r in rows
    ]
    return jsonify(data)

@app.get("/api/benhnhan/<mabn>")
@app.get("/api/benh-nhan/<mabn>")
def bn_get(mabn):
    cur = cn.cursor()
    cur.execute(
        """
        SELECT MABENHNHAN,HOVATEN,
               CONVERT(VARCHAR(10), NGAYSINH, 23) as NGAYSINH,
               SODIENTHOAI,DIACHI,QUEQUAN
        FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?
        """,
        mabn,
    )
    r = cur.fetchone()
    if not r:
        return jsonify({"error": "Not found"}), 404
    return jsonify(
        dict(
            MABENHNHAN=r[0],
            HOVATEN=r[1],
            NGAYSINH=r[2],
            SODIENTHOAI=r[3],
            DIACHI=r[4],
            QUEQUAN=r[5],
        )
    )

@app.post("/api/benhnhan")
@app.post("/api/benh-nhan")
def bn_create():
    d = request.get_json(force=True)
    required = ["MABENHNHAN", "HOVATEN"]
    miss = [k for k in required if not d.get(k)]
    if miss:
        return jsonify({"error": f"Thiếu trường bắt buộc: {', '.join(miss)}"}), 400

    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?", d["MABENHNHAN"])
    if cur.fetchone():
        return jsonify({"error": "Mã bệnh nhân đã tồn tại"}), 409

    cur.execute(
        """
        INSERT INTO DBO.HOSOBENHNHAN (MABENHNHAN,HOVATEN,NGAYSINH,SODIENTHOAI,DIACHI,QUEQUAN)
        VALUES (?,?,?,?,?,?)
        """,
        d["MABENHNHAN"],
        d["HOVATEN"],
        d.get("NGAYSINH"),
        d.get("SODIENTHOAI"),
        d.get("DIACHI"),
        d.get("QUEQUAN"),
    )
    return jsonify({"status": "created", "id": d["MABENHNHAN"]}), 201

@app.put("/api/benhnhan/<mabn>")
@app.put("/api/benh-nhan/<mabn>")
@app.patch("/api/benhnhan/<mabn>")
@app.patch("/api/benh-nhan/<mabn>")
def bn_update(mabn):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute(
        """
        SELECT MABENHNHAN,HOVATEN,NGAYSINH,SODIENTHOAI,DIACHI,QUEQUAN
        FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?
        """,
        mabn,
    )
    r = cur.fetchone()
    if not r:
        return jsonify({"error": "Not found"}), 404

    current = dict(
        MABENHNHAN=r[0],
        HOVATEN=r[1],
        NGAYSINH=r[2],
        SODIENTHOAI=r[3],
        DIACHI=r[4],
        QUEQUAN=r[5],
    )
    newvals = {
        "HOVATEN": d.get("HOVATEN", current["HOVATEN"]),
        "NGAYSINH": d.get("NGAYSINH", current["NGAYSINH"]),
        "SODIENTHOAI": d.get("SODIENTHOAI", current["SODIENTHOAI"]),
        "DIACHI": d.get("DIACHI", current["DIACHI"]),
        "QUEQUAN": d.get("QUEQUAN", current["QUEQUAN"]),
    }

    cur.execute(
        """
        UPDATE DBO.HOSOBENHNHAN
        SET HOVATEN=?, NGAYSINH=?, SODIENTHOAI=?, DIACHI=?, QUEQUAN=?
        WHERE MABENHNHAN=?
        """,
        newvals["HOVATEN"],
        newvals["NGAYSINH"],
        newvals["SODIENTHOAI"],
        newvals["DIACHI"],
        newvals["QUEQUAN"],
        mabn,
    )
    return jsonify({"status": "updated"})

@app.delete("/api/benhnhan/<mabn>")
@app.delete("/api/benh-nhan/<mabn>")
def bn_delete(mabn):
    try:
        cur = cn.cursor()

        # =================================================
        # BƯỚC 1: KIỂM TRA RÀNG BUỘC (LOGIC NGHIỆP VỤ)
        # =================================================

        # 1.1. Kiểm tra xem có Hóa đơn CHƯA thanh toán không?
        # Logic: Tìm trong bảng HOADON, nối với PHIEUKHAM để lấy MABENHNHAN
        cur.execute("""
            SELECT TOP 1 h.ID
            FROM DBO.HOADON h
            INNER JOIN DBO.PHIEUKHAM pk ON pk.MAPHIEU = h.PHIEUKHAM_ID
            WHERE pk.MABENHNHAN = ? 
              AND ISNULL(h.DATHANHTOAN, 0) = 0 -- 0 là chưa thanh toán
        """, (mabn,))
        
        if cur.fetchone():
            return jsonify({
                "ok": False, 
                "error": f"Bệnh nhân {mabn} còn hóa đơn chưa thanh toán. Vui lòng thanh toán trước khi xóa."
            }), 400

        # 1.2. Kiểm tra xem có Lịch hẹn SẮP TỚI không?
        # Logic: Tìm trong bảng LICHHEN, lấy những lịch có thời gian > hiện tại
        cur.execute("""
            SELECT TOP 1 ID
            FROM DBO.LICHHEN
            WHERE MABENHNHAN = ? 
              AND TGBATDAU > GETDATE() -- Lịch hẹn trong tương lai
              AND TRANGTHAI NOT IN ('CANCELLED', 'DONE') -- Chỉ chặn lịch đang chờ
        """, (mabn,))

        if cur.fetchone():
            return jsonify({
                "ok": False, 
                "error": f"Bệnh nhân {mabn} có lịch hẹn sắp tới. Vui lòng hủy lịch trước khi xóa."
            }), 400

        # =================================================
        # BƯỚC 2: THỰC HIỆN XÓA (NẾU ĐÃ VƯỢT QUA KIỂM TRA)
        # =================================================
        
        # Vì bạn đã chạy script SQL có "ON DELETE CASCADE", 
        # bạn chỉ cần xóa bảng cha (HOSOBENHNHAN), SQL Server sẽ tự động dọn dẹp phần còn lại.
        cur.execute("DELETE FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN = ?", (mabn,))
        
        if cur.rowcount == 0:
            return jsonify({"ok": False, "error": "Bệnh nhân không tồn tại"}), 404

        cn.commit()
        return jsonify({"ok": True, "status": "deleted", "message": f"Đã xóa hồ sơ bệnh nhân {mabn}"}), 200

    except Exception as e:
        cn.rollback()
        print(f"Lỗi khi xóa bệnh nhân {mabn}: {e}")
        return jsonify({"ok": False, "error": f"Lỗi hệ thống: {str(e)}"}), 500

# ====== HỒ SƠ: Đính kèm tệp ======
from werkzeug.utils import secure_filename
@app.get("/api/hoso/file/<int:file_id>")
def api_get_file(file_id):
    cur = cn.cursor()
    cur.execute("SELECT URL, TENTEP FROM dbo.HOSODINHKEM WHERE ID=?", file_id)
    row = cur.fetchone()
    if not row:
        return "Not found", 404

    url, tentep = row[0], row[1]

    # Nếu bạn đã lưu URL tĩnh (ví dụ /static/uploads/BN002/xxx.pdf)
    # thì có thể redirect thẳng:
    if url and url.startswith("/static/"):
        return redirect(url)

    # Còn nếu bạn lưu đường dẫn vật lý (full path), dùng send_file:
    # return send_file(url, as_attachment=False, download_name=tentep)
UPLOAD_ROOT = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_ROOT, exist_ok=True)

def _rows(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

@app.get("/api/hoso/<mabn>/files")
def api_hoso_files(mabn):
    """Danh sách tệp đính kèm theo BN, mới nhất trước."""
    cur = cn.cursor()
    cur.execute("""
        SELECT ID, MABENHNHAN, MAPHIEU, TENTEP, LOAITEP, URL,
               CONVERT(VARCHAR(19), NGAYTAI, 120) AS NGAYTAI, GHICHU
        FROM dbo.HOSODINHKEM
        WHERE MABENHNHAN=? 
        ORDER BY NGAYTAI DESC, ID DESC
    """, mabn)
    return jsonify(_rows(cur))

@app.post("/api/hoso/<mabn>/upload")
def api_hoso_upload(mabn):
    """Upload 1 file -> lưu /static/uploads/<mabn>/..., ghi record HOSODINHKEM."""
    if "file" not in request.files:
        return jsonify({"error": "Thiếu file"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "File rỗng"}), 400

    ghichu = (request.form.get("ghichu") or "").strip()
    maphieu = request.form.get("maphieu", type=int)

    # Lưu vật lý
    subdir = os.path.join(UPLOAD_ROOT, mabn)
    os.makedirs(subdir, exist_ok=True)
    safe_name = secure_filename(f.filename)
    # thêm uuid để tránh trùng tên
    filename = f"{uuid4().hex}_{safe_name}"
    fullpath = os.path.join(subdir, filename)
    f.save(fullpath)

    # URL tĩnh để mở từ trình duyệt
    url = f"/static/uploads/{mabn}/{filename}"
    loai = f.mimetype or ""
    tentep = f.filename

    # Ghi DB
    cur = cn.cursor()
    cur.execute("""
        INSERT INTO dbo.HOSODINHKEM(MABENHNHAN, MAPHIEU, TENTEP, LOAITEP, URL, GHICHU)
        VALUES(?, ?, ?, ?, ?, ?)
    """, mabn, maphieu, tentep, loai, url, ghichu)

    # Trả về record vừa thêm
    cur.execute("SELECT TOP 1 * FROM dbo.HOSODINHKEM WHERE MABENHNHAN=? ORDER BY ID DESC", mabn)
    rows = _rows(cur)
    return jsonify({"ok": True, "file": rows[0] if rows else {}})

@app.delete("/api/hoso/file/<int:file_id>")
def api_hoso_delete(file_id):
    """Xoá record + xoá file vật lý (nếu còn)."""
    cur = cn.cursor()
    cur.execute("SELECT URL, MABENHNHAN FROM dbo.HOSODINHKEM WHERE ID=?", file_id)
    r = cur.fetchone()
    if not r:
        return jsonify({"error": "Không tìm thấy"}), 404
    url, mabn = r[0], r[1]

    # Xoá file
    if url and url.startswith("/static/uploads/"):
        fullpath = os.path.join(app.root_path, url.lstrip("/"))
        if os.path.exists(fullpath):
            try: os.remove(fullpath)
            except: pass

    cur.execute("DELETE FROM dbo.HOSODINHKEM WHERE ID=?", file_id)
    return jsonify({"ok": True})


# API PHIẾU KHÁM (CREATE)

@app.post("/api/phieu-kham")
def create_phieu_kham():
    d = request.get_json(force=True)
    mabn = (d.get("MABENHNHAN") or "").strip()
    manv = (d.get("MANHANVIEN") or "").strip()
    khoa = d.get("KHOA")
    lydokham = d.get("LYDOKHAM")
    chandoan = d.get("CHANDOAN")
    ghichu = d.get("GHICHU")
    ngaykham = d.get("NGAYKHAM")

    if not mabn:
        return jsonify({"error": "Thiếu MABENHNHAN"}), 400

    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?", mabn)
    if not cur.fetchone():
        return jsonify({"error": "Bệnh nhân không tồn tại"}), 404

    ensure_nhanvien(manv)

    if ngaykham:
        cur.execute(
            """
            INSERT INTO DBO.PHIEUKHAM
            (MABENHNHAN, MANHANVIEN, NGAYKHAM, KHOA, LYDOKHAM, CHANDOAN, GHICHU)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mabn, manv if manv else None, ngaykham, khoa, lydokham, chandoan, ghichu),
        )
    else:
        cur.execute(
            """
            INSERT INTO DBO.PHIEUKHAM
            (MABENHNHAN, MANHANVIEN, KHOA, LYDOKHAM, CHANDOAN, GHICHU)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (mabn, manv if manv else None, khoa, lydokham, chandoan, ghichu),
        )

    return jsonify({"status": "created"}), 201


# VIEW HỒ SƠ BỆNH NHÂN

@app.route("/ho-so/<mabn>")
def ho_so_benh_nhan(mabn):
    # --- CHECK: Nếu là bệnh nhân, chỉ được xem hồ sơ của mình ---
    if session.get("role") == "patient":
        my_mabn = session.get("mabn")
        # So sánh chuỗi cho chắc chắn
        if not my_mabn or str(my_mabn).strip() != str(mabn).strip():
            return render_template("403.html", msg="Bạn chỉ có quyền xem hồ sơ của chính mình."), 403
            
    cur = cn.cursor()

    # 1) Bệnh nhân
    cur.execute("""
        SELECT MABENHNHAN, HOVATEN,
               CONVERT(VARCHAR(10), NGAYSINH, 23) as NGAYSINH,
               SODIENTHOAI, DIACHI, QUEQUAN
        FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?
    """, mabn)
    r = cur.fetchone()
    if not r:
        abort(404)

    bn = dict(
        MABENHNHAN=r[0],
        HOVATEN=r[1],
        NGAYSINH=r[2],
        SODIENTHOAI=r[3],
        DIACHI=r[4],
        QUEQUAN=r[5],
    )

    # 2) Phiếu khám của BN
    cur.execute("""
        SELECT MAPHIEU,
               CONVERT(VARCHAR(10), NGAYKHAM, 23) as NGAYKHAM,
               KHOA, LYDOKHAM, CHANDOAN, GHICHU
        FROM dbo.PHIEUKHAM
        WHERE MABENHNHAN = ?
        ORDER BY NGAYKHAM DESC, MAPHIEU DESC
    """, str(mabn).strip())
    kham = [
        dict(MAPHIEU=a, NGAYKHAM=b, KHOA=c, LYDOKHAM=d, CHANDOAN=e, GHICHU=f)
        for (a, b, c, d, e, f) in cur.fetchall()
    ]

    # Danh sách MAPHIEU để load XN/Đơn
    maphieu_list = [row["MAPHIEU"] for row in kham] if kham else []

    # 3) Xét nghiệm
    xn = []
    if maphieu_list:
        placeholders = ",".join("?" for _ in maphieu_list)
        cur.execute(f"""
            SELECT MAXN, MAPHIEU, LOAIXN, CHIDINH,
                   CONVERT(VARCHAR(16), NGAYCHIDINH, 120) as NGAYCHIDINH,
                   TRANGTHAI
            FROM DBO.XETNGHIEM
            WHERE MAPHIEU IN ({placeholders})
            ORDER BY NGAYCHIDINH DESC, MAXN DESC
        """, maphieu_list)
        xn = [
            dict(MAXN=a, MAPHIEU=b, LOAIXN=c, CHIDINH=d, NGAYCHIDINH=e, TRANGTHAI=f)
            for (a, b, c, d, e, f) in cur.fetchall()
        ]

    # 4) Đơn thuốc (header)
    don = []
    if maphieu_list:
        placeholders = ",".join("?" for _ in maphieu_list)
        cur.execute(f"""
            SELECT MADON, MAPHIEU,
                   CONVERT(VARCHAR(10), NGAYKE, 23) as NGAYKE,
                   BACSI, GHICHU
            FROM DBO.DONTHUOC
            WHERE MAPHIEU IN ({placeholders})
            ORDER BY NGAYKE DESC, MADON DESC
        """, maphieu_list)
        don = [
            dict(MADON=a, MAPHIEU=b, NGAYKE=c, BACSI=d, GHICHU=e)
            for (a, b, c, d, e) in cur.fetchall()
        ]

    # 5) Chi tiết từng đơn
    don_ct = {}
    for don_row in don:
        cur.execute("""
            SELECT TENTHUOC, HAMLUONG, LIEUDUNG, SOLUONG, DONVI, GHICHU
            FROM DBO.DONTHUOC_CT WHERE MADON=? ORDER BY ID
        """, don_row["MADON"])
        don_ct[don_row["MADON"]] = [
            dict(TENTHUOC=a, HAMLUONG=b, LIEUDUNG=c, SOLUONG=d, DONVI=e, GHICHU=f)
            for (a, b, c, d, e, f) in cur.fetchall()
        ]

    # 6) Render
    return render_template(
        "tracuuhoso.html",
        active="hồ_sơ_bệnh_nhân",
        title="Hồ sơ: {} ({})".format(bn["HOVATEN"], bn["MABENHNHAN"]),
        bn=bn,
        kham=kham,
        xn=xn,
        don=don,
        don_ct=don_ct,
        # nếu template có dùng các biến khác (chan_doan, dinhkem, …) có thể thêm mặc định:
        chan_doan={},
        dinhkem=[],
    )


# API NHÂN VIÊN (CRUD)

@app.get("/api/nhanvien")
def nv_list():
    q = (request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit", 20))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit/offset phải là số nguyên"}), 400

    where = ""
    params = []
    if q:
        where = """
        WHERE (MANHANVIEN LIKE ? OR HOVATEN LIKE ? OR KHOA LIKE ? OR
               CHUYENMON LIKE ? OR SDT LIKE ? OR CHUCVU LIKE ? OR TRINHDO LIKE ?)
        """
        key = f"%{q}%"
        params = [key, key, key, key, key, key, key]

    sql = f"""
      SELECT MANHANVIEN, HOVATEN, CHUYENMON, KHOA,
             CONVERT(VARCHAR(10), NGAYSINH, 23) AS NGAYSINH,
             DIACHI, SOCCCD, CHUCVU, SDT, TRINHDO
      FROM DBO.QUANLINHANVIEN
      {where}
      ORDER BY MANHANVIEN
      OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """
    params += [offset, limit]

    cur = cn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    data = [
        dict(
            MANHANVIEN=r[0],
            HOVATEN=r[1],
            CHUYENMON=r[2],
            KHOA=r[3],
            NGAYSINH=r[4],
            DIACHI=r[5],
            SOCCCD=r[6],
            CHUCVU=r[7],
            SDT=r[8],
            TRINHDO=r[9],
        )
        for r in rows
    ]
    return jsonify(data)

@app.get("/api/nhanvien/<manv>")
def nv_get(manv):
    cur = cn.cursor()
    cur.execute(
        """
      SELECT MANHANVIEN, HOVATEN, CHUYENMON, KHOA,
             CONVERT(VARCHAR(10), NGAYSINH, 23) AS NGAYSINH,
             DIACHI, SOCCCD, CHUCVU, SDT, TRINHDO
      FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN=?
      """,
        manv,
    )
    r = cur.fetchone()
    if not r:
        return jsonify({"error": "Not found"}), 404
    return jsonify(
        dict(
            MANHANVIEN=r[0],
            HOVATEN=r[1],
            CHUYENMON=r[2],
            KHOA=r[3],
            NGAYSINH=r[4],
            DIACHI=r[5],
            SOCCCD=r[6],
            CHUCVU=r[7],
            SDT=r[8],
            TRINHDO=r[9],
        )
    )

@app.post("/api/nhanvien")
def nv_create():
    d = request.get_json(force=True)
    required = ["MANHANVIEN", "HOVATEN"]
    miss = [k for k in required if not d.get(k)]
    if miss:
        return jsonify({"error": "Thiếu: " + ", ".join(miss)}), 400

    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN=?", d["MANHANVIEN"])
    if cur.fetchone():
        return jsonify({"error": "Mã nhân viên đã tồn tại"}), 409

    cur.execute(
        """
      INSERT INTO DBO.QUANLINHANVIEN
      (MANHANVIEN,HOVATEN,CHUYENMON,KHOA,NGAYSINH,DIACHI,SOCCCD,CHUCVU,SDT,TRINHDO)
      VALUES (?,?,?,?,?,?,?,?,?,?)
      """,
        d["MANHANVIEN"],
        d["HOVATEN"],
        d.get("CHUYENMON"),
        d.get("KHOA"),
        d.get("NGAYSINH"),
        d.get("DIACHI"),
        d.get("SOCCCD"),
        d.get("CHUCVU"),
        d.get("SDT"),
        d.get("TRINHDO"),
    )
    return jsonify({"status": "created"}), 201

@app.put("/api/nhanvien/<manv>")
@app.patch("/api/nhanvien/<manv>")
def nv_update(manv):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN=?", manv)
    if not cur.fetchone():
        return jsonify({"error": "Not found"}), 404

    cur.execute(
        """
      UPDATE DBO.QUANLINHANVIEN
      SET HOVATEN=?, CHUYENMON=?, KHOA=?, NGAYSINH=?, DIACHI=?, SOCCCD=?,
          CHUCVU=?, SDT=?, TRINHDO=?
      WHERE MANHANVIEN=?
      """,
        d.get("HOVATEN"),
        d.get("CHUYENMON"),
        d.get("KHOA"),
        d.get("NGAYSINH"),
        d.get("DIACHI"),
        d.get("SOCCCD"),
        d.get("CHUCVU"),
        d.get("SDT"),
        d.get("TRINHDO"),
        manv,
    )
    return jsonify({"status": "updated"})

@app.delete("/api/nhanvien/<manv>")
def nv_delete(manv):
    cur = cn.cursor()
    cur.execute("DELETE FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN=?", manv)
    if cur.rowcount == 0:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"status": "deleted"})


# XUẤT EXCEL: ĐƠN THUỐC

@app.route("/export-don-thuoc/<mabn>")
def export_don_thuoc(mabn):
    cur = cn.cursor()
    cur.execute(
        """
        SELECT d.MADON, d.MAPHIEU,
               CONVERT(VARCHAR(10), d.NGAYKE, 23) as NGAYKE,
               d.BACSI, d.GHICHU,
               ct.TENTHUOC, ct.HAMLUONG, ct.LIEUDUNG, ct.SOLUONG, ct.DONVI
        FROM DBO.DONTHUOC d
        LEFT JOIN DBO.DONTHUOC_CT ct ON d.MADON = ct.MADON
        WHERE d.MABENHNHAN = ?
        ORDER BY d.NGAYKE DESC, d.MADON
        """,
        mabn,
    )
    rows = cur.fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Don Thuoc"
    headers = [
        "Mã đơn","Mã phiếu","Ngày kê","Bác sĩ","Ghi chú",
        "Tên thuốc","Hàm lượng","Liều dùng","Số lượng","Đơn vị",
    ]
    ws.append(headers)
    for r in rows:
        ws.append([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]])

    f = io.BytesIO()
    wb.save(f)
    f.seek(0)
    return send_file(
        f, as_attachment=True, download_name=f"don_thuoc_{mabn}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# API LỊCH HẸN (CRUD)

@app.get("/api/lichhen")
def lh_list():
    q = (request.args.get("q") or "").strip()
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return jsonify({"error": "limit/offset phải là số nguyên"}), 400

    where = ""
    params = []
    if q:
        where = """
        WHERE (lh.MABENHNHAN LIKE ? OR lh.MANHANVIEN LIKE ? OR lh.GHICHU LIKE ?
               OR bn.HOVATEN LIKE ? OR nv.HOVATEN LIKE ?)
        """
        key = f"%{q}%"
        params = [key, key, key, key, key, key]

    sql = f"""
    SELECT 
        lh.ID,
        lh.MABENHNHAN,
        bn.HOVATEN AS TENBN,
        bn.SODIENTHOAI AS SDT,         -- ✅ SĐT bệnh nhân
        lh.MANHANVIEN,
        nv.HOVATEN AS TENNV,           -- ✅ tên bác sĩ
        CONVERT(VARCHAR(16), lh.TGBATDAU, 120) AS TGBATDAU,
        CONVERT(VARCHAR(16), lh.TGKETTHUC, 120) AS TGKETTHUC,
        lh.TRANGTHAI,
        lh.GHICHU,
        lh.STT,
        CONVERT(VARCHAR(10), lh.NGAY, 23) AS NGAY
    FROM DBO.LICHHEN lh
    LEFT JOIN DBO.HOSOBENHNHAN bn ON lh.MABENHNHAN = bn.MABENHNHAN
    LEFT JOIN DBO.QUANLINHANVIEN nv ON lh.MANHANVIEN = nv.MANHANVIEN
    {where}
    ORDER BY lh.TGBATDAU DESC
    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """
    params += [offset, limit]

    cur = cn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()

    data = [
        dict(
            ID=r[0],
            MABENHNHAN=r[1],
            TENBN=r[2],
            SDT=r[3],                # ✅ số điện thoại bệnh nhân
            MANHANVIEN=r[4],
            TENNV=r[5],              # ✅ tên bác sĩ
            TGBATDAU=r[6],
            TGKETTHUC=r[7],
            TRANGTHAI=r[8],
            GHICHU=r[9],
            STT=r[10],
            NGAY=r[11],
        )
        for r in rows
    ]
    return jsonify(data)
@app.get("/api/lichhen/<int:lid>")
def lh_get(lid):
    cur = cn.cursor()
    cur.execute(
        """
        SELECT ID, MABENHNHAN, MANHANVIEN,
               CONVERT(VARCHAR(16), TGBATDAU, 120),
               CONVERT(VARCHAR(16), TGKETTHUC, 120),
               TRANGTHAI, GHICHU, STT,
               CONVERT(VARCHAR(10), NGAY, 23)
        FROM DBO.LICHHEN WHERE ID=?
        """,
        lid,
    )
    r = cur.fetchone()
    if not r:
        return jsonify({"error": "Not found"}), 404
    return jsonify(
        dict(
            ID=r[0], MABENHNHAN=r[1], MANHANVIEN=r[2],
            TGBATDAU=r[3], TGKETTHUC=r[4], TRANGTHAI=r[5],
            GHICHU=r[6], STT=r[7], NGAY=r[8]
        )
    )

@app.post("/api/lichhen")
def lh_create():
    d = request.get_json(force=True)
    required = ["MABENHNHAN", "TGBATDAU", "TGKETTHUC"]
    miss = [k for k in required if not d.get(k)]
    if miss:
        return jsonify({"error": f"Thiếu: {', '.join(miss)}"}), 400

    try:
        batdau = datetime.fromisoformat(d["TGBATDAU"])
        ketthuc = datetime.fromisoformat(d["TGKETTHUC"])
        cur = cn.cursor()
        cur.execute(
            """
            INSERT INTO DBO.LICHHEN
            (MABENHNHAN, MANHANVIEN, TGBATDAU, TGKETTHUC, TRANGTHAI, GHICHU)
            VALUES (?,?,?,?,?,?)
            """,
            d["MABENHNHAN"],
            d.get("MANHANVIEN"),
            batdau, ketthuc,
            d.get("TRANGTHAI", "PENDING"),
            d.get("GHICHU"),
        )
        cn.commit()
        return jsonify({"status": "created"}), 201
    except Exception as e:
        cn.rollback()
        return jsonify({"error": str(e)}), 400

@app.put("/api/lichhen/<int:lid>")
@app.patch("/api/lichhen/<int:lid>")
def lh_update(lid):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.LICHHEN WHERE ID=?", lid)
    if not cur.fetchone():
        return jsonify({"error": "Not found"}), 404

    try:
        batdau = datetime.fromisoformat(d["TGBATDAU"]) if d.get("TGBATDAU") else None
        ketthuc = datetime.fromisoformat(d["TGKETTHUC"]) if d.get("TGKETTHUC") else None
        cur.execute(
            """
            UPDATE DBO.LICHHEN
            SET MABENHNHAN=?, MANHANVIEN=?, TGBATDAU=?, TGKETTHUC=?, TRANGTHAI=?, GHICHU=?
            WHERE ID=?
            """,
            d.get("MABENHNHAN"), d.get("MANHANVIEN"),
            batdau, ketthuc,
            d.get("TRANGTHAI"), d.get("GHICHU"),
            lid,
        )
        cn.commit()
        return jsonify({"status": "updated"})
    except Exception as e:
        cn.rollback()
        return jsonify({"error": str(e)}), 400

@app.delete("/api/lichhen/<int:lid>")
def lh_delete(lid):
    try:
        cur = cn.cursor()
        cur.execute("DELETE FROM DBO.LICHHEN WHERE ID=?", lid)
        if cur.rowcount == 0:
            return jsonify({"error": "Not found"}), 404
        cn.commit()
        return jsonify({"status": "deleted"})
    except Exception as e:
        cn.rollback()
        return jsonify({"error": str(e)}), 400


# API HÀNG ĐỢI GỌI SỐ

@app.post("/api/lay-so-online", endpoint="api_lay_so_online")
def api_lay_so_online():
    d = request.get_json(force=True)
    hovaten = (d.get("HOVATEN") or "").strip()
    khoa    = (d.get("KHOA") or "").strip()
    if not (hovaten and khoa):
        return jsonify({"error": "Thiếu HOVATEN/KHOA"}), 400

    mabn = f"ONLINE-{datetime.now():%Y%m%d}-{uuid4().hex[:6].upper()}"
    cur = cn.cursor()
    cur.execute("""
        SELECT ISNULL(MAX(SO_THU_TU),0) + 1
        FROM DBO.LAYSO_ONLINE
        WHERE KHOA=? AND CAST(CREATED_AT AS DATE)=CAST(SYSDATETIME() AS DATE)
    """, khoa)
    r = cur.fetchone()
    so = int(r[0]) if r else 1

    cur.execute("""
        INSERT INTO DBO.LAYSO_ONLINE
        (KHOA, SO_THU_TU, MABENHNHAN, HOVATEN, STATUS)
        VALUES (?, ?, ?, ?, N'WAITING')
    """, (khoa, so, mabn, hovaten))
    cn.commit()

    return jsonify({"status": "ok", "khoa": khoa, "so_thu_tu": so}), 201


# [Trong file app.py]

# 1. API Lấy danh sách hôm nay (Đã sửa để gọi Stored Procedure có lọc Khoa)
@app.get("/api/lay-so-online/today")
def api_list_today():
    khoa = request.args.get("khoa")
    cur = cn.cursor()

    # Log để debug xem khoa gửi lên là gì
    print(f"DEBUG: api_list_today called with khoa={khoa}")

    # Gọi Stored Procedure
    # Lưu ý cú pháp gọi EXEC trong pyodbc
    cur.execute("{CALL dbo.sp_LaySo_ListToday (?)}", (khoa,))
    
    rows = cur.fetchall()
    
    # Format lại dữ liệu trả về
    def _fmt_dt(x):
        if x is None: return ""
        return x.strftime("%H:%M:%S") if isinstance(x, datetime) else str(x)

    data = [
        {
            "ID":         r[0],
            "KHOA":       r[1],
            "SO_THU_TU":  r[2],
            "HOVATEN":    r[3],
            "STATUS":     r[4],
            "CREATED_AT": _fmt_dt(r[5]), 
        }
        for r in rows
    ]
    return jsonify(data)


# 2. API Lấy số đang gọi (Current)
@app.get("/api/lay-so-online/current")
def api_get_current():
    khoa = request.args.get("khoa")
    if not khoa:
        return jsonify({}) # Không có khoa thì không trả về gì
        
    cur = cn.cursor()
    cur.execute("{CALL dbo.sp_LaySo_GetCurrent (?)}", (khoa,))
    r = cur.fetchone()
    
    if not r:
        return jsonify({})
        
    return jsonify({
        "id": r[0], 
        "khoa": r[1], 
        "so_thu_tu": r[2],
        "hovaten": r[3], 
        "status": r[4],
        "created_at": str(r[5]) if r[5] else None
    })


# 3. API Gọi số tiếp theo (Next)
@app.post("/api/lay-so-online/next")
def api_call_next():
    d = request.get_json(force=True)
    khoa = (d.get("KHOA") or "").strip()
    
    if not khoa:
        return jsonify({"error": "Thiếu KHOA"}), 400
        
    cur = cn.cursor()
    # Gọi Procedure xử lý logic tìm người tiếp theo và update trạng thái
    cur.execute("{CALL dbo.sp_LaySo_Next (?)}", (khoa,))
    
    # Commit transaction vì Procedure có lệnh UPDATE
    cn.commit()
    
    # Procedure này trả về row người vừa được gọi (nếu có)
    # Tuy nhiên trong pyodbc, sau khi commit đôi khi cần fetch lại hoặc procedure phải có SELECT cuối cùng
    # Nếu procedure của bạn đã có SELECT * FROM ... WHERE ID = @NextID thì OK.
    # Để an toàn, API chỉ cần trả về success, frontend sẽ tự gọi refreshCurrent
    
    return jsonify({"success": True})

@app.post("/api/lay-so-online/set-status")
def api_set_status():
    d = request.get_json(force=True)
    id_ = d.get("id")
    status = (d.get("status") or "").strip().upper()
    if not id_ or status not in ["DONE", "SKIPPED", "WAITING"]:
        return jsonify({"error": "Thiếu id hoặc status không hợp lệ"}), 400
    cur = cn.cursor()
    cur.execute("EXEC dbo.sp_LaySo_SetStatus @Id=?, @Status=?", id_, status)
    r = cur.fetchone()
    return jsonify({"status": status, "affected": r[0] if r else 0})

# Tạo PHIẾU KHÁM
@app.post("/api/kham")
def api_kham_create():
    d = request.get_json(force=True)
    mabn = (d.get("MABENHNHAN") or "").strip()
    manv = (d.get("MANHANVIEN") or "").strip()
    khoa = d.get("KHOA")
    
    if not mabn:
        return jsonify({"error": "Thiếu MABENHNHAN"}), 400

    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN=?", mabn)
    if not cur.fetchone():
        return jsonify({"error": "Bệnh nhân không tồn tại"}), 404

    ensure_nhanvien(manv, hovaten=manv or "Chưa cập nhật", khoa=khoa)

    # THỰC HIỆN INSERT (Đã xóa bỏ hoàn toàn cột PHIKHAM trong lệnh SQL)
    try:
        if d.get("NGAYKHAM"):
            cur.execute(
                """
                INSERT INTO DBO.PHIEUKHAM
                (MABENHNHAN, MANHANVIEN, NGAYKHAM, KHOA, LYDOKHAM, CHANDOAN, GHICHU)
                OUTPUT INSERTED.MAPHIEU
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                mabn, manv if manv else None, d["NGAYKHAM"], khoa,
                d.get("LYDOKHAM"), d.get("CHANDOAN"), d.get("GHICHU")
            )
        else:
            cur.execute(
                """
                INSERT INTO DBO.PHIEUKHAM
                (MABENHNHAN, MANHANVIEN, KHOA, LYDOKHAM, CHANDOAN, GHICHU)
                OUTPUT INSERTED.MAPHIEU
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                mabn, manv if manv else None, khoa,
                d.get("LYDOKHAM"), d.get("CHANDOAN"), d.get("GHICHU")
            )
        
        r = cur.fetchone()
        cn.commit()
        return jsonify({"status": "created", "MAPHIEU": int(r[0]) if r else None}), 201
    except Exception as e:
        cn.rollback()
        return jsonify({"error": str(e)}), 500
@app.get("/api/benhnhan/<mabn>/phieu-moi-nhat")
def api_latest_phieu(mabn):
    cur = cn.cursor()
    cur.execute("SELECT TOP 1 MAPHIEU FROM DBO.PHIEUKHAM WHERE MABENHNHAN=? ORDER BY MAPHIEU DESC", mabn)
    r = cur.fetchone()
    if not r: return jsonify({"ok": False}), 404
    return jsonify({"ok": True, "maphieu": int(r[0])})

@app.get("/api/benhnhan/<mabn>/lich-hen-gan-nhat")
def api_latest_lichhen(mabn):
    # Lấy lịch hẹn gần nhất (hoặc sắp tới) của bệnh nhân
    cur = cn.cursor()
    cur.execute("""
        SELECT TOP 1 lh.ID, nv.KHOA, lh.MANHANVIEN, nv.HOVATEN as TENBS, 
               CONVERT(VARCHAR(19), lh.TGBATDAU, 120) as TGBATDAU, 
               lh.GHICHU, 
               CONVERT(VARCHAR(19), lh.TGKETTHUC, 120) as TGKETTHUC
        FROM DBO.LICHHEN lh
        LEFT JOIN DBO.QUANLINHANVIEN nv ON lh.MANHANVIEN = nv.MANHANVIEN
        WHERE lh.MABENHNHAN = ? 
          AND CAST(lh.TGBATDAU AS DATE) = CAST(GETDATE() AS DATE)
        ORDER BY ABS(DATEDIFF(SECOND, GETDATE(), lh.TGBATDAU)) ASC
    """, mabn)
    r = cur.fetchone()
    if not r:
        return jsonify({"ok": False}), 404
    
    return jsonify({
        "ok": True,
        "ID": r[0],
        "KHOA": r[1],
        "MANHANVIEN": r[2],
        "TENBS": r[3],
        "TGBATDAU": r[4],
        "GHICHU": r[5],
        "TGKETTHUC": r[6]
    })

# Lấy FULL 1 phiên khám
@app.get("/api/kham/<int:maphieu>")
def api_kham_get(maphieu):
    cur = cn.cursor()
    # Phiếu khám
    cur.execute(
        """
        SELECT MAPHIEU, MABENHNHAN, MANHANVIEN,
               CONVERT(VARCHAR(16), NGAYKHAM, 120) as NGAYKHAM,
               KHOA, LYDOKHAM, CHANDOAN, GHICHU
        FROM DBO.PHIEUKHAM WHERE MAPHIEU=?
        """,
        maphieu,
    )
    pk = cur.fetchone()
    if not pk:
        return jsonify({"error": "Not found"}), 404
    pk_obj = dict(
        MAPHIEU=pk[0], MABENHNHAN=pk[1], MANHANVIEN=pk[2], NGAYKHAM=pk[3],
        KHOA=pk[4], LYDOKHAM=pk[5], CHANDOAN=pk[6], GHICHU=pk[7]
    )

    # Chẩn đoán chi tiết
    cur.execute("SELECT ID, ICD10, MOTA, LACHINH FROM DBO.CHANDOANCT WHERE MAPHIEU=? ORDER BY ID", maphieu)
    cdx = [dict(ID=a, ICD10=b, MOTA=c, LACHINH=bool(d)) for (a,b,c,d) in cur.fetchall()]

    # Xét nghiệm
    cur.execute(
        """
        SELECT MAXN, LOAIXN, CHIDINH, 
               CONVERT(VARCHAR(16), NGAYCHIDINH, 120) as NGAYCHIDINH, 
               TRANGTHAI, 
               ISNULL(GIA, 0) as GIA  -- THÊM DÒNG NÀY
        FROM DBO.XETNGHIEM WHERE MAPHIEU=? ORDER BY MAXN DESC
        """,
        maphieu,
    )
    # Cập nhật phần biến xn để nhận thêm giá trị f (GIA)
    xn = [dict(MAXN=a, LOAIXN=b, CHIDINH=c, NGAYCHIDINH=d, TRANGTHAI=e, GIA=float(f)) 
          for (a,b,c,d,e,f) in cur.fetchall()]

    # Đơn thuốc + chi tiết
    cur.execute(
        """
        SELECT MADON, CONVERT(VARCHAR(10), NGAYKE, 23) as NGAYKE, BACSI, GHICHU
        FROM DBO.DONTHUOC WHERE MAPHIEU=?
        ORDER BY NGAYKE DESC, MADON DESC
        """,
        maphieu,
    )
    don = []
    for (madon, ngayke, bacsi, ghichu) in cur.fetchall():
        cur2 = cn.cursor()
        cur2.execute(
            """
            SELECT ct.ID, ct.MATHUOC, ct.TENTHUOC, ct.HAMLUONG, ct.LIEUDUNG, ct.SOLUONG, ct.DONVI, ISNULL(t.GIA, 0)
            FROM DBO.DONTHUOC_CT ct
            LEFT JOIN DBO.THUOC t ON ct.MATHUOC = t.MATHUOC
            WHERE ct.MADON=?
            ORDER BY ct.ID
            """,
            madon,
        )
        ct = [dict(ID=i, MATHUOC=m, TENTHUOC=t, HAMLUONG=h, LIEUDUNG=l, SOLUONG=float(s), DONVI=dv, GIA=float(g)) for (i,m,t,h,l,s,dv,g) in cur2.fetchall()]
        don.append(dict(MADON=madon, NGAYKE=ngayke, BACSI=bacsi, GHICHU=ghichu, CHITIET=ct))

    # Hóa đơn + chi tiết
    cur.execute(
        """
        SELECT ID, CONVERT(VARCHAR(16), NGAYLAP, 120) as NGAYLAP,
               TONGTIEN, DATHANHTOAN, HINHTHUC
        FROM DBO.HOADON WHERE PHIEUKHAM_ID=?
        ORDER BY NGAYLAP DESC, ID DESC
        """,
        maphieu,
    )
    hoadon = []
    for (hid, ngaylap, tong, paid, hinhthuc) in cur.fetchall():
        cur2 = cn.cursor()
        cur2.execute(
            """
            SELECT ID, LOAI, MOTA, SOLUONG, DONGIA, (SOLUONG*DONGIA) AS THANHTIEN
            FROM DBO.HOADON_CT WHERE HOADON_ID=? ORDER BY ID
            """,
            hid,
        )
        ct = [dict(ID=i, LOAI=l, MOTA=m, SOLUONG=s, DONGIA=float(g), THANHTIEN=float(tt)) for (i,l,m,s,g,tt) in cur2.fetchall()]
        hoadon.append(dict(ID=hid, NGAYLAP=ngaylap, TONGTIEN=float(tong), DATHANHTOAN=bool(paid), HINHTHUC=hinhthuc, CHITIET=ct))

    return jsonify(dict(phieukham=pk_obj, chandoan=cdx, xetnghiem=xn, don=don, hoadon=hoadon))


# Thêm CHẨN ĐOÁN
@app.post("/api/kham/<int:maphieu>/chandoan")
def api_chandoan_add(maphieu):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.PHIEUKHAM WHERE MAPHIEU=?", maphieu)
    if not cur.fetchone():
        return jsonify({"error": "Phiên khám không tồn tại"}), 404
    cur.execute(
        """
        INSERT INTO DBO.CHANDOANCT (MAPHIEU, ICD10, MOTA, LACHINH)
        VALUES (?, ?, ?, ?)
        """,
        maphieu, d.get("ICD10"), d.get("MOTA"), 1 if d.get("LACHINH") else 0,
    )
    return jsonify({"status": "created"}), 201


# Chỉ định XÉT NGHIỆM
# Tìm hàm api_xn_add trong app.py và sửa lại như sau:
@app.post("/api/kham/<int:maphieu>/xn")
def api_xn_add(maphieu):
    d = request.get_json(force=True)
    cur = cn.cursor()
    # Kiểm tra phiên khám tồn tại
    cur.execute("SELECT 1 FROM DBO.PHIEUKHAM WHERE MAPHIEU=?", maphieu)
    if not cur.fetchone():
        return jsonify({"error": "Phiên khám không tồn tại"}), 404
    
    # Lấy giá trị từ frontend gửi lên, mặc định là 0 nếu không có
    gia_xn = d.get("GIA", 0)

    cur.execute(
        """
        INSERT INTO DBO.XETNGHIEM (MAPHIEU, LOAIXN, CHIDINH, GIA) -- Thêm cột GIA
        OUTPUT INSERTED.MAXN
        VALUES (?, ?, ?, ?)
        """,
        maphieu, d.get("LOAIXN"), d.get("CHIDINH"), gia_xn,
    )
    r = cur.fetchone()
    cn.commit() # Đảm bảo dữ liệu được lưu xuống DB
    return jsonify({"status": "created", "MAXN": int(r[0]) if r else None}), 201


# Nhập KẾT QUẢ xét nghiệm
@app.post("/api/xn/<int:maxn>/ket-qua")
def api_xn_result_add(maxn):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.XETNGHIEM WHERE MAXN=?", maxn)
    if not cur.fetchone():
        return jsonify({"error": "Xét nghiệm không tồn tại"}), 404
    cur.execute(
        """
        INSERT INTO DBO.KETQUAXN (MAXN, CHISO, GIATRI, DONVI, MOCTHAMCHIEU, DANHGIA, FILEURL)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        maxn, d.get("CHISO"), d.get("GIATRI"), d.get("DONVI"),
        d.get("MOCTHAMCHIEU"), d.get("DANHGIA"), d.get("FILEURL"),
    )
    return jsonify({"status": "created"}), 201


# Tạo ĐƠN THUỐC
@app.post("/api/kham/<int:maphieu>/don")
def api_don_create(maphieu):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.PHIEUKHAM WHERE MAPHIEU=?", maphieu)
    if not cur.fetchone():
        return jsonify({"error": "Phiên khám không tồn tại"}), 404
    cur.execute(
        """
        INSERT INTO DBO.DONTHUOC (MAPHIEU, BACSI, GHICHU)
        OUTPUT INSERTED.MADON
        VALUES (?, ?, ?)
        """,
        maphieu, d.get("BACSI"), d.get("GHICHU"),
    )
    r = cur.fetchone()
    return jsonify({"status": "created", "MADON": int(r[0]) if r else None}), 201


# Lưu ĐƠN THUỐC (Replace mode: Xóa cũ, tạo mới) - Để tránh duplicate khi lưu nhiều lần
@app.post("/api/kham/<int:maphieu>/don/save")
def api_don_save(maphieu):
    d = request.get_json(force=True)
    bacsi = d.get("BACSI")
    ghichu = d.get("GHICHU")
    items = d.get("CHITIET", []) # List items

    cur = cn.cursor()
    try:
        # 1. Xóa tất cả đơn thuốc cũ của phiếu này (hoặc chỉ đơn mới nhất? Logic: 1 phiếu 1 đơn)
        # Để an toàn và đơn giản cho logic "Giỏ hàng": Xóa hết đơn cũ của phiếu này
        # Lấy danh sách ma đơn cũ
        cur.execute("SELECT MADON FROM DBO.DONTHUOC WHERE MAPHIEU=?", maphieu)
        old_dons = [r[0] for r in cur.fetchall()]
        
        for md in old_dons:
            cur.execute("DELETE FROM DBO.DONTHUOC_CT WHERE MADON=?", md)
            cur.execute("DELETE FROM DBO.DONTHUOC WHERE MADON=?", md)

        # 2. Tạo đơn mới
        cur.execute("""
            INSERT INTO DBO.DONTHUOC (MAPHIEU, BACSI, GHICHU)
            OUTPUT INSERTED.MADON
            VALUES (?, ?, ?)
        """, maphieu, bacsi, ghichu)
        r = cur.fetchone()
        if not r: raise Exception("Failed to create DONTHUOC header")
        madon = int(r[0])

        # 3. Insert chi tiết
        for i in items:
            cur.execute("""
                INSERT INTO DBO.DONTHUOC_CT (MADON, MATHUOC, TENTHUOC, HAMLUONG, LIEUDUNG, SOLUONG, DONVI, GHICHU)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, madon, i.get("MATHUOC"), i.get("TENTHUOC"), i.get("HAMLUONG"), 
               i.get("LIEUDUNG"), i.get("SOLUONG"), i.get("DONVI"), "")
        
        cn.commit()
        return jsonify({"status": "saved", "MADON": madon})
    
    except Exception as e:
        cn.rollback()
        return jsonify({"error": str(e)}), 500


# Thêm CHI TIẾT ĐƠN THUỐC
@app.post("/api/don/<int:madon>/ct")
def api_donct_add(madon):
    d = request.get_json(force=True)
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.DONTHUOC WHERE MADON=?", madon)
    if not cur.fetchone():
        return jsonify({"error": "Đơn không tồn tại"}), 404
    cur.execute(
        """
        INSERT INTO DBO.DONTHUOC_CT (MADON, MATHUOC, TENTHUOC, HAMLUONG, LIEUDUNG, SOLUONG, DONVI, GHICHU)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        madon, d.get("MATHUOC"), d.get("TENTHUOC"), d.get("HAMLUONG"),
        d.get("LIEUDUNG"), d.get("SOLUONG"), d.get("DONVI"), d.get("GHICHU"),
    )
    return jsonify({"status": "created"}), 201


# Tạo HÓA ĐƠN cho phiên khám
@app.post("/api/kham/<int:maphieu>/hoadon")
def api_hd_create(maphieu):
    d = request.get_json(force=True) or {}
    hinhthuc = (d.get("HINHTHUC") or d.get("hinhthuc") or "CASH").upper()
    da_tt = bool(d.get("DATHANHTOAN") or d.get("danhdau_dathanhtoan") or d.get("paid"))

    # ✅ dùng luôn API chốt hoá đơn từ lượt khám (đã cộng thuốc)
    # Logic y hệt /api/hoa-don/tao-tu-luot-kham
    cur = cn.cursor()
    cur.execute("SELECT 1 FROM DBO.PHIEUKHAM WHERE MAPHIEU=?", maphieu)
    if not cur.fetchone():
        return jsonify({"error": "Phiên khám không tồn tại"}), 404

    # Gọi trực tiếp hàm finalize hiện có (copy logic)
    # --- phí khám ---
    try:
        cur.execute("SELECT ISNULL(PHIKHAM,0) FROM DBO.PHIEUKHAM WHERE MAPHIEU=?", maphieu)
        r = cur.fetchone()
        phi_kham = float(r[0]) if r else 0.0
    except:
        phi_kham = 0.0

    # --- xét nghiệm ---
    xn = []
    try:
        cur.execute("""
          SELECT MAXN, COALESCE(LOAIXN,N'Xét nghiệm') AS TEN, ISNULL(GIA,0) AS GIA
          FROM DBO.XETNGHIEM WHERE MAPHIEU=?
          ORDER BY MAXN
        """, maphieu)
        xn = [{"MAXN": a, "TEN": b, "GIA": c} for (a,b,c) in cur.fetchall()]
    except:
        xn = []

    # --- thuốc (lấy từ DONTHUOC_CT + giá THUOC.GIA) ---
    th = []
    try:
        cur.execute("""
          SELECT ct.MATHUOC, ct.TENTHUOC, ISNULL(ct.DONVI,'') AS DONVI,
                 ISNULL(ct.SOLUONG,0) AS SL, ISNULL(t.GIA,0) AS DONGIA
          FROM DBO.DONTHUOC d
          JOIN DBO.DONTHUOC_CT ct ON ct.MADON = d.MADON
          LEFT JOIN DBO.THUOC t ON t.MATHUOC = ct.MATHUOC
          WHERE d.MAPHIEU=?
        """, maphieu)
        th = [{"MATHUOC":a,"TENTHUOC":b,"DONVI":c,"SL":d,"DONGIA":e} for (a,b,c,d,e) in cur.fetchall()]
    except:
        th = []

    # --- tạo hoặc lấy hoá đơn hiện có ---
    cur.execute("SELECT TOP 1 ID FROM DBO.HOADON WHERE PHIEUKHAM_ID=? ORDER BY ID DESC", maphieu)
    r = cur.fetchone()
    if r:
        mahd = int(r[0])
        # xoá chi tiết cũ (CHỈ XOÁ Auto Items có REF_ID, giữ Manual Service có REF_ID is NULL)
        cur.execute("DELETE FROM DBO.HOADON_CT WHERE HOADON_ID=? AND REF_ID IS NOT NULL", mahd)
        cur.execute("UPDATE DBO.HOADON SET HINHTHUC=?, DATHANHTOAN=? WHERE ID=?",
                    hinhthuc, 1 if da_tt else 0, mahd)
    else:
        cur.execute("""
            INSERT INTO DBO.HOADON(PHIEUKHAM_ID,HINHTHUC,DATHANHTOAN)
            OUTPUT INSERTED.ID
            VALUES(?,?,?)
        """, maphieu, hinhthuc, 1 if da_tt else 0)
        row = cur.fetchone()
        if not row or row[0] is None:
             raise Exception("Không thể tạo hóa đơn (INSERT failed)")
        mahd = int(row[0])

    # --- chèn lại các dòng & tính tổng ---
    tong = 0.0

    try:
        if phi_kham > 0:
            cur.execute("""
                INSERT INTO DBO.HOADON_CT(HOADON_ID,LOAI,MOTA,SOLUONG,DONGIA,REF_ID)
                VALUES(?,?,?,?,?,?)
            """, mahd, "SERVICE", "Phí khám", 1, phi_kham, str(maphieu))
            tong += float(phi_kham)

        for x in xn:
            gia = float(x.get("GIA") or 0)
            if gia > 0:
                cur.execute("""
                    INSERT INTO DBO.HOADON_CT(HOADON_ID,LOAI,MOTA,SOLUONG,DONGIA,REF_ID)
                    VALUES(?,?,?,?,?,?)
                """, mahd, LoaiXetNghiem.TONG_QUAT.value, x["TEN"], 1, gia, str(x["MAXN"]))
                tong += gia

        for t in th:
            sl = int(t.get("SL") or 0)
            dg = float(t.get("DONGIA") or 0)
            mathuoc = t.get("MATHUOC")

            if sl <= 0:
                continue

            # ✅ TRỪ KHO – nếu không đủ thì báo lỗi
            cur.execute("""
                UPDATE DBO.THUOC
                SET TONKHO = TONKHO - ?
                WHERE MATHUOC = ? AND TONKHO >= ?
            """, sl, mathuoc, sl)

            if cur.rowcount == 0:
                cn.rollback() # Rollback immediately if stock insufficient
                return jsonify({
                    "error": f"Trong kho đã hết thuốc: {mathuoc}"
                }), 409

            # insert chi tiết hóa đơn
            mota = f"{t['TENTHUOC']} ({t.get('DONVI','')})".strip()
            cur.execute("""
                INSERT INTO DBO.HOADON_CT (HOADON_ID, LOAI, MOTA, SOLUONG, DONGIA, REF_ID)
                VALUES (?, 'DRUG', ?, ?, ?, ?)
            """, mahd, mota, sl, dg, mathuoc)

            tong += sl * dg



        # Thay vì update thủ công, gọi hàm recompute để ĐẢM BẢO tính cả các dòng manual (SERVICE) còn lại
        final_total = recompute_hoadon_total(mahd)
        
        # cur.execute("UPDATE DBO.HOADON SET TONGTIEN=? WHERE ID=?", tong, mahd)
        cn.commit()  # ✅ COMMIT TRANSACTION

        return jsonify({"status": "created", "HOADON_ID": mahd, "TONGTIEN": final_total}), 201

    except Exception as e:
        cn.rollback()
        print(f"Error creating invoice: {e}")
        return jsonify({"error": str(e)}), 500


# Thêm dòng HÓA ĐƠN
@app.post("/api/hoadon/<int:hid>/ct")
def api_hdct_add(hid):
    d = request.get_json(force=True)
    cur = cn.cursor()
    # Kiểm tra hóa đơn tồn tại
    cur.execute("SELECT 1 FROM DBO.HOADON WHERE ID=?", hid)
    if not cur.fetchone():
        return jsonify({"error": "Hóa đơn không tồn tại"}), 404

    # --- ĐOẠN CẦN SỬA ---
    try:
        # Kiểm tra và xử lý số lượng
        soluong_raw = d.get("SOLUONG")
        soluong = int(soluong_raw) if (soluong_raw and str(soluong_raw).strip() != "") else 1
        
        # Kiểm tra và xử lý đơn giá (Tránh lỗi ValueError)
        dongia_raw = d.get("DONGIA")
        dongia = float(dongia_raw) if (dongia_raw and str(dongia_raw).strip() != "") else 0.0
    except (ValueError, TypeError):
        return jsonify({"error": "Số lượng hoặc Đơn giá không hợp lệ"}), 400
    # --------------------

    cur.execute(
        """
        INSERT INTO DBO.HOADON_CT (HOADON_ID, LOAI, MOTA, SOLUONG, DONGIA)
        VALUES (?, ?, ?, ?, ?)
        """,
        hid, d.get("LOAI"), d.get("MOTA"), soluong, dongia,
    )
    recompute_hoadon_total(hid)
    return jsonify({"status": "created"}), 201


# (TÙY CHỌN) Endpoint export Excel đúng chuẩn JOIN qua PHIEUKHAM
# Không thay endpoint cũ của bạn; dùng endpoint mới này nếu muốn đúng schema.
@app.get("/export-don-thuoc-fixed/<mabn>")
def export_don_thuoc_fixed(mabn):
    cur = cn.cursor()
    cur.execute(
        """
        SELECT d.MADON, d.MAPHIEU,
               CONVERT(VARCHAR(10), d.NGAYKE, 23) as NGAYKE,
               d.BACSI, d.GHICHU,
               ct.TENTHUOC, ct.HAMLUONG, ct.LIEUDUNG, ct.SOLUONG, ct.DONVI
        FROM DBO.DONTHUOC d
        INNER JOIN DBO.PHIEUKHAM pk ON d.MAPHIEU = pk.MAPHIEU
        LEFT JOIN DBO.DONTHUOC_CT ct ON d.MADON = ct.MADON
        WHERE pk.MABENHNHAN = ?
        ORDER BY d.NGAYKE DESC, d.MADON
        """,
        mabn,
    )
    rows = cur.fetchall()
    wb = Workbook(); ws = wb.active; ws.title = "Don Thuoc"
    ws.append(["Mã đơn","Mã phiếu","Ngày kê","Bác sĩ","Ghi chú","Tên thuốc","Hàm lượng","Liều dùng","Số lượng","Đơn vị"])
    for r in rows:
        ws.append([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"don_thuoc_{mabn}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.post("/api/hoa-don/tao-tu-luot-kham")
def api_hd_finalize():
    d = request.get_json(force=True) or {}
    maphieu = int(d.get("maphieu") or 0)
    hinhthuc = (d.get("hinhthuc") or "CASH").upper()
    da_tt = bool(d.get("danhdau_dathanhtoan"))

    if not maphieu:
        return jsonify({"ok": False, "error": "Thiếu MAPHIEU"}), 400

    cur = cn.cursor()

    # phí khám (nếu DB bạn có cột PHIKHAM, không có thì =0)
    try:
        cur.execute("SELECT ISNULL(PHIKHAM,0) FROM DBO.PHIEUKHAM WHERE MAPHIEU=?", maphieu)
        r = cur.fetchone(); phi_kham = float(r[0]) if r else 0.0
    except:
        phi_kham = 0.0

    # xét nghiệm (đổi truy vấn tuỳ schema xét nghiệm của bạn)
    try:
        cur.execute("""
          SELECT MAXN, COALESCE(LOAIXN,N'Xét nghiệm') AS TEN, ISNULL(GIA,0) AS GIA
          FROM DBO.XETNGHIEM WHERE MAPHIEU=?
        """, maphieu)
        xn = rows_to_dicts(cur)
    except:
        xn = []

    # thuốc theo đơn
    cur.execute("""
      SELECT ct.MATHUOC, ISNULL(t.TENTHUOC, ct.TENTHUOC) AS TENTHUOC,
             ISNULL(ct.SOLUONG,0) AS SL, ISNULL(t.GIA,0) AS DONGIA, ISNULL(ct.DONVI,'') AS DONVI
      FROM DBO.DONTHUOC dt
      JOIN DBO.DONTHUOC_CT ct ON ct.MADON = dt.MADON
      LEFT JOIN DBO.THUOC t ON t.MATHUOC = ct.MATHUOC
      WHERE dt.MAPHIEU=?
    """, maphieu)
    th = rows_to_dicts(cur)

    # tạo/cập nhật HOADON
    cur.execute("SELECT TOP 1 ID FROM DBO.HOADON WHERE PHIEUKHAM_ID=? ORDER BY ID DESC", maphieu)
    row = cur.fetchone()
    if row:
        mahd = int(row[0])
        # xoá các dòng auto cũ (giữ dòng thủ công: có thể xác định bằng REF_ID IS NULL/NOT NULL, ở đây xoá tất cả để đơn giản)
        # UPDATE: User requested KEEP Manual Services -> Delete only REF_ID IS NOT NULL
        cur.execute("DELETE FROM DBO.HOADON_CT WHERE HOADON_ID=? AND REF_ID IS NOT NULL", mahd)
        cur.execute("UPDATE DBO.HOADON SET HINHTHUC=?, DATHANHTOAN=? WHERE ID=?", hinhthuc, 1 if da_tt else 0, mahd)
    else:
        cur.execute("INSERT INTO DBO.HOADON(PHIEUKHAM_ID,HINHTHUC,DATHANHTOAN) VALUES(?,?,?)",
                    maphieu, hinhthuc, 1 if da_tt else 0)
        cur.execute("SELECT SCOPE_IDENTITY()"); mahd = int(cur.fetchone()[0])

    # chèn lại các dòng & tính tổng
    tong = 0
    if phi_kham>0:
        cur.execute("""INSERT INTO DBO.HOADON_CT(HOADON_ID,LOAI,MOTA,SOLUONG,DONGIA,REF_ID)
                       VALUES(?,?,?,?,?,?)""",
                    mahd,'SERVICE','Phí khám',1,phi_kham,str(maphieu))
        tong += phi_kham
    for x in xn:
        gia = float(x.get("GIA") or 0)
        if gia>0:
            cur.execute("""INSERT INTO DBO.HOADON_CT(HOADON_ID,LOAI,MOTA,SOLUONG,DONGIA,REF_ID)
                           VALUES(?,?,?,?,?,?)""",
                        mahd,LoaiXetNghiem.TONG_QUAT.value,x['TEN'],1,gia,str(x['MAXN']))
            tong += gia
    for t in th:
        sl=float(t['SL'] or 0); dg=float(t['DONGIA'] or 0)
        if sl>0:
            mota=f"{t['TENTHUOC']} ({t.get('DONVI','')})".strip()
            cur.execute("""INSERT INTO DBO.HOADON_CT(HOADON_ID,LOAI,MOTA,SOLUONG,DONGIA,REF_ID)
                           VALUES(?,?,?,?,?,?)""",
        mahd,'DRUG',mota,sl,dg,t.get('MATHUOC'))
            tong += sl*dg

    cur.execute("UPDATE DBO.HOADON SET TONGTIEN=? WHERE ID=?", tong, mahd)
    cn.commit()
    return jsonify({"HOADON_ID": mahd, "TONGTIEN": tong})


@app.post("/api/hoadon/<int:mahd>/update")
def api_hd_update(mahd):
    d = request.get_json(force=True) or {}
    cur = cn.cursor()
    
    # Update Payment Status if present
    if "DATHANHTOAN" in d:
        paid = bool(d.get("DATHANHTOAN"))
        cur.execute("UPDATE DBO.HOADON SET DATHANHTOAN=? WHERE ID=?", (1 if paid else 0, mahd))

    # Update Payment Method if present
    if "HINHTHUC" in d:
        ht = d.get("HINHTHUC")
        cur.execute("UPDATE DBO.HOADON SET HINHTHUC=? WHERE ID=?", (ht, mahd))

    cn.commit()
    return jsonify({"ok": True})





# ====== KHO THUỐC ======
# Hàm tiện ích: chuyển kết quả truy vấn SQL -> list[dict]
def rows_to_dicts(cur):
    """Chuyển kết quả truy vấn (cursor) thành list dict để jsonify dễ dàng."""
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

# ====== THUỐC: Danh sách + tìm kiếm ======
@app.get("/api/thuoc")
def api_thuoc_list():
    q = (request.args.get("q") or "").strip()
    group_id = (request.args.get("group_id") or "").strip()
    
    # Pagination Params
    try:
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
    except ValueError:
        page, limit = 1, 10
        
    offset = (page - 1) * limit
    
    conditions = []
    params = []

    if q:
        conditions.append("(t.MATHUOC LIKE ? OR t.TENTHUOC LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])

    if group_id and group_id.isdigit():
        conditions.append("t.NHOM_ID = ?")
        params.append(int(group_id))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    cur = cn.cursor()
    
    # 1. Count Total
    left_join = "LEFT JOIN DBO.NHOMTHUOC nt ON nt.ID = t.NHOM_ID"
    
    cur.execute(f"SELECT COUNT(*) FROM DBO.THUOC t {left_join} {where}", params if params else [])
    total = cur.fetchone()[0]
    
    # 2. Get Page Data
    cur.execute(f"""
        SELECT t.MATHUOC, t.TENTHUOC, t.DONVI, t.HANSUDUNG, t.GIA, t.TONKHO, t.TONTOITHIEU,
               t.NHOM_ID, nt.TEN AS TEN_NHOM
        FROM DBO.THUOC t
        {left_join}
        {where}
        ORDER BY t.TENTHUOC
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """, (params if params else []) + [offset, limit])
    
    items = []
    cols = [c[0] for c in cur.description]
    for row in cur.fetchall():
        items.append(dict(zip(cols, row)))
    
    return jsonify({
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    })



# ====== THUỐC: Tạo mới ======
@app.post("/api/thuoc")
def api_thuoc_create():
    d = request.get_json(force=True) or {}
    ma   = (d.get("MATHUOC") or "").strip()
    ten  = (d.get("TENTHUOC") or "").strip()
    dv   = (d.get("DONVI") or "").strip()
    hsd  = d.get("HANSUDUNG") or None        # 'YYYY-MM-DD' hoặc None
    gia  = float(d.get("GIA") or 0)
    ton  = int(d.get("TONKHO") or 0)
    ttt  = int(d.get("TONTOITHIEU") or 0)
    nhom_id = int(d.get("NHOM_ID") or 0)
    if nhom_id <= 0: nhom_id = None

    if not ma or not ten or not dv:
        return jsonify({"ok": False, "error": "Thiếu MÃ/TÊN/ĐƠN VỊ"}), 400

    cur = cn.cursor()
    # kiểm tra trùng mã
    cur.execute("SELECT 1 FROM DBO.THUOC WHERE MATHUOC=?", ma)
    if cur.fetchone():
        return jsonify({"ok": False, "error": "Mã thuốc đã tồn tại"}), 400

    cur.execute("""
        INSERT INTO DBO.THUOC (MATHUOC, TENTHUOC, DONVI, HANSUDUNG, GIA, TONKHO, TONTOITHIEU, NHOM_ID)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (ma, ten, dv, hsd, gia, ton, ttt, nhom_id))
    cn.commit()
    return jsonify({"ok": True})
    

# ====== THUỐC: Cập nhật (không chỉnh TONKHO trực tiếp) ======
@app.put("/api/thuoc/<ma>")
def api_thuoc_update(ma):
    d   = request.get_json(force=True) or {}
    ten = (d.get("TENTHUOC") or "").strip()
    dv  = (d.get("DONVI") or "").strip()
    hsd = d.get("HANSUDUNG") or None
    gia = float(d.get("GIA") or 0)
    ttt = int(d.get("TONTOITHIEU") or 0)
    nhom_id = int(d.get("NHOM_ID") or 0)
    if nhom_id <= 0: nhom_id = None

    cur = cn.cursor()
    cur.execute("""
        UPDATE DBO.THUOC
        SET TENTHUOC=?, DONVI=?, HANSUDUNG=?, GIA=?, TONTOITHIEU=?, NHOM_ID=?
        WHERE MATHUOC=?
    """, (ten, dv, hsd, gia, ttt, nhom_id, ma))
    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Không tìm thấy thuốc"}), 404
    cn.commit()
    return jsonify({"ok": True})


# ====== THUỐC: Xoá ======
@app.delete("/api/thuoc/<ma>")
def api_thuoc_delete(ma):
    cur = cn.cursor()
    try:
        cur.execute("DELETE FROM DBO.THUOC WHERE MATHUOC=?", ma)
        if cur.rowcount == 0:
            return jsonify({"ok": False, "error": "Không tìm thấy thuốc"}), 404
        cn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        # Có thể bị ràng buộc FK từ bảng khác (đơn thuốc, lịch sử kho, …)
        return jsonify({"ok": False, "error": "Không xoá được (đang được tham chiếu)"}), 400

# ====== NHÓM THUỐC ======
@app.get("/api/nhomthuoc")
def api_nhomthuoc_list():
    cur = cn.cursor()
    cur.execute("SELECT ID, TEN FROM DBO.NHOMTHUOC ORDER BY ID")
    rows = cur.fetchall()
    return jsonify([{"id": r[0], "ten": r[1]} for r in rows])


# ====== INIT DB STRUCTS (NẾU CHƯA CÓ) ======
def ensure_db_schema():
    if not cn: 
        return
    try:
        cur = cn.cursor()
        
        # 1. Bảng NHOMTHUOC
        cur.execute("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[NHOMTHUOC]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [dbo].[NHOMTHUOC](
                    [ID] [int] IDENTITY(1,1) NOT NULL PRIMARY KEY,
                    [TEN] [nvarchar](255) NOT NULL,
                    [MOTA] [nvarchar](max) NULL
                )
            END
        """)

        # 2. Sync Enum NhomThuoc -> DB
        # Chỉ insert nếu table trống hoặc chưa đủ (đơn giản hoá: Check count)
        # Tốt nhất là check từng item
        for nt in NhomThuoc:
            cur.execute("SELECT ID FROM DBO.NHOMTHUOC WHERE TEN=?", nt.value)
            if not cur.fetchone():
                cur.execute("INSERT INTO DBO.NHOMTHUOC(TEN) VALUES(?)", nt.value)
        
        # 3. Alter Table THUOC add column NHOM_ID if not exists
        cur.execute("""
            IF NOT EXISTS (
                SELECT * FROM sys.columns 
                WHERE Name = N'NHOM_ID' AND Object_ID = OBJECT_ID(N'dbo.THUOC')
            )
            BEGIN
                ALTER TABLE dbo.THUOC ADD NHOM_ID INT NULL;
                ALTER TABLE dbo.THUOC ADD CONSTRAINT FK_THUOC_NHOM FOREIGN KEY (NHOM_ID) REFERENCES dbo.NHOMTHUOC(ID);
            END
        """)
        cur.execute("""
            IF NOT EXISTS (
                SELECT * FROM sys.columns
                WHERE Name = N'KHOA_NUM' AND Object_ID = OBJECT_ID(N'dbo.DICHVU')
            )
            BEGIN
                ALTER TABLE dbo.DICHVU ADD KHOA_NUM INT NULL;
            END
        """)

        # 4. Set default KHAC for existing nulls (Optional but good practice)
        # Find KHAC ID
        cur.execute("SELECT ID FROM DBO.NHOMTHUOC WHERE TEN=?", NhomThuoc.KHAC.value)
        row = cur.fetchone()
        if row:
            khac_id = row[0]
            cur.execute("UPDATE DBO.THUOC SET NHOM_ID=? WHERE NHOM_ID IS NULL", khac_id)
            
        cn.commit()
        print(">>> [Database] Schema Verified (NhomThuoc)")

    except Exception as e:
        print(f">>> [Database] Schema Init Error: {e}")

# Run schema check on startup
ensure_db_schema()

# ====== KHO: Nhập/Xuất ======
@app.post("/api/kho/nhapxuat")
def api_kho_nhapxuat():
    d = request.get_json(force=True) or {}
    ma   = (d.get("MATHUOC") or "").strip()
    loai = (d.get("LOAI") or "").upper()     # 'IN' | 'OUT'
    sl   = int(d.get("SOLUONG") or 0)
    ref  = (d.get("THAMCHIEU") or "").strip()
    note = (d.get("GHICHU") or "").strip()

    if not ma or loai not in ("IN","OUT") or sl <= 0:
        return jsonify({"ok": False, "error": "Dữ liệu không hợp lệ"}), 400

    cur = cn.cursor()
    # kiểm tra thuốc tồn tại + lấy TONKHO
    cur.execute("SELECT TONKHO FROM DBO.THUOC WHERE MATHUOC=?", ma)
    r = cur.fetchone()
    if not r:
        return jsonify({"ok": False, "error": "Mã thuốc không tồn tại"}), 404
    ton = int(r[0])

    if loai == "OUT" and ton < sl:
        return jsonify({"ok": False, "error": f"Tồn kho không đủ (hiện {ton})"}), 400

    try:
        # 1) ghi lịch sử nhập/xuất
        cur.execute("""
            INSERT INTO DBO.XUATNHAP_KHO (MATHUOC, LOAI, SOLUONG, THAMCHIEU, GHICHU)
            VALUES (?, ?, ?, ?, ?)
        """, (ma, loai, sl, ref, note))

        # 2) cập nhật tồn kho
        if loai == "IN":
            cur.execute("UPDATE DBO.THUOC SET TONKHO = TONKHO + ? WHERE MATHUOC=?", (sl, ma))
        else:
            cur.execute("UPDATE DBO.THUOC SET TONKHO = TONKHO - ? WHERE MATHUOC=?", (sl, ma))

        cn.commit()
        return jsonify({"ok": True})
    except Exception as e:
        cn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500


# ====== KHO: Lịch sử nhập/xuất theo mã thuốc ======
@app.get("/api/kho/lichsu/<ma>")
def api_kho_lichsu(ma):
    cur = cn.cursor()
    cur.execute("""
        SELECT
            ID,
            LOAI,
            SOLUONG,
            CONVERT(VARCHAR(19), NGAYGD, 120) AS NGAYGD,  
            THAMCHIEU,
            GHICHU
        FROM DBO.XUATNHAP_KHO
        WHERE MATHUOC = ?
        ORDER BY NGAYGD DESC, ID DESC                     
    """, (ma,))
    cols = [c[0] for c in cur.description]
    data = [dict(zip(cols, r)) for r in cur.fetchall()]
    return jsonify(data)

# === LIST HÓA ĐƠN CHO TRANG /ql-thanh-toan ===
@app.get("/api/hoadon")
def api_hoadon_list():
    q = (request.args.get("q") or "").strip()
    only_unpaid = request.args.get("only_unpaid", "1").strip()  # mặc định chỉ hiện chưa TT

    where = []
    params = []

    # lọc chưa thanh toán nếu bật
    if only_unpaid in ("1", "true", "True", "yes", "on"):
        where.append("ISNULL(hd.DATHANHTOAN,0) = 0")

    # tìm theo mã BN / tên / sđt (bạn có thể thêm field nếu muốn)
    if q:
        where.append("(bn.MABENHNHAN LIKE ? OR bn.HOVATEN LIKE ? OR bn.SODIENTHOAI LIKE ?)")
        key = f"%{q}%"
        params += [key, key, key]

    # ✅ PHÂN QUYỀN: Bác sĩ chỉ xem được phiếu khám của mình
    if session.get("role") == "doctor":
        # Filter by actual MANHANVIEN ID linked to the account
        manv = session.get("manv")
        if manv:
            where.append("pk.MANHANVIEN = ?")
            params.append(manv)
        else:
             # Fallback if no employee ID linked (shouldn't happen if setup correctly)
             where.append("1=0") 

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # ✅ TÍNH TỔNG TIỀN TỪ HOADON_CT (bao gồm thuốc)
    sql = f"""
        SELECT
            hd.ID,
            hd.NGAYLAP,
            CAST(ISNULL(SUM(CAST(ct.SOLUONG AS DECIMAL(18,2)) * CAST(ct.DONGIA AS DECIMAL(18,2))), 0) AS FLOAT) AS TONGTIEN,
            hd.DATHANHTOAN,
            bn.MABENHNHAN  AS BN_MABN,
            bn.HOVATEN     AS BN_HOVATEN
        FROM dbo.HOADON hd
        INNER JOIN dbo.PHIEUKHAM pk ON pk.MAPHIEU = hd.PHIEUKHAM_ID
        INNER JOIN dbo.HOSOBENHNHAN bn ON bn.MABENHNHAN = pk.MABENHNHAN
        LEFT JOIN dbo.HOADON_CT ct ON ct.HOADON_ID = hd.ID
        {where_sql}
        GROUP BY
            hd.ID, hd.NGAYLAP, hd.DATHANHTOAN,
            bn.MABENHNHAN, bn.HOVATEN
        ORDER BY hd.NGAYLAP DESC, hd.ID DESC
    """

    cur = cn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()

    data = [
        dict(
            ID=r[0],
            NGAYLAP=str(r[1]) if r[1] else None,
            TONGTIEN=float(r[2] or 0),
            DATHANHTOAN=int(r[3] or 0),
            BN_MABN=r[4],
            BN_HOVATEN=r[5],
        )
        for r in rows
    ]
    return jsonify(data)

# MAIN
@app.post("/api/pay-url")
def api_pay_url():
    d = request.get_json(force=True) or {}
    hoadon_id = int(d.get("hoadon_id") or 0)
    if hoadon_id <= 0:
        return jsonify({"ok": False, "error": "Thiếu hoadon_id"}), 400

    cur = cn.cursor()
    cur.execute("SELECT ISNULL(DATHANHTOAN,0) FROM dbo.HOADON WHERE ID=?", hoadon_id)
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Hóa đơn không tồn tại"}), 404
    if int(row[0] or 0) == 1:
        return jsonify({"ok": False, "error": "Hóa đơn đã thanh toán"}), 409

    # ✅ TÍNH LẠI TỔNG TIỀN TỪ HOADON_CT (bao gồm thuốc)
    tong = recompute_hoadon_total(hoadon_id)

    txnref = uuid4().hex[:20]  # hoặc cách bạn đang tạo

    vnp_params = {
        "vnp_Version": "2.1.0",
        "vnp_Command": "pay",
        "vnp_TmnCode": VNPAY_TMN_CODE,
        "vnp_Amount": int(round(tong)) * 100,  # VNPAY dùng đơn vị x100
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": txnref,
        "vnp_OrderInfo": f"Thanh toan hoa don {hoadon_id}",
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_OrderType": "other",
        "vnp_Locale": "vn",
        "vnp_ReturnUrl": VNPAY_RETURN_URL if os.getenv("VNPAY_RETURN_URL") else url_for('vnpay_return', _external=True),
        "vnp_IpAddr": request.remote_addr or "127.0.0.1",
        "vnp_CreateDate": datetime.now().strftime("%Y%m%d%H%M%S"),
    }

    pay_url, secure_hash = vnpay_build_url(vnp_params)

    # lưu txnRef vào hóa đơn (tránh tạo trùng)
    cur.execute("""
        UPDATE dbo.HOADON SET
            VNPAY_TXNREF=?, VNPAY_TMN_CODE=?, VNPAY_STATUS=ISNULL(VNPAY_STATUS,'PENDING')
        WHERE ID=? AND ISNULL(DATHANHTOAN,0)=0
    """, txnref, VNPAY_TMN_CODE, hoadon_id)
    cn.commit()

    return jsonify({"url": pay_url, "txnRef": txnref})

# Xóa 1 hóa đơn (cho nút xóa lẻ)
@app.delete("/api/hoadon/<int:hid>")
def api_hoadon_delete_one(hid):
    cur = cn.cursor()
    cur.execute("SELECT ID, DATHANHTOAN FROM dbo.HOADON WHERE ID=?", hid)
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Hóa đơn không tồn tại"}), 404
    
    if int(row[1] or 0) == 1:
        return jsonify({"ok": False, "error": "Hóa đơn đã thanh toán, không thể xóa"}), 409

    # Xóa chi tiết trước (để an toàn nếu không có Cascade)
    cur.execute("DELETE FROM dbo.HOADON_CT WHERE HOADON_ID=?", hid)
    cur.execute("DELETE FROM dbo.HOADON WHERE ID=?", hid)
    cn.commit()
    return jsonify({"ok": True, "deleted": hid})

@app.get("/api/hoadon/<int:hid>/status")
def api_hoadon_status(hid):
    cur = cn.cursor()
    cur.execute("SELECT DATHANHTOAN FROM dbo.HOADON WHERE ID=?", hid)
    row = cur.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "DATHANHTOAN": bool(row[0])})

@app.delete("/api/hoadon")
def api_hoadon_delete_many():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"ok": False, "error": "Không có hóa đơn nào được chọn"}), 400

    cur = cn.cursor()
    qmarks = ",".join("?" for _ in ids)
    cur.execute(f"SELECT ID, DATHANHTOAN FROM dbo.HOADON WHERE ID IN ({qmarks})", ids)
    rows = cur.fetchall()
    paid = [r[0] for r in rows if int(r[1] or 0) == 1]
    if paid:
        return jsonify({"ok": False, "error": f"Hóa đơn {paid} đã thanh toán, không thể xóa"}), 409

    cur.execute(f"DELETE FROM dbo.HOADON WHERE ID IN ({qmarks})", ids)
    cn.commit()
    return jsonify({"ok": True, "deleted": len(ids)})
 
@app.get("/vnpay_return")
def vnpay_return():
    # Lấy tất cả query params
    qs = dict(request.args)
    v_secure = qs.pop("vnp_SecureHash", None)
    # build lại chuỗi ký
    sorted_params = dict(sorted(qs.items()))
    raw = "&".join([f"{k}={quote_plus(str(v))}" for k,v in sorted_params.items() if v is not None])
    calc = vnpay_hmac_sha512(VNPAY_HASH_SECRET, raw)

    valid = (v_secure and v_secure.lower() == calc.lower())
    txnref = qs.get("vnp_TxnRef")
    resp   = qs.get("vnp_ResponseCode")  # "00" thành công
    trans  = qs.get("vnp_TransactionNo")
    bank   = qs.get("vnp_BankCode")
    cardt  = qs.get("vnp_CardType")
    paydt  = qs.get("vnp_PayDate")

    # tìm hóa đơn theo TXNREF
    cur = cn.cursor()
    cur.execute("SELECT ID FROM dbo.HOADON WHERE VNPAY_TXNREF=?", txnref)
    row = cur.fetchone()
    if row:
        hid = int(row[0])
        # cập nhật trạng thái theo return (chưa chốt, IPN sẽ là nguồn “final”)
        status = "SUCCESS" if (valid and resp=="00") else "FAILED"
        
        # (IPN sẽ chạy sau để confirm lại, nhưng nếu return đã OK thì cứ set trước)
        req_paid = 1 if status == "SUCCESS" else 0

        cur.execute("""
            UPDATE dbo.HOADON SET
                VNPAY_TRANSACTIONNO=?, VNPAY_BANKCODE=?, VNPAY_CARDTYPE=?,
                VNPAY_PAYDATE=?, VNPAY_RESPONSECODE=?, VNPAY_SECUREHASH=?, VNPAY_STATUS=?,
                DATHANHTOAN=(CASE WHEN ?=1 THEN 1 ELSE DATHANHTOAN END) 
            WHERE ID=?
        """, trans, bank, cardt, paydt, resp, v_secure, status, req_paid, hid)
        cn.commit()

    # Hiển thị kết quả nhanh (có thể redirect về trang hồ sơ hay hóa đơn)
    msg = "Thanh toán thành công!" if (valid and resp=="00") else "Thanh toán thất bại hoặc không hợp lệ!"
    return render_template("thanhtoantrave.html", title="Kết quả thanh toán", message=msg, detail=qs, valid=valid)
@app.get("/vnpay_ipn")
def vnpay_ipn():
    qs = dict(request.args)
    v_secure = qs.pop("vnp_SecureHash", None)

    # verify
    sorted_params = dict(sorted(qs.items()))
    raw = "&".join([f"{k}={quote_plus(str(v))}" for k,v in sorted_params.items() if v is not None])
    calc = vnpay_hmac_sha512(VNPAY_HASH_SECRET, raw)
    if not (v_secure and v_secure.lower() == calc.lower()):
        # code theo spec: 97 = Invalid signature
        return jsonify({"RspCode":"97","Message":"Invalid signature"})

    txnref = qs.get("vnp_TxnRef")
    resp   = qs.get("vnp_ResponseCode")
    trans  = qs.get("vnp_TransactionNo")
    bank   = qs.get("vnp_BankCode")
    cardt  = qs.get("vnp_CardType")
    paydt  = qs.get("vnp_PayDate")
    amount = int(qs.get("vnp_Amount") or 0)

    cur = cn.cursor()
    cur.execute("SELECT ID, ISNULL(DATHANHTOAN,0) FROM dbo.HOADON WHERE VNPAY_TXNREF=?", txnref)
    r = cur.fetchone()
    if not r:
        return jsonify({"RspCode":"01","Message":"Order not found"})
    hid, paid = int(r[0]), int(r[1])

    if paid:
        return jsonify({"RspCode":"02","Message":"Order already paid"})

    # ✅ TÍNH LẠI TỔNG (bao gồm thuốc) rồi mới so amount
    tong = recompute_hoadon_total(hid)

    if int(round(tong)) * 100 != amount:
        return jsonify({"RspCode":"04","Message":"Invalid amount"})

    if resp == "00":
        cur.execute("""
            UPDATE dbo.HOADON 
            SET DATHANHTOAN=1, VNPAY_STATUS='SUCCESS', 
                VNPAY_TRANSACTIONNO=?, VNPAY_BANKCODE=?, VNPAY_CARDTYPE=?, VNPAY_PAYDATE=?
            WHERE ID=?
        """, trans, bank, cardt, paydt, hid)
        cn.commit()
        return jsonify({"RspCode":"00","Message":"Confirm Success"})
    else:
        cur.execute("UPDATE dbo.HOADON SET VNPAY_STATUS='FAILED' WHERE ID=?", hid)
        cn.commit()
        return jsonify({"RspCode":"00","Message":"Confirm Success"})

# ====== PHIẾU KHÁM TỔNG HỢP ======

@app.get("/phieu-tong-hop/<int:maphieu>")
def phieu_tong_hop_view(maphieu):
    cur = cn.cursor()
    # Chạy procedure lấy dữ liệu
    cur.execute("EXEC dbo.sp_PhieuKham_TongHop ?", maphieu)

    # recordset 1: header (Giữ nguyên)
    header = cur.fetchall()
    cols = [c[0] for c in cur.description]
    header = [dict(zip(cols, row)) for row in header]
    header = header[0] if header else {}

    # recordset 2: chi tiết chi phí (CẦN KIỂM TRA SQL TRONG PROCEDURE)
    cur.nextset()
    cols2 = [c[0] for c in cur.description]
    details = [dict(zip(cols2, row)) for row in cur.fetchall()]

    # TÍNH LẠI TỔNG TIỀN dựa trên giá trị thực tế trong details
    tong_tien = sum(float(r["THANHTIEN"] or 0) for r in details)

    return render_template(
        "phieukhamtong.html",
        header=header,
        details=details,
        tong_tien=tong_tien
    )
@app.get("/phieu-tong-hop-bn/<mabn>")
def phieu_tong_hop_by_bn(mabn):
    cur = cn.cursor()
    cur.execute("""
        SELECT TOP 1 MAPHIEU
        FROM DBO.PHIEUKHAM
        WHERE MABENHNHAN = ?
        ORDER BY NGAYKHAM DESC, MAPHIEU DESC
    """, mabn)
    row = cur.fetchone()
    if not row:
        abort(404, description="Bệnh nhân chưa có phiếu khám")
    maphieu = int(row[0])
    # Redirect sang trang đã có sẵn: /phieu-tong-hop/<maphieu>
    return redirect(url_for("phieu_tong_hop_view", maphieu=maphieu))
@app.get("/quansat-layso")
def quansat_layso():
    return render_template("quansatlaysochobenhnhan.html", title="Bảng số theo khoa", khoa_enum=Khoa)\
    ###BAOCAOTHONGKE
@app.route("/bao-cao-thong-ke")
def bao_cao_thong_ke():
    cur = cn.cursor()

    # ====== lấy tháng/năm từ querystring, mặc định hiện tại ======
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    # chặn giá trị bậy
    if month < 1 or month > 12:
        month = today.month
    if year < 2000 or year > 2100:
        year = today.year

    # ====== Tổng bệnh nhân ======
    cur.execute("SELECT COUNT(*) FROM DBO.HOSOBENHNHAN")
    tong_benh_nhan = int(cur.fetchone()[0] or 0)

    # ====== Lượt khám trong tháng ======
    cur.execute("""
        SELECT COUNT(*)
        FROM DBO.PHIEUKHAM
        WHERE YEAR(NGAYKHAM)=? AND MONTH(NGAYKHAM)=?
    """, (year, month))
    tong_luot_kham_thang = int(cur.fetchone()[0] or 0)

    # ====== Số bệnh nhân khám trong tháng (không trùng) ======
    cur.execute("""
        SELECT COUNT(DISTINCT MABENHNHAN)
        FROM DBO.PHIEUKHAM
        WHERE YEAR(NGAYKHAM)=? AND MONTH(NGAYKHAM)=?
    """, (year, month))
    benh_nhan_kham_thang = int(cur.fetchone()[0] or 0)

    # ====== Hóa đơn đã thanh toán trong tháng ======
    # Nếu DB bạn không có NGAYLAP thì đổi sang cột ngày tương ứng (VD: NGAYTAO)
    cur.execute("""
        SELECT COUNT(*)
        FROM DBO.HOADON
        WHERE DATHANHTOAN=1 AND YEAR(NGAYLAP)=? AND MONTH(NGAYLAP)=?
    """, (year, month))
    tong_hoa_don_thang = int(cur.fetchone()[0] or 0)

    cur.execute("""
        SELECT COALESCE(SUM(TONGTIEN), 0)
        FROM DBO.HOADON
        WHERE DATHANHTOAN=1 AND YEAR(NGAYLAP)=? AND MONTH(NGAYLAP)=?
    """, (year, month))
    tong_doanh_thu_thang = float(cur.fetchone()[0] or 0)

    # ====== Chart: doanh thu theo ngày trong tháng ======
    cur.execute("""
        SELECT DAY(NGAYLAP) AS NGAY, COALESCE(SUM(TONGTIEN),0) AS DOANHTHU
        FROM DBO.HOADON
        WHERE DATHANHTOAN=1 AND YEAR(NGAYLAP)=? AND MONTH(NGAYLAP)=?
        GROUP BY DAY(NGAYLAP)
        ORDER BY DAY(NGAYLAP)
    """, (year, month))

    labels, values = [], []
    for ngay, dt in cur.fetchall():
        labels.append(str(int(ngay)))
        values.append(float(dt or 0))

    # luôn tạo list tháng 1..12
    month_options = [{"value": i, "label": f"Tháng {i}"} for i in range(1, 13)]

    return render_template(
        "baocao.html",
        year=year,
        month=month,
        month_options=month_options,
        tong_benh_nhan=tong_benh_nhan,
        tong_luot_kham_thang=tong_luot_kham_thang,
        benh_nhan_kham_thang=benh_nhan_kham_thang,
        tong_hoa_don_thang=tong_hoa_don_thang,
        tong_doanh_thu_thang=tong_doanh_thu_thang,
        chart_data={"labels": labels, "values": values},
    )

app.register_blueprint(chatbot_bp)
# ==========================================
# ĐỔI MẬT KHẨU (CHO BỆNH NHÂN & BÁC SĨ)
# ==========================================

@app.route("/doi-mat-khau")
def doi_mat_khau_page():
    if "user" not in session:
        return redirect(url_for("login_page"))
    return render_template("doimatkhau.html", title="Đổi mật khẩu", active="doi_mat_khau")

@app.post("/api/change-password")
def api_change_password():
    if "user" not in session:
        return jsonify({"success": False, "error": "Vui lòng đăng nhập lại"}), 401

    d = request.get_json(force=True) or {}
    old_pass = (d.get("old_pass") or "").strip()
    new_pass = (d.get("new_pass") or "").strip()
    confirm_pass = (d.get("confirm_pass") or "").strip()

    # 1. Validate đầu vào
    if not old_pass or not new_pass:
        return jsonify({"success": False, "error": "Vui lòng nhập đầy đủ thông tin"}), 400
    
    if new_pass != confirm_pass:
        return jsonify({"success": False, "error": "Mật khẩu xác nhận không khớp"}), 400

    if len(new_pass) < 6:
        return jsonify({"success": False, "error": "Mật khẩu mới phải có ít nhất 6 ký tự"}), 400

    current_user = session["user"] # TAIKHOAN

    # 2. Kiểm tra mật khẩu cũ
    cur = cn.cursor()
    cur.execute("SELECT MATKHAU_HASH, MATKHAU FROM DBO.DANGNHAP WHERE TAIKHOAN = ?", current_user)
    row = cur.fetchone()
    
    if not row:
        return jsonify({"success": False, "error": "Tài khoản không tồn tại"}), 404

    db_hash, db_plain = row

    # Logic verify: Ưu tiên check hash argon2, nếu không có thì check plain text (cho tk cũ)
    is_valid = False
    try:
        if db_hash:
            is_valid = ph.verify(db_hash, old_pass)
        elif db_plain:
            is_valid = (db_plain == old_pass)
    except Exception:
        is_valid = False

    if not is_valid:
        return jsonify({"success": False, "error": "Mật khẩu cũ không chính xác"}), 400

    # 3. Cập nhật mật khẩu mới (Hash argon2)
    try:
        new_hash = ph.hash(new_pass)
        # Cập nhật hash và mật khẩu plain (nếu bạn muốn giữ plain để debug, 
        # nhưng tốt nhất là set MATKHAU=NULL hoặc lưu hash vào cả 2 cột tuỳ cấu trúc DB của bạn)
        # Ở đây tôi cập nhật cả 2 để tương thích code cũ của bạn
        cur.execute("""
            UPDATE DBO.DANGNHAP 
            SET MATKHAU_HASH = ?, MATKHAU = ? 
            WHERE TAIKHOAN = ?
        """, new_hash, new_pass, current_user)
        cn.commit()
        
        return jsonify({"success": True, "message": "Đổi mật khẩu thành công!"})
    except Exception as e:
        cn.rollback()
        print(f"Lỗi đổi mật khẩu: {e}")
        return jsonify({"success": False, "error": "Lỗi hệ thống"}), 500
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
    
    # Giới hạn an toàn: Sync tối đa 500 trang (50000 thuốc) mỗi lần gọi để tránh timeout/spam
    # Nếu muốn full: user có thể bấm sync nhiều lần hoặc tăng giới hạn này.
    MAX_PAGES = 500
    PAGE_SIZE = 100 
    
    cn_internal = None
    try:
        cn_internal = pyodbc.connect(CONN_STR, autocommit=True)
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

# ===== MOBILE APIs (for Flutter) — matched to real DB schema =====

# ── Shared ──

@app.get("/api/mobile/khoa")
def api_mobile_khoa():
    """List all active departments."""
    cur = cn.cursor()
    try:
        cur.execute("SELECT ID, TEN_KHOA, MO_TA FROM DBO.KHOA WHERE TRANG_THAI = 1 ORDER BY TEN_KHOA")
        rows = cur.fetchall()
        return jsonify([dict(ID=r[0], TEN_KHOA=r[1], MO_TA=r[2]) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.get("/api/mobile/bacsi")
def api_mobile_bacsi():
    """List doctors, optionally filtered by department (KHOA column in QUANLINHANVIEN)."""
    khoa = request.args.get("khoa", "").strip()
    cur = cn.cursor()
    try:
        sql = """
            SELECT nv.MANHANVIEN, nv.HOVATEN, nv.SDT, nv.EMAIL, nv.KHOA, nv.CHUCVU
            FROM DBO.QUANLINHANVIEN nv
            WHERE 1=1
        """
        params = []
        if khoa:
            sql += " AND nv.KHOA = ?"
            params.append(khoa)
        sql += " ORDER BY nv.HOVATEN"
        cur.execute(sql, params)
        rows = cur.fetchall()
        return jsonify([
            dict(MANHANVIEN=r[0], HOVATEN=r[1], SDT=r[2],
                 EMAIL=r[3], KHOA=r[4], CHUCVU=r[5])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Patient: Appointments ──

@app.post("/api/mobile/dat-lich")
def api_mobile_dat_lich():
    """Book an appointment. LICHHEN schema: MABENHNHAN, MANHANVIEN, TGBATDAU, TGKETTHUC, GHICHU."""
    d = request.get_json(force=True) or {}
    mabn = d.get("MABENHNHAN", "").strip()
    manv = d.get("MANHANVIEN", "").strip()
    ngay = d.get("NGAY", "").strip()           # e.g. "2026-03-25"
    gio = d.get("GIO", "").strip()             # e.g. "08:30"
    ghichu = d.get("GHICHU", "").strip()

    if not mabn or not ngay:
        return jsonify({"error": "Thiếu thông tin bắt buộc"}), 400

    tg_batdau = f"{ngay} {gio}:00" if gio else f"{ngay} 08:00:00"
    tg_ketthuc = f"{ngay} {gio.split(':')[0]}:30:00" if gio else f"{ngay} 08:30:00"

    cur = cn.cursor()
    try:
        cur.execute("""
            INSERT INTO DBO.LICHHEN (MABENHNHAN, MANHANVIEN, TGBATDAU, TGKETTHUC, GHICHU, TRANGTHAI)
            VALUES (?, ?, ?, ?, ?, N'PENDING')
        """, mabn, manv or None, tg_batdau, tg_ketthuc, ghichu or None)
        cn.commit()
        return jsonify({"success": True, "message": "Đặt lịch thành công"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.get("/api/mobile/my-appointments")
def api_mobile_my_appointments():
    """Get patient's appointments from LICHHEN."""
    mabn = request.args.get("mabn", "").strip()
    if not mabn:
        return jsonify({"error": "Missing mabn"}), 400

    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT lh.ID, lh.MABENHNHAN, lh.MANHANVIEN,
                   nv.HOVATEN as TEN_BACSI,
                   CONVERT(VARCHAR(10), lh.TGBATDAU, 23) as NGAY,
                   CONVERT(VARCHAR(5), lh.TGBATDAU, 108) as GIO,
                   lh.GHICHU, lh.TRANGTHAI, lh.STT
            FROM DBO.LICHHEN lh
            LEFT JOIN DBO.QUANLINHANVIEN nv ON nv.MANHANVIEN = lh.MANHANVIEN
            WHERE lh.MABENHNHAN = ?
            ORDER BY lh.TGBATDAU DESC
        """, mabn)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], MABENHNHAN=r[1], MANHANVIEN=r[2],
                 TEN_BACSI=r[3], NGAY=r[4], GIO=r[5],
                 GHICHU=r[6], TRANGTHAI=r[7], STT=r[8])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Patient: Services ──

@app.get("/api/mobile/dich-vu")
def api_mobile_dich_vu():
    """List medical services and prices from DICHVU."""
    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT ID, TEN_CHI_PHI, DON_GIA, KHOA_NUM
            FROM DBO.DICHVU
            ORDER BY TEN_CHI_PHI
        """)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], TEN_CHI_PHI=r[1], DON_GIA=float(r[2]) if r[2] else 0, KHOA_NUM=r[3])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Patient: Queue ──

@app.post("/api/mobile/lay-so-online")
def api_mobile_lay_so():
    """Take an online queue number — inserts into LAYSO_ONLINE."""
    d = request.get_json(force=True) or {}
    mabn = d.get("MABENHNHAN", "").strip()
    hovaten = d.get("HOVATEN", "").strip()
    khoa = d.get("KHOA", "").strip()

    if not mabn or not khoa:
        return jsonify({"error": "Thiếu mã BN hoặc khoa"}), 400

    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT ISNULL(MAX(SO_THU_TU), 0) + 1
            FROM DBO.LAYSO_ONLINE
            WHERE KHOA = ? AND CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)
        """, khoa)
        so = (cur.fetchone() or [1])[0]

        cur.execute("""
            INSERT INTO DBO.LAYSO_ONLINE (KHOA, SO_THU_TU, MABENHNHAN, HOVATEN, STATUS)
            VALUES (?, ?, ?, ?, 'WAITING')
        """, khoa, so, mabn, hovaten or mabn)
        cn.commit()
        return jsonify({"success": True, "so_thu_tu": so, "khoa": khoa})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.get("/api/mobile/list-today")
def api_mobile_list_today():
    """Queue list for today at a department from LAYSO_ONLINE."""
    khoa = request.args.get("khoa", "").strip()
    cur = cn.cursor()
    try:
        sql = """
            SELECT ID, KHOA, SO_THU_TU, MABENHNHAN, HOVATEN, STATUS,
                   CONVERT(VARCHAR(5), CREATED_AT, 108) as GIO
            FROM DBO.LAYSO_ONLINE
            WHERE CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)
        """
        params = []
        if khoa:
            sql += " AND KHOA = ?"
            params.append(khoa)
        sql += " ORDER BY SO_THU_TU"
        cur.execute(sql, params)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], KHOA=r[1], SO_THU_TU=r[2], MABENHNHAN=r[3],
                 HOVATEN=r[4], STATUS=r[5], GIO=r[6])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Patient: Records ──

@app.get("/api/mobile/my-records")
def api_mobile_my_records():
    """Get patient examination records from PHIEUKHAM."""
    mabn = request.args.get("mabn", "").strip()
    if not mabn:
        return jsonify({"error": "Missing mabn"}), 400

    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT pk.MAPHIEU,
                   CONVERT(VARCHAR(10), pk.NGAYKHAM, 23) as NGAYKHAM,
                   pk.KHOA, pk.MANHANVIEN,
                   nv.HOVATEN as TEN_BACSI,
                   pk.CHANDOAN, pk.LYDOKHAM, pk.GHICHU
            FROM DBO.PHIEUKHAM pk
            LEFT JOIN DBO.QUANLINHANVIEN nv ON nv.MANHANVIEN = pk.MANHANVIEN
            WHERE pk.MABENHNHAN = ?
            ORDER BY pk.NGAYKHAM DESC
        """, mabn)
        rows = cur.fetchall()
        return jsonify([
            dict(MAPHIEU=r[0], NGAYKHAM=r[1], KHOA=r[2],
                 BACSI=r[3], TEN_BACSI=r[4], CHANDOAN=r[5],
                 LYDOKHAM=r[6], GHICHU=r[7])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ===== DOCTOR MOBILE APIs (Phase 3) =====

# ── Doctor: Schedule ──

@app.get("/api/mobile/doctor/my-schedule")
def api_mobile_doctor_schedule():
    """Get doctor's work schedule from LICH_LAM_VIEC."""
    manv = request.args.get("manv", "").strip()
    if not manv:
        return jsonify({"error": "Missing manv"}), 400

    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT ID, MANHANVIEN,
                   CONVERT(VARCHAR(10), NGAY, 23) as NGAY,
                   CA,
                   CONVERT(VARCHAR(5), TGBATDAU, 108) as GIO_BAT_DAU,
                   CONVERT(VARCHAR(5), TGKETTHUC, 108) as GIO_KET_THUC
            FROM DBO.LICH_LAM_VIEC
            WHERE MANHANVIEN = ? AND NGAY >= CAST(SYSDATETIME() AS DATE)
            ORDER BY NGAY, CA
        """, manv)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], MANHANVIEN=r[1], NGAY=r[2], BUOI=r[3],
                 GIO_BAT_DAU=r[4], GIO_KET_THUC=r[5], TRANGTHAI='ACTIVE')
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.post("/api/mobile/doctor/register-schedule")
def api_mobile_doctor_register_schedule():
    """Register a new work shift."""
    d = request.get_json(force=True) or {}
    manv = d.get("MANHANVIEN", "").strip()
    ngay = d.get("NGAY", "").strip()
    buoi = d.get("BUOI", "").strip()          # Sáng / Chiều

    if not manv or not ngay or not buoi:
        return jsonify({"error": "Thiếu thông tin"}), 400

    gio_bd = "07:30" if buoi == "Sáng" else "13:30"
    gio_kt = "11:30" if buoi == "Sáng" else "16:30"

    cur = cn.cursor()
    try:
        # Check duplicate
        cur.execute("""
            SELECT COUNT(*) FROM DBO.LICH_LAM_VIEC
            WHERE MANHANVIEN = ? AND NGAY = ? AND CA = ?
        """, manv, ngay, buoi)
        if (cur.fetchone()[0] or 0) > 0:
            return jsonify({"error": "Đã đăng ký ca này rồi"}), 409

        cur.execute("""
            INSERT INTO DBO.LICH_LAM_VIEC (MANHANVIEN, NGAY, CA, TGBATDAU, TGKETTHUC)
            VALUES (?, ?, ?, ?, ?)
        """, manv, ngay, buoi, gio_bd, gio_kt)
        cn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.delete("/api/mobile/doctor/cancel-schedule/<int:schedule_id>")
def api_mobile_doctor_cancel_schedule(schedule_id):
    """Cancel a schedule shift."""
    cur = cn.cursor()
    try:
        cur.execute("UPDATE DBO.LICH_LAM_VIEC SET TRANGTHAI = 'CANCELLED' WHERE ID = ?", schedule_id)
        cn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Doctor: Appointments ──

@app.get("/api/mobile/doctor/appointments")
def api_mobile_doctor_appointments():
    """Get appointments for a doctor from LICHHEN."""
    manv = request.args.get("manv", "").strip()
    date = request.args.get("date", "").strip()
    cur = cn.cursor()
    try:
        sql = """
            SELECT lh.ID, lh.MABENHNHAN, bn.HOVATEN as TEN_BN,
                   CONVERT(VARCHAR(10), lh.TGBATDAU, 23) as NGAY,
                   CONVERT(VARCHAR(5), lh.TGBATDAU, 108) as GIO,
                   lh.GHICHU, lh.TRANGTHAI, lh.STT
            FROM DBO.LICHHEN lh
            LEFT JOIN DBO.HOSOBENHNHAN bn ON bn.MABENHNHAN = lh.MABENHNHAN
            WHERE 1=1
        """
        params = []
        if manv:
            sql += " AND lh.MANHANVIEN = ?"
            params.append(manv)
        if date:
            sql += " AND CAST(lh.TGBATDAU AS DATE) = ?"
            params.append(date)
        sql += " ORDER BY lh.TGBATDAU"
        cur.execute(sql, params)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], MABENHNHAN=r[1], TEN_BN=r[2], NGAY=r[3],
                 GIO=r[4], GHICHU=r[5], TRANGTHAI=r[6], STT=r[7])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.put("/api/mobile/doctor/appointments/<int:apt_id>")
def api_mobile_doctor_update_appointment(apt_id):
    """Update appointment status (CONFIRMED/CANCELLED/DONE)."""
    d = request.get_json(force=True) or {}
    status = d.get("TRANGTHAI", "").strip()
    if not status:
        return jsonify({"error": "Missing TRANGTHAI"}), 400
    cur = cn.cursor()
    try:
        cur.execute("UPDATE DBO.LICHHEN SET TRANGTHAI = ? WHERE ID = ?", status, apt_id)
        cn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Doctor: Queue Call ──

@app.post("/api/mobile/doctor/call-next")
def api_mobile_doctor_call_next():
    """Call next patient in queue — update LAYSO_ONLINE status."""
    d = request.get_json(force=True) or {}
    khoa = d.get("KHOA", "").strip()
    if not khoa:
        return jsonify({"error": "Missing KHOA"}), 400

    cur = cn.cursor()
    try:
        # Mark current CALLING as DONE
        cur.execute("""
            UPDATE DBO.LAYSO_ONLINE SET STATUS = 'DONE'
            WHERE KHOA = ? AND STATUS = 'CALLING'
              AND CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)
        """, khoa)

        # Find next WAITING
        cur.execute("""
            SELECT TOP 1 ID, SO_THU_TU, MABENHNHAN, HOVATEN
            FROM DBO.LAYSO_ONLINE
            WHERE KHOA = ? AND STATUS = 'WAITING'
              AND CAST(CREATED_AT AS DATE) = CAST(SYSDATETIME() AS DATE)
            ORDER BY SO_THU_TU
        """, khoa)
        row = cur.fetchone()
        if not row:
            cn.commit()
            return jsonify({"success": True, "message": "Hết bệnh nhân chờ", "current": None})

        cur.execute("UPDATE DBO.LAYSO_ONLINE SET STATUS = 'CALLING' WHERE ID = ?", row[0])
        cn.commit()
        return jsonify({
            "success": True,
            "current": dict(ID=row[0], SO_THU_TU=row[1], MABENHNHAN=row[2], HOVATEN=row[3])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Doctor: Room/Bed ──

@app.get("/api/mobile/doctor/phongbenh")
def api_mobile_doctor_phongbenh():
    """List rooms with bed counts."""
    khoa = request.args.get("khoa", "").strip()
    cur = cn.cursor()
    try:
        sql = """
            SELECT p.ID, p.TENPHONG, p.KHOA, p.LOAI, p.SUCCHUA, p.TRANGTHAI,
                   (SELECT COUNT(*) FROM DBO.GIUONGBENH g
                    WHERE g.PHONG_ID = p.ID AND g.TRANGTHAI = 'OCCUPIED') as DANG_DUNG
            FROM DBO.PHONGBENH p
            WHERE 1=1
        """
        params = []
        if khoa:
            sql += " AND p.KHOA = ?"
            params.append(khoa)
        sql += " ORDER BY p.TENPHONG"
        cur.execute(sql, params)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], TENPHONG=r[1], KHOA=r[2], LOAI=r[3],
                 SUCCHUA=r[4], TRANGTHAI=r[5], DANG_DUNG=r[6])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


@app.get("/api/mobile/doctor/giuongbenh/<int:phong_id>")
def api_mobile_doctor_giuongbenh(phong_id):
    """List beds in a room."""
    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT g.ID, g.TENGIUONG, g.MABENHNHAN,
                   bn.HOVATEN, g.TRANGTHAI,
                   CONVERT(VARCHAR(10), g.NGAYVAO, 23) as NGAYVAO
            FROM DBO.GIUONGBENH g
            LEFT JOIN DBO.HOSOBENHNHAN bn ON bn.MABENHNHAN = g.MABENHNHAN
            WHERE g.PHONG_ID = ?
            ORDER BY g.TENGIUONG
        """, phong_id)
        rows = cur.fetchall()
        return jsonify([
            dict(ID=r[0], TENGIUONG=r[1], MABENHNHAN=r[2],
                 HOVATEN=r[3], TRANGTHAI=r[4], NGAYVAO=r[5])
            for r in rows
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Change Password ──

@app.post("/api/mobile/doi-mat-khau")
def api_mobile_doi_mat_khau():
    """Change password for logged-in user."""
    d = request.get_json(force=True) or {}
    taikhoan = d.get("taikhoan", "").strip()
    mk_cu = d.get("matkhau_cu", "").strip()
    mk_moi = d.get("matkhau_moi", "").strip()

    if not taikhoan or not mk_cu or not mk_moi:
        return jsonify({"error": "Thiếu thông tin"}), 400

    if len(mk_moi) < 6:
        return jsonify({"error": "Mật khẩu mới phải ít nhất 6 ký tự"}), 400

    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT MATKHAU, MATKHAU_HASH FROM DBO.DANGNHAP WHERE TAIKHOAN = ?
        """, taikhoan)
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Tài khoản không tồn tại"}), 404

        mk_plain, mk_hash = row
        ok_pw = False
        if mk_hash:
            try:
                ok_pw = ph.verify(mk_hash, mk_cu)
            except VerifyMismatchError:
                ok_pw = False
        else:
            ok_pw = (mk_plain == mk_cu)

        if not ok_pw:
            return jsonify({"error": "Mật khẩu cũ không đúng"}), 401

        new_hash = ph.hash(mk_moi)
        cur.execute("""
            UPDATE DBO.DANGNHAP SET MATKHAU = ?, MATKHAU_HASH = ? WHERE TAIKHOAN = ?
        """, mk_moi, new_hash, taikhoan)
        cn.commit()
        return jsonify({"success": True, "message": "Đổi mật khẩu thành công"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


# ── Doctor: Profile ──

@app.get("/api/mobile/doctor/profile")
def api_mobile_doctor_profile():
    manv = request.args.get("manv", "")
    if not manv:
        return jsonify({"error": "Thiếu mã nhân viên"}), 400
    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT MANHANVIEN, HOVATEN, CHUYENMON, KHOA,
                   CONVERT(VARCHAR, NGAYSINH, 23) AS NGAYSINH,
                   DIACHI, SOCCCD, CHUCVU, SDT, TRINHDO, EMAIL
            FROM DBO.QUANLINHANVIEN WHERE MANHANVIEN = ?
        """, manv)
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Không tìm thấy bác sĩ"}), 404
        cols = [d[0] for d in cur.description]
        return jsonify(dict(zip(cols, row)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()

# ── Patient: Profile ──

@app.get("/api/mobile/patient/profile")
def api_mobile_patient_profile():
    mabn = request.args.get("mabn", "")
    if not mabn:
        return jsonify({"error": "Thiếu mã bệnh nhân"}), 400
    cur = cn.cursor()
    try:
        cur.execute("""
            SELECT MABENHNHAN, HOVATEN,
                   CONVERT(VARCHAR, NGAYSINH, 23) AS NGAYSINH,
                   SODIENTHOAI, EMAIL, DIACHI, QUEQUAN
            FROM DBO.HOSOBENHNHAN WHERE MABENHNHAN = ?
        """, mabn)
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Không tìm thấy bệnh nhân"}), 404
        cols = [d[0] for d in cur.description]
        return jsonify(dict(zip(cols, row)))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5000)
