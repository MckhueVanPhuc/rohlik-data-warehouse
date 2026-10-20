# **ROHLIK DECISION HUB**

## **PHẦN I – TASK DATA ENGINEERING: XÂY PIPELINE END-TO-END**

### **Hướng dẫn triển khai đã điều chỉnh theo quyết định của nhóm · Local-first · Bản bàn giao để xây dựng**

**Ngày cập nhật:** 21/10/2026  
 **Tài liệu nền:** Rohlik\_Decision\_Hub\_Huong\_dan\_xay\_dung\_he\_thong\_chi\_tiet(1).md, chỉ phần **PHẦN I**.  
 **Tính chất:** tài liệu triển khai mục tiêu, **không phải xác nhận rằng toàn bộ code đã chạy trong repository hiện tại**.

**QUYẾT ĐỊNH ĐÃ CHỐT:** Hoàn thành toàn bộ Data Engineering pipeline trên máy local trước. Chỉ sử dụng **5 CSV Kaggle gốc \+ 2 CSV giả định Finance/HR**, tạo **14 bảng nghiệp vụ tại 9 schema landing**, dùng **DuckDB trực tiếp** làm cả kho phân tích lẫn nơi tiếp nhận cập nhật từ Streamlit (**không dùng SQLite làm tầng nhập liệu**). Giữ kiến trúc **src\_\* → stg → core → mart → pred/meta**, bộ điều phối và cơ chế STUB/FINAL của V4. MotherDuck / GitHub Actions / Streamlit Cloud để giai đoạn sau.

**Phạm vi:** Nội dung của phần này dành cho Data Engineer. Phần Model Training/Colab và Dashboard trong file nguồn là các task riêng; chỉ trích dẫn khi cần chỉ rõ hợp đồng, phụ thuộc và cách nghiệm thu dữ liệu.

### **Cách đọc và đối chiếu tình trạng**

> > •           **\[GIỮ V4\]**: yêu cầu/hợp đồng/cấu trúc gốc phù hợp, chỉ đổi chỗ cần thiết.

> > •           **\[SỬA V4\]**: thay đổi đã chốt hoặc sửa lỗi thiết kế/rủi ro của V4.

> > •           **\[CẦN TRIỂN KHAI\]**: module/kiểm thử mong đợi, **chưa được xem là tồn tại trong repository** chỉ vì có code minh họa trong tài liệu.

> > •           **\[CHỜ BT CONFIRM\]**: khác biệt giữa Data Contract V4 và notebook/handoff/model card thật của BT1–BT8; chưa tự ý thay đổi kết quả khoa học.

### **Bảng quyết định không thay đổi trong toàn bộ tài liệu**

| Hạng mục | Quy định sau điều chỉnh |
| :---- | :---- |
| Triển khai | VS Code \+ .venv Python 3.13 \+ DuckDB local \+ DBeaver; Streamlit local khi UI hoàn thành |
| Nguồn đang hoạt động | 5 CSV Kaggle (orders/train.csv, sales/sales\_train.csv, sales/inventory.csv, sales/calendar.csv, sales/test\_weights.csv) \+ 2 params (assumptions/cost\_params.csv, assumptions/workforce\_params.csv) |
| Ngoài phạm vi pipeline chính | orders/train\_calendar.csv; nếu đã có trong bootstrap lịch sử thì **giữ nguyên** để truy vết, nhưng không dùng downstream V4 |
| Landing nghiệp vụ | **14 bảng** thuộc 9 phòng ban; không tạo bảng thứ 15 |
| Tầng ELT | src\_\* (landing) → stg (clean) → core (integrated) → mart (views) |
| Nhập liệu | Streamlit CSV upload/preview/confirm → **INSERT trực tiếp DuckDB** \+ audit **trong cùng transaction** |
| Dữ liệu gốc và rerun | CSV read-only, landing không bị init ghi đè khi đã có cập nhật; undo là **vô hiệu hóa lô** \+ audit, không xóa lịch sử |
| Mô hình | frames.py \+ output contract \+ 8 STUB; cắm FINAL sau khi hợp đồng được chốt |
| Dữ liệu dự báo | **14 bảng pred theo output contract \+ 2 bảng history \= 16**, không phải “16 \+ 2” |
| Online | Hoãn; không phải điều kiện nghiệm thu giai đoạn local |
| Parquet | Không bắt buộc để đạt V4 local. Có thể bổ sung snapshot sau, chỉ khi nhóm chốt yêu cầu đó |

## **I.1. Kiến trúc pipeline**

### **I.1.1. Mục tiêu và ranh giới hệ thống**

**\[GIỮ V4\]** Pipeline sử dụng kiến trúc ELT: extract/load dữ liệu vào DuckDB, transform bằng SQL trong kho, đưa dữ liệu qua các tầng, cung cấp đầu vào cho 8 mô hình và hiển thị qua dashboard. Hợp đồng đầu vào/đầu ra giúp nhóm Training và Dashboard phát triển song song.

**\[SỬA V4\]** Triển khai và nghiệm thu **local**. DuckDB là **database vật lý duy nhất cho pipeline và việc nhập dữ liệu**. Không đồng bộ qua SQLite; SQLite helper từng chuẩn bị trong repository có thể giữ làm mã hạ tầng không sử dụng, nhưng không xuất hiện trên critical path.

5 Kaggle CSV (read-only)    	2 Finance/HR params (ASSUMED)  
          	\\                     	/  
       	Source Registry / Data Contract / Preflight  
                         	|  
      	DuckDB local: 14 src\_\* landing nghiệp vụ  
                         	^  
                         	|  
          	Streamlit local CSV upload  
        	\[preview → validate → confirm\]  
           	→ INSERT \+ audit (1 transaction)  
                         	|  
                	stg (14 bảng sạch)  
                         	|  
             	core (facts/dims/params)  
                         	|  
                 	mart (5 views)  
                         	|  
           	frames.SCHEMA (F) → BT1...BT8  
                         	|  
            	    pred (14 \+ 2 hist)  
                         	|  
             	Streamlit local Dashboard

 meta: source lineage / batch events / DQ / pipeline\_runs / model\_registry  
 pipeline/run.py: init → refresh → models → all / evaluate / status

**Lưu ý kiến trúc local:** Khi Streamlit, DBeaver và pipeline là các tiến trình độc lập, DuckDB file không cho nhiều tiến trình cùng ghi tự do. Cần tổ chức **một writer** tại một thời điểm, khóa có owner/run ID, thao tác ghi ngắn, đóng kết nối sớm và hướng dẫn người dùng khi database đang bận. Retry không thay thế cơ chế điều phối ghi.

### **I.1.2. Chức năng từng schema**

| Schema | Thành phần ghi | Nội dung và số lượng | Nguyên tắc sau điều chỉnh |
| :---- | :---- | :---- | :---- |
| src\_sales, src\_marketing, src\_ops, src\_category, src\_planning, src\_digital, src\_external, src\_finance, src\_hr | ingest.py, entry.py | **14 bảng nghiệp vụ / 9 phòng ban** | Ghi bản mới theo batch; giữ lịch sử và metadata; không làm mất dữ liệu nhập khi rerun |
| stg | transform.stg() | **14 bảng** bản ghi có hiệu lực | Theo business key, chọn phiên bản đang active; xử lý ngoại lệ theo DQ policy, không tự ý sửa số liệu |
| core | transform.core() | fct\_warehouse\_day, fct\_sku\_day, dim\_product, dim\_warehouse, params\_cost, params\_workforce | Một tầng phân tích dùng chung, JOIN đúng grain, không nhân dòng |
| mart | transform.marts() | 5 view: sales\_orders\_day, ops\_warehouse\_day, category\_sku\_day, marketing\_promo\_day, exec\_kpi\_month | View nghiệp vụ, hạn chế cột theo nhu cầu |
| pred | pipeline/run.py | 14 bảng đầu ra \+ fc\_orders\_hist, fc\_sku\_hist | Kiểm output contract trước khi commit, có run\_id, model\_status |
| meta | ingest/entry/transform/models | entry\_log, batch\_status\_events, quality\_report, data\_freshness, pipeline\_runs, model\_registry, lineage | Audit là bản ghi sự kiện bất biến; log không chứa bí mật |

### **I.1.3. Sáu quy tắc vận hành bắt buộc**

> > 1\.         **Raw bất biến**: CSV gốc được dùng làm evidence; không sửa, không tái tạo test\_weights thành giả định; không cắt lịch sử ngầm đến một ngày demo.

> > 2\.         **init an toàn**: chỉ khởi tạo khi kho chưa có tập dữ liệu nguồn tương ứng hoặc tải nguồn theo idempotency key; tuyệt đối **không** tự CREATE OR REPLACE bảng landing đã có cập nhật. Nếu cần reset phải backup và xác nhận rõ, dùng database thử nghiệm.

> > 3\.         **Nhập liệu append-only**: bản mới có \_batch\_id, \_source, \_loaded\_at, \_entered\_by; người dùng không được chạy SQL tự do để ghi trực tiếp.

> > 4\.         **Undo mềm (logical undo)**: gắn trạng thái UNDONE cho batch, ghi event; stg bỏ qua batch đã bị undo; lịch sử landing không bị xóa vật lý.

> > 5\.         **Transaction thống nhất**: INSERT của batch \+ ghi meta.entry\_log/trạng thái \+ kiểm tra đồng thời phải nằm trong một transaction DuckDB; lỗi thì rollback cả batch.

> > 6\.         **Chặn khi lỗi**: khi DQ/Output Contract có lỗi mức ERROR, dừng bước sau và không quảng bá kết quả như hợp lệ. WARN có thể tiếp tục nếu được mô tả trong policy.

### **I.1.4. Phân biệt điều kiện đã chốt và vấn đề cần quyết định thêm**

Đã chốt kiến trúc local \+ direct DuckDB \+ 7 nguồn \+ 14 bảng. **Chưa chốt ở cấp model**: kết quả pred thật từ notebook BT1–BT8 có khớp toàn bộ output\_contract.yaml của V4 hay chưa; các cột liên quan phân vị (đặc biệt BT4), giả định giá/nhân sự và các đơn vị phải được model owner xác nhận trước khi khóa contract FINAL.

## **I.2. Thành phần chi tiết của pipeline**

### **I.2.1. Cấu trúc dự án mục tiêu (giữ thiết kế module V4, thích nghi repository đã có)**

rohlik-data-warehouse/           	\# repo hiện có, không cần tạo repo mới  
 ├── .gitignore  
 ├── README.md  
 ├── requirements.txt  
 ├── config/  
 │   ├── sources.yaml             	\# registry/evidence Task 07–08A hiện có  
 │   ├── settings.yaml            	\# mục tiêu theo V4, local-first  
 │   ├── contract.yaml            	\# 14 bảng nghiệp vụ \+ mapping  
 │   ├── output\_contract.yaml     	\# 14 outputs models – pending BT approval  
 │   ├── pipeline.yaml            	\# requires / produces / enabled của BT1–BT8  
 │   ├── models.yaml              	\# config từng mô hình  
 │   └── roles.yaml               	\# quyền đọc và nhập liệu  
 ├── src/ ...                     	\# hạ tầng hiện có: db, bootstrap, profiling, tests  
 ├── rohlik/ ...                  	\# module logic V4 sẽ được triển khai/cải biên  
 │   ├── config.py  db.py  frames.py  features.py  security.py  
 │   ├── de/ ingest.py transform.py quality.py entry.py contracts.py  
 │   └── models/ bt1.py ... bt8.py   \# STUB trước, FINAL sau  
 ├── pipeline/run.py              	\# orchestrator mục tiêu  
 ├── scripts/check\_model.py swap\_models.py  
 ├── templates/bt\_template.py stubs/  
 ├── app/ main.py common.py views/	\# phối hợp task Dashboard; local first  
 ├── docs/ ...              	      \# contracts, source mapping, nhật ký thay đổi  
 ├── tests/ ...                   	\# test hiện có \+ tests mới  
 ├── data/  
 │   ├── raw/orders/train.csv  
 │   ├── raw/sales/sales\_train.csv inventory.csv calendar.csv test\_weights.csv  
 │   ├── raw/assumptions/cost\_params.csv workforce\_params.csv  
 │   ├── warehouse/rohlik\_bootstrap\_dev.duckdb  \# chỉ thử nghiệm Task 08A  
 │   └── warehouse/rohlik.duckdb             	\# kho đích chính thức local  
 └── outputs/logs/ .run.lock backups/

