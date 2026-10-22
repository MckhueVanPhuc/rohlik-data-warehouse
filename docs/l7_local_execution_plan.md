# Rohlik DE/BI Local-first — kế hoạch sửa và thực thi trước BT1–BT8

> **Source of truth:** `Rohlik_HD_xay_dung_he_thong_DE_BI_Local_Cloud.md`, bản 2.0 (22/10/2026), SHA-256 `6bad5ad7c6e34ccca3e39567c85a9f42af7bc80afe9db47247cb96e4490d5f70`. Phạm vi tham chiếu: II.1–II.6, I.4.3, phụ lục B–C. **Không** tự thay hướng A + Core mỏng bằng Full V4. Các nguồn V4, các tài liệu lịch sử chỉ làm reference nếu nội dung trùng hợp đồng hiện tại.

## 0. Quy tắc triển khai

- Repository triển khai duy nhất: `MckhueVanPhuc/rohlik-data-warehouse`. Triển khai **Local** trước; Cloud C2 chỉ sau local acceptance và D10. Dashboard v3 có **một admin, chỉ đọc**, đúng 8 trang, tuyệt đối không có upload/undo/7 roles hay nút chạy model trong đợt này.
- D01 đề xuất **A + Core mỏng**, gồm `core.fct_warehouse_day`, `core.fct_sku_day`, `core.params_cost`, `core.params_workforce` (4 bảng) và 5 Mart views. Đây là **đề xuất**, vẫn phải có quyết định của trưởng nhóm. Không triển khai 14 STG/6 Core/CSV upload theo Full V4.
- D01–D05 đang **PENDING**, không tự phê duyệt. Không thay `config/settings.yaml`, `config/contract.yaml`, không đổi update policy, không promote warehouse thử nghiệm vào `data/warehouse/rohlik.duckdb` cho đến khi chốt.
- Landing nguồn giữ nguyên, chỉ đọc những source batches `COMPLETED`; đảm bảo không nhân dòng, không chèn số giả, không tẩy NULL/discount âm chưa được duyệt. Biến đổi đọc nguồn đã xác minh, kiểm soát thời gian theo `as_of`.
- Dashboard không import/train model và không sinh KPI giả. Mô hình BT1–BT8 chỉ chấp nhận khi handoff thực tế qua cổng nghiệm thu và output contract; tuyệt đối không gọi STUB là FINAL.

## 1. Execution tracker

| Mã | Trích mục | Công việc | Phụ thuộc | Kết quả / kiểm chứng | Hiện trạng |
| --- | --- | --- | --- | --- | --- |
| P0-01 | II.2.3, Phụ lục C | Duyệt D01 scope A + Core mỏng, không upload/undo/7 roles | Người duyệt | M5 có phương án, ngày, bằng chứng | BLOCKED_APPROVAL |
| P0-02 | II.3 L6 | Duyệt D02 source-only policy; đối chiếu parser Literal trong `src/config/source_registry.py` và production guard | Người duyệt + DE | Migration code/contract được kiểm thử, không vượt production guard | BLOCKED_APPROVAL |
| P0-03 | II.1, II.3 L7 | Duyệt D03 7 warehouses + cutoff/backtest/forecast; giữ khác biệt source date ranges | Người duyệt + chủ model | `settings.yaml` sửa cùng tests và tài liệu; as_of=2024-03-15, horizon=14 | BLOCKED_APPROVAL |
| P0-04 | II.1.2, II.3 L7 | Duyệt D04 NULL/discount âm/weather (proposal: flags+WARN, Landing bất biến) | Người duyệt + DE | Core SQL/DQ golden fixture, không giả định 0 cho NULL | BLOCKED_APPROVAL |
| P0-05 | I.4.3, II.3 L7 | Duyệt D05 danh mục cột/metric 5 mart theo M2; bảng hàng ngày chỉ 1 date, SKU mart category field | M2 + BI + người duyệt | Data dictionary, Mart schema tests và chart test | BLOCKED_APPROVAL |
| P1-01 | II.3 L5–L6 | Preflight 7 CSV, test 14 landing + 7 `COMPLETED` + NO_OP ở DB thử nghiệm | Không cần BT | `src.validate_source_registry`; `src.ingest_landing`; log kiểm định | CAN_RUN_ISOLATED |
| P1-02 | II.3 L7 | Xây L7 Core mỏng 2 facts/2 params từ Landing đã xác minh, bằng transaction+writer lock; không tạo lại Landing | D01–D04, M2 | DQ key coverage, JOIN cardinality, original row counts, no future actual leakage | GATED |
| P1-03 | II.3 L7/L9 | Xây 5 Mart; `app/services/reporting.py` allowlist giữ nguyên | D05, P1-02 | `5/5` real views, DATA_READY historical pages | GATED |
| P1-04 | II.6 + phụ lục B | Test L7 trên fixture và DB dev; rollback khi DQ fail, no overwrite, read-only dashboard | P1-02/03 | CI tests + evidence, 0 failed (không mặc định 207 sau đổi code) | CAN_PREPARE |
| P1-05 | II.3 L8 | Chuẩn bị handoff manifest, DAG & validation; chưa chạy model | D06, M3; FINAL chưa bàn giao | Interface chỉ là bản đề xuất, dependency BLOCKED khi upstream không hợp lệ | CAN_DESIGN |
| P2-01 | II.3 L0–L4 | Mac docs/CI macOS, lockfile trên môi trường đã test | D08/D09 | Bằng chứng cài và pytest thực tế từng OS | GATED |
| P2-02 | II.4 | Cloud C2 (một codebase, publish 1 chiều, secrets ngoài Git) | Local acceptance + D10/D12 | Cloud demo checked, không có kho dữ liệu rẽ nhánh | DEFERRED |

