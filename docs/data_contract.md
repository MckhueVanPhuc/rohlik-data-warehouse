# Data contract

Nguồn sự thật máy đọc được là `config/sources.yaml` và `config/contract.yaml`. Tài liệu này mô tả cách sử dụng, không thay thế hai file cấu hình đó.

## Source registry

Registry production có đúng 7 nguồn active. Mỗi nguồn khai báo đường dẫn, vai trò, trạng thái, checksum SHA-256 và metadata cần thiết. Finance/workforce có thể là dữ liệu giả định theo cờ trong registry; người dùng downstream phải giữ nhãn này.

| ID | File | Khóa nghiệp vụ | Loại |
| --- | --- | --- | --- |
| `orders` | `data/raw/orders/train.csv` | warehouse + date | Kaggle original |
| `sales` | `data/raw/sales/sales_train.csv` | unique_id + date | Kaggle original, Git LFS |
| `inventory` | `data/raw/sales/inventory.csv` | unique_id | Kaggle original |
| `calendar` | `data/raw/sales/calendar.csv` | warehouse + date | Kaggle original |
| `weights` | `data/raw/sales/test_weights.csv` | unique_id | Kaggle original |
| `cost_params` | `data/raw/assumptions/cost_params.csv` | L1 category | Assumed |
| `workforce_params` | `data/raw/assumptions/workforce_params.csv` | warehouse | Assumed |

`historical_sources.orders_calendar` được giữ để giải thích nguồn lịch sử. Nó không được load như nguồn active (`historical_sources_loaded=0`) và không phải runtime Task08A.

```powershell
.\.venv\Scripts\python.exe -m src.validate_source_registry --metadata-only --json
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
```

## Landing contract

Có 14 contract landing trong 9 schema `src_*`. Contract định nghĩa tên bảng, cột, kiểu dữ liệu, khóa, quy tắc null/duplicate và update policy. Không đổi schema hoặc policy chỉ để làm một file mới ingest được.

Grain chính gồm warehouse-ngày, SKU-ngày, SKU, L1 category và warehouse. Một file nguồn có thể cấp nhiều bảng contract; ví dụ sales cấp sales, price, promotion và availability. Danh sách đầy đủ của 14 bảng, từng cột, nullable flag và mapping nằm trong `config/contract.yaml`.

Policy được duyệt là `APPEND_FULL_ROW_SOFT_UNDO`: dữ liệu mới được append theo lô, giữ nguyên hàng nguồn và hỗ trợ undo mềm có audit. Mọi thao tác phải lưu batch/run metadata.

## Các lớp dữ liệu

| Lớp | Vai trò |
| --- | --- |
| Landing | Bản sao có kiểm soát của nguồn, phục vụ lineage và audit. |
| STG | 14 bảng chuẩn hóa kiểu dữ liệu và khóa. |
| Core | 6 bảng nghiệp vụ hợp nhất. |
| Mart | 5 mart nền cho reporting. |
| Model result | 7 mart/view công bố output BT1–BT8. |

Reporting chỉ đọc những mart nằm trong allowlist. Không cho UI truy vấn tùy ý vào landing hoặc bảng metadata nhạy cảm.

## NULL, anomaly và tiền tệ

- Cột `required` phải hiện diện; nullable được quyết định từng cột trong contract, không suy diễn toàn cục.
- Range checks chặn số âm không hợp lệ và ép cờ/tỷ lệ vào miền `[0,1]`; duplicate được đánh giá theo business key.
- Weather và một số measure sales được phép NULL đúng như YAML; không tự điền nếu transform không quy định.
- `hourly_wage_eur` mang đơn vị EUR. Các tỷ lệ cost/workforce là giả định, không phải số liệu tài chính đã đối soát.
- Anomaly vượt contract phải fail hoặc được ghi nhận bởi DQ, không âm thầm clamp/thay thế.

## Dữ liệu local và Git LFS

`data/raw/sales/sales_train.csv` được quản lý bằng Git LFS. Sau clone phải chạy `git lfs pull` và xác nhận file là CSV thật. Các nguồn hoặc database không được Git theo dõi phải được bàn giao qua kênh bảo mật; không commit chúng để “hoàn thiện” môi trường.

Ba file root `sales_test.csv`, `test.csv`, `test_calendar.csv` chưa có consumer runtime được chứng minh. Chúng được giữ nguyên theo nguyên tắc hold-for-review, không tự xóa hoặc đưa vào pipeline.
