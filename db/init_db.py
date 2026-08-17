import sqlite3
import hashlib
import os

# Xác định đường dẫn file CSDL nằm cùng thư mục với file script này
DB_PATH = os.path.join(os.path.dirname(__file__), "chatbot.db")

def hash_password(password: str) -> str:
    """Mã hóa mật khẩu bằng SHA-256"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_database():
    # Đảm bảo thư mục chứa CSDL tồn tại
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Bật tính năng kiểm tra khóa ngoại cho SQLite
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Bảng Users (Quản lý tài khoản, mã hóa mật khẩu và phân quyền)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        full_name VARCHAR(100) NOT NULL,
        role VARCHAR(20) NOT NULL CHECK (role IN ('STUDENT', 'STAFF')),
        class_code VARCHAR(50)
    )
    ''')

    # 2. Bảng AbsenceRequests (Đơn xin nghỉ học với đầy đủ các trạng thái nghiệp vụ)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS AbsenceRequests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        course_code VARCHAR(50) NOT NULL,
        class_code VARCHAR(50) NOT NULL,
        start_date DATE NOT NULL,
        end_date DATE NOT NULL,
        reason TEXT NOT NULL,
        status VARCHAR(20) DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES Users(id)
    )
    ''')

    # 3. Bảng RequestStatusHistory (Lưu vết lịch sử thay đổi trạng thái đơn)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS RequestStatusHistory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        old_status VARCHAR(20),
        new_status VARCHAR(20) NOT NULL,
        changed_by INTEGER NOT NULL,
        note TEXT,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (request_id) REFERENCES AbsenceRequests(id),
        FOREIGN KEY (changed_by) REFERENCES Users(id)
    )
    ''')

    # 4. Bảng Evidences (Lưu trữ đường dẫn file ảnh minh chứng đính kèm)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Evidences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id INTEGER NOT NULL,
        file_name VARCHAR(255) NOT NULL,
        file_url TEXT NOT NULL,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (request_id) REFERENCES AbsenceRequests(id)
    )
    ''')

    # Tạo mật khẩu mặc định được băm SHA-256 (Mật khẩu: 123456)
    default_password_hash = hash_password("123456")

    # Chèn dữ liệu mẫu cho sinh viên thực hiện đề tài
    cursor.execute('''
    INSERT OR IGNORE INTO Users (username, password_hash, full_name, role, class_code) 
    VALUES ('066305014844', ?, 'Lê Thị Tuyết Băng', 'STUDENT', 'DTH2151')
    ''', (default_password_hash,))

    # Chèn dữ liệu mẫu cho tài khoản giáo vụ/giảng viên duyệt đơn
    cursor.execute('''
    INSERT OR IGNORE INTO Users (username, password_hash, full_name, role, class_code) 
    VALUES ('gv_tien', ?, 'ThS. Nguyễn Thanh Tiên', 'STAFF', NULL)
    ''', (default_password_hash,))

    conn.commit()
    conn.close()
    try:
        print("Đã khởi tạo thành công CSDL mới với 4 bảng chuẩn và phân quyền đầy đủ!")
    except UnicodeEncodeError:
        print("Da khoi tao thanh cong CSDL moi!")

if __name__ == '__main__':
    init_database()