**Trong PR này**: tạo bảng quyết định ở `config/l7_decisions.yaml`, bổ sung CLI đọc-only `src.l7_readiness` để báo trạng thái cơ sở L7, test không có thao tác ghi, và chỉ ra các bước/điều kiện chặn trong bảng trên. **Chưa** tuyên bố L7/Core/Mart/8 FINAL được triển khai.

## 2. Giao ước D01–D05: không suy diễn chữ 'proposal' thành 'approved'

| Quyết định | Đề xuất từ tài liệu chuẩn | Chỉ triển khai sau khi… |
| --- | --- | --- |
| D01 | A + Core mỏng, không STG/upload/undo/7 roles | M5 ký/ghi APPROVED và phạm vi |
| D02 | Chỉ nạp nguồn, không người dùng sửa | Duyệt giá trị update-policy và migration parser/code; nghiệm thu fail-closed |
| D03 | 7 kho, train_from 2020-12-05, as_of 2024-03-15, forecast 2024-03-16→29 | Chốt cutoff và cách lọc features (Sales gốc còn có dữ liệu sau as_of) |
| D04 | Giữ NULL sales/total_orders, flag; discount âm được gắn flag và xử lý theo policy, weather giữ NULL, WARN | DQ spec M2 được ký, báo rõ KPI null treatment |
| D05 | 5 Mart có warehouse, date/month, category trên Mart SKU; numeric fields chỉ metrics thực | Danh sách cột/kiểu/grain từng Mart trong M2 được duyệt |

D06–D12: chờ M5. D06 dự kiến `run_model(inputs, config, artifact_dir)` không ép chủ mô hình đổi notebook trước bàn giao; D07 EUR conversion phải chờ tỷ giá được duyệt; D08 Mac CI; D09 lockfile; D10 Cloud; D11 owner/deadline; D12 Sharing.

## 3. Cách kiểm nhanh trên máy có dữ liệu

```powershell
# Windows, repo root — chỉ đọc, không yêu cầu thay đổi warehouse
.\.venv\Scripts\python.exe -m src.l7_readiness --json --database data/warehouse/rohlik_landing_dev.duckdb
.\.venv\Scripts\python.exe -m src.validate_source_registry --json
.\.venv\Scripts\python.exe -m pytest -q
```

```bash
# Mac, repo root — chưa được xác nhận CI Mac
.venv/bin/python -m src.l7_readiness --json --database data/warehouse/rohlik_landing_dev.duckdb
.venv/bin/python -m src.validate_source_registry --json
.venv/bin/python -m pytest -q
```

L7 readiness báo `BLOCKED` là đúng khi D01–D05 chưa có approval hoặc chưa đủ Landing; không chuyển một bảng thiếu thành `DATA_READY` và không khởi tạo database. Lệnh chỉ kiểm catalogue, batch status và config. **Nó không thay thế** lệnh ingest `NO_OP` reconciliation, unit/integration tests hay nghiệm thu DQ business.

## 4. Tiêu chí nghiệm thu theo hai mốc

**PRE-MODEL LOCAL:** 7 nguồn đúng registry; 14 Landing/7 batches với NO_OP; 4 Core; 5 Mart; DQ không ERROR; 8 trang Streamlit có historical readiness đúng; pipeline không tạo dự báo; 0 failed tests; có log/commit và quyết định D01–D05. Hợp đồng có thể được duyệt trước nhưng chỉ đánh dấu ACCEPTED khi các bằng chứng thực thi đã tồn tại.

**FINAL LOCAL:** nhận đủ 8 packages thật, tái lập output trong môi trường model riêng, mapping được model owner đồng ý, publish atomically 14 pred+2 hist nếu output contracts duyệt, dashboard phân biệt model status, E2E acceptance. Sau đó mới D10 Cloud C2.

## 5. Chỉnh tài liệu nguồn và repo sau khi quyết định

- II.1.1: bảng gọi 'bảy thành phần' nhưng hiện mới đánh số 1–6 → sửa tiêu đề/danh mục cho nhất quán khi xuất bản bản mới.
- II.1.1 L5 và II.5.1: tài liệu nói raw `data/raw` không lên Git, song `data/raw/**` đã được commit (commit `63e8875`) và Sales dùng Git LFS. Cần duyệt chính sách phân phối và sửa hướng dẫn LFS, **không tự xóa lịch sử Git**.
- II.1.5: mốc kiểm tra `bc9bbd5` không còn là HEAD (đã có `7f23ac7`); ghi rõ commit kiểm thử/test count tương ứng.
- II.1: 'lịch sử đến as_of' là **cửa sổ phân tích**, không phải toàn bộ source. Sales CSV có lịch sử sau as_of, Calendar xa hơn; lọc thời điểm khi xây feature, không cắt raw.
- D09: không tự ghim `requirements.lock` từ môi trường chưa tái lập; tách model dependencies khỏi root environment.

## 6. Bằng chứng còn thiếu / giới hạn triển khai này

- Các file M2/M3/M5 (bản đặc tả/phiếu ký) chỉ **được tham chiếu** trong tài liệu nguồn; chưa có bản tương ứng được xác nhận để khóa Mart columns và model output. Không tự bịa spec/metric.
- Không nhận được model package BT1–BT8; không có đánh giá benchmark/forecast thật.
- Không thực thi lệnh ghi vào warehouse chính, không bật cloud, không sửa credential, không xuất bản STUB.

Khi D01–D05 được duyệt, mới viết và nghiệm thu mã L7 trong PR kế tiếp hoặc tiếp tục trên nhánh sau review.
