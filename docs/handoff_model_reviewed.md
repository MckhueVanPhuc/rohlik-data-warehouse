# ROHLIK DECISION HUB

TÀI LIỆU HƯỚNG DẪN BÀN GIAO CODE & MODEL — BT1 ĐẾN BT8

Model Handover & Integration Package • Áp dụng cho nhóm thực hiện 8 bài toán ML/Tối ưu • DuckDB-only • V4-03 Landing

Phiên bản 1.0 — 21/10/2026 | Mục đích: gửi cho từng thành viên để chuẩn bị đầy đủ gói bàn giao có thể chạy lại và tích hợp.

**NGẮN GỌN: Các bạn ĐÃ làm xong mô hình không cần viết lại thuật toán. Hãy gửi notebook/code gốc, dữ liệu dùng để chạy, artifact (nếu có), môi trường, input/output mẫu và mô tả chính xác cách chạy. Nếu tách được một hàm inference/optimisation chuẩn thì làm theo mẫu ở Phần 6\. Người tích hợp sẽ chịu trách nhiệm kết nối DuckDB Landing và Streamlit.**

# 0\. Thông tin dự án và phạm vi áp dụng

Repository: https\://github.com/MckhueVanPhuc/rohlik-data-warehouse

Branch cơ sở khi soạn tài liệu: main, commit 2b91e0a1199bbdfe476c917e64083a2fa0b9b9d2; PR \#1 chứa V4-02/V4-03 đã merge. Đặc tả gần nhất: docs/v4\_03\_landing\_handover.md, docs/model\_integration\_contract.md, docs/model\_handover\_checklist.md, config/contract.yaml.

Pipeline hiện đã có: 7 CSV active → Source Registry \+ Data Contract → kiểm tra dữ liệu → nạp DuckDB Landing 14 bảng/9 schema → metadata, source batch, provenance, audit → so sánh NO\_OP. Không triển khai SQLite trong kiến trúc hiện tại. Không triển khai chung STG/Core/Mart. Cả 8 model, adapter, model runner và dashboard kết quả hiện chưa được nghiệm thu tích hợp trong repository, dù các bạn đã chạy xong notebook riêng.

Mục tiêu của tài liệu: thống nhất cách bàn giao để người tích hợp có thể nhận đúng input, gọi model, kiểm tra output, lưu kết quả và kết nối giao diện mà KHÔNG thay đổi ý nghĩa hoặc thuật toán nghiên cứu của từng BT.

# 1\. Phân công trách nhiệm — ai làm phần nào?

## 1.1 Thành viên phụ trách BT1–BT8 (người nhận tài liệu này)

• Nộp code/notebook đầy đủ và cho biết phiên bản nào là bản cuối đã chạy thành công.

• Nêu chính xác dữ liệu nào được đọc, cột nào cần thiết, và feature được tạo như thế nào. Không mô tả dựa trên suy đoán.

• Nộp file đã fit/trained như model/scaler/encoder nếu thuật toán sử dụng; nếu không có artifact, giải thích vì sao.

• Cung cấp thư viện và phiên bản môi trường, cách chạy lại, thời gian chạy và yêu cầu CPU/GPU.

• Cung cấp ít nhất một bộ input nhỏ và output tương ứng đã chạy thật để đối chiếu sau tích hợp.

• Chỉ rõ phụ thuộc các BT khác, data cutoff/as\_of, horizon, units và những hạn chế đã biết.

• Nếu có thể, tách phần chạy dự báo/tối ưu thành một hàm Python; nếu chưa thể thì bàn giao notebook nguyên vẹn và ghi rõ cell/chạy theo thứ tự.

## 1.2 Người phụ trách Data Engineering & Integration

• Xác minh database DuckDB chứa đúng batch đã hoàn tất và đối chiếu NO\_OP trước khi cấp snapshot cho model.

• Viết model-specific input adapter: đọc read-only từ 14 Landing tables, mapping columns, JOIN đúng key/grain, kiểm tra NULL/anomaly và leakage theo mô tả chủ model.

• Tạo Model Runner: quản lý run\_id, thứ tự phụ thuộc, môi trường runtime, lỗi, input manifest, output validation và lưu kết quả.

• Đối chiếu output tích hợp với kết quả nghiên cứu của chủ model trên cùng input, artifact và config.

