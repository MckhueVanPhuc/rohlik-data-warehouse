# Source Mapping — 6 CSV → 14 Source Tables (TASK 06)

Ngày 18/10/2026. **DESIGN / PENDING_CONFIRMATION**, chưa tạo schema/source tables.
[V3 E1/D1](../Rohlik_Decision_Hub_Huong_dan_thuc_hien_v3.md) là REFERENCE_ONLY,
[report](data_profiling_report.md) và [dictionary](data_dictionary.md) là evidence thực tế.
12 bảng có source fields để đề xuất projection, không phải schema đã duyệt;
hai nguồn Finance/HR MISSING. Expected rows là count projection giữ mọi dòng,
chưa filter/dedup/drop/null handling. Required fields là đề xuất, không constraint thật.

## 1. `sales_ecommerce.orders_daily`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | sales_ecommerce |
| Source CSV | data/raw/orders/train.csv |
| Source columns | warehouse,date,orders; id để provenance |
| Proposed output columns | Giữ key và orders |
| Grain | kho-ngày |
| Proposed business keys | warehouse,date |
| Expected rows / cách tính | 7,340 = count(*) orders, key unique quan sát |
| Required fields (đề xuất) | Keys warehouse,date; thêm orders |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Projection; integer type cần duyệt. |
| BT sử dụng theo v3 | BT1/2/8 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Null/type, ngày vắng và chính sách update. |
| Evidence | profile.json sources.orders: headers, key, SHA-256; v3 E1/D1. |

## 2. `sales_ecommerce.sku_sales_daily`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | sales_ecommerce |
| Source CSV | data/raw/sales/sales_train.csv |
| Source columns | unique_id,date,warehouse,sales,total_orders |
| Proposed output columns | Giữ các cột liệt kê |
| Grain | SKU cấp kho-ngày |
| Proposed business keys | unique_id,date |
| Expected rows / cách tính | 4,007,419 = count(*) sales, key unique quan sát |
| Required fields (đề xuất) | Keys unique_id,date; thêm warehouse,sales,total_orders |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Không SUM total_orders qua SKU; giữ 52 null để review. |
| BT sử dụng theo v3 | BT3/4/5/6/7 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Null và đơn vị sales. |
| Evidence | profile.json sources.sales: headers, key, SHA-256; v3 E1/D1. |

## 3. `marketing_pricing.prices`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | marketing_pricing |
| Source CSV | data/raw/sales/sales_train.csv |
| Source columns | unique_id,date,warehouse,sell_price_main |
| Proposed output columns | Giữ các cột liệt kê |
| Grain | SKU cấp kho-ngày |
| Proposed business keys | unique_id,date |
| Expected rows / cách tính | 4,007,419 = count(*) sales, key unique quan sát |
| Required fields (đề xuất) | Keys unique_id,date; thêm sell_price_main |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Projection giá chưa giảm, chưa tạo final_price. |
| BT sử dụng theo v3 | BT3/5/6/7 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Currency/precision/outliers. |
| Evidence | profile.json sources.sales: headers, key, SHA-256; v3 E1/D1. |

## 4. `marketing_pricing.promotions`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | marketing_pricing |
| Source CSV | data/raw/sales/sales_train.csv |
| Source columns | unique_id,date,warehouse,type_0_discount…type_6_discount |
| Proposed output columns | Giữ 7 cột; max_discount chỉ là đề xuất |
| Grain | SKU cấp kho-ngày |
| Proposed business keys | unique_id,date |
| Expected rows / cách tính | 4,007,419 = count(*) sales, key unique quan sát |
| Required fields (đề xuất) | Keys unique_id,date; thêm 7 discount fields |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Chưa clip, cộng dồn hay lấy max để sửa nguồn. |
| BT sử dụng theo v3 | BT5/7; BT4 tùy contract — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | 32 cell âm; stacking/max; hiệu lực. |
| Evidence | profile.json sources.sales: headers, key, SHA-256; v3 E1/D1. |

## 5. `marketing_pricing.min_order_value_changes`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | marketing_pricing |
| Source CSV | data/raw/orders/train.csv |
| Source columns | warehouse,date,mov_change |
| Proposed output columns | warehouse,date,mov_change |
| Grain | kho-ngày |
| Proposed business keys | warehouse,date |
| Expected rows / cách tính | 7,340 = count(*) orders, key unique quan sát |
| Required fields (đề xuất) | Keys warehouse,date; thêm mov_change |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Projection; Orders Calendar cũng có mov_change, không union chồng. |
| BT sử dụng theo v3 | BT1/8 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Scope/precedence Calendar và known-future. |
| Evidence | profile.json sources.orders: headers, key, SHA-256; v3 E1/D1. |

