# Chatbot Hỗ Trợ Xử Lý Chuyên Cần Của Sinh Viên (Vắng Buổi Học)

Hệ thống chatbot hội thoại hướng tác vụ (Task-Oriented Dialogue System) hỗ trợ sinh viên nộp đơn xin nghỉ học, tra cứu trạng thái, hủy đơn và hỗ trợ giáo vụ duyệt/từ chối đơn.

**Trường Đại học Giao thông Vận tải TP. Hồ Chí Minh**  
**Sinh viên thực hiện:** Lê Thị Tuyết Băng – 066305014844

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

> **Lưu ý:** `APPROVED`, `REJECTED`, `CANCELLED` là trạng thái cuối. Hệ thống chỉ cho chuyển từ `PENDING` sang các trạng thái này (không đổi qua lại giữa các trạng thái cuối).

### Khác

- Thông báo realtime qua **Server-Sent Events (SSE)** tại endpoint `/api/events`
- Giới hạn số lần đăng nhập sai theo IP (rate limit)
- Mật khẩu tài khoản mẫu **seed qua biến môi trường** (không hardcode trong mã nguồn)

---

## 2. Công nghệ sử dụng

| Thành phần          | Công nghệ                                  |
| ------------------- | ------------------------------------------ |
| Ngôn ngữ lập trình  | Python 3.9+                                |
| Chatbot Framework   | **Rasa 3.6.x**                             |
| NLU                 | DIETClassifier + Regex + Lookup            |
| Dialogue Management | RulePolicy + TEDPolicy + MemoizationPolicy |
| Custom Action       | Rasa SDK + Python                          |
| Web Framework       | **Flask 3.x**                              |
| Cơ sở dữ liệu       | **SQLite**                                 |
| Frontend            | HTML + CSS + JavaScript (Vanilla)          |
| Ngôn ngữ hội thoại  | Tiếng Việt                                 |

Phiên bản thư viện chính được khóa trong `requirements.txt` (`rasa==3.6.20`, `rasa-sdk==3.6.2`, `flask==3.0.3`, …).

---

## 3. Cấu trúc thư mục dự án

```text
Chatbot_SV/
├── actions/
│   └── actions.py              # Custom actions (validate, preview, submit,...)
├── data/
│   ├── nlu.yml                 # Dữ liệu huấn luyện NLU
│   ├── rules.yml               # Luật hội thoại
│   ├── stories.yml             # Stories huấn luyện
│   └── subjects.yml            # Danh sách môn học (lookup / validate)
├── db/
│   ├── init_db.py              # Khởi tạo database + seed tài khoản
│   └── store.py                # Thao tác CSDL, transition trạng thái, subjects
├── static/
│   ├── app.js
│   └── styles.css
├── templates/
│   └── index.html              # Giao diện web (SV + Giáo vụ)
├── tests/
│   ├── e2e_scenarios/          # 38 kịch bản End-to-End (YAML)
│   ├── run_e2e.py              # Runner E2E (chat + API)
│   ├── clean_test_data.py
│   ├── test_core.py
│   ├── test_system.py
│   ├── test_correction_cancel.py
│   └── e2e_results.json        # Kết quả lần chạy E2E gần nhất
├── config.yml                  # Pipeline NLU + policies
├── domain.yml
├── endpoints.yml               # Action endpoint http://localhost:5055/webhook
├── credentials.yml
├── requirements.txt
├── webapp.py                   # Flask: auth, chat proxy, API SV/GV, SSE
└── README.md
```

---

## 4. Yêu cầu hệ thống

- Python **3.9+**
- pip, venv
- Hệ điều hành: Windows / macOS / Linux

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
pip install -r requirements.txt
```

### Bước 4: Thiết lập biến môi trường (bắt buộc)

Tạo file `.env` ở thư mục gốc dự án (file này **không** được commit — đã có trong `.gitignore`):

```env
SECRET_KEY=doi-thanh-chuoi-bi-mat-dai-va-ngau-nhien
DEFAULT_PASSWORD=mat-khau-manh-dung-cho-tai-khoan-mau
```

Hoặc export trước khi chạy:

```bash
# Linux / macOS
export SECRET_KEY="doi-thanh-chuoi-bi-mat-dai-va-ngau-nhien"
export DEFAULT_PASSWORD="mat-khau-manh-dung-cho-tai-khoan-mau"