• Kết nối Streamlit sau khi output đã đạt validation. Không chạy training lại mỗi lần dashboard refresh.

## 1.3 Những việc thành viên model KHÔNG cần làm

• Không sửa bảng DuckDB Landing, metadata hoặc config/source registry của dự án.

• Không tự thiết kế lại 14 STG, 6 Core, 5 Mart; kiến trúc tích hợp hiện chủ động bỏ các lớp này.

• Không viết lại thuật toán chỉ để đổi tên file hay tạo ra model khác.

• Không tự viết phần upload CSV, backup, writer lock, SQLite hoặc Streamlit giao diện chung.

• Không ép tất cả model dùng một thư viện hoặc một phiên bản Python nếu có xung đột thật.

# 2\. Danh sách file cần gửi — MUST / IF APPLICABLE / OPTIONAL

## 2.1 Bắt buộc phải có (MUST)

• README.md — mô tả bài toán, phương pháp, mục tiêu, kết quả, cách chạy, người phụ trách và lưu ý.

• original\_notebook.ipynb HOẶC source Python đầy đủ (.py); nếu sử dụng cả hai thì gửi cả hai và chỉ rõ file chính.

• model\_manifest.yaml — điền các thông tin cấu hình/đầu vào/đầu ra theo Phần 5\. Không để các trường cần thiết bị đoán.

• requirements-model.txt — những package thật đã dùng và phiên bản; nêu phiên bản Python/OS/runtime trong README.

• samples/input\_sample.\* — bộ dữ liệu mẫu hợp lệ và được phép chia sẻ, cùng mô tả schema. Giữ nguyên logic/kiểu dữ liệu.

• samples/expected\_output.\* — output THỰC TẾ tương ứng với đúng input mẫu, đúng version artifact/config.

• run\_instructions.md hoặc phần 'Cách chạy' trong README — các bước từ máy sạch, thứ tự cell/scripts, đường dẫn biến đầu vào, tham số, và lỗi thường gặp.

• Danh sách input file/dataset/source ngoài 7 CSV của dự án (nếu có), nguồn gốc và cách truy cập hoặc tái tạo. Không cần chuyển dữ liệu không được phép chia sẻ, nhưng phải khai báo.

## 2.2 Bắt buộc khi model thật sự sử dụng (IF APPLICABLE)

• artifacts/ — model đã fit, weights, encoders, scalers, tokenizer, label maps, solver coefficients… với phiên bản và checksum.

• preprocess.py, features.py — code feature engineering và transforms đặc thù nếu được tách ngoài notebook.

• config.yaml / config.json — training/inference parameters, seed, forecast horizon, quantiles, threshold và thông số solver.

• training\_data\_schema.json hoặc equivalent — khi cần dữ liệu training khác inference.

• Output của các BT upstream và đúng version/run ID đã dùng, nếu model phụ thuộc kết quả BT khác.

• Thông tin GPU, Colab, CUDA hoặc API/solver license nếu cần.

## 2.3 Khuyến nghị thêm (OPTIONAL)