**\[SỬA V4\]** Tên repository/đường dẫn thực tế **giữ theo dự án đang dùng**, không bắt buộc đổi repo hoặc copy nguyên rohlik\_decision\_hub\_v4.zip vào main. Có thể giữ src/ cho hạ tầng và thêm rohlik//pipeline/ theo V4; **không tạo hai implementation song song cho cùng một chức năng**. Cần quyết định ranh giới import nhất quán ở PR triển khai.

**.gitignore bắt buộc:** .venv/, data/raw/, data/warehouse/, data/exports/, outputs/, .env, .streamlit/secrets.toml, dữ liệu upload, snapshot cá nhân. Không commit secrets hoặc CSV nhạy cảm.

### **I.2.2. Bảng mô tả module và mức tái sử dụng**

| Thành phần | Vai trò giữ từ V4 | Điều chỉnh đã chốt |
| :---- | :---- | :---- |
| config/settings.yaml | Database, raw paths, forecast horizon, SKU scope | Local DuckDB mặc định, Python 3.13; không buộc runner: github |
| config/sources.yaml | Source evidence từ Task 07/08A | Cập nhật **5 Kaggle \+ 2 params active**; orders calendar được lưu historical-only, không active |
| config/contract.yaml | 14 bảng nghiệp vụ, file/columns/keys/editable/checks | Fix count 14, mapping HR tiếng Việt, DQ policy cho raw và nhập liệu |
| rohlik/config.py | Đọc cấu hình và đường dẫn dự án | Tương thích repo hiện có, không trông đợi .env online |
| rohlik/db.py | Kết nối DuckDB, query, exists, write, new\_id | **Local-first**; quản lý read/write, lock \+ transaction, backup; MotherDuck ở future plan |
| rohlik/de/ingest.py | CSV → 14 landing | **Không overwrite landing khi rerun**, chống tải trùng theo nguồn/hash, provenance |
| rohlik/de/transform.py | stg → core → mart | Chỉ đọc batch active, xử lý NULL/raw anomalies có kiểm định, giữ logic facts/dims V4 |
| rohlik/de/quality.py | 14 duplicate checks \+ 7 checks bổ sung | Gắn severity, bổ sung checks cho 2 params/loại anomaly, không khẳng định pass trước khi chạy |
| rohlik/de/entry.py | CSV/template/validate/append/undo | **Ghi trực tiếp DuckDB**, SQL INSERT \+ log cùng transaction, soft undo, role checks |
| rohlik/frames.py | Tạo 6 DataFrames F, load\_raw/load\_warehouse | Chốt cùng SCHEMA V4; kiểm raw/warehouse chỉ trong tình trạng tương đương |
| rohlik/de/contracts.py | Bắt lỗi model outputs | Không chấp nhận bảng chưa có contract; không tự ép/round dữ liệu gây mất nghĩa |
| config/pipeline.yaml, 8 STUB | Điều phối phụ thuộc BT1–BT8 | Giữ 8 bước, STUB có model\_status=stub; khớp output contract đã xác nhận |
| pipeline/run.py | init / refresh / models / all / evaluate / status | Tách khởi tạo nguồn và refresh; lock an toàn; rollback/atomic publish hợp lý |
| rohlik/security.py | Roles và SQL explorer | Không dùng regex đơn thuần như ranh giới an ninh; backend whitelist tables/query \+ read-only |
| tests/ | Test source, input, updates, model, permissions | Thêm rerun/undo/transaction/lock/null/params/quality/E2E trên DB tạm |
| app/ | Streamlit dashboard theo V4 | Chạy local, không buộc cloud, UI gọi service được cấp quyền thay vì SQL ghi tùy ý |

### **I.2.3. Môi trường thực thi**

| Thành phần | Giai đoạn hiện tại | Tương lai (không nằm trong nghiệm thu local) |
| :---- | :---- | :---- |
| Data Warehouse | data/warehouse/rohlik.duckdb trong máy local | MotherDuck nếu nhóm chọn triển khai online |
| Pipeline | VS Code terminal, python \-m pipeline.run ... | GitHub Actions/scheduler |
| Database GUI | DBeaver để kiểm tra SQL; tránh giữ writer kết nối khi pipeline chạy | GUI online nếu cần |
| Dashboard | Streamlit localhost:8501 | Streamlit Cloud hoặc host khác |
| Training | Google Colab hoặc local tùy thành viên, handoff CSV | Cắm các file FINAL |
| Testing | Pytest \+ DuckDB temp database, test trên snapshot an toàn | CI sau nghiệm thu |

### **I.2.4. Ranh giới Task 08A → V4 chính thức**

Repository hiện đã có Task 08A: rohlik\_bootstrap\_dev.duckdb chứa **6 Bronze \+ 12 projections provisional** (kể cả train\_calendar.csv), Source Registry, profiling và DQ cơ bản. Đây **không** phải 14 bảng landing chính thức và **chưa** phải stg/core/mart.

Lộ trình thích nghi: (1) giữ nguyên file bootstrap thử nghiệm; (2) chỉ định 7 nguồn active, cập nhật schema/mapping; (3) tạo database chính thức riêng, hoặc chuyển dữ liệu được xác minh bằng bước promotion có test; (4) xây 14 landing \+ stg/core/mart; (5) chỉ được xem là hoàn thành khi có log và E2E test trên warehouse chính thức. Không ghi đè bootstrap hay database populated đang có.

## **I.3. Luồng dữ liệu – lần theo một bản ghi qua pipeline**

**\[GIỮ V4\]** Ví dụ sản phẩm **Pomelo\_2**, unique\_id=2647, kho Prague\_1, ngày 2024-02-15 minh họa đường đi của một dòng Sales. Những giá trị minh họa dưới đây được **trích từ ví dụ V4**; không mặc định sẽ giống khi nạp nguyên bộ Kaggle bạn đang giữ (không cắt lịch sử theo V4).

### **Chặng 1 — CSV lịch sử (read-only)**

Ví dụ V4: sales/sales\_train.csv chứa unique\_id=2647, date=2024-02-15, warehouse=Prague\_1, sales=1482.6, sell\_price\_main=58.15, availability=0.89, type\_0\_discount=0.33721. Một dòng nguồn có thể cung cấp dữ liệu cho Sales, Marketing và Operations. File này không được edit trực tiếp.

### **Chặng 2 — Landing (ingest.py \+ contract.yaml)**

| Bảng | Business fields minh họa | Provenance |
| :---- | :---- | :---- |
| src\_sales.sku\_sales\_daily | unique\_id, date, warehouse, sales, total\_orders | \_batch\_id, \_source, \_loaded\_at, \_entered\_by |
| src\_marketing.prices | unique\_id, date, sell\_price\_main | Các trường provenance tương tự |
| src\_marketing.promotions | unique\_id, date, 7 mức discount | Các trường provenance tương tự |
| src\_ops.availability | unique\_id, date, availability | Các trường provenance tương tự |

Giai đoạn ingest chỉ **chọn và chuẩn hóa kiểu cột**, gắn lineage, kiểm tra bản ghi; không sửa doanh số, giá/khuyến mãi hay tự lấp NULL. init ghi nguồn lịch sử **một lần theo source fingerprint**, không được làm mất các bản nhập về sau.

### **Chặng 3 — Người dùng nhập CSV trực tiếp vào DuckDB**

Ví dụ Operations tải template, nhập availability mới cho cùng khóa (2647, 2024-02-15) rồi xác nhận. Backend kiểm tra quyền, file, khóa, kiểu và miền giá trị. Nếu hợp lệ: một DuckDB transaction INSERT dòng mới vào src\_ops.availability, INSERT log và trạng thái batch. Mọi record là **đầy đủ các cột nghiệp vụ của bảng**; trường trống không được mặc định là yêu cầu giữ giá trị cũ nếu contract chưa định nghĩa patch semantics.

Nếu người dùng Undo, backend **ghi sự kiện hủy batch**, không DELETE vật lý khỏi landing. Bản cập nhật được loại khỏi tập active khi refresh; bản lịch sử cũ trở lại nếu còn hiệu lực.

### **Chặng 4 — stg: chọn bản hợp lệ đang hoạt động và làm sạch có kiểm soát**

stg giữ một record/khóa từ tập batch active theo \_loaded\_at và tie-break ổn định. Không âm thầm kẹp discount âm thành 0, gán NULL thành 0 hoặc loại dòng doanh số âm mà không giữ bằng chứng. Các phép chuẩn hóa được quyết định trong DQ policy: ERROR, WARN, quarantine hoặc biến đổi được chủ dữ liệu chấp thuận.

### **Chặng 5 — core: bảng tích hợp dùng chung**

**\[GIỮ V4\]** Sáu bảng chính:

> > •           core.dim\_product nối danh mục sản phẩm \+ SKU weights; không hiểu weight là kg hoặc giá vốn (đây là trọng số dùng đánh giá, theo định nghĩa nguồn).

> > •           core.params\_cost đưa cost\_ratio, shelf\_life\_days, waste\_handling\_cost\_ratio lên mô hình.

> > •           core.params\_workforce chứa tham số HR canonical \+ các tham số bổ sung đã mapping; giữ dấu ASSUMED trong metadata.

> > •           core.fct\_sku\_day nối sales, prices, promotions, availability, category và calendar; tính max\_discount, final\_price khi dữ liệu đủ điều kiện.

> > •           core.fct\_warehouse\_day kết hợp orders và order\_index, lịch, vận hành, thời tiết và thông tin hoạt động người dùng.

> > •           core.dim\_warehouse mô tả 7 kho và thông số liên quan.

Ví dụ V4 về final\_price: 58.15 × (1 − 0.33721) ≈ 38.54. Đây là **công thức và giá trị minh họa**, không thay thế các bước kiểm tra giá/discount thật trong bộ nguồn.

### **Chặng 6 — mart: 5 view theo phòng ban**

Giữ nguyên ý nghĩa 5 views V4: sales\_orders\_day, ops\_warehouse\_day, category\_sku\_day, marketing\_promo\_day, exec\_kpi\_month. Mart đọc Core đã được kiểm định và chỉ công bố trường được cấp quyền.

### **Chặng 7 — frames.SCHEMA: tạo input F cho mô hình**

F \= {wh\_day, calendar, sku\_day, sku\_plan, params\_cost, params\_workforce}. Colab có frames.load\_raw(), pipeline có frames.load\_warehouse(); hai phương thức phải đồng nhất schema và ý nghĩa cột **ở cùng phạm vi dữ liệu/phiên bản, trước khi có chỉnh sửa riêng trong warehouse**. Không áp điều kiện “mọi thời điểm raw \== warehouse” sau khi đã có upload thủ công.

### **Chặng 8 — BT1–BT8 → pred → dashboard**

8 mô hình có run(F, cfg, reg) trả DataFrame theo config/output\_contract.yaml; STUB chỉ chứng minh luồng hoạt động, **không phải kết quả khoa học**. Sau validation, ghi 14 bảng pred và 2 bảng \_hist theo thiết kế đã duyệt. Dashboard Streamlit **local** đọc mart/pred/meta bằng quyền thích hợp. Nếu kết quả đến từ STUB, UI phải hiển thị cảnh báo rõ ràng.

### **Dòng chảy khi cập nhật/ngắt sự cố**

| Tình huống | Hệ thống bắt buộc làm gì |
| :---- | :---- |
| Upload lỗi header/key/kiểu/quyền | Trả lỗi theo dòng/cột; không ghi một phần khi policy chưa cho phép |
| Upload hợp lệ | INSERT \+ entry log trong một DuckDB transaction; batch status ACTIVE |
| Upload trùng | Nhận diện hash/key theo policy; không nhân đôi một batch do retry |
| refresh | stg → core → mart → DQ, không nạp lại raw và không tự chạy models |
| init rerun | Phát hiện raw đã ingest; no-op hoặc từ chối có giải thích; không thay landing populated |
| DQ FAIL | Dừng trước models; không thông báo bộ số liệu mới đã đạt |
| Undo | Ghi event UNDONE, stg bỏ batch; lịch sử raw+landing vẫn còn |
| Mô hình lỗi | Giữ bản pred trước đó; không publish kết quả dở dang của bước lỗi |

