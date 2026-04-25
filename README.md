# Hệ Thống Quản Lý Bệnh Viện (Hospital Management System)

Dự án phần mềm quản lý bệnh viện toàn diện, được xây dựng bằng **Python (Flask)** và **SQL Server**, tích hợp các tính năng hiện đại như đặt lịch online, thanh toán VNPAY, bảo mật 2 lớp (2FA) và Chatbot AI hỗ trợ.

## 🚀 Tính Năng Chính

### 1. Quản Trị Hệ Thống & Bảo Mật
- **Đăng nhập/Đăng xuất:** Xác thực người dùng an toàn.
- **Bảo mật 2 lớp (2FA):** Tích hợp TOTP (Google Authenticator) để tăng cường bảo mật cho tài khoản nhân viên/bác sĩ.
- **Phân quyền:** Hệ thống phân quyền rõ ràng cho Admin, Bác sĩ và Nhân viên.

### 2. Quản Lý Bệnh Nhân
- **Hồ sơ bệnh nhân:** Lưu trữ và tra cứu thông tin hành chính, lịch sử khám bệnh.
- **Tiếp nhận:** Quản lý quy trình tiếp nhận bệnh nhân mới và tái khám.

### 3. Đặt Lịch & Quản Lý Lịch Hẹn
- **Đặt lịch Online:** Bệnh nhân có thể đặt lịch khám trực tuyến qua website.
- **Lấy số tự động:** Hệ thống cấp số thứ tự khám bệnh.
- **Màn hình gọi số:** Giao diện hiển thị số thứ tự đang khám, số tiếp theo (Real-time).

### 4. Quản Lý Khám Chữa Bệnh
- **Bác sĩ làm việc:** Xem danh sách bệnh nhân chờ, thực hiện khám bệnh.
- **Chỉ định:** Ra y lệnh các dịch vụ cận lâm sàng (Xét nghiệm, Siêu âm, X-Quang...).
- **Kê đơn thuốc:** Tra cứu thuốc tồn kho và kê đơn trực tiếp trên phần mềm.
- **Lịch làm việc:** Quản lý ca trực, lịch làm việc của bác sĩ.

### 5. Quản Lý Dược & Kho
- **Danh mục thuốc:** Quản lý thông tin thuốc, đơn vị tính, giá bán.
- **Tồn kho:** Theo dõi số lượng thuốc xuất/nhập, cảnh báo tồn kho tối thiểu.

### 6. Tài Chính & Thanh Toán
- **Quản lý hóa đơn:** Tự động tính toán chi phí khám, xét nghiệm, thuốc.
- **Thanh toán Online:** Tích hợp cổng thanh toán **VNPAY** (Môi trường Sandbox).

### 7. Tính Năng Mở Rộng (AI)
- **Chatbot hỗ trợ:** Tích hợp RAG (Retrieval-Augmented Generation) để hỗ trợ tra cứu thông tin chuyên môn hoặc hướng dẫn quy trình.

---

## 🛠️ Yêu Cầu Kỹ Thuật

- **Ngôn ngữ:** Python 3.8+
- **Framework:** Flask
- **Cơ sở dữ liệu:** Microsoft SQL Server
- **Frontend:** HTML, CSS, JavaScript (Jinja2 Templates)
- **AI/LLM:** ChromaDB, Google Gemini / OpenAI (tùy cấu hình)

---

## ⚙️ Hướng Dẫn Cài Đặt & Setup

### Bước 1: Clone dự án
```bash
git clone https://github.com/your-repo/duanquanlibenhvien.git
cd duanquanlibenhvien
```

### Bước 2: Tạo môi trường ảo (Khuyên dùng)
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

### Bước 3: Cài đặt thư viện
Dự án sử dụng file `requirements_flask.txt` cho các dependencies chính.
```bash
pip install -r requirements_flask.txt
```

### Bước 4: Cấu hình biến môi trường
Tạo file `.env` tại thư mục gốc và cấu hình các thông số kết nối Database và API Key.
```bash
cp .env.example .env
```
Nội dung file `.env` mẫu:
```ini
# Cấu hình Database SQL Server
DB_SERVER=localhost
DB_NAME=quanlibenhvien
DB_USER=sa
DB_PASSWORD=YourStrongPassword

# VNPAY Config (Demo)
VNPAY_TMN_CODE=XHOC0ESL
VNPAY_HASH_SECRET=N3M7I6SKVVCJFBYCBK92W4J3APR7DNYK
VNPAY_PAY_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
VNPAY_RETURN_URL=http://localhost:5000/vnpay_return

# Khóa bí mật Flask
SECRET_KEY=super-secret-key-change-this

# Cấu hình AI (Nếu dùng Chatbot)
OPENAI_API_KEY=sk-...
# Hoặc GOOGLE_API_KEY nếu dùng Gemini
```

### Bước 5: Khởi tạo Cơ sở dữ liệu
Đảm bảo bạn đã cài đặt SQL Server và tạo database `quanlibenhvien`.
Sau đó chạy các script SQL trong thư mục (nếu có) hoặc đảm bảo cấu trúc bảng đã được khởi tạo đúng.

### Bước 6: Chạy ứng dụng
```bash
python app.py
```
Hệ thống sẽ khởi chạy tại: `http://localhost:5000`

---

## 📂 Cấu Trúc Thư Mục Chính

```
.
├── app.py                  # File chính khởi chạy ứng dụng Flask
├── chatbot_routes.py       # Các route xử lý Chatbot AI
├── sync_logic.py           # Logic đồng bộ dữ liệu (nếu có)
├── requirements_flask.txt  # Danh sách thư viện cần thiết
├── templates/              # Chứa các file giao diện HTML (Jinja2)
│   ├── home.html           # Trang chủ
│   ├── khambenh.html       # Giao diện khám bệnh
│   ├── ...
├── static/                 # Chứa CSS, JS, Images
└── data/                   # Dữ liệu cho VectorDB (RAG)
```

## 🤝 Đóng Góp
Mọi đóng góp đều được hoan nghênh. Vui lòng tạo Pull Request hoặc mở Issue để báo lỗi.
