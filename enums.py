from enum import Enum

class Khoa(str, Enum):
    NOI = "Khoa Nội"
    NGOAI = "Khoa Ngoại"
    SAN = "Khoa Sản"
    NHI = "Khoa Nhi"
    CAP_CUU = "Khoa Cấp Cứu"
    MAT = "Khoa Mắt"
    TAI_MUI_HONG = "Khoa Tai Mũi Họng"
    RANG_HAM_MAT = "Khoa Răng Hàm Mặt"
    DA_LIEU = "Khoa Da Liễu"
    PHUC_HOI_CHUC_NANG = "Khoa Phục Hồi Chức Năng"
    # Add others as needed

class LoaiXetNghiem(str, Enum):
    TONG_QUAT = "XET_NGHIEM"
    HUYET_HOC = "Huyết Học"
    SINH_HOA = "Sinh Hóa"
    VI_SINH = "Vi Sinh"
    MIEN_DICH = "Miễn Dịch"
    GIAI_PHAU_BENH = "Giải Phẫu Bệnh"
    # --- Bổ Sung: Nhóm Bệnh Phẩm Khác ---
    NUOC_TIEU = "Nước Tiểu"
    PHAN = "Phân"
    DICH_CHOC_DO = "Dịch Chọc Dò (Màng phổi/bụng/khớp)"

    # --- Bổ Sung: Nhóm Huyết Học Chuyên Sâu ---
    DONG_MAU = "Đông Máu"
    NHOM_MAU = "Định Nhóm Máu"
    KHI_MAU = "Khí Máu Động Mạch"

    # --- Bổ Sung: Nhóm Sinh Hóa/Chuyển Hóa (Chi tiết) ---
    CHUC_NANG_GAN = "Chức Năng Gan"
    CHUC_NANG_THAN = "Chức Năng Thận"
    MO_MAU = "Mỡ Máu (Lipid)"
    DUONG_HUYET = "Đường Huyết & HbA1c"
    DIEN_GIAI_DO = "Điện Giải Đồ"
    MEN_TIM = "Men Tim (Tim Mạch)"
    VI_CHAT = "Vi Chất & Vitamin"
    
    # --- Bổ Sung: Nhóm Nội Tiết & Hormone ---
    TUYEN_GIAP = "Chức Năng Tuyến Giáp"
    NOI_TIET_TO_NU = "Nội Tiết Tố Nữ"
    NOI_TIET_TO_NAM = "Nội Tiết Tố Nam"
    TUYEN_YEN = "Tuyến Yên"

    # --- Bổ Sung: Nhóm Truyền Nhiễm & Ký Sinh Trùng ---
    VIEM_GAN = "Viêm Gan (A, B, C...)"
    KY_SINH_TRUNG = "Ký Sinh Trùng (Giun/Sán)"
    HIV = "HIV/AIDS"
    BENH_XA_HOI = "Bệnh Xã Hội (Lậu, Giang mai...)"
    SOT_XUAT_HUYET = "Sốt Xuất Huyết"
    CUM_COVID = "Cúm & Covid-19"
    LAO = "Lao"

    # --- Bổ Sung: Nhóm Ung Bướu & Di Truyền ---
    MARKER_UNG_THU = "Dấu Ấn Ung Thư (Tumor Markers)"
    SINH_HOC_PHAN_TU = "Sinh Học Phân Tử (PCR)"
    DI_TRUYEN = "Di Truyền Học (NST, Gen)"
    TE_BAO_HOC = "Tế Bào Học"

    # --- Bổ Sung: Nhóm Thai Sản & Sàng Lọc ---
    SANG_LOC_TRUOC_SINH = "Sàng Lọc Trước Sinh (NIPT, Double/Triple Test)"
    SANG_LOC_SO_SINH = "Sàng Lọc Sơ Sinh"
    
    # --- Bổ Sung: Khác ---
    DI_UNG = "Dị Ứng (Panel Dị Nguyên)"
    DOC_CHAT = "Độc Chất Học"

class NhomThuoc(str, Enum):
    KHANG_SINH = "Kháng sinh"
    GIAM_DAU_HA_SOT = "Giảm đau, Hạ sốt"
    KHANG_VIEM = "Kháng viêm"
    TIM_MACH = "Tim mạch"
    HO_HAP = "Hô hấp"
    TIEU_HOA = "Tiêu hóa"
    THAN_KINH = "Thần kinh"
    VITAMIN_KHOANG = "Vitamin & Khoáng chất"
    DA_LIEU = "Da liễu"
    MAT = "Mắt"
    TAI_MUI_HONG = "Tai Mũi Họng"
    CO_XUONG_KHOP = "Cơ Xương Khớp"
    NOI_TIET = "Nội tiết"
    DONG_Y = "Đông y"
    KHAC = "Khác"