# Windows PowerShell
$env:SECRET_KEY="doi-thanh-chuoi-bi-mat-dai-va-ngau-nhien"
$env:DEFAULT_PASSWORD="mat-khau-manh-dung-cho-tai-khoan-mau"
```

| Biến                                  | Bắt buộc khi                       | Mô tả                                                      |
| ------------------------------------- | ---------------------------------- | ---------------------------------------------------------- |
| `SECRET_KEY`                          | Chạy `webapp.py`                   | Khóa session Flask                                         |
| `DEFAULT_PASSWORD`                    | Chạy `db/init_db.py` và E2E/pytest | Mật khẩu seed cho tài khoản mẫu                            |
| `E2E_STUDENT_PASS` / `E2E_STAFF_PASS` | (Tuỳ chọn) E2E                     | Ghi đè mật khẩu test; nếu thiếu sẽ dùng `DEFAULT_PASSWORD` |
| `RASA_REST_URL`                       | (Tuỳ chọn)                         | Mặc định `http://localhost:5005/webhooks/rest/webhook`     |

- Thiếu `SECRET_KEY` → `webapp.py` **dừng** với lỗi rõ ràng.
- Thiếu `DEFAULT_PASSWORD` → `init_db.py` **dừng**; E2E/`run_e2e.py` cũng yêu cầu mật khẩu qua env.

### Bước 5: Khởi tạo cơ sở dữ liệu

```bash
python db/init_db.py
```

Lệnh này tạo `db/chatbot.db` (4 bảng: Users, AbsenceRequests, RequestStatusHistory, Evidences) và seed 2 tài khoản mẫu với mật khẩu đã băm từ `DEFAULT_PASSWORD`.

### Bước 6 (khi cần): Huấn luyện model Rasa

```bash
rasa train
```

Model được lưu trong `models/` (thư mục này đã được `.gitignore`).

---

## 6. Cách chạy hệ thống

Cần **3 tiến trình** đồng thời (3 terminal), trong môi trường ảo đã kích hoạt và đã có biến môi trường.

### Terminal 1: Action Server

```bash
rasa run actions
```

Chạy tại `http://localhost:5055`

### Terminal 2: Rasa Server

```bash
rasa run --enable-api --cors "*" --port 5005
```

Chạy tại `http://localhost:5005`

### Terminal 3: Flask Web App

```bash
python webapp.py
```

Giao diện: **http://localhost:5000**

> Action Server nên khởi động trước Rasa Server. Sau khi sửa `actions/actions.py`, **restart** Action Server.

---

## 7. Tài khoản mẫu (chỉ môi trường phát triển)

| Vai trò   | Tài khoản      | Ghi chú                     |
| --------- | -------------- | --------------------------- |
| Sinh viên | `066305014844` | Lê Thị Tuyết Băng – DTH2151 |
| Giáo vụ   | `gv_tien`      | ThS. Nguyễn Thanh Tiến      |

> **Bảo mật:**
>
> - Mật khẩu **không** hardcode trong source hay README.
> - Seed qua `DEFAULT_PASSWORD` trong `.env`.
> - **Không commit** file `.env` hoặc mật khẩu thật lên GitHub.
> - Khi triển khai thật, hãy đổi mật khẩu sau lần đăng nhập đầu.

---

## 8. Huấn luyện lại model

Khi thay đổi `data/nlu.yml`, `data/stories.yml`, `data/rules.yml` hoặc `config.yml`:

```bash
rasa train
```

Sau đó khởi động lại Rasa Server (Terminal 2).

---

## 9. Kiểm thử

### Unit / API (pytest)

```bash
# Cần DEFAULT_PASSWORD (hoặc E2E_*_PASS) trong môi trường
python -m pytest tests/test_core.py tests/test_system.py -v
```

### End-to-End (38 kịch bản)

Cần 3 service đang chạy (Action, Rasa, Flask) và biến môi trường mật khẩu:

```bash
python tests/clean_test_data.py --yes
python tests/run_e2e.py
```

- Bộ kịch bản: `tests/e2e_scenarios/` (**38** file YAML) — gồm hội thoại chatbot và API (form web, duyệt/từ chối, phân quyền, đăng nhập sai).
- Runner kiểm tra phản hồi bot (từ khóa), `db_status`, `has_evidence`, `expected_turn_count` (khi khai báo trong YAML).
- Kết quả ghi vào `tests/e2e_results.json`.