• model.py — hàm \`run\_model\` theo giao diện chung ở Phần 6; nếu chưa làm được hãy để người tích hợp chuyển đổi từ notebook.

• tests/test\_model.py — tối thiểu một smoke test gọi model bằng input mẫu.

• evaluation.md — số liệu metric, chart, so sánh baseline, bất định, limitations và nghiệm thu khoa học.

• sample\_result.json — JSON metadata cho run mẫu; không chứa khóa bí mật.

**KHÔNG BAO GIỜ gửi: mật khẩu, API key, token, tài khoản Google Drive, credential, tệp dữ liệu nhạy cảm không có quyền chia sẻ. Không bắt buộc commit model binary hoặc CSV nặng vào Git. Có thể chuyển qua folder chia sẻ được cấp quyền; ghi checksum và version trong manifest.**

# 3\. Cấu trúc thư mục bàn giao cho từng BT

handover/

└── BT1/                          \# đổi BT1 thành BT2 ... BT8

    ├── README.md                 \# REQUIRED

    ├── original\_notebook.ipynb   \# hoặc full source .py

    ├── model\_manifest.yaml       \# REQUIRED

    ├── requirements-model.txt    \# REQUIRED

    ├── model.py                  \# RECOMMENDED nếu đã tách được inference

    ├── preprocess.py             \# IF APPLICABLE

    ├── config.yaml               \# IF APPLICABLE

    ├── artifacts/                \# IF APPLICABLE, KHÔNG tạo giả

    │   ├── trained\_model.\<ext\>

    │   └── fitted\_preprocessor.\<ext\>

    ├── samples/

    │   ├── input\_sample.parquet

    │   ├── expected\_output.parquet

    │   └── sample\_notes.md

    └── tests/

        └── test\_model.py         \# RECOMMENDED

Bạn có thể dùng CSV/JSON thay Parquet nếu công cụ của bạn chưa hỗ trợ Parquet. Quan trọng là chỉ rõ filename, encoding, columns, data types, đơn vị và bảo toàn giá trị NULL; người tích hợp sẽ thống nhất định dạng khi nhận.

Nếu model tạo nhiều output, gửi nhiều file \`expected\_output\_\<name\>.parquet\` và liệt kê tất cả trong manifest; không nén chúng vào một bảng gây mất nghĩa.

# 4\. Mẫu README.md — hãy điền tất cả mục

\# BT\[X\] — \[TÊN BÀI TOÁN\]

\- Người phụ trách / kênh liên hệ:

\- Notebook / git commit / ngày chốt:

\- Trạng thái: đã chạy thành công trên môi trường nào?

\- Mục tiêu nghiệp vụ và output sử dụng để ra quyết định:

\- Phương pháp / thuật toán (ghi đúng phiên bản thực tế):

\- Loại chạy: INFERENCE / OPTIMISATION / REQUIRES\_REFIT / TRAINING\_ONLY

\- Input: tên file và nơi lấy, grain, business key, schema, unit

\- Preprocessing: tên cell/hàm, fitted scaler/encoder, imputation

\- Time: train interval, inference interval, cutoff/as\_of, horizon

\- Upstream BT: model nào? output file/table nào? bắt buộc hay tùy chọn?

\- Model artifact: filename, framework, version, checksum hoặc N/A

\- Output: tên bảng/file, cột, grain, key, unit, nullable, ý nghĩa

\- Kết quả mẫu: input\_sample → expected\_output (cùng revision)

\- Môi trường: Python, OS, package versions, CPU/GPU, RAM

\- Thứ tự các bước chạy cụ thể (lệnh/cell)

\- Runtime ước lượng và random seed

\- Metrics / validation / acceptable tolerance

\- Hạn chế: missing data, anomalies, overfit, leakage, package conflict...

\- Đường dẫn/vị trí lưu toàn bộ file bàn giao

# 5\. Mẫu model\_manifest.yaml — COPY VÀ ĐIỀN

Đây là cấu trúc đề xuất để người tích hợp đọc được thông tin chính. Những giá trị IN HOA là placeholder chưa được duyệt; hãy thay bằng thông tin lấy từ model của bạn. Không dùng placeholder như dữ liệu sản xuất.

bt\_id: BT1

task\_name: "ACTUAL\_TASK\_NAME"

owner: "PERSON\_OR\_TEAM"

model\_version: "ACTUAL\_VERSION"

source\_revision: "NOTEBOOK\_REVISION\_OR\_COMMIT"

execution\_type: "inference"       \# inference | optimisation | requires\_refit

main\_entrypoint: "original\_notebook.ipynb"  \# hoặc model.py:run\_model

python\_version: "ACTUAL\_VERSION"

runtime: "windows|colab|linux|other"

requires\_gpu: false               \# khai báo thực tế

requirements\_file: "requirements-model.txt"

inputs:

  \- logical\_name: "ACTUAL\_INPUT\_NAME"

    sample\_path: "samples/input\_sample.parquet"

    required\_columns:

      \- name: "ACTUAL\_COLUMN\_NAME"

        dtype: "ACTUAL\_DTYPE"

        nullable: false

        unit: "ACTUAL\_UNIT\_OR\_NA"

    grain: "ACTUAL\_GRAIN"

    business\_keys: \["ACTUAL\_KEY"\]

    source\_dataset\_or\_tables: \["ACTUAL\_SOURCE"\]

    null\_policy: "APPROVED\_MODEL\_POLICY"

    anomaly\_policy: "APPROVED\_MODEL\_POLICY"

    as\_of\_semantics: "ACTUAL\_CUTOFF\_DEFINITION"

    training\_window: "ACTUAL\_WINDOW\_OR\_NA"

    inference\_window: "ACTUAL\_WINDOW"

    forecast\_horizon: "ACTUAL\_HORIZON\_OR\_NA"

upstream\_models: \[\]

\# Ví dụ khi đã xác nhận:

\# \- bt\_id: BT1

\#   output\_name: fc\_orders

\#   required: true

\#   expected\_version: "ACTUAL\_VERSION"

artifacts: \[\]

\# \- path: "artifacts/trained\_model.joblib"

\#   format: "joblib"

\#   sha256: "ACTUAL\_SHA256"

\#   library\_version: "ACTUAL\_FRAMEWORK\_VERSION"

outputs:

  \- logical\_name: "ACTUAL\_OUTPUT\_NAME"

    sample\_path: "samples/expected\_output.parquet"

    grain: "ACTUAL\_OUTPUT\_GRAIN"

    business\_keys: \["ACTUAL\_OUTPUT\_KEY"\]

    schema\_reference: "README.md\#output"

    unit: "ACTUAL\_OUTPUT\_UNIT"

    validation\_rules: \["ACTUAL\_APPROVED\_RULES"\]

reproducibility:

  random\_seed: "ACTUAL\_SEED\_OR\_NA"

  expected\_runtime: "MEASURED\_TIME"

  metric\_or\_tolerance: "ACTUAL\_APPROVED\_TOLERANCE"

known\_limitations:

  \- "ACTUAL\_LIMITATION\_OR\_NONE"

Nếu model có nhiều input hoặc output thì lặp block tương ứng. Nếu trường không áp dụng, ghi \`N/A\` cùng lý do, không xóa mù mờ. Nếu chưa xác nhận, ghi \`TO\_CONFIRM\` và giải thích ai sẽ xác nhận; model đó chưa đủ điều kiện tích hợp FINAL.

# 6\. Template code Python \`model.py\` — giao diện chuẩn ĐỀ XUẤT

Hàm bên dưới là skeleton để thống nhất lời gọi, KHÔNG phải một model thật đã chạy. Các thành viên chỉ điền khi đã tách được inference/optimisation. Giữ nguyên thuật toán/phép biến đổi đã nghiên cứu; không thêm dự báo giả để vượt kiểm thử.

from pathlib import Path

from typing import Any

import pandas as pd

def run\_model(

    \*,

    inputs: dict\[str, pd.DataFrame\],

    config: dict\[str, Any\],

    artifact\_dir: Path,

) \-\> dict\[str, pd.DataFrame\]:

    """

    inputs: DataFrames ĐÃ ĐƯỢC adapter cung cấp theo schema xác nhận.

    config: cấu hình đúng version, as\_of, horizon, params, seed.

    artifact\_dir: nơi chứa model/scaler/... đáng tin cậy nếu có.

    return: {logical\_output\_name: actual\_output\_dataframe}

    """

    required \= set(config\["required\_inputs"\])

    missing \= sorted(required \- set(inputs))

    if missing:

        raise ValueError(f"Missing model inputs: {missing}")

    \# 1\. Validate input types/columns/keys/time based on REAL model schema.

    \# 2\. Apply ORIGINAL approved feature preprocessing.

    \# 3\. Load APPROVED fitted artifacts (if required).

    \# 4\. Execute genuine inference or optimisation.

    \# 5\. Build and validate actual output DataFrames.

    raise NotImplementedError(

        "Replace with REAL model code; never return fake predictions"

    )

Những lưu ý khi tách code: không gọi \`pd.read\_csv('/content/...')\` trong model.py; không mount drive ngầm; không ghi vào DuckDB; không phụ thuộc biến lưu lại từ cell notebook đã chạy trước đó; không tự fit scaler trên tập inference nếu thiết kế gốc dùng fitted scaler; không train lại ngầm khi người dùng mở dashboard.

Nếu model gốc chỉ nhận file path hoặc có API riêng, đừng cố phá cấu trúc đang chạy. Hãy mô tả cách gọi trong README; người tích hợp có thể viết wrapper điều chỉnh \`inputs\` thành file tạm và gọi chương trình gốc, miễn bảo toàn logic và có kiểm thử tái lập.

# 7\. Mẫu code tự kiểm tra trước khi gửi

Điều kiện căn bản: gọi được trên data mẫu; đầu ra thật không rỗng khi ví dụ được thiết kế phải có dữ liệu; key/schema khớp; thiếu input phải ném lỗi rõ ràng. Không kiểm thử bằng output tự tạo để qua vòng nghiệm thu.

\# PSEUDOCODE TEST — chỉnh cho phù hợp schema thực tế

from pathlib import Path

import pandas as pd

import pytest

from model import run\_model

def test\_known\_sample\_matches\_reference():

    sample \= pd.read\_parquet("samples/input\_sample.parquet")

    \# expected \= pd.read\_parquet("samples/expected\_output.parquet")

    config \= {

        "required\_inputs": \["ACTUAL\_INPUT\_NAME"\],

        \# \+ actual params/seed/as\_of

    }

    result \= run\_model(

        inputs={"ACTUAL\_INPUT\_NAME": sample},

        config=config,

        artifact\_dir=Path("artifacts"),

    )

    assert "ACTUAL\_OUTPUT\_NAME" in result

    assert isinstance(result\["ACTUAL\_OUTPUT\_NAME"\], pd.DataFrame)

    \# Compare to REAL reference output with approved tolerances.

def test\_missing\_required\_input\_fails():

    with pytest.raises((ValueError, KeyError)):

        run\_model(

            inputs={},

            config={"required\_inputs": \["ACTUAL\_INPUT\_NAME"\]},

            artifact\_dir=Path("artifacts"),

        )

# 8\. Hướng dẫn xử lý Notebook/Colab đã hoàn thành

## 8.1 Với notebook đã có kết quả hoàn chỉnh

• Lưu notebook bản cuối từ Colab/Jupyter, xóa thông tin nhạy cảm và chỉ rõ cell quan trọng.

• Liệt kê những file input notebook đã load và những file output/artifact notebook đã tạo. Đừng chỉ gửi ảnh chụp kết quả.

• Chỉ rõ các \`\!pip install\`, \`drive.mount\`, đường dẫn \`/content/\`, files Google Drive, API/download runtime và biến có trạng thái ẩn.

• Ghi một hướng dẫn chạy lại từ kernel sạch (Restart & Run All) hoặc chỉ rõ những cell không được chạy và lý do.

• Ghi nếu model chưa lưu artifact, buộc retrain hoặc chỉ hoạt động trên Colab/GPU. Người nhận sẽ đánh dấu trạng thái BLOCKED/REQUIRES\_REFIT phù hợp, không tự tuyên bố inference đã sẵn sàng.

## 8.2 Khi không thể chạy model trên Windows/Python 3.13

• Gửi requirements thật, versions và traceback lỗi chính xác.

• Cho biết notebook hoạt động với Python/Colab version nào; có yêu cầu CUDA/GPU/license không.

• Không bắt tự nâng/hạ thư viện khiến metric hoặc logic thay đổi. Người tích hợp sẽ đánh giá isolated environment/Colab snapshot hoặc container theo nguồn lực của nhóm.

• Output mẫu vẫn phải kèm model/artifact \+ config \+ input version để người tích hợp đối chiếu.

# 9\. Khai báo Data Contract từ góc nhìn model

Source V4-03 là 14 bảng Landing thuộc 9 schema DuckDB, không phải các bảng \`gold.\*\`/\`mart.\*\` như một số tài liệu cũ. Đừng giả định bảng \`gold.fct\_sku\_day\` có sẵn. Nếu notebook dùng \`gold.\*\` hoặc file đã clean sẵn, cần mô tả CHÍNH XÁC phép JOIN, tập cột, keys/grain, lọc ngày và chuẩn hóa đã tạo ra dữ liệu đó; người tích hợp sẽ viết adapter tương đương.

Danh mục bảng để tham chiếu (chỉ có thể sử dụng khi đã xác nhận mapping thực tế):

• src\_sales.orders\_daily — orders, warehouse+date.

• src\_sales.sku\_sales\_daily — SKU sales và total\_orders, unique\_id+date.

• src\_marketing.prices — giá chính, unique\_id+date.

• src\_marketing.promotions — 7 loại discount, unique\_id+date.

• src\_marketing.mov\_changes — mov\_change, warehouse+date.

• src\_ops.availability — availability, unique\_id+date.

• src\_ops.ops\_events — shutdown/blackout events, warehouse+date.

• src\_category.product\_master — sản phẩm, category, warehouse, unique\_id.

• src\_planning.calendar — calendar/holidays, warehouse+date.

• src\_digital.user\_activity — user activity, warehouse+date.

• src\_external.weather — precipitation/snow, warehouse+date.

• src\_finance.sku\_weights — trọng số SKU, unique\_id; KHÔNG hiểu là kg hay giá vốn.

• src\_finance.cost\_params — tham số giả định chi phí theo L1 category (ASSUMED).

• src\_hr.workforce\_params — tham số giả định nhân sự theo warehouse (ASSUMED).

Thành viên không cần viết SQL. Cần chỉ ra đúng dữ liệu nguyên bản và phép biến đổi thực tế notebook đang làm. Data Engineer sẽ đối chiếu với config/contract.yaml trước khi xây adapter.

## 9.1 Các vấn đề dữ liệu phải xác nhận, nếu BT có sử dụng

• Sales có 52 giá trị NULL tại sales và 52 NULL tại total\_orders; phải ghi rõ xử lý missing theo model, không âm thầm điền 0\.

• Sales có 32 discount âm (27 type\_0, 1 type\_4, 4 type\_6); phải ghi rõ được dùng, loại, cắt ngưỡng hay xử lý khác theo logic đã duyệt.

• Orders weather có 270 NULL ở precipitation và 270 NULL ở snow; NULL không đồng nghĩa với không mưa/không tuyết.

• Orders \`orders\` và Sales \`total\_orders\` không tương đương; JOIN kho-ngày với SKU-ngày dễ nhân dòng.

• Hai bảng Finance/HR là ASSUMED, không phải dữ liệu tài chính/nhân sự đã ghi nhận từ doanh nghiệp.

• Bài toán forecasting phải khai báo as\_of, prediction horizon và trường nào biết được trước thời điểm dự báo để tránh data leakage.

# 10\. Gợi ý riêng cho BT1–BT8 (REFERENCE ONLY — PHẢI XÁC NHẬN TỪ NOTEBOOK)

Các phụ thuộc dưới đây lấy từ docs/model\_integration\_contract.md (bản DRAFT tham chiếu v3), KHÔNG xác nhận đã đúng với 8 model thực tế. Nếu notebook khác, ưu tiên notebook thực tế và cùng nhau thống nhất mapping; không chỉnh thuật toán theo bảng tham khảo.

## BT1 — Dự báo Orders

Gợi ý dữ liệu: orders\_daily theo kho-ngày, calendar, weather/ops/user activity nếu thật sự có trong feature set. Cần bàn giao: target orders hay transformed target; horizons theo kho; regressors có thể biết trước; output dự báo theo warehouse-date, prediction intervals/quantiles nếu có; evaluation split và artifact. Tham khảo: không thấy upstream BT bắt buộc.

## BT2 — Workforce/Driver Planning

Gợi ý dữ liệu: outputs forecast BT1 và tham số workforce giả định; tài liệu tham khảo ghi phụ thuộc BT1. Cần làm rõ liệu dùng mean/p50/p90 forecast, quy tắc năng suất, số ca/người, chi phí, constraints, objective và output riêng staff\_plan/driver\_plan. Không giả định BT1 outputs có sẵn nếu chưa bàn giao.

## BT3 — Lost Sales

Gợi ý dữ liệu: sku\_sales\_daily \+ availability, keys theo SKU/date. Cần mô tả khi availability=0 hoặc NULL, cách tính lost demand, lựa chọn features/target và output grain. Nếu nhu cầu mất là ước lượng thì nêu uncertainty/limitation. Tham khảo: không thấy upstream BT bắt buộc.

## BT4 — SKU Forecast

Gợi ý dữ liệu: sales, prices, promotions, product/category, calendar, output BT3 và/hoặc BT1 theo notebook thực tế. Tài liệu tham khảo nói phụ thuộc BT1/BT3. Cần làm rõ SKU-level horizon, price/discount regressors, forecast quantile, key/date alignment và cách dùng lost-sales adjustments.

## BT5 — Promotion Effect

Gợi ý dữ liệu: promotions \+ prices \+ sku sales. Cần mô tả treatment/control, confounders, time window, điều kiện causal/associational, output effect by promotion type và độ tin cậy. Không biến kết quả tương quan thành kết luận nhân quả nếu model không chứng minh.

## BT6 — Replenishment

Gợi ý dữ liệu: outputs BT4/BT3 và cost params ASSUMED, nếu notebook thực sự dùng. Cần nêu inventory snapshot thực tế có hay không, lead time, shelf life, service level, constraints, unit sản phẩm, quy tắc tính order quantity và solver; không tạo giả tồn kho để cho ra số lượng đặt.

## BT7 — Markdown Optimisation

Gợi ý dữ liệu: outputs BT3/BT4/BT5/BT6 và giá/chi phí, nếu notebook thật dùng. Cần nêu stock-on-hand, hạn dùng, các mức giá hợp lệ, optimization objective, cost assumptions, constraints, output price/discount plan và rủi ro khi input giả định.

## BT8 — Warehouse Growth

Gợi ý dữ liệu: lịch sử orders theo kho/ngày và các bối cảnh liên quan. Cần mô tả thời điểm mở kho, cohort/horizon, fit curve, scenarios và output growth curves/projections. Tham khảo: không thấy upstream BT bắt buộc.

# 11\. Đồng bộ Model Runner — flow sau khi nhận đủ 8 gói

Người tích hợp sẽ vận hành quy trình: verify dataset version và NO\_OP trên DuckDB snapshot cô lập → tạo DataFrames theo từng input\_schema từ các batch canonical COMPLETED → freeze input manifest với run\_id/as\_of/data version → chạy upstream theo DAG xác nhận → gọi model.py/inference wrapper → validate output schema, unique keys, ngày, null/range/unit → lưu staging kết quả có checksum và run metadata → publish chỉ sau validation → Streamlit đọc output đã publish.

Không cho model viết trực tiếp vào DuckDB Landing. Không dùng SQLite. Không tự train lại khi refresh dashboard. Nếu BT phụ thuộc upstream FAILED/BLOCKED thì BT đó SKIPPED/BLOCKED, không âm thầm dùng kết quả cũ hoặc giả lập dự báo.

# 12\. Cách kiểm thử và tiêu chí nghiệm thu của một gói

## 12.1 SELF-CHECK — thành viên tự kiểm tra

• Mở được notebook/source; tất cả file dependency có đủ hoặc ghi N/A/limitation có lý do.

• Chạy lại từ trạng thái sạch trên đúng environment có tài liệu, không phụ thuộc cell ẩn.

• Run trên input\_sample cho ra expected\_output thực, có thể đối chiếu bằng key/grain.

• Tên cột, kiểu, unit, NULL, date range, as\_of và horizon được mô tả đầy đủ.

• Model/preprocessor được load đúng phiên bản, không fit lại trái dự kiến.

• Nếu có randomness, seed và phạm vi tolerance được ghi rõ.

• Bỏ một required input/artifact phải cho lỗi rõ ràng; không im lặng tiếp tục và tạo output giả.

• Không có credentials, dữ liệu riêng tư hoặc đường dẫn cá nhân buộc phải sửa thủ công mà không có hướng dẫn.

## 12.2 ACCEPTANCE — người tích hợp kiểm tra

• RECEIVED: đủ file và người chịu trách nhiệm, version/link bằng chứng.

• REPRODUCIBLE: chạy lại model gốc trên sample, so được actual với expected và mức sai số cho phép.

• MAPPABLE: map được input model với Landing/upstream, key/grain và date semantics phù hợp; nếu cần nguồn ngoài thì nguồn đó có thật và được duyệt.

• INTEGRATABLE: callable wrapper chạy được trên môi trường được lựa chọn, không phá code nghiên cứu.

• VALIDATED: output schema/keys/dtypes/units/ranges hợp lệ, không leakage và không dùng upstream sai phiên bản.

• READY\_FOR\_PIPELINE chỉ khi các mục quan trọng ở trên đạt; mọi mục chờ duyệt phải có owner và giải pháp.

## 12.3 Trạng thái dùng chung

RECEIVED \= đã nhận file nhưng chưa chứng minh chạy. BLOCKED \= thiếu input/artifact/environment hay mapping bắt buộc. REPRODUCIBLE \= đã chạy lại độc lập được trên input mẫu. INTEGRATABLE \= đã có interface và mapping được xác nhận. VALIDATED \= output đã kiểm tra khớp reference. READY\_FOR\_PIPELINE \= đủ điều kiện đưa vào orchestration. SUCCESS/FAILED của run và trạng thái PUBLISHED phải lưu riêng.

# 13\. Lịch bàn giao và quy trình trao đổi (đề xuất)

BƯỚC A — Thành viên gửi bản đang có (notebook/code \+ files \+ README) càng sớm càng tốt, không chờ viết lại theo format hoàn hảo.

BƯỚC B — Người tích hợp rà soát package và trả một danh sách thiếu theo từng BT; chỉ yêu cầu bổ sung những gì chưa thấy bằng chứng.

BƯỚC C — Thành viên chạy sample cùng người tích hợp, xác nhận input schema/output schema/metric và artifact.

BƯỚC D — Người tích hợp viết adapter đọc DuckDB đã xác minh, đối chiếu với output reference của notebook.

BƯỚC E — Đồng bộ các BT theo DAG đã được xác nhận, kiểm thử end-to-end đến output và dashboard.

# 14\. Phiếu điền nhanh cho TỪNG THÀNH VIÊN — copy và điền

MÃ BT: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

TÊN BÀI TOÁN: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

NGƯỜI PHỤ TRÁCH: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

NOTEBOOK/CODE LINK: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

BẢN CHẠY CUỐI / VERSION: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

PHƯƠNG PHÁP / LOẠI CHẠY: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

INPUT FILES \+ NGUỒN: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

INPUT COLUMNS / TYPES / KEYS / GRAIN: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

PREPROCESSING / SCALER / ENCODER: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

TRAIN RANGE / AS\_OF / HORIZON: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

UPSTREAM BT \+ OUTPUT / VERSION / REQUIRED?: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

ARTIFACT PATH \+ HASH / N/A LÝ DO: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

REQUIREMENTS / PYTHON / CPU-GPU: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

OUTPUTS \+ COLUMNS / KEYS / UNITS: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

INPUT SAMPLE: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

EXPECTED OUTPUT SAMPLE: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

METRIC/TOLERANCE/SEED: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

CÁCH CHẠY TỪ MÁY SẠCH: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

HẠN CHẾ / THỨ CẦN HỖ TRỢ: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

NGÀY BÀN GIAO / NGƯỜI NHẬN: \_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_

# 15\. Checklist trước khi nhấn 'Gửi bàn giao'

• Tôi đã gửi notebook/code đúng bản cuối và giải thích cách chạy từ đầu.

• Tôi đã gửi input nguồn, các file trung gian quan trọng, output sample đã chạy thật.

• Tôi đã khai báo input/output theo đúng tên, type, grain, key, date và units.

• Tôi đã ghi đúng bản model/preprocessor artifact, package versions và runtime.

• Tôi đã khai báo đủ upstream BT và dữ liệu bên ngoài 7 CSV nếu có.

• Tôi đã nêu giới hạn về NULL, discount âm, ASSUMED params và leakage khi áp dụng.

• Tôi đã phân biệt phần training, inference và optimisation; không tạo kết quả giả.

• Tôi không gửi secret hoặc dữ liệu không có quyền chia sẻ.

• Tôi đã cung cấp thông tin liên hệ và xác nhận có thể đối chiếu output với người tích hợp.

# 16\. Nguồn chính thức dùng để đối chiếu

Repository main: https\://github.com/MckhueVanPhuc/rohlik-data-warehouse

V4-03 Landing Handover: https\://github.com/MckhueVanPhuc/rohlik-data-warehouse/blob/main/docs/v4\_03\_landing\_handover.md

Model Integration Guide (DRAFT, tham khảo): https\://github.com/MckhueVanPhuc/rohlik-data-warehouse/blob/main/docs/model\_integration\_contract.md

Model Handover Checklist (DRAFT): https\://github.com/MckhueVanPhuc/rohlik-data-warehouse/blob/main/docs/model\_handover\_checklist.md

Canonical business contract: https\://github.com/MckhueVanPhuc/rohlik-data-warehouse/blob/main/config/contract.yaml

Lưu ý nguồn: Các bảng BT1–BT8 và dependencies trong tài liệu cũ là REFERENCE\_ONLY; khi model đã chạy xong, notebook/output/artifact thật của thành viên mới là bằng chứng kỹ thuật để chốt giao diện FINAL.

KẾT LUẬN: Một gói model tốt không nhất thiết phải có nhiều file \`.py\`. Nó phải đủ bằng chứng để người khác chạy lại đúng phiên bản, xác minh kết quả và nối với DuckDB Landing mà không thay đổi logic. Đó là điều kiện để tích hợp 8 model an toàn, nhất quán.