**Khác V4 gốc:** Không dùng số liệu/duration mẫu từ bản “tạo lại raw trên Hugging Face” để cam kết thời gian hoặc row count trên 5 CSV Kaggle thực tế; số liệu nghiệm thu phải đo bằng log và profiler của repo bạn.

## **I.4. Nguyên tắc triển khai và trình tự xây dựng**

**\[GIỮ V4\]** Xây từ dưới lên, kiểm ngay sau mỗi tầng. Những nguyên tắc ELT, config-driven, contracts, idempotency, lineage, DQ, observability, locks, secrets, mô-đun hóa và pytest tiếp tục áp dụng.

| Nguyên tắc | Cách hiện thực theo thiết kế cuối cùng |
| :---- | :---- |
| Tách tầng | Raw → src\_\* → stg → core → mart → F → pred |
| Config-driven | sources.yaml, settings.yaml, contract.yaml, pipeline.yaml, models.yaml, roles.yaml |
| Bảo toàn raw | Các CSV gốc bất biến; fingerprint nguồn; không sửa/test\_weights giả |
| Idempotent | init nhận diện nguồn đã nạp; append retry không tạo batch trùng; refresh deterministic |
| Provenance \+ audit | \_batch\_id, \_source, \_loaded\_at, \_entered\_by \+ meta.entry\_log \+ meta.batch\_status\_events |
| Transaction | Ghi landing \+ audit cùng transaction; lỗi rollback hoàn toàn |
| DQ gate | Mỗi kiểm tra có severity; ERROR dừng run và log chi tiết |
| Model plug-in | frames.SCHEMA, pipeline.yaml, output\_contract.yaml, 8 STUB/FINAL |
| Observability | meta.pipeline\_runs, quality\_report, data\_freshness, model\_registry, file logs |
| Writer coordination | Một tiến trình ghi DuckDB tại một thời điểm; lock và đóng connection; không hi vọng DuckDB file hoạt động như DB server đa writer |
| Secrets và query safety | .env/Streamlit secrets ignored; roles kiểm server-side; SQL explorer read-only/allowlist |
| Kiểm thử | Unit \+ integration \+ end-to-end trên database tạm; backup trước migrate |

**Thứ tự triển khai tối ưu:** (0) setup/nhận diện repo → (1) chốt schema 14 bảng \+ tham số HR → (2) DuckDB local → (3) preflight 7 nguồn → (4) landing an toàn → (5) stg/core/mart → (6) DQ → (7) frames → (8) output contract → (9) 8 STUB → (10) orchestrator → (11) direct entry/undo → (12) roles/query → (13) model integration tools → (14) test → (15) chuẩn bị cloud nhưng chưa triển khai → (16) local acceptance.

**Quy tắc phát triển:** mỗi PR ghi rõ bảng, grain, keys, source, loại migration và test tương ứng. Khi thay đổi Data Contract, cập nhật cùng lúc code transform, frames, docs, DQ và test; không thay tên cột âm thầm.

## **I.5. Hướng dẫn triển khai chi tiết theo Bước 0–16**

**Quan trọng:** Lệnh và interface trong các bước dưới đây là **mục tiêu triển khai** theo V4 đã điều chỉnh. Ở repository hiện tại, src.bootstrap\_sources đã có; pipeline.run và nhiều module V4 khác chưa được xác minh là tồn tại. **Không chạy lệnh mục tiêu trước khi tạo code và test.**

### **Bước 0\. Môi trường Python, repository và thư mục**

**Mục đích \[GIỮ V4\]:** chuẩn bị Python, venv, dependencies, cấu trúc package; cùng một môi trường chạy lại được. **\[SỬA V4\]** Không tạo repo mới, sử dụng repo đã tồn tại; Python 3.13 (ở máy đang ghi nhận 3.13.15), không yêu cầu hạ xuống 3.10–3.12 khi không có lỗi thực tế.

**Trên PowerShell (ở project root):**

.\\.venv\\Scripts\\python.exe \--version  
 .\\.venv\\Scripts\\python.exe \-m pip install \-r requirements.txt  
 .\\.venv\\Scripts\\python.exe \-m pip check  
 .\\.venv\\Scripts\\python.exe \-m pytest \-q  
 git status \--short

Nếu chưa có .venv, tạo bằng bản Python 3.13 đã cài rồi trong VS Code chọn Python: Select Interpreter → .venv\\Scripts\\python.exe. Các thư viện V4 gồm DuckDB, pandas, pyarrow, pyyaml, scikit-learn, lightgbm, statsmodels, PuLP, Streamlit, pytest… **phải kiểm thử thực tế trên Python 3.13** trước khi chốt phiên bản; đừng chép nguyên version range V4 mà chưa chạy thử.

**Sản phẩm:** interpreter thống nhất; requirements.txt được kiểm soát phiên bản; .gitignore bảo vệ DB/raw/secrets. **Kiểm tra:** unit test hiện có pass; không có .env, raw hay .duckdb trong git ls-files.

### **Bước 1\. Chốt config/settings.yaml, contract.yaml, sources.yaml**

**Mục đích:** làm hợp đồng duy nhất trước khi viết transform, entry và model. **\[GIỮ V4\]** settings.yaml chọn kho, raw, 14-day horizon, phạm vi SKU. **\[SỬA V4\]** mọi lệnh local dùng đường dẫn DuckDB vật lý.

*\# config/settings.yaml – ví dụ mục tiêu (local only)*  
 warehouse: data/warehouse/rohlik.duckdb  
 raw\_dir: data/raw  
 horizon\_days: 14  
 sku\_scope:  
   warehouses: \[Prague\_1\]  
   train\_from: "2022-06-01"  
 runner: local  
 source\_mode: kaggle\_original

**14 bảng nghiệp vụ trong V4**: giữ nguyên các bảng sau, không thêm bảng thứ 15\.

| Phòng ban/schema | Bảng nghiệp vụ | Raw CSV |
| :---- | :---- | :---- |
| Sales src\_sales | orders\_daily, sku\_sales\_daily | orders/train.csv, sales/sales\_train.csv |
| Marketing src\_marketing | prices, promotions, mov\_changes | Sales CSV, Orders CSV |
| Warehouse src\_ops | availability, ops\_events | Sales CSV, Orders CSV |
| Category src\_category | product\_master | sales/inventory.csv |
| Planning src\_planning | calendar | sales/calendar.csv |
| Digital src\_digital | user\_activity | orders/train.csv |
| External src\_external | weather | orders/train.csv |
| Finance src\_finance | sku\_weights, cost\_params | sales/test\_weights.csv, assumptions/cost\_params.csv |
| HR src\_hr | workforce\_params | assumptions/workforce\_params.csv |

**Hợp đồng contract.yaml – giữ nguyên mapping 13 bảng V4; sửa bảng HR theo các cột thực tế.** Trích định nghĩa từ V4 đã chỉnh tên cột:

orders\_daily: 	{schema: src\_sales, 	raw: {file: orders/train.csv, columns: \[warehouse, date, orders\]},   
                	keys: \[warehouse, date\], editable: \[orders\], checks: {orders: {min: 0}}}   
 sku\_sales\_daily:  {schema: src\_sales, 	raw: {file: sales/sales\_train.csv, columns: \[unique\_id, date, warehouse, sales, total\_orders\]},   
                	keys: \[unique\_id, date\], editable: \[sales, total\_orders\], checks: {sales: {min: 0}, total\_orders: {min: 0}}}   
 prices:       	{schema: src\_marketing, raw: {file: sales/sales\_train.csv, columns: \[unique\_id, date, sell\_price\_main\]},   
                	keys: \[unique\_id, date\], editable: \[sell\_price\_main\], checks: {sell\_price\_main: {min: 0.01}}}   
 promotions:   	{schema: src\_marketing, raw: {file: sales/sales\_train.csv, columns: \[unique\_id, date, type\_0\_discount, type\_1\_discount, type\_2\_discount, type\_3\_discount, type\_4\_discount, type\_5\_discount, type\_6\_discount\]},   
                	keys: \[unique\_id, date\], editable: \[type\_0\_discount, type\_1\_discount, type\_2\_discount, type\_3\_discount, type\_4\_discount, type\_5\_discount, type\_6\_discount\],   
                	checks: {"\*": {min: 0, max: 1}}}   
 mov\_changes:  	{schema: src\_marketing, raw: {file: orders/train.csv, columns: \[warehouse, date, mov\_change\]},   
                	keys: \[warehouse, date\], editable: \[mov\_change\], checks: {mov\_change: {min: 0, max: 1}}}   
 availability: 	{schema: src\_ops,   	raw: {file: sales/sales\_train.csv, columns: \[unique\_id, date, availability\]},   
                	keys: \[unique\_id, date\], editable: \[availability\], checks: {availability: {min: 0, max: 1}}}   
 ops\_events:   	{schema: src\_ops,   	raw: {file: orders/train.csv, columns: \[warehouse, date, shutdown, mini\_shutdown, blackout, frankfurt\_shutdown\]},   
                	keys: \[warehouse, date\], editable: \[shutdown, mini\_shutdown, blackout, frankfurt\_shutdown\], checks: {"\*": {min: 0, max: 1}}}   
 product\_master:   {schema: src\_category,  raw: {file: sales/inventory.csv, columns: \[unique\_id, product\_unique\_id, name, L1\_category\_name\_en, L2\_category\_name\_en, L3\_category\_name\_en, L4\_category\_name\_en, warehouse\]},   
                	keys: \[unique\_id\], editable: \[name, L1\_category\_name\_en, L2\_category\_name\_en, L3\_category\_name\_en, L4\_category\_name\_en, warehouse\]}   
 calendar:     	{schema: src\_planning,  raw: {file: sales/calendar.csv, columns: \[warehouse, date, holiday\_name, holiday, shops\_closed, winter\_school\_holidays, school\_holidays\]},   
                	keys: \[warehouse, date\], editable: \[holiday\_name, holiday, shops\_closed, winter\_school\_holidays, school\_holidays\]}   
 user\_activity:	{schema: src\_digital,   raw: {file: orders/train.csv, columns: \[warehouse, date, user\_activity\_1, user\_activity\_2\]},   
                	keys: \[warehouse, date\], editable: \[user\_activity\_1, user\_activity\_2\], checks: {"\*": {min: 0}}}   
 weather:      	{schema: src\_external,  raw: {file: orders/train.csv, columns: \[warehouse, date, precipitation, snow\]},   
                	keys: \[warehouse, date\], editable: \[precipitation, snow\], checks: {"\*": {min: 0}}}   
 sku\_weights:  	{schema: src\_finance,   raw: {file: sales/test\_weights.csv, columns: \[unique\_id, weight\]},   
                	keys: \[unique\_id\], editable: \[weight\], checks: {weight: {min: 0}}}   
 cost\_params:  	{schema: src\_finance,   raw: {file: assumptions/cost\_params.csv, columns: \[L1\_category\_name\_en, cost\_ratio, shelf\_life\_days, waste\_handling\_cost\_ratio\]},   
                	keys: \[L1\_category\_name\_en\], editable: \[cost\_ratio, shelf\_life\_days, waste\_handling\_cost\_ratio\]}   
 workforce\_params:  
   schema: src\_hr  
   raw:  
 	file: assumptions/workforce\_params.csv  
 	columns:  
   	\- warehouse  
   	\- {hourly\_wage\_eur: wage\_eur\_per\_hour}  
   	\- items\_per\_order  
   	\- picks\_per\_hour  
   	\- shift\_hours  
   	\- {morning\_shift\_ratio: morning\_share}  
   	\- overtime\_multiplier  
   	\- {overtime\_cap\_ratio: overtime\_cap}  
   	\- {shortage\_penalty\_multiplier: shortage\_penalty}  
   	\- {legacy\_rule\_buffer\_ratio: rule\_buffer}  
   	\- orders\_per\_driver\_shift  
   keys: \[warehouse\]  
   editable: \[hourly\_wage\_eur, items\_per\_order, picks\_per\_hour, shift\_hours,  
          	morning\_shift\_ratio, overtime\_multiplier, overtime\_cap\_ratio,  
          	shortage\_penalty\_multiplier, legacy\_rule\_buffer\_ratio, orders\_per\_driver\_shift\]  
   *\# bổ sung vào contract chính thức: types / nullable / allowed ranges / source\_type ASSUMED*

