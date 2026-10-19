# Data Dictionary — sáu CSV lịch sử (TASK 06)

Ngày 18/10/2026. Nguồn số liệu: CLI `src.profile_sources`, DuckDB 1.5.6;
nghiệp vụ: [v3 C2/C3/A2/E1](../Rohlik_Decision_Hub_Huong_dan_thuc_hien_v3.md).
Đây là dictionary quan sát và đề xuất, **không phải schema SQLite/Gold đã duyệt**.
Workflow Data Contract BT1–BT8 đã RETIRED ngày 19/10/2026; dictionary vẫn là bằng
chứng quan sát, không tự phê duyệt schema nghiệp vụ.

Inferred types dùng full-file sample_size=-1 và strict parse. DOUBLE là float,
không phải DECIMAL chính xác. Tiền chưa chốt precision/scale/currency nên không tự
đổi DECIMAL(p,s). Integer-valued DOUBLE vẫn ghi rõ type nguồn; BIGINT đề xuất cần duyệt.
SQLite type chỉ đề xuất nếu cột được duyệt cho CSV upload, không cấp quyền upload.
DATE → TEXT ISO-8601; mã BIGINT không chứng minh mã tương lai luôn là số.
Observed nullable là có null quan sát, không quyết định constraint nghiệp vụ.
Distinct bỏ null; min/max chuỗi chỉ lexical, không là độ lớn nghiệp vụ.
Blank/whitespace và categorical values chi tiết ở profiling report/JSON.

## orders — `data/raw/orders/train.csv`

7,340 dòng, 18 cột. Key/grain dự kiến: `warehouse, date`.

