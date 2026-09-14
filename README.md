# Chatbot Hỗ Trợ Xử Lý Chuyên Cần Của Sinh Viên (Vắng Buổi Học)

Hệ thống chatbot hội thoại hướng tác vụ (Task-Oriented Dialogue System) hỗ trợ sinh viên nộp đơn xin nghỉ học, tra cứu trạng thái, hủy đơn và hỗ trợ giáo vụ duyệt/từ chối đơn.

**Trường Đại học Giao thông Vận tải TP. Hồ Chí Minh**  
**Viện Công nghệ Thông tin và Điện, Điện tử**  
**Sinh viên thực hiện:** Lê Thị Tuyết Băng – 066305014844  
**Giảng viên hướng dẫn:** ThS. Nguyễn Thanh Tiến

---

## 1. Tính năng chính

### Dành cho Sinh viên

- Đăng nhập bằng MSSV
- Nộp đơn xin nghỉ học qua **Chatbot** (hội thoại tự nhiên tiếng Việt) hoặc **Form web**
- Hỗ trợ ngày tương đối (“mai”, “ngày kia”, “thứ 2 tuần sau”…) và ngày tuyệt đối
- Xem danh sách đơn đã nộp và trạng thái
- Hủy đơn đang ở trạng thái **PENDING**

### Dành cho Giáo vụ

- Đăng nhập phân quyền STAFF
- Xem toàn bộ đơn xin nghỉ của sinh viên
- Lọc theo trạng thái: Chờ duyệt / Đã duyệt / Từ chối / Đã hủy
- Xem chi tiết đơn + lịch sử thay đổi trạng thái + minh chứng
- Duyệt hoặc Từ chối đơn

### Trạng thái đơn

- `PENDING` → Chờ duyệt
- `APPROVED` → Đã duyệt
- `REJECTED` → Từ chối
- `CANCELLED` → Đã hủy

---

## 2. Công nghệ sử dụng

| Thành phần          | Công nghệ                                  |
| ------------------- | ------------------------------------------ |
| Ngôn ngữ lập trình  | Python 3.9+                                |
| Chatbot Framework   | **Rasa 3.x**                               |
| NLU                 | DIETClassifier + Regex + Lookup            |
| Dialogue Management | RulePolicy + TEDPolicy + MemoizationPolicy |
| Custom Action       | Rasa SDK + Python                          |
| Web Framework       | **Flask**                                  |
| Cơ sở dữ liệu       | **SQLite**                                 |
| Frontend            | HTML + CSS + JavaScript (Vanilla)          |
| Ngôn ngữ hội thoại  | Tiếng Việt                                 |

---

## 3. Cấu trúc thư mục dự án

```
Chatbot_SV/
├── actions/
│   └── actions.py              # Custom actions (validate, submit, cancel, check status...)
├── data/
│   ├── nlu.yml                 # Dữ liệu huấn luyện NLU
│   ├── rules.yml               # Luật hội thoại
│   └── stories.yml             # Stories huấn luyện
├── db/
│   ├── init_db.py              # Khởi tạo database + tài khoản mẫu
│   └── store.py                # Các hàm thao tác CSDL
├── static/
│   ├── app.js
│   └── styles.css
├── templates/
│   └── index.html              # Giao diện web duy nhất
├── tests/
│   ├── test_stories.yml
│   └── test_system.py
├── config.yml                  # Cấu hình pipeline NLU + Policy
├── domain.yml                  # Intents, entities, slots, forms, responses
├── endpoints.yml               # Địa chỉ Action Server
├── credentials.yml
├── webapp.py                   # Ứng dụng Flask
└── README.md
```

---

## 4. Yêu cầu môi trường

- **Python** 3.9 hoặc 3.10 (khuyến nghị 3.10)
- **pip**
- **virtualenv** (khuyến nghị)
- Hệ điều hành: Windows / macOS / Linux
- RAM khuyến nghị: ≥ 8GB (khi train Rasa)

---

## 5. Cài đặt

### Bước 1: Clone dự án

```bash
git clone https://github.com/LeThiTuyetBang/Chatbot_SV.git
cd Chatbot_SV
git checkout main
```

### Bước 2: Tạo môi trường ảo

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### Bước 3: Cài đặt thư viện

```bash
pip install --upgrade pip
pip install rasa==3.6.20
pip install rasa-sdk
pip install flask
```