**Cách dùng hợp đồng:** schema là schema đích, raw.file là đường dẫn tương đối từ data/raw, raw.columns hỗ trợ {tên\_chuẩn: tên\_file\_csv}, keys quy định grain, editable là cột được người dùng phép nhập, checks là miền hợp lệ. Cần **bổ sung rõ data types, required/nullable, schema\_version, update\_policy** trước khi dùng cho uploader; contract V4 nguyên thủy chưa đầy đủ các chính sách này.

**Mapping HR theo file CSV mới** (11 header snake\_case tiếng Anh; UTF-8 **không BOM**, đã đối chiếu trực tiếp file):

| Header trong CSV hiện tại | Tên canonical trong V4 | Ý nghĩa / cách xử lý |
| :---- | :---- | :---- |
| warehouse | warehouse | Kho, business key — giữ nguyên |
| wage\_eur\_per\_hour | hourly\_wage\_eur | Đổi tên; lương EUR/giờ |
| items\_per\_order | items\_per\_order | Món/đơn — giữ nguyên |
| picks\_per\_hour | picks\_per\_hour | Món/giờ — giữ nguyên |
| shift\_hours | shift\_hours | Giờ/ca — giữ nguyên |
| morning\_share | morning\_shift\_ratio | Đổi tên; tỷ lệ phân bổ ca sáng |
| overtime\_multiplier | overtime\_multiplier | Hệ số lương làm thêm — giữ nguyên |
| overtime\_cap | overtime\_cap\_ratio | Đổi tên; trần tỷ lệ làm thêm |
| shortage\_penalty | shortage\_penalty\_multiplier | Đổi tên; hệ số phạt thiếu công suất |
| rule\_buffer | legacy\_rule\_buffer\_ratio | Đổi tên; hệ số đệm quy tắc cũ |
| orders\_per\_driver\_shift | orders\_per\_driver\_shift | Đơn/ca tài xế — giữ nguyên |

**Quy tắc xuyên suốt:** ingest.py và frames.load\_raw() đọc **header CSV mới** rồi đổi 5 tên khi tạo dữ liệu canonical; stg.workforce\_params, core.params\_workforce, templates upload, Data Quality và mọi API trong pipeline dùng **tên canonical**. Sáu header đã khớp thì giữ nguyên. Không đổi ngược canonical API của V4 thành tên CSV, vì sẽ làm lệch BT2 và các downstream contracts.

cost\_params.csv có 3 ngành và bốn cột gốc: L1\_category\_name\_en, cost\_ratio, shelf\_life\_days, waste\_handling\_cost\_ratio. workforce\_params.csv có 7 kho và 11 cột gốc tiếng Anh. **Cả hai là ASSUMED**; log nguồn/phê duyệt/phiên bản trong registry, không coi như chi phí/nhân sự thực tế. test\_weights.csv không phải thông số chi phí và không phải kilogram.

**Bất nhất cần tránh:** Source Registry của Task 07/08A vẫn ghi MISSING Finance/HR; khi triển khai thì cập nhật registry/validator, mapping và unit tests **trong cùng một PR**, chỉ đổi trạng thái sau khi kiểm tra file nguồn và nghiệm thu ingestion. Source Registry còn có 6 Kaggle CSV từ Task 08A; **đánh dấu train\_calendar.csv là historical-only/inactive**, giữ evidence nếu đã tồn tại.

**Kiểm tra kết thúc Bước 1:** Parse YAML thành công; đúng 14 logical tables và 7 unique active file paths; tất cả cột gốc của 7 CSV được tìm thấy; mọi tên cột trong frames.SCHEMA có đường đi về nguồn/transform; test mapping HR pass.

### **Bước 2\. Đọc cấu hình và kết nối DuckDB local**

**\[GIỮ V4\]** config.py có settings(), path(); db.py có connect(), query(), exists(), write(), new\_id(). **\[SỬA V4\]** Local-first: database đích nằm trong data/warehouse/rohlik.duckdb, không tự động tạo MotherDuck database. Dùng read\_only=True cho luồng chỉ đọc; ghi theo writer lock.

*\# MINH HỌA giao diện, không thay thế module db.py đầy đủ*  
 from pathlib import Path  
 import duckdb

 WAREHOUSE \= Path("data/warehouse/rohlik.duckdb")

 def connect\_local(\*, read\_only=False):  
 	if read\_only and not WAREHOUSE.exists():  
     	raise FileNotFoundError(WAREHOUSE)  
 	if not read\_only:  
     	WAREHOUSE.parent.mkdir(parents=True, exist\_ok=True)  
 	return duckdb.connect(str(WAREHOUSE), read\_only=read\_only)

**Quy tắc writer:** thao tác ghi của Streamlit và CLI phải đi qua service chung/lock dùng được giữa tiến trình. Nếu DuckDB đang bị writer khác giữ khóa thì đưa ra thông báo, có retry giới hạn và timeout. Không để model training giữ write transaction trong thời gian dài. Backup .duckdb khi chuẩn bị migration/reset; không sao chép database file tùy ý khi còn kết nối ghi đang hoạt động.

**Kiểm tra:** mở DB tạm \+ SELECT 42 \+ đóng kết nối; DBeaver truy vấn read-only; test trường hợp hai writer để đảm bảo hệ thống xử lý xung đột minh bạch.

### **Bước 3\. Chuẩn bị 7 CSV đầu vào thật**

**\[SỬA V4\]** Không dùng script scripts/prepare\_raw.py của V4 để tải bản thay thế từ Hugging Face, cắt lịch sử đến 01/03/2024 hay sinh test\_weights.csv giả. Bộ dữ liệu nguồn của nhóm **đã có**, giữ read-only, sao chép vào đúng vị trí sau (nếu chưa đặt):

data/raw/orders/train.csv  
 data/raw/sales/sales\_train.csv  
 data/raw/sales/inventory.csv  
 data/raw/sales/calendar.csv  
 data/raw/sales/test\_weights.csv  
 data/raw/assumptions/cost\_params.csv  
 data/raw/assumptions/workforce\_params.csv

Không đưa orders/train\_calendar.csv vào pipeline V4. Nếu file đã hiện diện, có thể giữ trong thư mục lịch sử/Task 08A; không thêm vào contract.yaml hay frames.SCHEMA và không biến thành bảng thứ 15\.

**Preflight bắt buộc:** tồn tại file, checksum SHA-256, byte size, encoding/BOM, header, cột bắt buộc, định dạng ngày, kiểu/nullable, khóa, số dòng, trùng khóa, miền tham số; đặc biệt HR yêu cầu đúng 11 header tiếng Anh mới, không tìm các header tiếng Việt cũ; ghi evidence vào docs/source\_registry.md hoặc báo cáo. Không nạp sales\_train.csv 4+ triệu dòng qua pandas chỉ để bootstrap. Để test giới hạn tài nguyên, DuckDB trực tiếp read\_csv với explicit types đã profile.

**Thông tin thực tế từ file HR mới:** 7 dòng dữ liệu, 11 cột; thứ tự header: warehouse, wage\_eur\_per\_hour, items\_per\_order, picks\_per\_hour, shift\_hours, morning\_share, overtime\_multiplier, overtime\_cap, shortage\_penalty, rule\_buffer, orders\_per\_driver\_shift. Không còn header tiếng Việt/BOM. Không sửa bộ header này khi lưu file raw.

**Số lượng dữ liệu quan sát từ Task 08A** (để đối chiếu nguồn, **không phải số liệu runtime V4**): Orders train.csv 7.340 dòng, Sales sales\_train.csv 4.007.419 dòng, Inventory 5.432 dòng, Calendar 23.016 dòng, Weights 5.390 dòng. Hai Params lần lượt 3 và 7 dòng. Nếu thay file phiên bản khác phải tính và duyệt fingerprint mới.

**Kiểm tra kết thúc:** source\_registry xác nhận 7 active inputs và 14 contracts; riêng HR khớp đúng 11 header UTF-8 không BOM với 5 tên cần rename; không có hành động ghi nào lên raw; log hashes có thể đối chiếu sau này.

### **Bước 4\. Ingest 7 nguồn vào 14 bảng landing – an toàn khi rerun**

**\[GIỮ V4\]** Ingest sử dụng contract.yaml để tách các cột của cùng một CSV thành nhiều bảng src\_\*; mỗi dòng có \_batch\_id, \_source, \_loaded\_at, \_entered\_by. **\[SỬA V4\]** Không dùng lệnh CREATE OR REPLACE TABLE để ghi đè landing khi init chạy lại.

**Thiết kế bắt buộc:**

> > 1\.         Validator đối chiếu nguồn với contract và fingerprint; không sửa raw.

> > 2\.         Nếu bảng chưa có: tạo table đúng schema và cột metadata; ingest lịch sử từ file.

> > 3\.         Nếu cùng source fingerprint đã ingest thành công: đánh dấu NO\_OP và không thêm dòng hoặc xóa dữ liệu tay.

> > 4\.         Nếu dữ liệu nguồn đổi: từ chối/thực hiện một migration có phiên bản, kế hoạch backup và phê duyệt riêng, không tự thay tất cả bảng.

> > 5\.         Ghi sự kiện batch/system ingest \+ hash, row counts, status bằng transaction/atomic batch policy.

> > 6\.         Sau ingest kiểm số dòng và key coverage, không claim 14 nguồn vật lý (chỉ **7 file vật lý → 14 logical landing**).

*\-- PSEUDOCODE SQL: tạo schema/table bằng DDL từ contract (không copy chạy nguyên bản)*  
 BEGIN TRANSACTION;  
 *\-- assert source\_hash chưa ingest; insert full projected rows into src\_sales.orders\_daily*  
 *\-- insert ingest metadata, source lineage, row counts for batch*  
 COMMIT;

**Ánh xạ 5 header tại ingestion (minh họa trong preflight/ingest adapter):**

HR\_HEADER\_MAPPING \= {  
     "wage\_eur\_per\_hour": "hourly\_wage\_eur",  
 	"morning\_share": "morning\_shift\_ratio",  
 	"overtime\_cap": "overtime\_cap\_ratio",  
 	"shortage\_penalty": "shortage\_penalty\_multiplier",  
 	"rule\_buffer": "legacy\_rule\_buffer\_ratio",  
 }  
 *\# Source Registry kiểm tra header CSV gốc; landing chỉ ghi tên canonical.*  
 *\# Rename phải xảy ra trước khi validator downstream so schema.*

**Rủi ro V4 đã sửa:** CREATE OR REPLACE TABLE src\_x.t AS SELECT ... khi init lại sẽ làm mất records do phòng ban nhập trước đó. Vì vậy quy tắc idempotency phải kiểm source fingerprints, không “replace cho chắc”. **Khuyến nghị:** database rohlik\_bootstrap\_dev.duckdb thuộc Task 08A không được auto-reset hoặc làm nơi nhập liệu thật.

**Kiểm tra kết thúc:** 14 bảng tồn tại; Finance/HR có 3/7 dòng sau mapping; src\_hr.workforce\_params có đủ 11 cột canonical và không sót tên header CSV nguồn; chạy ingest lần hai báo NO\_OP; upload trước đó vẫn còn; không tạo bảng thứ 15\.

### **Bước 5\. Biến đổi src\_\* → stg → core → mart (rohlik/de/transform.py)**

**\[GIỮ V4\]** Giữ ba hàm stg(con), core(con), marts(con) và sáu bảng Core, năm view Mart. Phương pháp ELT bằng SQL phù hợp với DuckDB local. **\[SỬA V4\]** Thay logic bản mới nhất một cách an toàn, không tùy tiện COALESCE/clip dữ liệu gốc bất thường.

