# DuckDB Infrastructure Setup

## Phạm vi và trạng thái

Đã triển khai file DuckDB rỗng, module kết nối đọc/ghi, transaction và CLI khởi tạo.
Chưa nạp CSV, tạo schema/bảng nghiệp vụ, ETL, Bronze/Silver/Gold/Mart hoặc Model Runner.
DuckDB có catalog/schema hệ thống mặc định; điều này không có nghĩa đã tạo Warehouse nghiệp vụ.
Không thay đổi SQLite Infrastructure tại `data/input.db`.

Database mặc định: `data/warehouse/rohlik.duckdb`. Cấu hình tập trung tại
`DEFAULT_DATABASE` trong [src/db/duckdb.py](../src/db/duckdb.py), dùng `pathlib` tính
từ vị trí module. Đường dẫn tương đối truyền vào API/CLI cũng tính từ root dự án.
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
| `connection(path, read_only=False)` | Cho phép ghi; mặc định autocommit. Chỉ dùng trong tiến trình DE được giao quyền ghi. |
| `transaction(path=DEFAULT_DATABASE)` | Mở writer riêng, BEGIN; commit thành công, rollback khi có exception, phát lại lỗi và đóng connection. |
| `initialize_database(path=DEFAULT_DATABASE)` | Tạo nếu thiếu, xác minh read-only; không tạo application schema. |

Truyền giá trị bằng `conn.execute("SELECT ?", (value,))`, không nối chuỗi input vào
SQL. Không gọi commit/rollback hoặc nhét lệnh điều khiển transaction thủ công trong
context `transaction()`. Test dùng bảng kỹ thuật trên file tạm, không dùng bảng nghiệp vụ.

### Quy tắc vận hành kết nối cục bộ

Trong cách dùng file embedded của dự án: một tiến trình DE làm writer; các thao tác
ghi/đọc chạy tuần tự và đóng connection trước khi đổi chế độ. Không mở đồng thời
read-only và read-write tới cùng file với cấu hình khác nhau. Nhiều tiến trình có thể
đọc read-only khi không có writer; không giả định có writer liên tiến trình như SQLite.
Module không cung cấp lock liên tiến trình, retry hay pooling.
Xem [Python DB API](https://duckdb.org/docs/current/clients/python/dbapi) và
[Concurrency](https://duckdb.org/docs/current/connect/concurrency) của DuckDB.

Streamlit dự kiến đọc **published snapshots** ở `data/published/`, tránh giữ kết nối
vào file DuckDB đang được DE ghi. Chưa có exporter/publisher hoặc Streamlit integration.
Không cache/chia sẻ writer toàn cục giữa nhiều phiên Streamlit. Giữ database trên
ổ cục bộ máy chủ; không đặt lên thư mục đồng bộ hoặc chia sẻ file để né lock.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_duckdb.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Kỳ vọng hiện tại: **14 ca DuckDB PASS**, **28 ca toàn bộ PASS** (14 SQLite + 14 DuckDB).
Test kiểm tra tạo file đúng đường dẫn, không có bảng, query tham số, đóng connection,
read-only từ chối ghi, commit, rollback do lỗi Python/SQL, init lặp giữ nguyên byte
và record, chuỗi writer–reader, không tự tạo nguồn thiếu, giữ file hỏng, đường dẫn
độc lập cwd, backup offline và CLI SUCCESS/FAILED.
Tất cả ghi test dùng `tmp_path`, không ghi vào database dự án.

## Backup an toàn và phục hồi

**Chưa có DuckDB backup/restore CLI.** `src.db.backup` là utility **SQLite**, không
được dùng cho DuckDB. Phương án giai đoạn này là backup **offline**, chỉ khi:

1. Dừng tiến trình DE/writer, DBeaver/ứng dụng đang mở DuckDB và mọi tác vụ có thể
   mở lại file. Đảm bảo khoảng bảo trì không có writer khởi động trong lúc copy.
2. Đóng sạch mọi connection ghi. Nếu còn `.wal`, dừng copy; không xoá WAL. Để người
   phụ trách mở bằng đúng phiên bản DuckDB trong lúc không có client khác, xử lý
   recovery/checkpoint và đóng sạch, rồi kiểm tra lại. Không ép checkpoint để phá transaction.
3. Chỉ copy file `.duckdb` đã đóng sạch sang **tên mới**; không ghi đè backup cũ.
4. Mở backup read-only, kiểm tra catalog/query. Khi có dữ liệu nghiệp vụ, bổ sung
   đối chiếu schema/số dòng/nội dung theo contract trước khi coi backup đủ điều kiện phục hồi.

Ví dụ thủ công dưới đây chỉ chạy **sau khi đáp ứng các điều kiện offline trên**.
Kiểm tra WAL không tự chứng minh không có writer; người vận hành phải bảo đảm điều đó.

```powershell
@'
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4
from src.db.duckdb import DEFAULT_DATABASE, PROJECT_ROOT, connection

source = DEFAULT_DATABASE
if not source.is_file():
    raise FileNotFoundError(source)
if Path(str(source) + ".wal").exists():
    raise RuntimeError("WAL present: stop and investigate; do not delete it")
directory = PROJECT_ROOT / "data" / "backups"
directory.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
target = directory / f"rohlik_{stamp}_{uuid4().hex}.duckdb"
with source.open("rb") as src, target.open("xb") as dst:
    shutil.copyfileobj(src, dst)
with connection(target) as conn:
    assert conn.execute("SELECT 42").fetchone() == (42,)
    print("Backup tables:", conn.execute("SHOW TABLES").fetchall())
print("Backup verified:", target)
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
| Cannot execute ... read-only | Context mặc định chỉ đọc; thao tác DE được phép ghi phải chọn `read_only=False` hoặc transaction. |
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
- [x] 14 ca DuckDB và 14 ca SQLite PASS trên môi trường hiện tại.
- [x] Backup offline đã được test trên database tạm, không copy database dự án lần này.
- [x] Git ignore được kiểm tra; SQLite source giữ nguyên.
- [ ] Setup trên máy sạch, backup/restore vận hành thật: chưa nghiệm thu.
- [ ] Dataset/contracts và mọi thành phần Warehouse nghiệp vụ: chờ giai đoạn sau.