## 6. `warehouse_ops.availability`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | warehouse_ops |
| Source CSV | data/raw/sales/sales_train.csv |
| Source columns | unique_id,date,warehouse,availability |
| Proposed output columns | Giữ các cột liệt kê |
| Grain | SKU cấp kho-ngày |
| Proposed business keys | unique_id,date |
| Expected rows / cách tính | 4,007,419 = count(*) sales, key unique quan sát |
| Required fields (đề xuất) | Keys unique_id,date; thêm availability |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | <1 là thiếu hàng một phần, không tự drop. |
| BT sử dụng theo v3 | BT3; BT4 qua BT3 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Ngưỡng và availability tại as_of. |
| Evidence | profile.json sources.sales: headers, key, SHA-256; v3 E1/D1. |

## 7. `warehouse_ops.ops_events`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | warehouse_ops |
| Source CSV | data/raw/orders/train.csv |
| Source columns | warehouse,date,shutdown,mini_shutdown,blackout,frankfurt_shutdown |
| Proposed output columns | Giữ cờ; warehouse_limited chỉ đề xuất bổ sung sau duyệt |
| Grain | kho-ngày |
| Proposed business keys | warehouse,date |
| Expected rows / cách tính | 7,340 = count(*) orders, key unique quan sát |
| Required fields (đề xuất) | Keys warehouse,date; thêm các cờ vận hành |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Projection; Calendar có thêm warehouse_limited, không gộp mặc định. |
| BT sử dụng theo v3 | BT8/EDA; không future actuals — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Meaning/coverage/precedence của warehouse_limited. |
| Evidence | profile.json sources.orders: headers, key, SHA-256; v3 E1/D1. |

## 8. `category.product_master`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | category |
| Source CSV | data/raw/sales/inventory.csv |
| Source columns | unique_id,product_unique_id,name,L1_category_name_en…L4_category_name_en,warehouse |
| Proposed output columns | Giữ đủ 8 cột |
| Grain | SKU cấp kho |
| Proposed business keys | unique_id |
| Expected rows / cách tính | 5,432 = count(*) inventory, key unique quan sát |
| Required fields (đề xuất) | Keys unique_id; thêm product_unique_id,name,warehouse,L1…L4 |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Giữ toàn 5.432 SKU, không tự lọc 42 inventory-only. |
| BT sử dụng theo v3 | BT3–BT7/dimensions — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | SCD/update và product key giữa kho. |
| Evidence | profile.json sources.inventory: headers, key, SHA-256; v3 E1/D1. |

## 9. `planning.calendar`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | planning |
| Source CSV | data/raw/orders/train_calendar.csv + data/raw/sales/calendar.csv |
| Source columns | warehouse,date,holiday_name,holiday,shops_closed,school_holidays,winter_school_holidays; Orders-only có 8 cột khác |
| Proposed output columns | key + 5 fields chung + provenance; cột mở rộng chờ duyệt |
| Grain | kho-ngày |
| Proposed business keys | warehouse,date |
| Expected rows / cách tính | 23.016 distinct union keys; Sales Calendar chứa cả 13.307 Orders Calendar keys |
| Required fields (đề xuất) | Keys warehouse,date; thêm 4 cờ lịch chung; holiday_name có thể null |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Outer union key, giữ nguồn từng thuộc tính, không fill 0 phần thiếu. |
| BT sử dụng theo v3 | BT1/4/5/8 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Precedence, known-future và việc giữ weather/events. |
| Evidence | profile.json calendars + calendar JOIN counts; năm shared fields conflict=0. |

## 10. `digital_product.user_activity`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | digital_product |
| Source CSV | data/raw/orders/train.csv |
| Source columns | warehouse,date,user_activity_1,user_activity_2 |
| Proposed output columns | Giữ các cột liệt kê |
| Grain | kho-ngày |
| Proposed business keys | warehouse,date |
| Expected rows / cách tính | 7,340 = count(*) orders, key unique quan sát |
| Required fields (đề xuất) | Keys warehouse,date; thêm user_activity_1,user_activity_2 |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Projection, không tự fill tương lai. |
| BT sử dụng theo v3 | BT8/EDA — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Đơn vị, meaning chi tiết và độ trễ. |
| Evidence | profile.json sources.orders: headers, key, SHA-256; v3 E1/D1. |

