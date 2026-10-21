# DuckDB Infrastructure Setup

## Phạm vi và trạng thái

Đã triển khai V4-02: cấu hình DuckDB local, kết nối read-only, write transaction có
khóa liên tiến trình, backup được xác minh và metadata foundation có version guard.
V4-03 đã triển khai initial 7-CSV → 14-table landing bootstrap cho database cô lập,
với dry-run mặc định, fingerprint/idempotency, reconciliation và rollback atomic.
Production database chưa được nạp; stg/core/mart, user upload/entry và Model Runner chưa triển khai.
Không thay đổi SQLite Infrastructure tại `data/input.db`.

Kiến trúc V4 dự kiến: Streamlit CSV upload → validate/confirm → DuckDB landing +
audit trong cùng transaction. Initial bootstrap đã có; entry/undo vẫn **PLANNED** và
không chốt update/conflict policy. `meta.source_batches.status` là current status
canonical; `meta.batch_status_events` là immutable audit history, không được suy diễn
latest state bằng timestamp hoặc UUID của event.

Database mặc định: `data/warehouse/rohlik.duckdb`. Cấu hình tập trung tại
`warehouse` trong [config/settings.yaml](../config/settings.yaml), được kiểm tra là
đường dẫn `.duckdb` tương đối nằm dưới `data/warehouse`. Đường dẫn tương đối truyền
vào API/CLI cũng tính từ root dự án và không được thoát root/đi vào `data/raw`.
Không dùng chung cấu hình với SQLite để giữ nguyên implementation SQLite đang hoạt động.

## Setup và CLI

Tại root repository, dùng Python 3.13 trong `.venv` và dependencies hiện có:

```powershell
.\.venv\Scripts\python.exe -c "import duckdb; print(duckdb.__version__)"
.\.venv\Scripts\python.exe -m src.init_duckdb
```