**Tầng stg** thực hiện theo thứ tự: (1) chỉ đọc batch active; (2) loại khóa NULL theo chính sách được phê duyệt và báo lỗi; (3) chuẩn hóa kiểu dữ liệu/canonical columns; (4) quyết định record đang có hiệu lực cho từng business key; (5) lưu thống kê bản ghi bị loại/cảnh báo; (6) không sửa raw. V4 có 14 bảng stg tương ứng 14 bảng src\_\*.

*\-- SQL MINH HỌA cho một bảng; triển khai riêng theo catalog/keys đã validate.*  
 CREATE OR REPLACE TABLE stg.availability AS  
 SELECT \* EXCLUDE (rn)  
 FROM (  
   SELECT l.\*,  
      	row\_number() OVER (  
        	PARTITION BY unique\_id, date  
        	ORDER BY \_loaded\_at DESC, \_batch\_id DESC  
      	) AS rn  
   FROM src\_ops.availability AS l  
   LEFT JOIN meta.entry\_log AS b ON b.batch\_id \= l.\_batch\_id  
   WHERE COALESCE(b.status, 'ACTIVE') \= 'ACTIVE'  
 	AND unique\_id IS NOT NULL AND date IS NOT NULL  
 )  
 WHERE rn \= 1;

**Lưu ý với SQL minh họa:** triển khai thật phải dùng một bảng/truy vấn trạng thái batch **duy nhất và nhất quán**, xử lý cả system-ingest batches đã hoàn tất, chống lặp entry\_log theo batch và tách trạng thái lịch sử với trạng thái hiện hành. Nếu sử dụng batch\_status\_events, cần lấy sự kiện mới nhất theo batch; không nối trực tiếp vào toàn bộ lịch sử event vì sẽ nhân dòng. Không chạy DDL CREATE OR REPLACE khi dashboard đang đọc trong trạng thái publication chưa nhất quán; tổ chức staging/temp+swap hoặc transaction phù hợp, có kiểm thử.

**Tại sao sửa V4 gốc?** V4 dùng row\_number() ... ORDER BY \_loaded\_at hợp lý cho sửa bản ghi, nhưng undo\_batch() lại xóa khỏi landing. Khi nhóm đã chọn nguồn landing có lịch sử, cách chuẩn là **soft undo**: batch UNDONE bị loại khỏi stg mà dữ liệu gốc vẫn có thể truy vết.

**Tầng core** giữ thiết kế V4:

| Bảng core | Grain / nội dung | Nguồn chính |
| :---- | :---- | :---- |
| core.dim\_product | 1 SKU-kho theo unique\_id; category L1–L4, tên, weight | stg.product\_master, stg.sku\_weights |
| core.dim\_warehouse | 1 kho, 7 kho; dates \+ HR params | stg.orders\_daily, core.params\_workforce |
| core.params\_cost | 1 ngành hàng L1 | stg.cost\_params |
| core.params\_workforce | 1 kho, đủ 11 tham số canonical HR đã mapping | stg.workforce\_params |
| core.fct\_sku\_day | 1 unique\_id,date, sales/price/discount/availability/category/calendar | stg SKU sales, prices, promotions, availability, product\_master, calendar |
| core.fct\_warehouse\_day | 1 warehouse,date, orders, order\_index, calendar, ops, digital, weather | stg orders, calendar, ops, mov\_changes, user\_activity, weather; tổng hợp SKU |

Định nghĩa V4 cần **giữ đúng**: order\_index là trung vị total\_orders theo kho/ngày từ Sales (không phải orders thực của Orders competition); max\_discount là giá trị lớn nhất trong 7 loại giảm giá đã xác minh; final\_price \= sell\_price\_main × (1 − max\_discount) chỉ tính khi dữ liệu hợp lệ. **Không tự suy luận** weight là trọng lượng sản phẩm; đây là trọng số dự đoán/chấm điểm.

**SQL projection canonical cho HR (minh họa sau khi ingest đã rename):**

CREATE OR REPLACE TABLE core.params\_workforce AS  
 SELECT warehouse, hourly\_wage\_eur, items\_per\_order, picks\_per\_hour, shift\_hours,  
    	morning\_shift\_ratio, overtime\_multiplier, overtime\_cap\_ratio,  
    	shortage\_penalty\_multiplier, legacy\_rule\_buffer\_ratio,  
    	orders\_per\_driver\_shift  
 FROM stg.workforce\_params;

**Không bỏ 4 tham số bổ sung chỉ vì frames.SCHEMA V4 hiện cung cấp 7 cột cho BT2.** Tầng core bảo toàn toàn bộ 11 cột canonical; tầng frames chỉ chiếu 7 cột theo hợp đồng mô hình cho đến khi chủ mô hình xác nhận cần thêm.

**Điểm sửa cần xử lý rõ tại tầng Core:** nếu raw sales\_train.csv có NULL hoặc mức giảm giá ngoài \[0,1\], không dùng COALESCE(...,0) và LEAST/GREATEST âm thầm rồi coi như dữ liệu đúng. Chốt data policy theo chủ dữ liệu: (a) raw giữ nguyên; (b) DQ báo anomaly; (c) core chỉ tính KPI/feature khi hợp lệ, hoặc áp dụng fallback có tài liệu và flag. Tương tự, không xóa dòng sales \< 0 khỏi stg mà thiếu rejected-record log.

**Tầng mart** giữ 5 view V4, không sao chép dữ liệu:

| View | Đọc từ | Vai trò |
| :---- | :---- | :---- |
| mart.sales\_orders\_day | core.fct\_warehouse\_day | Sales/E-commerce |
| mart.ops\_warehouse\_day | core.fct\_warehouse\_day | Warehouse Ops |
| mart.category\_sku\_day | core.fct\_sku\_day | Category/Demand Planning |
| mart.marketing\_promo\_day | core.fct\_sku\_day | Marketing/Pricing |
| mart.exec\_kpi\_month | core.fct\_warehouse\_day | Executive KPI |

Cập nhật meta.data\_freshness theo đúng 14 bảng nguồn, không dùng 15\. Kiểm tra sau Bước 5: khóa unique đúng grain; số ngày/kho được đối chiếu với source; 5 views tồn tại; không có JOIN nhân dòng; Finance/HR params lên core đúng kiểu; stg loại được bản ghi bị soft undo mà không xóa landing.

### **Bước 6\. Kiểm định chất lượng (rohlik/de/quality.py)**

**\[GIỮ V4\]** Có run\_checks(con) xuất meta.quality\_report và **21 kiểm tra nền**: 14 kiểm tra trùng business key trong từng bảng stg, cộng 7 kiểm tra chuyên biệt được định nghĩa trong V4. Cần giữ lỗi mức ERROR làm cổng chặn trước khi chạy mô hình.

| Nhóm | Số kiểm tra V4 | Nội dung | Chính sách |
| :---- | ----: | :---- | :---- |
| Unique business key | 14 | Không trùng key sau staging ở 14 bảng | ERROR |
| Product coverage | 1 | SKU bán có trong product\_master | ERROR |
| Giá bán | 1 | Price \<= 0 không hợp lệ | ERROR |
| Số đơn | 1 | Orders âm | ERROR |
| Calendar coverage | 1 | Sales day thiếu calendar | WARN hoặc ERROR theo mục tiêu |
| Freshness kho | 1 | Kho chưa có Orders ngày mới nhất | WARN |
| Availability coverage | 1 | Sales thiếu availability | WARN hoặc ERROR theo model |
| Horizon calendar | 1 | Calendar chưa phủ 14 ngày dự báo | WARN hoặc ERROR theo model |
| **Tổng nền** | **21** | 14 \+ 7 | Ghi cả PASS/WARN/FAIL |

**\[SỬA V4\]** 21/21 OK không nên mặc định là trạng thái bắt buộc trên dữ liệu Kaggle gốc trước khi kiểm tra: dữ liệu source có anomalies được Task 06/08A ghi nhận. Cần lưu cả số WARN, các exception có chủ đích và chính sách được phê duyệt; **không hạ ERROR xuống WARN chỉ để cho pipeline qua**. Những kiểm tra như NULL sales/total\_orders, discount âm, completeness của Params, key-coverage, schema-version, batch integrity nên **bổ sung ngoài 21 kiểm tra nền** nếu cần, vì nhóm đã có nguồn thực tế khác nguồn mẫu của V4.

**Bổ sung kiểm tra bắt buộc cho Params:** cost\_params có 3 L1, không trùng, 0\<=cost\_ratio\<=1, shelf\_life\_days\>0, waste\_handling\_cost\_ratio\>=0; HR có 7 warehouses, hourly\_wage\_eur\>0, items\_per\_order\>0, picks\_per\_hour\>0, shift\_hours\>0, morning\_shift\_ratio và overtime\_cap\_ratio trong \[0,1\], overtime\_multiplier\>=1, các tham số phạt hợp lệ. **Kiểm tra đơn vị chứ không chỉ miền số học**.

**Kết quả tối thiểu:** các cột check\_id, table, severity, observed, threshold, status, run\_id, checked\_at, reason trong báo cáo DQ (nếu schema V4 chỉ có check,value,level,status thì có thể thêm metadata song không phá giao diện mà Dashboard cần). Các violation ERROR phải có minh chứng để truy lại hàng nguồn/batch.

**Kiểm tra sau bước:** chạy DQ trên DB tạm \+ dữ liệu lỗi tự tạo, chứng minh pipeline **dừng đúng** ở ERROR và tạo WARN minh bạch cho cảnh báo. Không ghi “21/21 OK” vào báo cáo nếu chưa chạy thật.

### **Bước 7\. Hợp đồng đầu vào mô hình (rohlik/frames.py)**

**\[GIỮ V4\]** Cơ chế frames.SCHEMA, conform(), load\_raw(), load\_warehouse() và sáu khung dữ liệu. Với CSV 7 nguồn đã chốt, mọi trường hợp load\_raw đều đọc Sales Calendar, **không đọc train\_calendar.csv**. params\_workforce trong F hiện chỉ yêu cầu 7 cột từ V4; các trường HR bổ sung được giữ ở source/core để model BT2 có thể sử dụng nếu xác nhận từ notebook.

**Bộ SCHEMA gốc V4 (giữ tên cột/ý nghĩa hiện có):**

DISC \= \[f"type\_{i}\_discount" for i in range(7)\]   
 CAL \= \["holiday", "shops\_closed", "school\_holidays", "winter\_school\_holidays"\]   
 SCHEMA \= {   
 	"wh\_day": \["warehouse", "date", "orders", "order\_index"\] \+ CAL,   
 	"calendar": \["warehouse", "date"\] \+ CAL,   
 	"sku\_day": \["unique\_id", "date", "warehouse", "sales", "total\_orders", "sell\_price\_main"\] \+ DISC \+   
            	\["max\_discount", "final\_price", "availability", "L1", "L2", "L3", "weight"\] \+ CAL,   
 	"sku\_plan": \["unique\_id", "date", "warehouse", "sell\_price\_main"\] \+ DISC \+ \["max\_discount", "final\_price", "L1", "L2", "L3", "weight"\] \+ CAL,   
 	"params\_cost": \["L1", "cost\_ratio", "shelf\_life\_days", "waste\_handling\_cost\_ratio"\],   
 	"params\_workforce": \["warehouse", "hourly\_wage\_eur", "items\_per\_order", "picks\_per\_hour", "shift\_hours",   
                      	"overtime\_multiplier", "orders\_per\_driver\_shift"\],   
 }

**Chức năng 6 khung dữ liệu F:**

| Tên khung | Mục đích | Nguồn từ warehouse |
| :---- | :---- | :---- |
| wh\_day | Chuỗi quá khứ kho-ngày cho BT1/BT8; orders, order\_index, lịch | core.fct\_warehouse\_day với ngày có lịch sử |
| calendar | Feature tương lai biết trước 14 ngày | core.fct\_warehouse\_day theo calendar |
| sku\_day | SKU lịch sử phục vụ BT3–BT7 | core.fct\_sku\_day có sales, theo SKU scope |
| sku\_plan | Giá/khuyến mãi kế hoạch tương lai do Marketing nhập | core.fct\_sku\_day với future price/plan |
| params\_cost | Cost, shelf-life, waste assumptions | core.params\_cost |
| params\_workforce | Wage, productivity, shift, driver assumptions | core.params\_workforce |

