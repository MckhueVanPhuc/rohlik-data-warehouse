# SQLite Infrastructure Setup

## Vai trò và phạm vi

SQLite là nơi lưu dữ liệu nhân viên nhập qua Streamlit trong tương lai. File mặc định:
`C:\Users\win11\Documents\rohlik-data-warehouse\data\input.db`.
Không có bảng nghiệp vụ hoặc dữ liệu mẫu; schema và phân quyền vẫn cần quyết định
nghiệp vụ dựa trên bằng chứng nguồn. Workflow Data Contract BT1–BT8 đã RETIRED.
Không tạo DuckDB, ETL hay giao diện ở giai đoạn này.

Phương thức nhập chính đã thống nhất là **CSV upload**, không bắt buộc form từng
record: chọn bảng theo quyền → template/upload/preview → backend validation → nhân
viên xác nhận → records hợp lệ + audit + metadata batch cùng transaction SQLite.
INSERT/UPSERT và chống trùng phải theo chính sách đã duyệt; sau lưu là `PENDING_SYNC`
để DE chủ động đồng bộ. Toàn bộ luồng **PLANNED**, chưa có schema/API triển khai.
Xem [CSV Upload Contract](csv_upload_contract.md). Không đổi sáu CSV gốc;
Finance/HR chỉ nhận CSV riêng sau phê duyệt schema và giá trị.

Ứng dụng chạy trên máy chủ nội bộ; người dùng truy cập Streamlit qua LAN.
Giữ file SQLite trên ổ đĩa cục bộ của máy chủ, không cho nhiều máy mở file qua
SMB/network share: WAL cần các tiến trình chia sẻ bộ nhớ trên cùng máy.

## Khởi tạo và kiểm tra

Từ thư mục gốc repository, chạy:

```powershell
.\.venv\Scripts\python.exe -m src.init_sqlite
.\.venv\Scripts\python.exe -m pytest -q
```

CLI in SUCCESS cùng đường dẫn và các PRAGMA đã xác minh, hoặc FAILED và exit code 1.
Chạy lại không xoá, thay thế database hay tạo bảng. Trên máy khác: lấy source,
tạo môi trường theo README, chạy lệnh trên. Nếu đã có database tại đường dẫn đó,
chương trình mở tại chỗ. Đóng các ứng dụng kết nối trước lần đầu bật WAL.
File lỗi/corrupt sẽ báo FAILED; không tự sửa, xoá hay restore.

Đường dẫn mặc định tính từ vị trí module, không từ working directory. Module Python
có thể import từ ứng dụng; với CLI `-m`, cần chạy từ root hoặc đặt root vào PYTHONPATH.
Tuỳ chọn `--database PATH` hỗ trợ database khác; PATH tương đối tính từ root dự án.

## Kết nối DBeaver Community (thao tác thủ công)