Máy hiện tại dùng DuckDB **1.5.6**. Nếu máy mới chưa có thư viện, cài theo
[Setup Tutorial](setup_tutorial.md#phan-4); không cần công nghệ mới hay DuckDB server.

Kết quả mong đợi:

```text
SUCCESS: DuckDB initialized and verified; no application schema created
database_path: <duong-dan-root>\data\warehouse\rohlik.duckdb
duckdb_version: v1.5.6
created: True
```

Chạy lại trả `created: False`: mở file đã tồn tại ở chế độ read-only để xác minh
`SELECT version()` và `SELECT 42`, không tạo bảng hoặc sửa dữ liệu. File lỗi không bị
xoá, thay thế hoặc tự sửa; CLI in `FAILED` và exit code 1. Lần đầu tạo file chỉ dùng
connection ghi để khởi tạo định dạng DuckDB rồi đóng trước khi mở read-only.
Chạy init trong lúc bảo trì, trước khi ứng dụng/writer bắt đầu; không dùng init để
phối hợp nhiều tiến trình tạo file đồng thời.

Có thể chọn database riêng:

```powershell
.\.venv\Scripts\python.exe -m src.init_duckdb --help
```

Option thực tế là `--database PATH`. Không chạy vào vị trí chứa file nguồn khác.

V4-03 landing CLI mặc định chỉ preflight/dry-run và không mở warehouse để ghi:

```powershell
.\.venv\Scripts\python.exe -m src.ingest_landing
```

`--execute` yêu cầu thêm `--database` trỏ tới DuckDB cô lập đã init. CLI từ chối
production target mặc định trong khi 14 update policies còn `PENDING_CONFIRMATION`.
NO_OP chỉ được trả về sau khi đối chiếu completed batch metadata, row counts và nội dung
canonical với source; batch nhập tay khác được bảo toàn.

## Kiểm tra kết nối, quản lý đọc/ghi

```powershell
@'
from src.db.duckdb import connection
with connection() as conn:
    print(conn.execute("SELECT version()").fetchone())
    print(conn.execute("SELECT 42").fetchone())
    print(conn.execute("SHOW TABLES").fetchall())
'@ | .\.venv\Scripts\python.exe -
```

Kỳ vọng `('v1.5.6',)`, `(42,)`, `[]` ở giai đoạn database rỗng hiện tại.
Đây là kiểm tra chỉ đọc. Phiên bản phải đối chiếu lại nếu đổi môi trường.

| API | Hành vi |
| --- | --- |
| `connection(path=DEFAULT_DATABASE, read_only=True)` | Chỉ mở file đã có, mặc định đọc; luôn đóng khi rời context, kể cả có exception. File thiếu báo FileNotFoundError thay vì vô tình tạo DB. |
| `connection(path, read_only=False)` | Bị chặn; writable caller phải qua shared writer service. |
| `transaction(path, lock_timeout=10)` | Lấy khóa OS liên tiến trình, BEGIN; commit thành công, rollback mọi exception; chặn nested transaction. |
| `initialize_database(path)` | Explicit init; khóa writer, tạo nếu thiếu, không thay file có sẵn; không tạo business schema. |
| `backup_database(path, backup_directory=...)` | Khóa writer, từ chối khi có WAL, tạo tên unique bằng `xb`, hash + reopen/catalog verify. |
| `initialize_metadata(path)` | Tạo idempotent 5 bảng `meta.*` v1; shape/version lạ bị chặn, không auto-migrate. |

Truyền giá trị bằng `conn.execute("SELECT ?", (value,))`, không nối chuỗi input vào
SQL. Không gọi commit/rollback hoặc nhét lệnh điều khiển transaction thủ công trong
context `transaction()`. Test dùng bảng kỹ thuật trên file tạm, không dùng bảng nghiệp vụ.

### Quy tắc vận hành kết nối cục bộ

Trong cách dùng file embedded của dự án: một tiến trình DE làm writer; các thao tác
ghi/đọc chạy tuần tự và đóng connection trước khi đổi chế độ. Không mở đồng thời
read-only và read-write tới cùng file với cấu hình khác nhau. Nhiều tiến trình có thể
đọc read-only khi không có writer; không giả định có writer liên tiến trình như SQLite.
Khóa dùng byte-range lock của OS (`msvcrt.locking` trên Windows), kết hợp lock nội
process và timeout hữu hạn. OS tự giải phóng khi process/handle kết thúc; file lock
chỉ giữ owner metadata, không bị xóa/force-unlock. Mọi CLI/Streamlit writer tương lai
phải dùng `transaction()`; module không cung cấp pooling hoặc transaction dài.
Xem [Python DB API](https://duckdb.org/docs/current/clients/python/dbapi) và
[Concurrency](https://duckdb.org/docs/current/connect/concurrency) của DuckDB.

Streamlit dự kiến đọc **published Parquet snapshots** ở `data/published/`, tránh giữ kết nối
vào file DuckDB đang được DE ghi. Chưa có exporter/publisher hoặc Streamlit integration.
Không cache/chia sẻ writer toàn cục giữa nhiều phiên Streamlit. Giữ database trên
ổ cục bộ máy chủ; không đặt lên thư mục đồng bộ hoặc chia sẻ file để né lock.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_duckdb.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Test V4-02 bao gồm init/read/commit/rollback, path guards, nested write, process lock,
timeout, process termination, backup và metadata version/idempotency trên `tmp_path`.
Test kiểm tra tạo file đúng đường dẫn, không có bảng, query tham số, đóng connection,
read-only từ chối ghi, commit, rollback do lỗi Python/SQL, init lặp giữ nguyên byte
và record, chuỗi writer–reader, không tự tạo nguồn thiếu, giữ file hỏng, đường dẫn
độc lập cwd, backup offline và CLI SUCCESS/FAILED.
Tất cả ghi test dùng `tmp_path`, không ghi vào database dự án.

## Backup an toàn và phục hồi

`src.db.backup` vẫn là utility **SQLite** riêng. DuckDB dùng
`src.db.duckdb.backup_database()`; helper lấy cùng writer lock với transaction, giữ
read-only source connection khi copy, yêu cầu không có WAL, tạo tên UTC+UUID không
ghi đè, so hash/kích thước và mở lại backup read-only để đối chiếu version/catalog.
Backup chỉ an toàn khi mọi writer của ứng dụng tuân shared service; DBeaver/client
ngoài service phải đóng trước bảo trì.

1. Dừng tiến trình DE/writer, DBeaver/ứng dụng đang mở DuckDB và mọi tác vụ có thể
   mở lại file. Đảm bảo khoảng bảo trì không có writer khởi động trong lúc copy.
2. Đóng sạch mọi connection ghi. Nếu còn `.wal`, dừng copy; không xoá WAL. Để người
   phụ trách mở bằng đúng phiên bản DuckDB trong lúc không có client khác, xử lý
   recovery/checkpoint và đóng sạch, rồi kiểm tra lại. Không ép checkpoint để phá transaction.
3. Gọi `backup_database`; không tự copy hoặc ghi đè backup cũ.
4. Mở backup read-only, kiểm tra catalog/query. Khi có dữ liệu nghiệp vụ, bổ sung
   đối chiếu schema/số dòng/nội dung theo contract trước khi coi backup đủ điều kiện phục hồi.

Ví dụ chỉ chạy sau khi đáp ứng các điều kiện offline trên:

```powershell
@'
from src.db.duckdb import backup_database
print(backup_database())
'@ | .\.venv\Scripts\python.exe -
```

Mở/SELECT thành công là smoke check, không phải integrity check đầy đủ mọi trang dữ
liệu. Không dùng `PRAGMA integrity_check` của SQLite cho DuckDB. Test đã xác minh
copy offline vào file mới và đọc lại record trên database tạm; chưa diễn tập phục
hồi database dự án. Đối chiếu [hướng dẫn CHECKPOINT](https://duckdb.org/docs/current/sql/statements/checkpoint).

Nếu cần restore: giữ nguyên database/WAL hiện tại; kiểm tra bản phục hồi ở đường
dẫn mới, đối chiếu dữ liệu và xin chủ dữ liệu duyệt trước khi thay đường dẫn vận
hành. Không tự động restore/ghi đè `rohlik.duckdb`. Chính sách lưu backup ngoài máy,
retention và người chịu trách nhiệm vẫn chờ thống nhất.

## Xử lý lỗi

| Lỗi | Cách xử lý |
| --- | --- |
| No module named duckdb | Dùng Python trong `.venv`, cài requirements theo tutorial; không dùng pip global. |
| No module named src | Chạy `-m src.init_duckdb` từ root repository. |
| Database not found | Kiểm tra đường dẫn, chạy CLI init trước; connection không tự tạo file thiếu. |
| Could not set lock / conflicting configuration | Đóng client/tiến trình khác, kiểm tra writer đã kết thúc; chạy tuần tự. Không xoá file để né lock. |
| Direct writable connections are blocked | Dùng `transaction()`; không chọn `read_only=False` để bypass lock. |
| Timed out waiting for writer lock | Writer khác đang hoạt động; chờ hoặc xử lý owner, không xóa/force-unlock file lock. |
| File is not a valid DuckDB database | Giữ nguyên file, kiểm tra chọn nhầm SQLite/file rỗng hay không; không xoá hoặc tạo đè. |
| WAL còn lại sau crash | Dừng thao tác backup/copy, bảo toàn DB và WAL; điều tra recovery với phiên bản phù hợp. |
| Permission denied | Kiểm tra quyền file/thư mục và ổ cục bộ, bảo đảm thư mục không read-only. |

## Git và nghiệm thu

`.gitignore` hiện có bao phủ toàn bộ `data/warehouse/`, `data/published/`, backups,
`*.duckdb` và `*.duckdb.wal`; không cần sửa rule. Kiểm tra:

```powershell
git check-ignore -v -- data/warehouse/rohlik.duckdb data/warehouse/rohlik.duckdb.wal data/warehouse/rohlik.duckdb.tmp/probe.tmp data/published/probe.parquet data/backups/probe.duckdb
git ls-files -- '*.duckdb' '*.duckdb.wal' 'data/warehouse/*'
```

Lệnh cuối phải trống. Không stage file dữ liệu; không tự commit/push.

- [x] DuckDB 1.5.6: init lần đầu và chạy lại thành công; file thật không có bảng.
- [x] Cross-process lock/timeout/process termination được test bằng subprocess thật.
- [x] Backup và metadata foundation được test trên database tạm; không copy database dự án.
- [x] Git ignore được kiểm tra; SQLite source giữ nguyên.
- [ ] Setup trên máy sạch, backup/restore vận hành thật: chưa nghiệm thu.
- [x] Dataset/contracts và initial landing bootstrap: đã triển khai/test trên database tạm cô lập.
- [ ] Production load, user entry/undo và STG/Core/Mart: chờ giai đoạn sau/phê duyệt policy.