**\[SỬA V4\]** frames.load\_raw() phải áp dụng đúng 5 đổi tên HR như contract.yaml (không thể đọc pd.read\_csv() rồi đưa nguyên header mới vào conform() vì thiếu hourly\_wage\_eur). Việc conform chỉ giữ những cột trong SCHEMA không có nghĩa dữ liệu HR bổ sung nên bị xóa khỏi Warehouse. Cột có thể ở core.params\_workforce, nhưng nếu BT2/BT6 cần dùng thì phải sửa SCHEMA **theo quyết định của model owner** và điều chỉnh cả load\_raw, load\_warehouse cùng test. Không tự chèn những cột mà V4/notebook không dùng vào hợp đồng cố định ngay.

**Quan trọng với parity test:** load\_raw \== load\_warehouse áp dụng khi cùng nguồn/phiên bản, phạm vi, transformation, và trước khi nhập dữ liệu bổ sung. Khi người dùng đã cập nhật DuckDB, raw-vs-warehouse cần cho phép khác **đúng nơi phát sinh cập nhật**, thay vì coi tất cả khác biệt là lỗi. Các phép so phải xét dtype, sort/grain, null semantics, row count và giá trị số học với tolerance hợp lý.

**Kiểm tra:** cả sáu F có đủ cột/kiểu/grain; frames.load\_raw() thực hiện rename CSV→canonical trước conform(); các trường calendar đều đến từ sales/calendar.csv, Finance/HR có 3/7 logical keys; load\_raw/load\_warehouse parity trên fixture clean và đường cập nhật đúng trên fixture edited.

### **Bước 8\. Hợp đồng đầu ra \+ kiểm định (config/output\_contract.yaml, rohlik/de/contracts.py)**

**\[GIỮ V4\]** Output Contract định nghĩa **14 bảng kết quả nghiệp vụ mô hình** (không phải 16; 2 bảng lịch sử là \*\_hist do orchestrator tạo thêm). Bộ kiểm bắt thiếu cột, kiểu dữ liệu, trùng key, giá trị âm không được phép và các ràng buộc như p90 \>= p50.

**Bản 14 output specifications theo V4 (để đối chiếu trong giai đoạn STUB):**

fc\_orders:      	{cols: {warehouse: str, date: date, series: str, p50: num, p90: num, model: str}, keys: \[series, warehouse, date\],   
                  	nonneg: \[p50, p90\], checks: \["p90 \>= p50 \- 1e-6", "series in ('orders', 'order\_index')"\]}   
 staff\_plan:     	{cols: {warehouse: str, date: date, shift: str, staff: int, policy: str, cost\_eur: num}, keys: \[warehouse, date, shift\], nonneg: \[staff, cost\_eur\]}   
 driver\_plan:    	{cols: {warehouse: str, date: date, orders\_p50: num, orders\_p90: num, orders\_per\_driver\_shift: num, drivers\_needed: int}, keys: \[warehouse, date\], nonneg: \[drivers\_needed\]}   
 lost\_sales:     	{cols: {unique\_id: int, date: date, warehouse: str, L1: str, sales: num, availability: num, final\_price: num, est\_demand: num, lost\_units: num, lost\_revenue: num},   
                  	keys: \[unique\_id, date\], nonneg: \[est\_demand, lost\_units\], checks: \["est\_demand \>= sales \- 1e-6"\]}   
 lost\_sales\_summary: {cols: {warehouse: str, L1: str, stockout\_days\_share: num, revenue: num, lost\_revenue: num, "lost\_%\_of\_revenue": num}, keys: \[warehouse, L1\]}   
 lost\_sales\_monthly: {cols: {warehouse: str, L1: str, month: date, revenue: num, lost\_revenue: num}, keys: \[warehouse, L1, month\]}   
 fc\_sku:         	{cols: {unique\_id: int, date: date, warehouse: str, L1: str, final\_price: num, p\_point: num, p20: num, p30: num, p40: num, p50: num,   
                         	p60: num, p70: num, p80: num, p90: num, model: str, price\_source: str, order\_index\_source: str},   
                  	keys: \[unique\_id, date\], nonneg: \[p20, p50, p90\], checks: \["p90 \>= p50 \- 1e-6", "p50 \>= p20 \- 1e-6"\]}   
 promo\_effect:   	{cols: {L1: str, discount: num, "lift\_%": num, "ci\_low\_%": num, "ci\_high\_%": num}, keys: \[L1, discount\]}   
 promo\_type\_effect:  {cols: {promo\_type: str, theta: num}, keys: \[promo\_type\]}   
 replenishment:  	{cols: {unique\_id: int, date: date, warehouse: str, L1: str, final\_price: num, p50: num, order\_qty: num, policy: str}, keys: \[unique\_id, date\], nonneg: \[order\_qty\]}   
 markdown\_plan:  	{cols: {unique\_id: int, date: date, L1: str, discount: num, stock: num, expiring\_today: num, expected\_waste: num}, keys: \[unique\_id, date\],   
                  	checks: \["discount \>= 0", "discount \<= 0.5"\]}   
 markdown\_summary:   {cols: {policy: str, gross\_margin: num}, keys: \[policy\]}   
 growth\_curves:  	{cols: {warehouse: str, month: date, t: num, orders: num}, keys: \[warehouse, month\]}   
 growth\_projection:  {cols: {warehouse: str, t: num, fitted: num, model: str}, keys: \[warehouse, t\]}

| BT | Bảng dự báo/kết quả phải tạo |
| :---- | :---- |
| BT1 | fc\_orders |
| BT2 | staff\_plan, driver\_plan |
| BT3 | lost\_sales, lost\_sales\_summary, lost\_sales\_monthly |
| BT4 | fc\_sku |
| BT5 | promo\_effect, promo\_type\_effect |
| BT6 | replenishment |
| BT7 | markdown\_plan, markdown\_summary |
| BT8 | growth\_curves, growth\_projection |

**\[CHỜ BT CONFIRM\]** Đây là **contract mục tiêu tham khảo V4**, chưa được tự động xem là output thật của tất cả notebook nhóm đang làm. Ví dụ BT4 trong hồ sơ bàn giao trước từng dùng p10/p50/p90, còn V4 yêu cầu p20...p90 và p\_point. **Không tự suy ra phân vị còn thiếu** hoặc coi như chúng được mô hình huấn luyện. Model owner và Dashboard phải cùng chốt schema chính thức trước khi khóa STUB/FINAL interface.

**Các thay đổi an toàn cần có trong contracts.py:**

> > 1\.         **Không silently accept unknown output name**: nếu tên bảng không có trong output\_contract.yaml thì phải ERROR; code V4 gốc if spec is None: return df, \[\] chưa đủ chặt.

> > 2\.         **Không làm tròn kiểu int tùy ý**: số 2.7 không được âm thầm .round().astype(int) thành 3 nếu contract yêu cầu integer thật.

> > 3\.         Check một số ràng buộc phân vị theo cặp (p20 ≤ p30 ≤ … ≤ p90) nếu xác định trong contract; tránh check sơ sài chỉ p20, p50, p90.

> > 4\.         Kiểm null theo từng cột; kiểm dtype/enum, range, grain và mốc thời gian dự báo.

> > 5\.         Chỉ ghi kết quả đã qua validation, bên trong transaction của một bước mô hình; không ghi dở một tập produces.

**Kiểm tra:** test thiếu bảng, thiếu cột, tên sai, dtype sai, key trùng, phân vị nghịch, NaN, số âm, forecast horizon/warehouse, các trường metadata.

### **Bước 9\. Cấu hình pipeline \+ 8 STUB (config/pipeline.yaml, rohlik/models/)**

**\[GIỮ V4\]** Tên module, requires, produces, enabled, hai bảng lịch sử; 8 mô hình là các plug-in có cùng chữ ký run(F,cfg,reg). Bản STUB đơn giản phục vụ mục tiêu **kiểm tra luồng dữ liệu**, không dùng làm kết luận kinh doanh.

**Danh sách bước theo V4:**

steps:   
   \- {id: bt1, name: "Dự báo số đơn",              module: rohlik.models.bt1, requires: \[\],                                     	produces: \[fc\_orders\],                                      	enabled: true}   
   \- {id: bt2, name: "Xếp ca kho & tài xế",    	module: rohlik.models.bt2, requires: \[fc\_orders\],                            	produces: \[staff\_plan, driver\_plan\],                        	enabled: true}   
   \- {id: bt3, name: "Nhu cầu bị mất",         	module: rohlik.models.bt3, requires: \[\],                                     	produces: \[lost\_sales, lost\_sales\_summary, lost\_sales\_monthly\], enabled: true}   
   \- {id: bt4, name: "Dự báo SKU",             	module: rohlik.models.bt4, requires: \[fc\_orders, lost\_sales\],                	produces: \[fc\_sku\],                                         	enabled: true}   
   \- {id: bt5, name: "Hiệu ứng giảm giá",      	module: rohlik.models.bt5, requires: \[\],                                     	produces: \[promo\_effect, promo\_type\_effect\],                	enabled: true}   
   \- {id: bt6, name: "Lượng đặt hàng",         	module: rohlik.models.bt6, requires: \[fc\_sku, lost\_sales\],                   	produces: \[replenishment\],                                  	enabled: true}   
   \- {id: bt7, name: "Giảm giá hàng sắp hết hạn",  module: rohlik.models.bt7, requires: \[fc\_sku, promo\_effect, replenishment\],  	produces: \[markdown\_plan, markdown\_summary\],                	enabled: true}   
   \- {id: bt8, name: "Tăng trưởng kho mới",    	module: rohlik.models.bt8, requires: \[\],                                     	produces: \[growth\_curves, growth\_projection\],               	enabled: true}   
 history: \[fc\_orders, fc\_sku\]      	*\# các bảng được lưu thêm lịch sử (pred.\<bảng\>\_hist) để đo độ chính xác dự báo*

| BT | Ý tưởng STUB V4 | Quy tắc khi chưa có FINAL |
| :---- | :---- | :---- |
| BT1 | Seasonal naive cùng ngày thứ tuần trước, P90 khoảng 1.1×P50 | model\_status=stub, không dùng để lập kế hoạch thật |
| BT2 | Nhân công theo P50/số món/năng suất; tài xế theo P90 | Ghi giả định và đơn vị, không công bố savings thật |
| BT3 | Nhu cầu gần đúng từ sales/availability | Chỉ test interface |
| BT4 | Trung bình 28 ngày và hệ số phân vị | Chỉ tạo cột đã được model owner xác nhận |
| BT5 | Lift giả lập theo discount | Không gọi là ước lượng nhân quả thực |
| BT6 | Đặt hàng gần P50 | Không coi là tối ưu Newsvendor thật |
| BT7 | Mặc định không markdown | Không gọi là tối ưu lợi nhuận thật |
| BT8 | Xu hướng tăng trưởng tuyến tính | Chỉ để dashboard có dữ liệu |

**Trình tự phụ thuộc:** BT1 trước BT2/BT4; BT3 trước BT4/BT6; BT4 trước BT6/BT7; BT5 trước BT7; BT6 trước BT7; BT8 độc lập. Orchestrator phải kiểm requires và **tất cả** produces trước khi ghi.

**Tiêu chí đạt:** 8 file STUB cùng interface, 14 bảng output đúng contract \+ 2 bảng history nếu bật history, 8 dòng model registry, model\_status=stub, không có dữ liệu từ STUB được hiển thị như dự báo thật.

### **Bước 10\. Bộ điều phối (pipeline/run.py)**

**\[GIỮ V4\]** Tái sử dụng cách phân chia hàm log, step, do\_ingest, do\_transform, do\_models, status, main. Interface CLI V4 được giữ vì dễ sử dụng và hỗ trợ việc cắm model sau này. **\[SỬA V4\]** init không ghi đè landing; locks cần an toàn; rollback/publish theo từng bước.

