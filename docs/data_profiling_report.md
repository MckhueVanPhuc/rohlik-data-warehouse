# Source Profiling & V3 Gap Analysis — TASK 06

Ngày 18/10/2026; kết quả thực tế từ sáu CSV lịch sử, không đọc CSV test Kaggle.
CLI đã chạy SUCCESS; summary tại `data/exports/source_profiling/profile.json` (ignore).
[Dictionary](data_dictionary.md) đủ 64 cột, [mapping](source_mapping.md) đủ 14 bảng,
[DQ rules](data_quality_rules.md) là thiết kế, chưa phải pipeline đang chạy.

## Nguồn đối chiếu và phương pháp

Đã đối chiếu [v3 A2/C1–C4/D1/E0/E1](../Rohlik_Decision_Hub_Huong_dan_thuc_hien_v3.md),
README, Setup Tutorial, CSV Upload Contract và Model Integration Guide. Workflow tám
Data Contract từng được đối chiếu ở Task 06 đã RETIRED ngày 19/10/2026. Kế hoạch
`Rohlik_Plan_Data_Warehouse_Streamlit_Step_by_Step.docx`: **NOT_AVAILABLE**.
Không tự tạo nội dung thay thế; không coi số liệu v3 đã chạy tại repository này.

```powershell
.\.venv\Scripts\python.exe -m src.profile_sources
.\.venv\Scripts\python.exe -m pytest tests/test_profile_sources.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

DuckDB `:memory:`, 2 threads, memory_limit=1GB, chỉ TEMP source tables; spill trong
ignored reports. Không mở SQLite/DuckDB nghiệp vụ, không tạo physical JOIN tables.
JOIN cardinality tính từ key multiplicities: LEFT=sum(n_left*coalesce(n_right,1)),
INNER=sum(n_left*n_right); null keys không khớp theo SQL chuẩn. Không tải Sales vào Pandas.
CSV full-file type inference `sample_size=-1`, header=true, strict_mode=true,
ignore_errors=false; dialect sniff 20.480 mẫu và parse toàn file strict. UTF-8 kiểm
tra toàn bytes, chỉ xác nhận compatibility, không khẳng định encoding gốc duy nhất.
Các type/unit chưa rõ cần duyệt; SHA-256 chỉ nhận diện phiên bản, không chứng minh
dữ liệu hợp lệ. Correlation không xác định được ghi JSON null.

## 1. Source Inventory

| Nguồn | Relative path | Bytes | Rows | Columns | Date range | Kho | Tồn tại/read |
| --- | --- | --- | --- | --- | --- | --- | --- |
| orders | data/raw/orders/train.csv | 673371 | 7340 | 18 | 2020-12-05 → 2024-03-15 | 7 | Có / đọc thành công |
| orders_calendar | data/raw/orders/train_calendar.csv | 684353 | 13307 | 15 | 2019-01-01 → 2024-03-15 | 7 | Có / đọc thành công |
| sales | data/raw/sales/sales_train.csv | 308004437 | 4007419 | 14 | 2020-08-01 → 2024-06-02 | 7 | Có / đọc thành công |
| inventory | data/raw/sales/inventory.csv | 583850 | 5432 | 8 | N/A | 7 | Có / đọc thành công |
| sales_calendar | data/raw/sales/calendar.csv | 694501 | 23016 | 7 | 2016-01-01 → 2024-12-31 | 7 | Có / đọc thành công |
| weights | data/raw/sales/test_weights.csv | 125367 | 5390 | 2 | N/A | N/A | Có / đọc thành công |

- **orders** SHA-256 `1d0e15de6f8edceb501bfc2c4007cc595781494c8c9c86954584c86e4710be67`; UTF-8 compatible, BOM=False, dialect={'Delimiter': ',', 'Quote': '(empty)', 'Escape': '(empty)', 'NewLineDelimiter': '\\n', 'HasHeader': 'True', 'DateFormat': '%Y-%m-%d'}; hash trước/sau khớp.
- **orders_calendar** SHA-256 `502345a98099e9f9764226562da1ee2bda5cefe0f4fda1667d3ee32a5555eb18`; UTF-8 compatible, BOM=False, dialect={'Delimiter': ',', 'Quote': '(empty)', 'Escape': '(empty)', 'NewLineDelimiter': '\\n', 'HasHeader': 'True', 'DateFormat': '%Y-%m-%d'}; hash trước/sau khớp.
- **sales** SHA-256 `af45f951bd0e9f6132bc64fddca14b00829d260abca0591c9f637437833e0469`; UTF-8 compatible, BOM=False, dialect={'Delimiter': ',', 'Quote': '(empty)', 'Escape': '(empty)', 'NewLineDelimiter': '\\n', 'HasHeader': 'True', 'DateFormat': '%Y-%m-%d'}; hash trước/sau khớp.
- **inventory** SHA-256 `e1ada9e6d5af544e1ccefd7e8ef2785a78ad7784e783c4b25811a909ca7e966b`; UTF-8 compatible, BOM=False, dialect={'Delimiter': ',', 'Quote': '(empty)', 'Escape': '(empty)', 'NewLineDelimiter': '\\n', 'HasHeader': 'True', 'DateFormat': 'None'}; hash trước/sau khớp.
- **sales_calendar** SHA-256 `2633d53eecd494a49080c748b0e335574dc3706342723c85d9ee9636a2e36e84`; UTF-8 compatible, BOM=False, dialect={'Delimiter': ',', 'Quote': '(empty)', 'Escape': '(empty)', 'NewLineDelimiter': '\\n', 'HasHeader': 'True', 'DateFormat': '%Y-%m-%d'}; hash trước/sau khớp.
- **weights** SHA-256 `a3b33db34dbe0da26687496b6d98e8ec759a943f776e209a2573937406ccb783`; UTF-8 compatible, BOM=False, dialect={'Delimiter': ',', 'Quote': '(empty)', 'Escape': '(empty)', 'NewLineDelimiter': '\\n', 'HasHeader': 'True', 'DateFormat': 'None'}; hash trước/sau khớp.

Cả sáu file ở đúng đường dẫn yêu cầu, không đổi tên/di chuyển. Weights không có warehouse/date; không suy coverage trực tiếp. Column names/types/min/max/examples đầy đủ ở dictionary.

## 2. Profiling từng cột

### orders

| Cột | Null | Null % | Distinct | Âm | Fractional | Zero nếu kiểm tra | Ngoài [0,1] | Nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| warehouse | 0 | 0.000000 | 7 | N/A | N/A | N/A | N/A | N/A |
| date | 0 | 0.000000 | 1193 | N/A | N/A | N/A | N/A | N/A |
| orders | 0 | 0.000000 | 4426 | 0 | 0 | 0 | N/A | 0 |
| holiday_name | 7122 | 97.029973 | 24 | N/A | N/A | N/A | N/A | N/A |
| holiday | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| shutdown | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| mini_shutdown | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| shops_closed | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| winter_school_holidays | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| school_holidays | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| blackout | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| mov_change | 0 | 0.000000 | 3 | 0 | 144 | N/A | N/A | 0 |
| frankfurt_shutdown | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| precipitation | 270 | 3.678474 | 772 | 0 | 2716 | N/A | N/A | 0 |
| snow | 270 | 3.678474 | 158 | 0 | 234 | N/A | N/A | 0 |
| user_activity_1 | 0 | 0.000000 | 1135 | 0 | 0 | N/A | N/A | 0 |
| user_activity_2 | 0 | 0.000000 | 6147 | 0 | 0 | N/A | N/A | 0 |
| id | 0 | 0.000000 | 7340 | N/A | N/A | N/A | N/A | N/A |

- `warehouse` blank=0, whitespace=0, distinct/normalized lower(trim)=7/7. Values: Brno_1 (1193); Budapest_1 (1154); Frankfurt_1 (629); Munich_1 (785); Prague_1 (1193); Prague_2 (1193); Prague_3 (1193).
- `holiday_name` blank=0, whitespace=0, distinct/normalized lower(trim)=24/24. Values: 1848 Revolution Memorial Day (Extra holiday) (1); 2nd Christmas Day (16); All Saints' Day Holiday (1); Christmas Eve (23); Cyrila a Metodej (12); Day of National Unity (3); Den boje za svobodu a demokracii (12); Den ceske statnosti (12); Den osvobozeni (12); Den vzniku samostatneho ceskoslovenskeho statu (12); Easter Monday (12); Good Friday (12); Independent Hungary Day (3); International womens day (26); Jan Hus (12); Labour Day (12); Memorial Day for the Martyrs of Arad (3); Memorial Day for the Victims of the Communist Dictatorships (4); Memorial Day for the Victims of the Holocaust (3); Memorial Day of the Republic (4); National Defense Day (3); New Years Day (16); Peace Festival in Augsburg (2); Reformation Day (2); None (7122).
- `id` blank=0, whitespace=0, distinct/normalized lower(trim)=7340/7340. Values: Brno_1_2020-12-05, Brno_1_2020-12-06, Brno_1_2020-12-07, Brno_1_2020-12-08, Brno_1_2020-12-09 (mẫu, không phải toàn domain).
### orders_calendar

| Cột | Null | Null % | Distinct | Âm | Fractional | Zero nếu kiểm tra | Ngoài [0,1] | Nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| date | 0 | 0.000000 | 1901 | N/A | N/A | N/A | N/A | N/A |
| holiday_name | 12744 | 95.769144 | 37 | N/A | N/A | N/A | N/A | N/A |
| holiday | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| shutdown | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| mini_shutdown | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| warehouse_limited | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| shops_closed | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| winter_school_holidays | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| school_holidays | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| blackout | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| mov_change | 0 | 0.000000 | 3 | 0 | 151 | N/A | N/A | 0 |
| frankfurt_shutdown | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| precipitation | 2108 | 15.841287 | 847 | 0 | 3764 | N/A | N/A | 0 |
| snow | 2108 | 15.841287 | 169 | 0 | 251 | N/A | N/A | 0 |
| warehouse | 0 | 0.000000 | 7 | N/A | N/A | N/A | N/A | N/A |

- `holiday_name` blank=0, whitespace=0, distinct/normalized lower(trim)=37/37. Values: 1848 Revolution Memorial Day (Extra holiday) (1); 1st Christmas Day (35); 2nd Christmas Day (35); All Saints Day (10); All Saints' Day Holiday (1); Ascension day (10); Assumption of the Virgin Mary (5); Christmas Eve (35); Christmas Holiday (1); Corpus Christi (10); Cyrila a Metodej (20); Day of National Unity (5); Den boje za svobodu a demokracii (20); Den ceske statnosti (20); Den osvobozeni (20); Den vzniku samostatneho ceskoslovenskeho statu (20); Easter Monday (35); Epiphany (6); German Unity Day (10); Good Friday (35); Hungary National Day Holiday (2); Independent Hungary Day (5); International womens day (42); Jan Hus (20); Labour Day (35); Memorial Day for the Martyrs of Arad (5); Memorial Day for the Victims of the Communist Dictatorships (6); Memorial Day for the Victims of the Holocaust (11); Memorial Day of the Republic (6); Memorial day of the 1956 Revolution (5); National Defense Day (5); New Years Day (42); Peace Festival in Augsburg (5); Reformation Day (5); State Foundation Day (5); Whit monday (15); Whit sunday (15); None (12744).
- `warehouse` blank=0, whitespace=0, distinct/normalized lower(trim)=7/7. Values: Brno_1 (1901); Budapest_1 (1901); Frankfurt_1 (1901); Munich_1 (1901); Prague_1 (1901); Prague_2 (1901); Prague_3 (1901).
### sales

| Cột | Null | Null % | Distinct | Âm | Fractional | Zero nếu kiểm tra | Ngoài [0,1] | Nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unique_id | 0 | 0.000000 | 5390 | 0 | 0 | N/A | N/A | 0 |
| date | 0 | 0.000000 | 1402 | N/A | N/A | N/A | N/A | N/A |
| warehouse | 0 | 0.000000 | 7 | N/A | N/A | N/A | N/A | N/A |
| total_orders | 52 | 0.001298 | 7508 | 0 | 0 | 0 | N/A | 0 |
| sales | 52 | 0.001298 | 127279 | 0 | 3918680 | 49207 | N/A | 0 |
| sell_price_main | 0 | 0.000000 | 35723 | 0 | 3968887 | 0 | N/A | 0 |
| availability | 0 | 0.000000 | 100 | 0 | 972208 | N/A | 0 | 0 |
| type_0_discount | 0 | 0.000000 | 17786 | 27 | 145307 | N/A | 27 | 0 |
| type_1_discount | 0 | 0.000000 | 154 | 0 | 2512 | N/A | 0 | 0 |
| type_2_discount | 0 | 0.000000 | 3521 | 0 | 19021 | N/A | 0 | 0 |
| type_3_discount | 0 | 0.000000 | 18 | 0 | 179 | N/A | 0 | 0 |
| type_4_discount | 0 | 0.000000 | 1019 | 1 | 150513 | N/A | 1 | 0 |
| type_5_discount | 0 | 0.000000 | 675 | 0 | 9030 | N/A | 0 | 0 |
| type_6_discount | 0 | 0.000000 | 44658 | 4 | 278798 | N/A | 4 | 0 |

- `warehouse` blank=0, whitespace=0, distinct/normalized lower(trim)=7/7. Values: Brno_1 (643637); Budapest_1 (574582); Frankfurt_1 (198937); Munich_1 (259333); Prague_1 (780566); Prague_2 (770709); Prague_3 (779655).
### inventory

| Cột | Null | Null % | Distinct | Âm | Fractional | Zero nếu kiểm tra | Ngoài [0,1] | Nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unique_id | 0 | 0.000000 | 5432 | 0 | 0 | N/A | N/A | 0 |
| product_unique_id | 0 | 0.000000 | 2670 | 0 | 0 | N/A | N/A | 0 |
| name | 0 | 0.000000 | 2670 | N/A | N/A | N/A | N/A | N/A |
| L1_category_name_en | 0 | 0.000000 | 3 | N/A | N/A | N/A | N/A | N/A |
| L2_category_name_en | 0 | 0.000000 | 47 | N/A | N/A | N/A | N/A | N/A |
| L3_category_name_en | 0 | 0.000000 | 177 | N/A | N/A | N/A | N/A | N/A |
| L4_category_name_en | 0 | 0.000000 | 68 | N/A | N/A | N/A | N/A | N/A |
| warehouse | 0 | 0.000000 | 7 | N/A | N/A | N/A | N/A | N/A |

- `name` blank=0, whitespace=0, distinct/normalized lower(trim)=2670/2668. Values: Apple_0, Apple_1, Apple_10, Apple_100, Apple_101 (mẫu, không phải toàn domain).
- `L1_category_name_en` blank=0, whitespace=0, distinct/normalized lower(trim)=3/3. Values: Bakery (1616); Fruit and vegetable (3282); Meat and fish (534).
- `L2_category_name_en` blank=0, whitespace=0, distinct/normalized lower(trim)=47/47. Values: Bakery_L2_10 (58); Bakery_L2_14 (351); Bakery_L2_18 (80); Bakery_L2_21 (10); Bakery_L2_22 (39); Bakery_L2_24 (9); Bakery_L2_28 (38); Bakery_L2_29 (68); Bakery_L2_34 (18); Bakery_L2_35 (8); Bakery_L2_40 (9); Bakery_L2_44 (4); Bakery_L2_5 (73); Bakery_L2_7 (314); Bakery_L2_8 (188); Bakery_L2_9 (349); Fruit and vegetable_L2_0 (224); Fruit and vegetable_L2_1 (1146); Fruit and vegetable_L2_11 (64); Fruit and vegetable_L2_12 (51); Fruit and vegetable_L2_16 (22); Fruit and vegetable_L2_17 (77); Fruit and vegetable_L2_19 (7); Fruit and vegetable_L2_2 (84); Fruit and vegetable_L2_27 (9); Fruit and vegetable_L2_3 (1362); Fruit and vegetable_L2_30 (91); Fruit and vegetable_L2_31 (8); Fruit and vegetable_L2_33 (5); Fruit and vegetable_L2_36 (7); Fruit and vegetable_L2_37 (16); Fruit and vegetable_L2_39 (10); Fruit and vegetable_L2_4 (20); Fruit and vegetable_L2_41 (2); Fruit and vegetable_L2_42 (3); Fruit and vegetable_L2_43 (2); Fruit and vegetable_L2_45 (8); Fruit and vegetable_L2_6 (64); Meat and fish_L2_13 (287); Meat and fish_L2_15 (97); Meat and fish_L2_20 (13); Meat and fish_L2_23 (14); Meat and fish_L2_25 (51); Meat and fish_L2_26 (59); Meat and fish_L2_27 (5); Meat and fish_L2_32 (5); Meat and fish_L2_38 (3).
- `L3_category_name_en` blank=0, whitespace=0, distinct/normalized lower(trim)=177/177. Values: Bakery_L3_100, Bakery_L3_103, Bakery_L3_104, Bakery_L3_105, Bakery_L3_107 (mẫu, không phải toàn domain).
- `L4_category_name_en` blank=0, whitespace=0, distinct/normalized lower(trim)=68/68. Values: Bakery_L4_1 (1301); Bakery_L4_15 (87); Bakery_L4_27 (25); Bakery_L4_3 (99); Bakery_L4_30 (25); Bakery_L4_40 (28); Bakery_L4_55 (26); Bakery_L4_8 (9); Bakery_L4_9 (16); Fruit and vegetable_L4_0 (10); Fruit and vegetable_L4_1 (2522); Fruit and vegetable_L4_10 (40); Fruit and vegetable_L4_12 (33); Fruit and vegetable_L4_13 (22); Fruit and vegetable_L4_14 (15); Fruit and vegetable_L4_16 (7); Fruit and vegetable_L4_17 (11); Fruit and vegetable_L4_18 (47); Fruit and vegetable_L4_19 (28); Fruit and vegetable_L4_2 (11); Fruit and vegetable_L4_20 (40); Fruit and vegetable_L4_22 (30); Fruit and vegetable_L4_24 (76); Fruit and vegetable_L4_25 (8); Fruit and vegetable_L4_26 (36); Fruit and vegetable_L4_28 (25); Fruit and vegetable_L4_31 (12); Fruit and vegetable_L4_32 (54); Fruit and vegetable_L4_33 (8); Fruit and vegetable_L4_34 (12); Fruit and vegetable_L4_35 (2); Fruit and vegetable_L4_36 (44); Fruit and vegetable_L4_37 (1); Fruit and vegetable_L4_38 (31); Fruit and vegetable_L4_39 (7); Fruit and vegetable_L4_41 (24); Fruit and vegetable_L4_42 (20); Fruit and vegetable_L4_45 (6); Fruit and vegetable_L4_49 (4); Fruit and vegetable_L4_52 (32); Fruit and vegetable_L4_53 (32); Fruit and vegetable_L4_56 (2); Fruit and vegetable_L4_57 (8); Fruit and vegetable_L4_58 (12); Fruit and vegetable_L4_60 (2); Fruit and vegetable_L4_61 (4); Fruit and vegetable_L4_64 (3); Fruit and vegetable_L4_65 (1); Meat and fish_L4_1 (216); Meat and fish_L4_11 (16); Meat and fish_L4_21 (31); Meat and fish_L4_23 (14); Meat and fish_L4_29 (4); Meat and fish_L4_4 (35); Meat and fish_L4_43 (8); Meat and fish_L4_44 (19); Meat and fish_L4_46 (4); Meat and fish_L4_47 (12); Meat and fish_L4_48 (16); Meat and fish_L4_5 (35); Meat and fish_L4_50 (16); Meat and fish_L4_51 (8); Meat and fish_L4_54 (4); Meat and fish_L4_59 (4); Meat and fish_L4_6 (12); Meat and fish_L4_62 (8); Meat and fish_L4_63 (4); Meat and fish_L4_7 (68).
- `warehouse` blank=0, whitespace=0, distinct/normalized lower(trim)=7/7. Values: Brno_1 (763); Budapest_1 (949); Frankfurt_1 (487); Munich_1 (643); Prague_1 (863); Prague_2 (860); Prague_3 (867).
### sales_calendar

| Cột | Null | Null % | Distinct | Âm | Fractional | Zero nếu kiểm tra | Ngoài [0,1] | Nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| date | 0 | 0.000000 | 3288 | N/A | N/A | N/A | N/A | N/A |
| holiday_name | 22086 | 95.959333 | 37 | N/A | N/A | N/A | N/A | N/A |
| holiday | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| shops_closed | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| winter_school_holidays | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| school_holidays | 0 | 0.000000 | 2 | 0 | 0 | N/A | N/A | 0 |
| warehouse | 0 | 0.000000 | 7 | N/A | N/A | N/A | N/A | N/A |

- `holiday_name` blank=0, whitespace=0, distinct/normalized lower(trim)=37/37. Values: 1848 Revolution Memorial Day (Extra holiday) (1); 1st Christmas Day (63); 2nd Christmas Day (63); All Saints Day (18); All Saints' Day Holiday (1); Ascension day (18); Assumption of the Virgin Mary (9); Christmas Eve (63); Christmas Holiday (1); Corpus Christi (18); Cyrila a Metodej (36); Day of National Unity (8); Den boje za svobodu a demokracii (36); Den ceske statnosti (36); Den osvobozeni (36); Den vzniku samostatneho ceskoslovenskeho statu (36); Easter Monday (42); Epiphany (9); German Unity Day (18); Good Friday (42); Hungary National Day Holiday (2); Independent Hungary Day (9); International womens day (63); Jan Hus (36); Labour Day (63); Memorial Day for the Martyrs of Arad (9); Memorial Day for the Victims of the Communist Dictatorships (9); Memorial Day for the Victims of the Holocaust (18); Memorial Day of the Republic (9); Memorial day of the 1956 Revolution (9); National Defense Day (8); New Years Day (63); Peace Festival in Augsburg (6); Reformation Day (9); State Foundation Day (9); Whit monday (27); Whit sunday (27); None (22086).
- `warehouse` blank=0, whitespace=0, distinct/normalized lower(trim)=7/7. Values: Brno_1 (3288); Budapest_1 (3288); Frankfurt_1 (3288); Munich_1 (3288); Prague_1 (3288); Prague_2 (3288); Prague_3 (3288).
### weights

| Cột | Null | Null % | Distinct | Âm | Fractional | Zero nếu kiểm tra | Ngoài [0,1] | Nonfinite |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| unique_id | 0 | 0.000000 | 5390 | 0 | 0 | N/A | N/A | 0 |
| weight | 0 | 0.000000 | 3074 | 0 | 5390 | 0 | N/A | 0 |


Không thấy blank-only hoặc khác whitespace/case làm giảm domain trong các cột chữ.
holiday_name null không tự là lỗi, cần đối chiếu holiday. Các cột date parse được
toàn bộ, không null và invalid_date_count=0. Giá/sales cực trị không tự là outlier sai;
phải xác nhận currency/unit. unique_id=0 không tự loại; sales lẻ phù hợp kg/chiếc.

## 3. Keys, grain và duplicate rows

| Nguồn | Key / grain | Distinct key groups | Null/blank key rows | Duplicate groups | Key excess rows | Full-row excess |
| --- | --- | --- | --- | --- | --- | --- |
| orders | warehouse, date | 7340 | 0 | 0 | 0 | 0 |
| orders_calendar | warehouse, date | 13307 | 0 | 0 | 0 | 0 |
| sales | unique_id, date | 4007419 | 0 | 0 | 0 | 0 |
| inventory | unique_id | 5432 | 0 | 0 | 0 | 0 |
| sales_calendar | warehouse, date | 23016 | 0 | 0 | 0 | 0 |
| weights | unique_id | 5390 | 0 | 0 | 0 | 0 |


Excess=sum(count-1) theo key hay toàn bộ cột tương ứng; distinct key groups bao gồm
nhóm null nếu có (hiện 0 null). Không có duplicate examples vì không có duplicates;
không drop/dedup. Inventory có 5.432 SKU unique_id và 2.670 product_unique_id dùng
chung giữa kho; không dùng product_unique_id thay SKU JOIN Sales. Sales/Inventory
warehouse mismatch=0 trên mọi dòng khớp unique_id.

## 4. Relationships và JOIN validation

Null JOIN keys đều 0 theo bảng keys. Max right multiplicity chỉ tính trên keys
khớp phía LEFT; counts unmatched đã kiểm cả hai phía.

| Left → Right | Keys | LEFT rows | INNER rows | Unmatched left rows/keys | Unmatched right rows/keys | Max L/matched R |
| --- | --- | --- | --- | --- | --- | --- |
| sales → inventory | unique_id | 4007419 | 4007419 | 0/0 | 42/42 | 1402/1 |
| sales → weights | unique_id | 4007419 | 4007419 | 0/0 | 0/0 | 1402/1 |
| sales → sales_calendar | warehouse, date | 4007419 | 4007419 | 0/0 | 14049/14049 | 657/1 |
| orders → orders_calendar | warehouse, date | 7340 | 7340 | 0/0 | 5967/5967 | 1/1 |
| orders → sales | warehouse, date | 3398556 | 3398556 | 0/0 | 608863/1627 | 1/657 |
| orders_calendar → sales_calendar | warehouse, date | 13307 | 13307 | 0/0 | 9709/9709 | 1/1 |


Sales→Inventory/Weights/Calendar là nhiều:1 lookup, không nhân dòng (right unique).
Inventory có 42 SKU không xuất hiện Sales, không tự xoá; lịch dư ngày là coverage
khác, không tự kết luận lỗi FK. Orders→Orders Calendar và calendar overlap là 1:1.
Orders→Sales là 1:n: JOIN trực tiếp nhân 7.340 Orders rows thành 3.398.556 rows,
không được SUM orders trên kết quả SKU. Phải aggregate Sales theo warehouse/date
trước JOIN, có 7.340 cặp khớp. Sales có 1.627 kho-ngày / 608.863 rows ngoài Orders.

## 5. Orders vs Sales gap / order_index

Orders: 2020-12-05→2024-03-15; Sales: 2020-08-01→2024-06-02, cả hai bảy kho.
Overlap=7.340 kho-ngày. Theo v3, đề xuất order_index=MEDIAN(total_orders) trên các
SKU rows cùng warehouse/date, bỏ null; không median DISTINCT hoặc SUM tổng lặp.
Nếu mọi total_orders null phải báo thiếu, không sinh kết quả giả. Chưa tạo cột/bảng thật.
Relative gap=abs(orders-order_index)/abs(orders); denominator=0 bị loại, hiện count=0.
Pearson corr theo kho trên cặp non-null, không gộp xuyên kho.

| Kho | Overlap days | Từ | Đến | Pearson corr | Median abs gap | Median relative gap % |
| --- | --- | --- | --- | --- | --- | --- |
| Brno_1 | 1193 | 2020-12-05 | 2024-03-15 | 0.64509851 | 1101 | 15.904018 |
| Budapest_1 | 1154 | 2020-12-05 | 2024-03-14 | 0.86005467 | 151 | 2.7337016 |
| Frankfurt_1 | 629 | 2022-02-18 | 2024-03-15 | 0.74228642 | 54 | 3.8076152 |
| Munich_1 | 785 | 2021-07-21 | 2024-03-15 | 0.81843325 | 257 | 8.9197225 |
| Prague_1 | 1193 | 2020-12-05 | 2024-03-15 | 0.81131119 | 664 | 7.9698184 |
| Prague_2 | 1193 | 2020-12-05 | 2024-03-15 | 0.69178674 | 422 | 8.3520983 |
| Prague_3 | 1193 | 2020-12-05 | 2024-03-15 | 0.73423948 | 225 | 4.8744094 |

| Kho | Sales days | Ngày nhiều total_orders | Max distinct totals | Từ | Đến |
| --- | --- | --- | --- | --- | --- |
| Brno_1 | 1402 | 1398 | 3 | 2020-08-01 | 2024-06-02 |
| Budapest_1 | 1402 | 1348 | 2 | 2020-08-01 | 2024-06-02 |
| Frankfurt_1 | 855 | 1 | 2 | 2021-12-08 | 2024-06-02 |
| Munich_1 | 1102 | 579 | 2 | 2021-05-20 | 2024-06-02 |
| Prague_1 | 1402 | 1396 | 6 | 2020-08-01 | 2024-06-02 |
| Prague_2 | 1402 | 1398 | 6 | 2020-08-01 | 2024-06-02 |
| Prague_3 | 1402 | 1397 | 5 | 2020-08-01 | 2024-06-02 |

Ví dụ nhiều total_orders cùng key, không phải duplicates key Sales:

| Kho | Ngày | SKU rows | Distinct totals | Min | Max | Median |
| --- | --- | --- | --- | --- | --- | --- |
| Brno_1 | 2020-08-01 | 351 | 2 | 4797 | 4991 | 4797 |
| Brno_1 | 2020-08-02 | 345 | 2 | 4888 | 4919 | 4888 |
| Brno_1 | 2020-08-03 | 349 | 2 | 5201 | 5588 | 5588 |
| Brno_1 | 2020-08-04 | 350 | 2 | 5170 | 5495 | 5170 |
| Brno_1 | 2020-08-05 | 358 | 2 | 4849 | 4928 | 4928 |
| Brno_1 | 2020-08-06 | 359 | 2 | 5090 | 5235 | 5235 |
| Brno_1 | 2020-08-07 | 359 | 2 | 5326 | 5518 | 5326 |


BT1 phải phân biệt orders với order_index; BT4 cần forecast order_index cùng horizon,
không dùng future total_orders thật. BT8 phải chốt chuỗi và định nghĩa ngày mở kho:
ngày Sales đầu tiên ở Frankfurt/Munich sớm hơn Orders, chưa chứng minh ngày khai trương.
Không đọc test Kaggle, không nội suy future actuals hoặc backtest bằng dữ liệu chưa
biết tại as_of. Các input/output BT vẫn cần model owner xác nhận.

## 6. Calendar reconciliation

Orders Calendar 15 cột, Sales Calendar 7; 13.307 keys overlap, Orders-only keys=0,
Sales-only=9.709. DATE/warehouse là keys; năm trường giá trị chung:

| Field | Orders type | Sales type | Null-safe conflict count |
| --- | --- | --- | --- |
| holiday | BIGINT | BIGINT | 0 |
| holiday_name | VARCHAR | VARCHAR | 0 |
| school_holidays | BIGINT | BIGINT | 0 |
| shops_closed | BIGINT | BIGINT | 0 |
| winter_school_holidays | BIGINT | BIGINT | 0 |


Không có conflict examples vì counts=0. Orders-only columns: blackout,
frankfurt_shutdown, mini_shutdown, mov_change, precipitation, shutdown, snow,
warehouse_limited. Sales-only columns: không có.

Mapping đề xuất: outer union warehouse/date → 23.016 keys hiện tại; đồng nhất năm
trường chung sau kiểm tra và giữ provenance. Enrich Orders-only trên phạm vi có
nguồn, không fill 0 ngoài coverage. Không tự chọn precedence: conflict ở snapshot
sau phải review với Planning; schema/mapping cuối vẫn PENDING_CONFIRMATION.

- holiday/name, shops_closed, school/winter holidays có thể known-future nếu lịch
  đã công bố tại as_of, cần version và người xác nhận.
- shutdown/mini/blackout/frankfurt là vận hành quan sát; không dùng future actuals.
- precipitation/snow là thời tiết quan sát, không phải weather forecast.
- mov_change chỉ dùng future nếu pricing schedule đã được duyệt và biết tại as_of.
- warehouse_limited có thật nhưng v3 chưa định nghĩa riêng: PENDING_CONFIRMATION,
  không gộp shutdown, chưa dùng feature tương lai trước xác nhận.

### Coverage theo warehouse

#### orders

| Warehouse | Rows | Min date | Max date |
| --- | --- | --- | --- |
| Brno_1 | 1193 | 2020-12-05 | 2024-03-15 |
| Budapest_1 | 1154 | 2020-12-05 | 2024-03-14 |
| Frankfurt_1 | 629 | 2022-02-18 | 2024-03-15 |
| Munich_1 | 785 | 2021-07-21 | 2024-03-15 |
| Prague_1 | 1193 | 2020-12-05 | 2024-03-15 |
| Prague_2 | 1193 | 2020-12-05 | 2024-03-15 |
| Prague_3 | 1193 | 2020-12-05 | 2024-03-15 |

#### orders_calendar

| Warehouse | Rows | Min date | Max date |
| --- | --- | --- | --- |
| Brno_1 | 1901 | 2019-01-01 | 2024-03-15 |
| Budapest_1 | 1901 | 2019-01-01 | 2024-03-15 |
| Frankfurt_1 | 1901 | 2019-01-01 | 2024-03-15 |
| Munich_1 | 1901 | 2019-01-01 | 2024-03-15 |
| Prague_1 | 1901 | 2019-01-01 | 2024-03-15 |
| Prague_2 | 1901 | 2019-01-01 | 2024-03-15 |
| Prague_3 | 1901 | 2019-01-01 | 2024-03-15 |

#### sales

| Warehouse | Rows | Min date | Max date |
| --- | --- | --- | --- |
| Brno_1 | 643637 | 2020-08-01 | 2024-06-02 |
| Budapest_1 | 574582 | 2020-08-01 | 2024-06-02 |
| Frankfurt_1 | 198937 | 2021-12-08 | 2024-06-02 |
| Munich_1 | 259333 | 2021-05-20 | 2024-06-02 |
| Prague_1 | 780566 | 2020-08-01 | 2024-06-02 |
| Prague_2 | 770709 | 2020-08-01 | 2024-06-02 |
| Prague_3 | 779655 | 2020-08-01 | 2024-06-02 |

#### inventory

| Warehouse | Rows | Min date | Max date |
| --- | --- | --- | --- |
| Brno_1 | 763 | N/A | N/A |
| Budapest_1 | 949 | N/A | N/A |
| Frankfurt_1 | 487 | N/A | N/A |
| Munich_1 | 643 | N/A | N/A |
| Prague_1 | 863 | N/A | N/A |
| Prague_2 | 860 | N/A | N/A |
| Prague_3 | 867 | N/A | N/A |

#### sales_calendar

| Warehouse | Rows | Min date | Max date |
| --- | --- | --- | --- |
| Brno_1 | 3288 | 2016-01-01 | 2024-12-31 |
| Budapest_1 | 3288 | 2016-01-01 | 2024-12-31 |
| Frankfurt_1 | 3288 | 2016-01-01 | 2024-12-31 |
| Munich_1 | 3288 | 2016-01-01 | 2024-12-31 |
| Prague_1 | 3288 | 2016-01-01 | 2024-12-31 |
| Prague_2 | 3288 | 2016-01-01 | 2024-12-31 |
| Prague_3 | 3288 | 2016-01-01 | 2024-12-31 |

## 7. Data quality và khác biệt v3

Availability<1: 972,208/4,007,419 = 24.260203%. Max discount>0: 585,487/4,007,419 = 14.610077%.

| V3 tham khảo | Thực tế / ảnh hưởng |
| --- | --- |
| A2: 7.340 overlap; corr 0,65–0,86; gap 2,7–15,9% | Khớp làm tròn: corr 0,645099–0,860055; relative abs gap 2,733702–15,904018%. orders không bằng total_orders. |
| A2: 6/7 kho có nhiều total_orders | Thực tế 7/7 kho, tổng 7.517 kho-ngày; Frankfurt có đúng 1 ngày. Không bỏ ngoại lệ để khớp v3. |
| C1: 5.390 SKU; E1: Gold 4.007.367 rows | Raw Sales 4.007.419; sales/total_orders mỗi cột null=52; Sales/Weights 5.390 SKU, inventory 5.432. Raw–Gold lệch 52 nhưng chưa có code mẫu chứng minh nguyên nhân drop. |
| C4: 24,3% availability<1; 14,6% giảm giá | Khớp xấp xỉ làm tròn; không phải toàn bộ dữ liệu đã PASS DQ. |
| C4: discount âm, duplicate khi nạp update | type_0 âm 27 cell, type_4 âm 1, type_6 âm 4 (32 cell, chưa cộng thành số dòng). Key/full rows duplicate=0 trong gốc; không kiểm file cập nhật. |
| E1: clip/drop và keep latest | Không áp dụng sửa/loại. Sales âm=0, availability ngoài miền=0; policy precedence/clip cần duyệt. |
| E1: giả định Finance/HR | Không có nguồn thật cost_params/workforce_params; MISSING, giá trị v3 REFERENCE_ONLY. |
| E0/E1: pipeline/dashboard/pred.* có sẵn | Repo chỉ hạ tầng. Giữ CSV Upload→SQLite→DE batch→DuckDB→Parquet; không chạy script mẫu chưa có. |


Cú sốc Munich +23% theo tháng, ngày khai trương thực tế và lịch nghỉ Chủ nhật trong
v3 chưa được coi là xác minh từ min/max: định nghĩa metric/ngày hoạt động cần chốt,
giữ REFERENCE_ONLY/PENDING_CONFIRMATION thay vì tự suy từ ngày có/không có dòng.

## 8. Quyết định và readiness

Cần xác nhận 52 null Sales, 42 inventory-only SKU, warehouse_limited, discount âm,
currency/unit, calendar precedence/known-future, upload key/update policy, nguồn
Finance/HR và notebook/input/output thật BT1–BT8.

**Task 07 Source Registry: READY có điều kiện để soạn registry nháp** từ metadata
đã đo; policy/domain còn mở giữ PENDING_CONFIRMATION, Finance/HR MISSING. Chưa làm Task 07.
**Task 08 Bootstrap đủ 14 Source Tables: NOT READY** để triển khai/phê duyệt đầy đủ:
mapping/key/type/null và các nguồn/chính sách chưa chốt. Không giả Finance/HR.

## 9. Kiểm thử và bảo toàn

10 tests profiling mới PASS; toàn bộ pytest **38 PASS, 0 FAIL** (5,11 giây).
Lỗi development đã sửa: alias SQL cần AS cho value/days, NaN serialization khi
correlation không xác định. Không sửa nguồn để vượt test. Không coi 18/18 của v3
hoặc 26 DQ rule specs là số tests PASS. Baseline SHA-256 sáu CSV, database/backup
và các Data Contract lịch sử được kiểm tra trước/sau tại thời điểm Task 06; kết quả
nghiệm thu khi đó ghi nhận **20 file được bảo toàn, toàn bộ hash khớp**. Workflow này
đã RETIRED sau đó; bằng chứng lịch sử không phải yêu cầu hiện hành. Dictionary đã kiểm
tra đủ 64 cột/6 nguồn, mapping đủ 14 bảng và đúng hai nguồn MISSING; links/anchors/
whitespace và `git diff --check` đạt. Không mở database nghiệp vụ để lấy số liệu profiling.