Chưa xác minh kết nối qua giao diện DBeaver trên máy này.
Theo [hướng dẫn SQLite chính thức của DBeaver](https://dbeaver.com/docs/dbeaver/Database-driver-SQLite/):

1. Mở DBeaver Community, chọn **Database → New Database Connection → SQLite**.
2. Trong trường đường dẫn database, chọn file `data/input.db` ở đường dẫn tuyệt đối trên.
3. Chọn **Test Connection**; nếu được yêu cầu, tải JDBC driver rồi thử lại. Chọn **Finish**.
4. Mở SQL Editor của kết nối và chạy từng câu:

```sql
SELECT sqlite_version();
PRAGMA journal_mode;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout;
PRAGMA foreign_keys;
SELECT name, type, sql FROM sqlite_master ORDER BY type, name;
```

Kỳ vọng journal_mode=wal, busy_timeout=5000, foreign_keys=1. SQLite của JDBC có
thể khác phiên bản SQLite trong Python. Trong Database Navigator, mở kết nối →
Tables và Refresh để xem bảng. Hiện danh sách bảng trống là đúng.
PRAGMA foreign_keys phải đặt ngoài transaction; đặt hai PRAGMA theo connection
trong phần initialization SQL nếu cấu hình DBeaver hỗ trợ, rồi kiểm tra lại sau reconnect.
Module Python không cấu hình thay cho connection của DBeaver.

## Connection, transaction và tích hợp Streamlit

`src.db.sqlite.connection()` mở file đã tồn tại ở chế độ autocommit, bật foreign keys,
đặt timeout 5000 ms và luôn đóng connection khi rời context. Nó không bật lại WAL;
chạy bước khởi tạo trước khi ứng dụng bắt đầu.
`transaction()` dùng BEGIN tường minh, commit khi thành công, rollback khi có exception,
kể cả DDL. Không gọi commit/rollback hoặc executescript thủ công trong context này.

WAL cho phép reader tiếp tục đọc khi writer có transaction; SQLite vẫn chỉ có một writer
tại một thời điểm. Timeout chờ lock tối đa 5 giây trước khi báo lỗi. Foreign keys
bảo vệ quan hệ khi có schema, phải bật trên từng connection mới.

Người làm Streamlit import module và mở connection riêng cho mỗi thao tác:

```python
from src.db.sqlite import connection, transaction

with connection() as conn:
    result = conn.execute("SELECT ? AS value", (42,)).fetchone()

# Sau khi schema được duyệt, đặt các câu INSERT/UPDATE có placeholders
# trong `with transaction() as conn:`; lỗi sẽ rollback cả transaction.
```

Không cache hoặc chia sẻ connection toàn cục giữa các phiên Streamlit. Không giữ
transaction trong lúc chờ người dùng, tải file hoặc chạy mô hình. Truyền giá trị qua
`?` hoặc named parameters, không nối chuỗi/f-string từ đầu vào vào SQL.
Tên bảng/cột không thể bind như giá trị: chỉ dùng tên cố định đã được phê duyệt.
Module không chứa form, save_record hay logic phân quyền chưa được xác nhận.

## Backup và xác minh

```powershell
.\.venv\Scripts\python.exe -m src.db.backup
.\.venv\Scripts\python.exe -m src.db.backup --check "data/backups/<ten-backup>.db"
```

Thay `<ten-backup>` bằng tên thực tế in ra. Utility dùng SQLite Backup API, tạo file
mới trong `data/backups/` với timestamp UTC và UUID, không ghi đè backup cũ.
Sau backup luôn chạy `PRAGMA integrity_check`, chỉ SUCCESS nếu kết quả là `ok`.
Có thể chọn `--database PATH --backup-dir PATH`; nguồn phải tồn tại, không tạo nguồn thiếu.
Không copy riêng file .db đang hoạt động ở WAL vì có thể bỏ sót dữ liệu đã commit.
Backup/restore đã được kiểm thử trên database tạm; không có lệnh tự động restore database thật.
Integrity check xác minh cấu trúc SQLite, không thay thế kiểm tra dữ liệu nghiệp vụ.

## Lỗi thường gặp trên Windows

| Lỗi | Cách xử lý |
| --- | --- |
| Unable to open database file | Kiểm tra đường dẫn tuyệt đối, file tồn tại và quyền đọc/ghi cả thư mục chứa WAL/SHM. Chạy init trước ứng dụng. |
| Database is locked | Commit/rollback thao tác còn mở trong DBeaver; rút ngắn transaction; đóng kết nối trước lần đầu bật WAL. Không xoá WAL/SHM để giải quyết lock. |
| Readonly database | Kiểm tra thuộc tính read-only và quyền thư mục; dùng ổ cục bộ có quyền ghi. |
| File is not a database / integrity lỗi | Dừng ghi, giữ nguyên nguồn và backup; điều tra trước khi quyết định phục hồi thủ công. |
| PowerShell chặn Activate.ps1 | Dùng trực tiếp `.\.venv\Scripts\python.exe`, không cần kích hoạt. |
| No module named src | Chuyển về root repository trước lệnh `-m`. |
| DBeaver không tải driver | Kiểm tra kết nối mạng/proxy và cấu hình driver; chưa coi Test Connection là thành công khi còn lỗi. |

## Git và nghiệm thu

`.gitignore` hiện bao phủ database, WAL/SHM và toàn bộ backups. Không stage dữ liệu.

```powershell
git check-ignore -v -- data/input.db data/input.db-wal data/input.db-shm data/backups/probe.db
git ls-files -- '*.db' '*.db-wal' '*.db-shm' 'data/backups/*'
```

Lệnh thứ hai phải không có kết quả. Không sửa CSV, không tự commit/push.
Giai đoạn này dừng tại hạ tầng SQLite. Chờ nghiệm thu và phê duyệt schema trước khi
phân quyền nghiệp vụ, CSV upload/preview/xác nhận, ETL, Warehouse hoặc tích hợp BT1–BT8.