| Lệnh CLI mục tiêu | Chức năng theo thiết kế đã chốt |
| :---- | :---- |
| python \-m pipeline.run init | Preflight 7 CSV → khởi tạo 14 landing/source fingerprint idempotent → stg/core/mart → DQ; **không xóa nhập liệu cũ** |
| python \-m pipeline.run refresh | Đọc landing **đang active** → stg/core/mart → DQ; **không chạy ingest raw** |
| python \-m pipeline.run models | Đọc F đã validate → chạy 8 STUB/FINAL → output contract → pred/meta |
| python \-m pipeline.run all | refresh \+ models theo thứ tự, dừng nếu DQ fail |
| python \-m pipeline.run evaluate | Gọi evaluate() ở model có hỗ trợ; xuất báo cáo so sánh |
| python \-m pipeline.run status | Đọc phiên bản nguồn, DB, trạng thái bảng, last run, STUB/FINAL, DQ |
| \--only bt1,bt2 | Chỉ định bước nhưng phải kiểm dependencies và stale upstream; từ chối nếu đầu ra yêu cầu không hợp lệ |

**\[CẦN TRIỂN KHAI\]** Các lệnh pipeline.run chưa được xác nhận tồn tại trong repository đã kiểm; đây là mục tiêu. Chạy thật bằng interpreter .venv sau khi module hoàn chỉnh.

**Luồng điều phối được khuyến nghị:**

status/preflight  
    └─ init (chỉ khi nguồn chưa được nạp hợp lệ)  
    	└─ ingest 7 sources → 14 tables \+ source metadata  
        	└─ refresh (stg → core → mart → DQ gate)  
            	└─ models (F → 8 STUB/FINAL → 14 outputs \+ 2 hist)  
                	└─ model registry / run logs → dashboard

**Rủi ro vận hành cần xử lý thay cho code V4 nguyên trạng:**

> > •           Lock bằng tạo file thông thường có thể bị race (hai tiến trình cùng thấy chưa tồn tại). Dùng **atomic file create / OS lock**, owner PID/run\_id/heartbeat, expired lock có kiểm tra, không khuyên người dùng xóa lock bừa.

> > •           do\_transform tạo lại bảng bằng DDL; nếu fail giữa chuỗi, có thể để warehouse nửa cũ nửa mới. Sử dụng transaction/temporary version+swap, kiểm thử khả năng rollback trước khi bàn giao.

> > •           do\_models V4 ghi từng output và history tuần tự. Với bước có nhiều outputs, phải validate đủ trước và ghi atomically; fail giữa chừng phải giữ bản trước hợp lệ.

> > •           Chạy training ngoài write transaction; acquire write lock chỉ khi cần commit. Không hi vọng DBeaver và Streamlit writer luôn truy cập đồng thời mà không lỗi.

> > •           Mỗi run ghi started/finished/duration/error và code commit/config version; khi FAIL không được báo toàn pipeline complete.

> > •           \--only chỉ dùng outputs cũ nếu freshness/contract/run lineage tương thích; tránh trộn output từ phiên bản khác.

**Kiểm tra:** run init → refresh → models → status; thử init lần hai, lỗi DQ, lỗi model, kill giữa commit, concurrent writer, chỉ chạy BT4 khi BT1/BT3 stale.

### **Bước 11\. Nhập liệu trực tiếp DuckDB (rohlik/de/entry.py) — KHÔNG SQLITE**

**\[SỬA V4 – QUYẾT ĐỊNH CUỐI\]** Người dùng chọn **ghi trực tiếp vào DuckDB** thay cho luồng Streamlit→SQLite→DuckDB từng cân nhắc. Đây là luồng nhập duy nhất được mô tả trong bản tài liệu này. Giữ tên entry.py, template/validate/append/undo và src\_\* của V4, nhưng sửa nghiệp vụ và transaction.

**Luồng nhập liệu chính:**

Đăng nhập Streamlit local  
 	→ chọn phòng ban/bảng được phép  
 	→ tải CSV template đúng schema\_version  
 	→ upload CSV  
 	→ preview (số dòng, lỗi theo dòng/cột, trùng key)  
 	→ người dùng xác nhận payload đã kiểm tra  
 	→ backend kiểm lại role/schema/hash/version  
 	→ acquire DuckDB writer lock  
 	→ BEGIN TRANSACTION  
    	INSERT full-row updates INTO src\_department.table  
    	INSERT meta.entry\_log / batch event  
    	COMMIT  
 	→ trả batch\_id \+ ACTIVE \+ hướng dẫn refresh  
 	→ pipeline.run refresh → stg/core/mart/DQ

**Không dùng form từng record làm phương thức nhập chính**; có thể cho form admin nội bộ sau nếu cần, nhưng contract chính là CSV upload.

**4 cột lineage giữ từ V4:** \_batch\_id, \_source, \_loaded\_at (UTC), \_entered\_by. meta.entry\_log phải lưu batch ID duy nhất, bảng, người nhập, số bản ghi, source, hash/version, status, thời gian. Các sự kiện hủy được ghi thêm vào meta.batch\_status\_events (hoặc audit table tương đương) thay vì xóa entry log.

**Validation trước khi ghi** (giữ phần phù hợp từ V4, mở rộng cho CSV upload):

| Nhóm | Bắt buộc kiểm |
| :---- | :---- |
| File | Kích thước, encoding UTF-8/BOM, delimiter, rỗng, cột dư/thiếu/trùng header; từ chối CSV formula/path nguy hiểm khi export/template |
| Contract | Bảng nằm trong 14 bảng; schema\_version; chính xác keys, editable, units và nullability |
| Quyền | User thực tế được backend xác thực và cho phép ghi bảng đó; không tin role do client gửi |
| Khóa | Key đủ, không null, không trùng trong file; chính sách với key đang tồn tại |
| Giá trị | Kiểu số/ngày/chuỗi, domain, nonneg/range; không âm thầm đổi sai thành 0 |
| Batch | Fingerprint/nguồn, upload trùng, trạng thái, retry và double click |
| Xác nhận | Payload cuối giống preview đã kiểm, người dùng biết số insert/update/cảnh báo |

**Chính sách update giai đoạn MVP:** file template người dùng tải từ dashboard hiển thị **tên canonical** (đặc biệt 11 cột HR đã mapping), không hiển thị header CSV lịch sử khác tên. Một bản ghi input phải chứa **đầy đủ các cột editable bắt buộc** của bảng (full-row replacement). Các bảng như Promotions có 7 cột discount, không cho phép để trống một cột chỉ vì muốn giữ giá trị trước; nếu cần patch semantics phải thiết kế merge theo cột và test riêng. Khi key đã tồn tại, append phiên bản mới; stg lấy phiên bản active mới nhất. Không âm thầm drop duplicate row “giữ dòng cuối” trong upload khi chưa có xác nhận rõ.

**Transaction SQL khung bắt buộc (minh họa, ứng dụng tự bind parameters):**

BEGIN TRANSACTION;  
 *\-- INSERT INTO src\_marketing.prices ...  (new \_batch\_id / provenance)*  
 *\-- INSERT INTO meta.entry\_log ...   	(same batch\_id, actor, file hash)*  
 *\-- INSERT INTO meta.batch\_status\_events ... ('ACTIVE')*  
 COMMIT;  
 *\-- ON ERROR: ROLLBACK; không trả batch\_id thành công*

**Undo/rollback batch:** User gửi batch\_id, backend kiểm role/ownership và trạng thái; ghi thêm event UNDONE trong transaction và audit actor/thời điểm/lý do; sau refresh, stg bỏ tất cả rows thuộc batch đã UNDONE. **Không dùng DELETE FROM src\_\* WHERE \_batch\_id=... của V4 gốc**, vì trái với mục tiêu giữ bằng chứng lịch sử. Lệnh undo lặp lại trả trạng thái đã undone, không hủy nhầm batch khác.

**Lưu ý concurrency:** DBeaver/Streamlit/CLI có thể cùng mở file. Với trực tiếp DuckDB, **số lượng người nhập đồng thời bị giới hạn bởi khả năng điều phối writer**. Nếu 9 phòng ban cùng ghi từ nhiều máy, phải chuyển sang kiến trúc server/online hoặc một write service tập trung; bản local MVP **không cam kết chịu tải đa writer**.

**Kiểm tra vòng đầu-cuối:** upload một cập nhật availability; kiểm entry\_log \+ landing; refresh thấy core đổi; undo, refresh thấy giá trị trước; lỗi khi audit ghi thì toàn bộ INSERT rollback; upload trùng không nhân đôi; init lại không làm mất cập nhật.

### **Bước 12\. Phân quyền & an toàn truy vấn (config/roles.yaml, rohlik/security.py)**

**\[GIỮ V4\]** Giữ các role V4 (executive, sales, demand\_planning, warehouse\_ops, logistics, marketing, data\_team) và cấu hình pages/read/write theo phòng. Mục nhập liệu chọn bảng thuộc 14 bảng và ghi thông qua entry.py sau kiểm tra role server-side.

**\[SỬA V4\]** Regex như check\_select() trong V4 **chỉ là bộ lọc sơ bộ, không phải sandbox SQL bảo mật đầy đủ**. Không cho người dùng submit tùy ý SQL tới kết nối có quyền ghi; dùng read-only connection, danh sách bảng/mẫu câu truy vấn được phép, parameter binding và giới hạn số dòng/timeout khi EDA. Không cho bypass xác thực ở backend bằng cách sửa UI.

**Local-first:** phân quyền cho demo vẫn hữu ích, nhưng không mô tả như bảo mật production nếu mọi người có trực tiếp quyền truy cập file .duckdb. File system permissions và bảo vệ thư mục trên Windows là lớp kiểm soát riêng. Không commit password, token hoặc file dữ liệu cá nhân.

**Kiểm thử:** sales không upload vào HR; Marketing không ghi vào Ops; SQL explorer không ghi/đọc file qua function; user thiếu quyền bị từ chối cả ở service, không chỉ ẩn nút. Các kiểm tra này chạy trên database temp, không trên DB chứa dữ liệu thật.

### **Bước 13\. Công cụ tích hợp FINAL (template, check\_model, swap\_models)**

**\[GIỮ V4\]** Cơ chế ba thành phần:

> > •           templates/bt\_template.py: skeleton META \+ run(F,cfg,reg) \[+ evaluate\] cho mỗi BT.

> > •           scripts/check\_model.py: nạp riêng BT, kiểm requires/produces \+ output contract trên fixture trước khi cắm vào pipeline.

> > •           scripts/swap\_models.py: sao lưu model đang dùng và thay STUB/FINAL theo danh sách rõ ràng, không sửa orchestrator.

**\[CHỜ BT CONFIRM\]** Không xem 8 lời giải tham khảo của V4 như model FINAL của nhóm; các số liệu notebook V4 không phải kết quả thực nghiệm do nhóm đã chạy. Sử dụng chỉ để hiểu expected interface. Nếu contract BT4 (hoặc BT khác) chưa chốt, check\_model phải báo **PENDING** thay vì “đạt” bằng một contract chưa được duyệt.

**Lưu ý số liệu**: bảng pred có model\_status phân biệt STUB/FINAL; handoff artifacts dùng để so output trong cùng kỳ dữ liệu. Không được dùng backtest actual của tương lai làm feature khi chạy forecast thật; tránh rò rỉ thời gian.

**Kiểm tra:** thay một STUB bằng FINAL trong database/temp fixture; đảm bảo output schema/horizon/keys đúng, không làm thay đổi những module khác; rollback được về STUB có sao lưu.

### **Bước 14\. Bộ test tự động và tích hợp (tests/)**

**\[GIỮ V4\]** Test sử dụng raw thu nhỏ và DuckDB temp database; không đụng kho dữ liệu đang dùng. V4 có nhóm test T01–T12 và tài liệu nói 30 passed cho bộ mã của tác giả; **không coi đó là kết quả kiểm thử repository hiện tại**.

**Danh sách test nên có trong bản local đã điều chỉnh:**