> Nếu gặp lỗi phiên bản, có thể dùng:
>
> ```bash
> pip install rasa==3.6.20 rasa-sdk flask
> ```

### Bước 4: Khởi tạo cơ sở dữ liệu

```bash
python db/init_db.py
```

Lệnh này sẽ tạo file `db/chatbot.db` và thêm 2 tài khoản mẫu.

---

## 6. Cách chạy hệ thống

Hệ thống cần chạy **3 tiến trình** đồng thời (mở 3 terminal).

### Terminal 1: Action Server

```bash
rasa run actions
```

Chạy tại: `http://localhost:5055`

### Terminal 2: Rasa Server

```bash
rasa run --enable-api --cors "*" --port 5005
```

Chạy tại: `http://localhost:5005`

### Terminal 3: Flask Web App

```bash
python webapp.py
```

Truy cập giao diện: **http://localhost:5000**

---

## 7. Tài khoản mặc định

| Vai trò   | Tài khoản      | Mật khẩu | Ghi chú                     |
| --------- | -------------- | -------- | --------------------------- |
| Sinh viên | `066305014844` | `123456` | Lê Thị Tuyết Băng - CN2302C |
| Giáo vụ   | `gv_tien`      | `123456` | ThS. Nguyễn Thanh Tiến      |

---

## 8. Huấn luyện lại model (khi thay đổi NLU / Stories / Rules)

```bash
rasa train
```

Model sẽ được lưu trong thư mục `models/`.

Sau khi train xong, khởi động lại Rasa Server (Terminal 2).

---

## 9. Kiểm thử

### Kiểm thử hệ thống (Unit + API)

```bash
python -m pytest tests/test_system.py -v
```

### Kiểm thử hội thoại (Rasa)

```bash
rasa test
```

---

## 10. Các API chính (tham khảo)

| Method | Endpoint                            | Mô tả                       | Quyền     |
| ------ | ----------------------------------- | --------------------------- | --------- |
| POST   | `/api/auth/login`                   | Đăng nhập                   | Public    |
| POST   | `/api/auth/logout`                  | Đăng xuất                   | Login     |
| GET    | `/api/auth/me`                      | Lấy thông tin user hiện tại | Login     |
| POST   | `/api/chat`                         | Gửi tin nhắn tới chatbot    | Sinh viên |
| GET    | `/api/student/requests`             | Lấy danh sách đơn của SV    | Sinh viên |
| POST   | `/api/student/requests`             | Tạo đơn qua Form            | Sinh viên |
| POST   | `/api/student/requests/<id>/cancel` | Hủy đơn                     | Sinh viên |
| GET    | `/api/admin/requests`               | Lấy tất cả đơn              | Giáo vụ   |
| POST   | `/api/admin/requests/<id>/approve`  | Duyệt đơn                   | Giáo vụ   |
| POST   | `/api/admin/requests/<id>/reject`   | Từ chối đơn                 | Giáo vụ   |

---

## 11. Ghi chú quan trọng

- Database mặc định nằm tại `db/chatbot.db`. Nếu muốn reset dữ liệu, xóa file này rồi chạy lại `python db/init_db.py`.
- Action Server phải chạy trước Rasa Server.
- Nếu thay đổi `actions/actions.py`, cần restart Action Server.
- Ngưỡng fallback hiện tại: `0.7` (trong `config.yml`).
- Hệ thống hỗ trợ cả hai cách nộp đơn: **Chatbot** và **Form web**.

---

## 12. Hướng dẫn nhanh khi gặp lỗi

| Lỗi                         | Cách xử lý                                  |
| --------------------------- | ------------------------------------------- |
| Không kết nối được Rasa     | Kiểm tra Terminal 2 đã chạy chưa            |
| Action không chạy           | Kiểm tra Terminal 1 + `endpoints.yml`       |
| Lỗi database                | Xóa `db/chatbot.db` → chạy lại `init_db.py` |
| Model không nhận intent tốt | Chạy `rasa train` lại                       |
| Port bị chiếm               | Đổi port hoặc tắt tiến trình đang dùng port |

---

## 13. Tác giả

- **Sinh viên:** Lê Thị Tuyết Băng – MSSV 066305014844
- **Giảng viên hướng dẫn:** ThS. Nguyễn Thanh Tiến
- **Đề tài:** Xây dựng chatbot hỗ trợ xử lý chuyên cần của sinh viên (vắng buổi học)

---