---

## 10. Các API chính (tham khảo)

| Method | Endpoint                            | Mô tả                                     | Quyền     |
| ------ | ----------------------------------- | ----------------------------------------- | --------- |
| POST   | `/api/auth/login`                   | Đăng nhập                                 | Public    |
| POST   | `/api/auth/logout`                  | Đăng xuất                                 | Login     |
| GET    | `/api/auth/me`                      | Thông tin user hiện tại                   | Login     |
| POST   | `/api/chat`                         | Gửi tin nhắn tới chatbot                  | Sinh viên |
| POST   | `/api/chat/restart`                 | Reset hội thoại Rasa                      | Login     |
| GET    | `/api/student/requests`             | Danh sách đơn của SV                      | Sinh viên |
| POST   | `/api/student/requests`             | Tạo đơn qua Form                          | Sinh viên |
| POST   | `/api/student/requests/<id>/cancel` | Hủy đơn theo id (PENDING)                 | Sinh viên |
| POST   | `/api/student/cancel-latest`        | Hủy đơn PENDING gần nhất                  | Sinh viên |
| GET    | `/api/admin/requests`               | Tất cả đơn (+ lọc status)                 | Giáo vụ   |
| GET    | `/api/admin/requests/<id>`          | Chi tiết đơn + lịch sử + evidence         | Giáo vụ   |
| POST   | `/api/admin/requests/<id>/approve`  | Duyệt đơn                                 | Giáo vụ   |
| POST   | `/api/admin/requests/<id>/reject`   | Từ chối đơn                               | Giáo vụ   |
| PUT    | `/api/admin/requests/<id>`          | Điều chỉnh trạng thái (APPROVED/REJECTED) | Giáo vụ   |
| GET    | `/api/events`                       | SSE realtime (đơn mới / cập nhật)         | Login     |

---

## 11. Ghi chú quan trọng

- Database mặc định: `db/chatbot.db`. Reset: xóa file này rồi chạy lại `python db/init_db.py` (vẫn cần `DEFAULT_PASSWORD`).
- Danh sách môn phục vụ validate/lookup: `data/subjects.yml` (và có thể bổ sung từ DB).
- Ngưỡng fallback NLU: **0.7** (`config.yml`). Pipeline có `random_seed: 42` để tái lập kết quả.
- Đăng nhập sai quá nhiều lần từ cùng IP sẽ bị tạm chặn (rate limit trong `webapp.py`).
- Hệ thống hỗ trợ nộp đơn bằng **Chatbot** và **Form web**.

---

## 12. Hướng dẫn nhanh khi gặp lỗi

| Lỗi                                      | Cách xử lý                                                              |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `Thiếu biến môi trường SECRET_KEY`       | Tạo `.env` hoặc `export`/`$env:SECRET_KEY`                              |
| `Thiếu biến môi trường DEFAULT_PASSWORD` | Thêm `DEFAULT_PASSWORD` vào `.env` rồi chạy lại `init_db` / E2E         |
| Không kết nối được Rasa                  | Kiểm tra Terminal 2 (`rasa run --enable-api …`)                         |
| Action không chạy                        | Kiểm tra Terminal 1 + `endpoints.yml`; restart sau khi sửa `actions.py` |
| Lỗi database                             | Xóa `db/chatbot.db` → `python db/init_db.py`                            |
| Model không nhận intent tốt              | `rasa train` rồi restart Rasa Server                                    |
| Port bị chiếm                            | Đổi port hoặc tắt tiến trình đang dùng port                             |
| E2E thiếu mật khẩu                       | Set `DEFAULT_PASSWORD` hoặc `E2E_STUDENT_PASS` / `E2E_STAFF_PASS`       |

---

## 13. Tác giả

- **Sinh viên:** Lê Thị Tuyết Băng – MSSV 066305014844
- **Người hướng dẫn:** ThS. Nguyễn Thanh Tiến
- **Đề tài:** Xây dựng chatbot hỗ trợ xử lý chuyên cần của sinh viên (vắng buổi học)
- **Mã nguồn:** https://github.com/LeThiTuyetBang/Chatbot_SV.git