| Nhóm test | Mục tiêu kiểm chứng |
| :---- | :---- |
| T01 – Source/ingest | Đúng 7 CSV, 14 bảng; map 11 HR headers tiếng Anh (5 rename), đủ 3/7 params; fingerprint & NO\_OP khi init rerun |
| T02 – ELT/DQ | stg/core/mart đúng grain; JOIN không nhân dòng; ERROR/WARN hoạt động |
| T03 – Frames | 6 F đúng schema; parity raw/warehouse trên fixture giống nhau |
| T04 – Entry validation | Thiếu khóa, sai kiểu, sai quyền, sai params, CSV trùng đều bị chặn |
| T05 – Undo | Append mới → stg bản mới; soft undo → stg quay về cũ; landing giữ lịch sử |
| T06 – Refresh | Upload ngày mới → core \+ mart cập nhật, không gọi lại ingest/raw |
| T07 – Output Contract | Thiếu/ngoài hợp đồng/trùng key/NaN/phân vị sai bị từ chối |
| T08 – Model pipeline | 8 STUB → 14 pred \+ 2 hist khi bật history; registry đủ 8 |
| T09 – Authz | Không đọc/ghi sai phòng; backend xác thực role |
| T10 – SQL safety | SQL explorer từ chối statement/function nguy hiểm, giới hạn queries |
| T11 – CLI robustness | init, refresh, models, all, \--only, status \+ logs |
| T12 – Transaction/lock | Audit fail → rollback, concurrent writer, crash/retry không nhân đôi |
| T13 – Source fidelity | 5 CSV Kaggle không bị thay giả, 2 Params có label ASSUMED |
| T14 – End-to-end | Từ raw → 14 landing → core/mart → 8 STUB/pred → Streamlit local |

**Test báo cáo:** nêu tổng test pass/fail, số WARN DQ có lý do, thời gian, git commit và fingerprints đầu vào. Không chốt một con số “30 passed” hay “109 passed” như ngưỡng mới; phải có đủ các **loại hành vi** ở trên và chạy thành công trên code thực tế.

**Cách chạy (khi các module đã triển khai):**

.\\.venv\\Scripts\\python.exe \-m pytest \-q  
 .\\.venv\\Scripts\\python.exe \-m pipeline.run status  
 .\\.venv\\Scripts\\python.exe \-m pipeline.run init  
 .\\.venv\\Scripts\\python.exe \-m pipeline.run models

Nếu pipeline.run chưa tồn tại, chỉ chạy test của repo và đánh dấu nhóm kiểm thử còn PENDING. Trước khi test trên kho chính thức phải backup; E2E destructive test chỉ trên DB tạm.

### **Bước 15\. Hoãn triển khai MotherDuck / GitHub Actions – chuẩn bị khả năng chuyển đổi**

**\[SỬA V4 – QUYẾT ĐỊNH CUỐI\]** Phần cloud của V4 **không phải bước triển khai ở giai đoạn hiện tại**. Giữ mô tả như một roadmap sau khi local đạt nghiệm thu.

**Hiện tại không thực hiện:** tạo MotherDuck token, chuyển ROHLIK\_WAREHOUSE=md:rohlik, up toàn bộ Kaggle lên online, cấu hình GitHub Actions workflow/scheduler, triển khai Streamlit Cloud. Không đưa secrets lên repository.

**Chỉ chuẩn bị khả năng chuyển đổi**: database URL được config hóa; phụ thuộc giữa SQL/logic/data contract không gắn cứng đường dẫn Windows; tách IO, credentials và model training; lưu venv dependencies; kiểm thử idempotency. Nếu sau này có nhiều writer/phòng ban thật, cần **đánh giá lại kiến trúc nhập liệu** thay vì giả định chuyển sang MotherDuck chỉ bằng cách đổi một biến môi trường.

### **Bước 16\. Nghiệm thu Data Engineering local và bàn giao**

**\[SỬA V4\]** Chỉ công nhận hoàn thành khi demo từ đầu đến cuối trên DuckDB local; cloud không nằm trong tiêu chí. Bảng sau thay thế mục “15 landing, 30 passed, MotherDuck” trong V4.

| STT | Tiêu chí nghiệm thu bắt buộc | Bằng chứng |
| ----: | :---- | :---- |
| 1 | 5 Kaggle gốc \+ 2 CSV assumptions được preflight, hash và ghi nhận; train\_calendar.csv không đi downstream | registry/report \+ hashes |
| 2 | Có đúng 14 bảng src\_\* thuộc 9 phòng ban, Finance/HR có 3/7 dòng canonical, HR giữ đủ 11 cột (5 rename); rerun ingest không trùng/mất nhập liệu | SQL count \+ rerun log |
| 3 | 14 stg \+ 6 core \+ 5 mart được tạo, đúng key/grain, output chính xác theo quy tắc đã duyệt | SQL DQ \+ integration tests |
| 4 | 21 kiểm tra DQ nền được chạy và lưu trạng thái, không có ERROR chưa xử lý; checks Params/nullable được ghi bổ sung | meta.quality\_report |
| 5 | frames tạo đủ 6 F, đúng schema, raw/warehouse parity trong phạm vi tương đương | Frame tests |
| 6 | 8 STUB theo pipeline.yaml ghi đủ 14 pred \+ 2 \_hist, model\_registry có 8 entries; STUB được đánh dấu | pipeline.run models \+ queries |
| 7 | output\_contract bắt sai kiểu, thiếu cột, trùng key, phân vị sai, output ngoài contract | Negative tests |
| 8 | CSV upload từ Streamlit local → landing DuckDB trực tiếp; audit+data transaction; refresh phản ánh cập nhật | Video/log/SQL demo |
| 9 | Undo mềm khôi phục bản có hiệu lực trước, lịch sử landing còn nguyên; init không ghi đè updates | Undo \+ rerun tests |
| 10 | CLI init/refresh/models/all/status có lock/log, xử lý FAIL/rollback rõ ràng; không trộn model stale | Orchestrator E2E tests |
| 11 | Phân quyền backend, SQL Explorer read-only, file/secrets không được commit | Security tests \+ git check |
| 12 | README \+ kiến trúc \+ contracts \+ params assumptions \+ hướng dẫn bàn giao được cập nhật; test suite green trên code hiện tại | Repo commit \+ test report |

**Bàn giao cho task Gộp/Training**: Git commit/tag, database local được dựng lại từ các file nguồn và script, hướng dẫn CLI, báo cáo DQ, frames.SCHEMA, output\_contract.yaml đã đối chiếu model owner, 8 STUB và công cụ check\_model/swap\_models. Handoff phải phân biệt rõ **STUB** và **FINAL**.

**Bàn giao cho Dashboard**: 5 tên mart, 14 bảng pred, 2 bảng lịch sử và các bảng meta, quyền đọc/ghi, service nhập CSV, mô tả cảnh báo khi STUB và cách tránh writer lock khi chạy local.

**Không nghiệm thu dựa vào những câu khẳng định trong tài liệu V4 gốc** rằng 30 tests/8 notebooks/MotherDuck đã chạy; các chứng cứ đó chỉ áp dụng cho bộ mã và dữ liệu tác giả V4 từng sử dụng. Đội dự án phải tự chạy/ghi bằng chứng trên repository hiện hành.

---

## **Phụ lục A. Danh sách nội dung giữ lại từ V4 và điểm sửa bắt buộc**

| Hạng mục V4 | Giữ / sửa | Thực hiện |
| :---- | :---- | :---- |
| I.1 Kiến trúc ELT | Giữ | src\_\* → stg → core → mart → pred/meta |
| I.2 Module map / config | Giữ có điều chỉnh | Dựa trên repo hiện tại, Python 3.13, chỉ local |
| I.3 Ví dụ Pomelo\_2 | Giữ ở mức minh họa | Không lấy row-count hay ngày cắt của raw giả làm expected values |
| I.4 Best practices | Giữ | Chỉnh idempotency/undo/transactions cho đúng |
| Bước 0–2 | Giữ chức năng | Venv local, schema/contracts, DuckDB writer control |
| Bước 3 | Sửa đáng kể | Không dùng bản sao Hugging Face, dùng 5 CSV Kaggle gốc \+ 2 params |
| Bước 4 | Sửa nghiêm trọng | init không CREATE OR REPLACE landing có cập nhật |
| Bước 5 | Giữ logic core/mart | Không silently clip/drop source anomalies, batch active filter |
| Bước 6 | Giữ 21 checks nền | Bổ sung DQ & severity minh bạch |
| Bước 7–9 | Giữ cơ chế F/Output/STUB | Chốt BT contracts trước FINAL; 14 \+ 2 pred/hist |
| Bước 10 | Giữ CLI | Hardening lock, transaction, stale upstream, logs |
| Bước 11 | Ghi trực tiếp DuckDB | **Không SQLite**; transaction \+ soft undo \+ backend checks |
| Bước 12–14 | Giữ chức năng | Tighten SQL safety, tests local và evidence |
| Bước 15 | Hoãn | MotherDuck/Actions/Cloud ngoài phạm vi |
| Bước 16 | Thay tiêu chí | Local E2E, 14 bảng, 7 file, no unverified claims |

## **Phụ lục B. Những quyết định còn cần model owner xác nhận (không tự thay V4)**

> > 1\.         **BT4 phân vị**: output thực tế của FINAL có p10/p50/p90 hay đầy đủ p20...p90/p\_point theo V4? Cần thống nhất Output Contract sau khi xem notebook/model card và yêu cầu BT6/BT7.

> > 2\.         **Phạm vi cột HR bổ sung**: BT2 có dùng morning\_shift\_ratio, overtime\_cap\_ratio, shortage\_penalty\_multiplier, legacy\_rule\_buffer\_ratio không? Nếu có, cần cập nhật F/params\_workforce và các hàm dự báo tương ứng.

> > 3\.         **Nguồn chi phí**: cost\_ratio, waste\_handling\_cost\_ratio, shelf\_life\_days là ASSUMED; cần phê duyệt miền/đơn vị và giải thích độ nhạy trong BT6/BT7.

> > 4\.         **Xử lý anomaly trong Kaggle**: NULL sales/total\_orders, discount âm, weather NULL; định nghĩa policy trước khi clean, không tự đổi số liệu.

> > 5\.         **Chính sách nhập liệu**: full-row vs patch, retry duplicate detection, ai được undo batch nào, thời gian giữ lịch sử/log, giới hạn kích thước upload; ban đầu khuyến nghị full-row và soft undo.

> > 6\.         **Data freshness và forecast cut-off**: dữ liệu Kaggle nguyên gốc khác khoảng cắt mẫu của V4; phải chốt as-of cho demo và feature thời gian để tránh rò rỉ.

> > 7\.         **Phương án online về sau**: chỉ quyết định sau khi hệ thống local đã chạy thành công, có bằng chứng nhu cầu thật về multiuser.

## **Phụ lục C. Nguồn và giới hạn của bản hướng dẫn**

> > •           **Nguồn chính:** Rohlik\_Decision\_Hub\_Huong\_dan\_xay\_dung\_he\_thong\_chi\_tiet(1).md, **Phần I**: kiến trúc I.1, modules I.2, ví dụ dòng dữ liệu I.3, nguyên tắc I.4, 17 bước (0–16) I.5.

> > •           **Nguồn dữ liệu đối chiếu:** 5 CSV Kaggle và cost\_params.csv, workforce\_params.csv mà nhóm đã cung cấp; file HR cập nhật có **11 header tiếng Anh không BOM**, trong đó 5 cột cần rename theo hợp đồng V4; mọi mô tả mapping đã đồng bộ theo file này.

> > •           **Repository hiện tại:** Task 08A, source registry/validator và các thành phần DB infrastructure mới là cơ sở tái sử dụng; không được đồng nhất bản demo V4 với trạng thái code thực tế.

> > •           **Ranh giới:** tài liệu này **mô tả đầy đủ cách xây dựng/kiểm thử mục tiêu**. Các đoạn ký hiệu “minh họa” là định hướng triển khai, **không tự nhận là bản source code hoàn thiện đã chạy**. Các yêu cầu có nhãn “\[CHỜ BT CONFIRM\]” phải được chủ model xác nhận trước khi dùng làm acceptance cho FINAL.

