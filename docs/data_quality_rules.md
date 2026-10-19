# Data Quality Rules — thiết kế sau Source Profiling (TASK 06)

Ngày 18/10/2026. **Pipeline rules: PLANNED / PENDING_CONFIRMATION**, chưa có engine
thực thi, ingestion hoặc quarantine. Các phép đo thật nằm ở
[profiling report](data_profiling_report.md); không gọi chúng là 18 pipeline rules
đã PASS. V3 E1 nói 18 checks của bộ mã mẫu, không phải số tests của repository này.

Severity đề xuất: **FAIL** chặn nhận/publish phần dữ liệu bị ảnh hưởng; **WARN** cần
review và quyết định chủ dữ liệu, không tự sửa; **INFO** ghi nhận/provenance. Quyết
định chặn toàn file hay nhận phần hợp lệ cho upload vẫn theo CSV Upload Contract
chưa được duyệt; không tự áp dụng từ severity của tài liệu này.

| Rule ID | Table/column | Condition đề xuất | Severity | Expected behavior | Business justification | Trạng thái / bằng chứng Task 06 |
| --- | --- | --- | --- | --- | --- | --- |
| SRC-01 | 6 CSV / registry | File trong allowlist tồn tại, đọc được, strict parse không bỏ lỗi | FAIL | Dừng bước phụ thuộc khi thiếu/lỗi; lưu chẩn đoán | Không coi nguồn thiếu là dữ liệu rỗng | Đã đo 6/6 có thật; pipeline policy PENDING_CONFIRMATION |
| SRC-02 | Mọi source / schema | Header/cột bắt buộc/kiểu khớp schema_version đã duyệt | FAIL | Không tự thêm cột/đổi schema; báo diff | Tránh model đọc nhầm contract | Headers/types đã đo; business schema chưa duyệt |
| SRC-03 | CSV keys | Key không null/blank | FAIL | Báo dòng/key, không INSERT key thiếu | Cần định danh và JOIN/UPSERT | Đã đo 0 null/blank key ở sáu nguồn |
| SRC-04 | Mọi business key | Một dòng/key trong snapshot hoặc conflict policy đã duyệt | FAIL | Ghi duplicate group/excess, không tự keep latest | Ngăn row explosion và ghi đè nhầm | Đã đo duplicate key=0; upload policy chưa chốt |
| SRC-05 | Full source rows | Full-row duplicates được phát hiện riêng khỏi duplicate keys | WARN | Không tự drop; kiểm tra provenance/batch | Cùng key khác payload không phải full-row duplicate | Đã đo full-row excess=0 |
| SRC-06 | date / Orders/Sales/calendars | Parse DATE hợp lệ, không null cho key; ngữ nghĩa timezone/đơn vị đã chốt | FAIL | Reject/quarantine theo policy, không sinh ngày thay thế | Phân chia thời gian, JOIN và leakage | Đã đo invalid date=0; date null=0 |
| SRC-07 | orders,total_orders | Hữu hạn, >=0; nguyên nếu contract xác nhận count; orders>0 chỉ khi nghiệp vụ quy định | WARN | Phân biệt đóng cửa/ngày thiếu, không tự fill hoặc drop | Zero có thể có ngữ nghĩa, không suy từ v3 mẫu | Orders min 790, không null; total_orders null=52; fractional=0 |
| SRC-08 | sales | Hữu hạn, >=0; cho phép số lẻ theo đơn vị | WARN | Review null/âm và đơn vị; không ép integer | Kg và đơn vị bán không nhất thiết nguyên | Null=52, âm=0, zero=49.207, nhiều fractional |
| SRC-09 | sell_price_main | Hữu hạn, >0; currency/unit/precision nhất quán | WARN | Chủ dữ liệu review cực trị, không winsorize/loại tự động | Giá khác currency không so trực tiếp | Min=0,02, max=21.682,99, <=0=0; currency pending |
| SRC-10 | availability | Hữu hạn và [0,1] | FAIL | Báo ngoài miền; không tự clip | Tỷ lệ thời gian có hàng | Ngoài miền=0; <1 là thiếu hàng hợp lệ, không phải FAIL |
| SRC-11 | type_0…6_discount | Hữu hạn, [0,1] sau khi chốt semantics | WARN | Quarantine/review hoặc sửa theo policy đã duyệt, không clip trong profiling | Giảm giá âm có thể lỗi/khác nghĩa | 27/1/4 cell âm ở type_0/4/6; tổng 32 cell, không khẳng định 32 dòng |
| SRC-12 | weight | Hữu hạn, >0; không giới hạn <=1 | FAIL | Review nguồn/hiệu lực; không coi là khối lượng | Trọng số WMAE, không phải kg | 5.390 weight đều dương, max≈73,28 |
| SRC-13 | Sales→Inventory/Weights | Key lookup không null; right unique; unmatched theo hợp đồng | FAIL | Chặn lookup thiếu bắt buộc và nhân dòng | Đảm bảo category/trọng số đúng SKU | Sales unmatched=0; 42 inventory-only cần INFO, không tự xoá |
| SRC-14 | Sales/Orders→calendar | Có lịch đúng warehouse/date trong phạm vi cần dùng | FAIL | Báo ngày thiếu; không coi ngày lịch dư là lỗi FK | Feature lịch và backtest đúng thời gian | Unmatched facts=0 ở JOIN đã đo |
| SRC-15 | Orders↔Sales | Không coi orders=total_orders; aggregate Sales trước JOIN kho-ngày | FAIL | Không SUM orders sau JOIN SKU; assert expected grain/row count | JOIN 1:n có thể nhân metric | 7.340 cặp sau aggregate; JOIN thẳng 3.398.556 dòng |
| SRC-16 | planning.calendar | Shared field đồng nhất null-safe trên cùng key | WARN | Giữ cả provenance, chờ Planning quyết định precedence nếu conflict | Không chọn nguồn tùy tiện | Năm shared fields conflict=0 trên 13.307 key; future conflict policy pending |
| SRC-17 | warehouse_limited | Meaning, availability-at-as_of và mapping được duyệt trước dùng | WARN | Giữ nguồn, không gộp shutdown hoặc dùng future predictor | V3 chưa định nghĩa riêng cột thực tế này | Có ở Orders Calendar, không ở Sales Calendar; PENDING_CONFIRMATION |
| SRC-18 | Numeric/boolean fields | Không NaN/Inf; cờ đúng domain được phê duyệt | FAIL | Báo thay vì chuyển 0; semantic domains có version | Giá trị không hữu hạn làm hỏng aggregate/model | Numeric nonfinite=0; binary observed min/max=0/1; mov_change không binary |
| SRC-19 | Source coverage | Theo dõi date min/max, missing days, kho/SKU ngoài baseline | INFO | Không tự tạo ngày/SKU, báo thay đổi phạm vi | Hai dataset lệch lịch sử, kho mở khác ngày | Coverage theo kho đã đo; lịch vận hành/ngày mở cần xác nhận |
| SRC-20 | JOIN cardinality | Assert expected left/inner rows và right uniqueness theo grain | FAIL | Chặn publish metric nhân dòng, lưu matched/unmatched | JOIN lookup khác aggregate JOIN | Đã đo bằng key multiplicities; chưa có pipeline gate |
| SRC-21 | Upload batch/idempotency | Cùng nội dung/batch retry không tạo records/audit thay đổi dữ liệu lặp | FAIL | Chống trùng trong transaction theo policy; không add lại khi sync retry | Đúng kiến trúc CSV Upload Contract | PLANNED, chưa kiểm thử upload hoặc sync |
| SRC-22 | Provenance / all stages | source path/hash, data_version, schema_version, as_of, batch/sync run có thể truy vết | FAIL | Không publish nguồn không truy vết; hash không thay validation | Tái lập và audit | Sáu SHA-256 trước/sau có thật; batch metadata chưa triển khai |
| SRC-23 | Forecast features | Chỉ dữ liệu biết tại as_of; split thời gian; không dùng test Kaggle/future actuals | FAIL | BLOCKED nếu thiếu forecast upstream bắt buộc; không giả dữ liệu | BT1/4/8 có nguy cơ leakage cao | Task 06 không đọc test CSV; feature availability còn cần ML xác nhận |
| SRC-24 | finance.cost_params / hr.workforce_params | Nguồn, schema, giá trị, version được Finance/HR phê duyệt | FAIL | MISSING/BLOCKED phần phụ thuộc, không bootstrap dữ liệu giả định | V3 dùng giả định không phải dữ liệu thật | MISSING; chỉ có đề xuất schema ở mapping |
| SRC-25 | Categorical/text fields | Blank/null/whitespace/case và domain version kiểm soát | WARN | Báo thay đổi biểu diễn; không đổi mã/tên tự động | Chuẩn hoá có thể làm mất nghĩa/key | Đã đo blank/whitespace/normalized distinct; chưa thấy lệch trong các cột chữ |
| SRC-26 | SQL→DuckDB→published Parquet | Snapshot input nhất quán, sync retry không lặp, chỉ publish sau kiểm định | FAIL | Giữ bản publish cũ, không lộ snapshot một phần | Không có transaction chung SQLite/DuckDB | PLANNED, chưa có sync/publisher/end-to-end tests |

## Nguyên tắc xử lý sau khi được duyệt

V3 gợi ý clip, drop sales âm và giữ file mới nhất. Đây là **REFERENCE_ONLY**, chưa
đủ để tự sửa nguồn hoặc quyết định Silver. Mỗi rule cần chủ bảng, reviewer, ngày,
phiên bản và hành động rõ ràng trước triển khai. Những findings WARN hiện tại cần
review, không tự cấm cả bộ dữ liệu lịch sử và cũng không tự bỏ qua.

Không coi full-row/key uniqueness của sáu snapshot là idempotency CSV upload đã
được chứng minh. Không coi 26 rule specs là 26 tests PASS; số tests thật ghi ở report.