## 11. `external.weather`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | external |
| Source CSV | data/raw/orders/train.csv |
| Source columns | warehouse,date,precipitation,snow |
| Proposed output columns | Giữ các cột liệt kê |
| Grain | kho-ngày |
| Proposed business keys | warehouse,date |
| Expected rows / cách tính | 7,340 = count(*) orders, key unique quan sát |
| Required fields (đề xuất) | Keys warehouse,date; thêm null policy weather cần chốt |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | 270 null mỗi field ở train, không fill 0; Calendar có coverage khác. |
| BT sử dụng theo v3 | BT8/EDA — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Đơn vị/precedence và actuals so với forecast. |
| Evidence | profile.json sources.orders: headers, key, SHA-256; v3 E1/D1. |

## 12. `finance.sku_weights`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | finance |
| Source CSV | data/raw/sales/test_weights.csv |
| Source columns | unique_id,weight |
| Proposed output columns | Giữ nguồn; warehouse chỉ enrich nếu duyệt |
| Grain | SKU cấp kho |
| Proposed business keys | unique_id |
| Expected rows / cách tính | 5,390 = count(*) weights, key unique quan sát |
| Required fields (đề xuất) | Keys unique_id; thêm weight |
| Availability | AVAILABLE_FIELDS / PENDING_CONFIRMATION |
| Transformation tương lai | Không coi weight là kg hoặc giới hạn <=1. |
| BT sử dụng theo v3 | BT3/4/WMAE — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Weight cho SKU mới và hiệu lực. |
| Evidence | profile.json sources.weights: headers, key, SHA-256; v3 E1/D1. |

## 13. `finance.cost_params`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | finance |
| Source CSV | NOT_AVAILABLE — không có trong sáu CSV |
| Source columns | Không có Finance CSV thật |
| Proposed output columns | L1_category_name_en TEXT, cost_ratio DOUBLE/DECIMAL?, shelf_life_days INTEGER, disposal_cost_ratio DOUBLE/DECIMAL? — đề xuất |
| Grain | L1-version/hiệu lực cần chốt |
| Proposed business keys | L1_category_name_en + version/hiệu lực (đề xuất) |
| Expected rows / cách tính | MISSING |
| Required fields (đề xuất) | Keys L1_category_name_en + version/hiệu lực (đề xuất); thêm mọi tham số phải được Finance duyệt |
| Availability | MISSING |
| Transformation tương lai | Không tạo giá trị giả định v3 hoặc INSERT. |
| BT sử dụng theo v3 | BT6/7 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Schema, precision/currency, range/hiệu lực và giá trị thật. |
| Evidence | Header sáu CSV và v3 C2 ghi tham số giả định. |

## 14. `hr.workforce_params`

| Thuộc tính | Đề xuất / bằng chứng |
| --- | --- |
| Department | hr |
| Source CSV | NOT_AVAILABLE — không có trong sáu CSV |
| Source columns | Không có HR CSV thật |
| Proposed output columns | warehouse TEXT, hourly_wage DECIMAL?, items_per_order DOUBLE, items_per_hour DOUBLE, shift_hours DOUBLE, overtime_multiplier DOUBLE, orders_per_driver_shift DOUBLE — đề xuất |
| Grain | kho-version/hiệu lực cần chốt |
| Proposed business keys | warehouse + version/hiệu lực (đề xuất) |
| Expected rows / cách tính | MISSING |
| Required fields (đề xuất) | Keys warehouse + version/hiệu lực (đề xuất); thêm mọi tham số phải được HR duyệt |
| Availability | MISSING |
| Transformation tương lai | Không tạo giá trị giả định v3 hoặc INSERT. |
| BT sử dụng theo v3 | BT2 — REFERENCE_ONLY, chờ model owner |
| Unresolved decisions | Schema, currency/đơn vị, owner/hiệu lực và giá trị thật. |
| Evidence | Header sáu CSV và v3 C2 ghi tham số giả định. |

## Các chính sách chưa chốt

Không tự keep latest, clip/drop hay chọn calendar precedence. `order_index` là
aggregate từ Sales, không sửa thành orders hoặc SUM tổng đơn qua SKU. Provenance,
batch_id/as_of và schema_version cần chốt trong Source Registry/CSV Upload Contract,
không thêm vào CSV gốc ở Task 06. Finance/HR chỉ có CSV riêng sau duyệt schema/giá trị.
Giữ kiến trúc CSV lịch sử read-only và CSV upload→SQLite records+audit/metadata cùng
transaction→PENDING_SYNC→DE batch DuckDB→Parquet sau kiểm định. Workflow Data Contract
BT1–BT8 đã RETIRED. Task 08A có thể chuẩn bị trong môi trường thử nghiệm tách biệt sau
phê duyệt phạm vi; Task 08B chính thức vẫn NOT_READY vì các quyết định trên chưa chốt.