| Cột | Inferred type | DuckDB đề xuất | SQLite đề xuất | Observed nullable | Null | Null % | Distinct | Min | Max | Ví dụ tối đa 3 | Ý nghĩa / nguồn | DQ notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| warehouse | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 7 | Brno_1 | Prague_3 | Brno_1, Budapest_1, Frankfurt_1 | Mã kho; key cùng date (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| date | DATE | DATE | TEXT | Không thấy | 0 | 0.000000% | 1193 | 2020-12-05 | 2024-03-15 | 2020-12-05, 2020-12-06, 2020-12-07 | Ngày quan sát/lịch; không phải as_of (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| orders | DOUBLE | BIGINT (đề xuất sau duyệt) | INTEGER | Không thấy | 0 | 0.000000% | 4426 | 790 | 18139 | 790.0, 797.0, 800.0 | Số đơn kho-ngày, target BT1, khác total_orders (v3 C2/A2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| holiday_name | VARCHAR | VARCHAR | TEXT | Có | 7122 | 97.029973% | 24 | 1848 Revolution Memorial Day (Extra holiday) | Reformation Day | 1848 Revolution Memorial Day (Extra holiday), 2nd Christmas Day, All Saints' Day Holiday | Tên ngày lễ; null có thể ngày không lễ, cần đối chiếu holiday (v3 C2). | null policy cần xác nhận |
| holiday | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ ngày lễ (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| shutdown | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ gián đoạn kho, không mặc định biết trước (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| mini_shutdown | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ gián đoạn nhỏ, không mặc định biết trước (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| shops_closed | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ cửa hàng truyền thống đóng cửa (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| winter_school_holidays | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ nghỉ đông (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| school_holidays | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ nghỉ học (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| blackout | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ mất điện/gián đoạn (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| mov_change | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 3 | 0 | 1 | 0.0, 0.7, 1.0 | Thay đổi minimum order value; có số lẻ, không coi là binary (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| frankfurt_shutdown | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ gián đoạn Frankfurt (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| precipitation | DOUBLE | DOUBLE | REAL | Có | 270 | 3.678474% | 772 | 0 | 80 | 0.0, 0.1, 0.11 | Mưa quan sát, đơn vị chưa xác nhận (v3 C2). | null policy cần xác nhận |
| snow | DOUBLE | DOUBLE | REAL | Có | 270 | 3.678474% | 158 | 0 | 19.84 | 0.0, 0.1, 0.11 | Tuyết quan sát, đơn vị chưa xác nhận (v3 C2). | null policy cần xác nhận |
| user_activity_1 | DOUBLE | BIGINT (đề xuất sau duyệt) | INTEGER | Không thấy | 0 | 0.000000% | 1135 | 482 | 3437 | 482.0, 502.0, 506.0 | Chỉ số hoạt động app/web 1, đơn vị/nghĩa chi tiết chưa chốt (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| user_activity_2 | DOUBLE | BIGINT (đề xuất sau duyệt) | INTEGER | Không thấy | 0 | 0.000000% | 6147 | 1797 | 45769 | 1797.0, 2042.0, 2380.0 | Chỉ số hoạt động app/web 2, đơn vị/nghĩa chi tiết chưa chốt (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| id | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 7340 | Brno_1_2020-12-05 | Prague_3_2024-03-15 | Brno_1_2020-12-05, Brno_1_2020-12-06, Brno_1_2020-12-07 | Mã dòng warehouse_date theo v3 C2; không thay business key chưa kiểm tra công thức. | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |

## orders_calendar — `data/raw/orders/train_calendar.csv`

13,307 dòng, 15 cột. Key/grain dự kiến: `warehouse, date`.

| Cột | Inferred type | DuckDB đề xuất | SQLite đề xuất | Observed nullable | Null | Null % | Distinct | Min | Max | Ví dụ tối đa 3 | Ý nghĩa / nguồn | DQ notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| date | DATE | DATE | TEXT | Không thấy | 0 | 0.000000% | 1901 | 2019-01-01 | 2024-03-15 | 2019-01-01, 2019-01-02, 2019-01-03 | Ngày quan sát/lịch; không phải as_of (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| holiday_name | VARCHAR | VARCHAR | TEXT | Có | 12744 | 95.769144% | 37 | 1848 Revolution Memorial Day (Extra holiday) | Whit sunday | 1848 Revolution Memorial Day (Extra holiday), 1st Christmas Day, 2nd Christmas Day | Tên ngày lễ; null có thể ngày không lễ, cần đối chiếu holiday (v3 C2). | null policy cần xác nhận |
| holiday | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ ngày lễ (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| shutdown | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ gián đoạn kho, không mặc định biết trước (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| mini_shutdown | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ gián đoạn nhỏ, không mặc định biết trước (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| warehouse_limited | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Có thật ở Orders Calendar; v3 C2 chưa định nghĩa riêng. PENDING_CONFIRMATION về nghĩa và thời điểm biết. | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| shops_closed | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ cửa hàng truyền thống đóng cửa (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| winter_school_holidays | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ nghỉ đông (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| school_holidays | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ nghỉ học (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| blackout | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ mất điện/gián đoạn (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| mov_change | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 3 | 0 | 1 | 0.0, 0.7, 1.0 | Thay đổi minimum order value; có số lẻ, không coi là binary (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| frankfurt_shutdown | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ gián đoạn Frankfurt (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| precipitation | DOUBLE | DOUBLE | REAL | Có | 2108 | 15.841287% | 847 | 0 | 80 | 0.0, 0.1, 0.11 | Mưa quan sát, đơn vị chưa xác nhận (v3 C2). | null policy cần xác nhận |
| snow | DOUBLE | DOUBLE | REAL | Có | 2108 | 15.841287% | 169 | 0 | 19.84 | 0.0, 0.1, 0.11 | Tuyết quan sát, đơn vị chưa xác nhận (v3 C2). | null policy cần xác nhận |
| warehouse | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 7 | Brno_1 | Prague_3 | Brno_1, Budapest_1, Frankfurt_1 | Mã kho; key cùng date (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |

## sales — `data/raw/sales/sales_train.csv`

4,007,419 dòng, 14 cột. Key/grain dự kiến: `unique_id, date`.

| Cột | Inferred type | DuckDB đề xuất | SQLite đề xuất | Observed nullable | Null | Null % | Distinct | Min | Max | Ví dụ tối đa 3 | Ý nghĩa / nguồn | DQ notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unique_id | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 5390 | 0 | 5431 | 0, 1, 2 | SKU cấp kho, không phải sản phẩm dùng chung giữa kho (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| date | DATE | DATE | TEXT | Không thấy | 0 | 0.000000% | 1402 | 2020-08-01 | 2024-06-02 | 2020-08-01, 2020-08-02, 2020-08-03 | Ngày quan sát/lịch; không phải as_of (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| warehouse | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 7 | Brno_1 | Prague_3 | Brno_1, Budapest_1, Frankfurt_1 | Mã kho; key cùng date (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| total_orders | DOUBLE | BIGINT (đề xuất sau duyệt) | INTEGER | Có | 52 | 0.001298% | 7508 | 458 | 18475 | 458.0, 464.0, 475.0 | Số đơn báo trong Sales; có thể khác theo SKU cùng kho-ngày, không bằng orders (v3 A2/C2). | null policy cần xác nhận |
| sales | DOUBLE | DOUBLE | REAL | Có | 52 | 0.001298% | 127279 | 0 | 26316.19 | 0.0, 0.02, 0.03 | Số lượng bán kg/chiếc theo sản phẩm, có thể lẻ; BT3/BT4 (v3 C2). | null policy cần xác nhận |
| sell_price_main | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 35723 | 0.02 | 21682.99 | 0.02, 0.04, 0.11 | Giá chính chưa giảm; currency/unit/precision chưa được xác nhận (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| availability | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 100 | 0.01 | 1 | 0.01, 0.02, 0.03 | Tỷ lệ thời gian SKU còn hàng; <1 là thiếu hàng một phần ngày (v3 C2/C4). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| type_0_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 17786 | -20.9493 | 0.99164 | -20.9493, -11.81868, -0.42066 | Tỷ lệ giảm giá loại 0, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | negative_count=27; outside_0_1=27 |
| type_1_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 154 | 0 | 0.5 | 0.0, 0.00146, 0.00376 | Tỷ lệ giảm giá loại 1, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| type_2_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 3521 | 0 | 0.76372 | 0.0, 0.00031, 0.00102 | Tỷ lệ giảm giá loại 2, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| type_3_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 18 | 0 | 0.25063 | 0.0, 0.00907, 0.01093 | Tỷ lệ giảm giá loại 3, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| type_4_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 1019 | -0.04712 | 0.4529 | -0.04712, 0.0, 0.0011 | Tỷ lệ giảm giá loại 4, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | negative_count=1; outside_0_1=1 |
| type_5_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 675 | 0 | 0.66914 | 0.0, 0.00258, 0.00305 | Tỷ lệ giảm giá loại 5, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| type_6_discount | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 44658 | -0.80149 | 0.90005 | -0.80149, -0.53746, -0.31571 | Tỷ lệ giảm giá loại 6, miền tham khảo [0,1]; âm cần điều tra, không tự clip (v3 C2). | negative_count=4; outside_0_1=4 |

## inventory — `data/raw/sales/inventory.csv`

5,432 dòng, 8 cột. Key/grain dự kiến: `unique_id`.

| Cột | Inferred type | DuckDB đề xuất | SQLite đề xuất | Observed nullable | Null | Null % | Distinct | Min | Max | Ví dụ tối đa 3 | Ý nghĩa / nguồn | DQ notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unique_id | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 5432 | 0 | 5431 | 0, 1, 2 | SKU cấp kho, không phải sản phẩm dùng chung giữa kho (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| product_unique_id | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2670 | 0 | 2669 | 0, 1, 2 | Mã sản phẩm chung giữa kho, không thay unique_id JOIN Sales (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| name | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 2670 | Apple_0 | Zucchini_9 | Apple_0, Apple_1, Apple_10 | Tên sản phẩm ẩn danh; inventory là danh mục, không là tồn kho (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| L1_category_name_en | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 3 | Bakery | Meat and fish | Bakery, Fruit and vegetable, Meat and fish | Ngành hàng cấp L1, tên tiếng Anh/ẩn danh (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| L2_category_name_en | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 47 | Bakery_L2_10 | Meat and fish_L2_38 | Bakery_L2_10, Bakery_L2_14, Bakery_L2_18 | Ngành hàng cấp L2, tên tiếng Anh/ẩn danh (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| L3_category_name_en | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 177 | Bakery_L3_100 | Meat and fish_L3_98 | Bakery_L3_100, Bakery_L3_103, Bakery_L3_104 | Ngành hàng cấp L3, tên tiếng Anh/ẩn danh (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| L4_category_name_en | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 68 | Bakery_L4_1 | Meat and fish_L4_7 | Bakery_L4_1, Bakery_L4_15, Bakery_L4_27 | Ngành hàng cấp L4, tên tiếng Anh/ẩn danh (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| warehouse | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 7 | Brno_1 | Prague_3 | Brno_1, Budapest_1, Frankfurt_1 | Mã kho; key cùng date (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |

## sales_calendar — `data/raw/sales/calendar.csv`

23,016 dòng, 7 cột. Key/grain dự kiến: `warehouse, date`.

| Cột | Inferred type | DuckDB đề xuất | SQLite đề xuất | Observed nullable | Null | Null % | Distinct | Min | Max | Ví dụ tối đa 3 | Ý nghĩa / nguồn | DQ notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| date | DATE | DATE | TEXT | Không thấy | 0 | 0.000000% | 3288 | 2016-01-01 | 2024-12-31 | 2016-01-01, 2016-01-02, 2016-01-03 | Ngày quan sát/lịch; không phải as_of (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| holiday_name | VARCHAR | VARCHAR | TEXT | Có | 22086 | 95.959333% | 37 | 1848 Revolution Memorial Day (Extra holiday) | Whit sunday | 1848 Revolution Memorial Day (Extra holiday), 1st Christmas Day, 2nd Christmas Day | Tên ngày lễ; null có thể ngày không lễ, cần đối chiếu holiday (v3 C2). | null policy cần xác nhận |
| holiday | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ ngày lễ (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| shops_closed | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ cửa hàng truyền thống đóng cửa (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| winter_school_holidays | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ nghỉ đông (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| school_holidays | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 2 | 0 | 1 | 0, 1 | Cờ nghỉ học (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| warehouse | VARCHAR | VARCHAR | TEXT | Không thấy | 0 | 0.000000% | 7 | Brno_1 | Prague_3 | Brno_1, Budapest_1, Frankfurt_1 | Mã kho; key cùng date (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |

## weights — `data/raw/sales/test_weights.csv`

5,390 dòng, 2 cột. Key/grain dự kiến: `unique_id`.

| Cột | Inferred type | DuckDB đề xuất | SQLite đề xuất | Observed nullable | Null | Null % | Distinct | Min | Max | Ví dụ tối đa 3 | Ý nghĩa / nguồn | DQ notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unique_id | BIGINT | BIGINT | INTEGER | Không thấy | 0 | 0.000000% | 5390 | 0 | 5431 | 0, 1, 2 | SKU cấp kho, không phải sản phẩm dùng chung giữa kho (v3 C2/C3). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |
| weight | DOUBLE | DOUBLE | REAL | Không thấy | 0 | 0.000000% | 3074 | 0.040064622 | 73.281676 | 0.04006462248598747, 0.10895668986852282, 0.11733797370456304 | Trọng số WMAE, không phải kg và không giới hạn <=1 (v3 C2). | Không thấy lỗi miền đã đo; chưa xác nhận nghiệp vụ |

## Cột đề xuất chưa tồn tại trong nguồn

`order_index` là median(total_orders) theo warehouse/date (bỏ null, lưu coverage); `max_discount`, `final_price` là biến đổi tương lai. batch_id/audit/as_of là metadata upload dự kiến. Không tạo các cột này trong Task 06. Finance/HR tham số v3 không phải dữ liệu thật.
