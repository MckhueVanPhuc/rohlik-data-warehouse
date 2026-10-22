# Mô hình BT1–BT8

Model runner nằm trong `src/models/`; registry trung tâm định nghĩa DAG, input, prediction output và evaluation output. Tham số được version tại `config/model_params/BT1.json` … `BT8.json`.

## Danh mục output

| Model | Prediction output | Evaluation output chính |
| --- | --- | --- |
| BT1 | `fc_orders` | backtest, model comparison |
| BT2 | `staff_plan`, `driver_plan` | comparisons, sensitivity, solve log |
| BT3 | `lost_sales`, summary, monthly | model comparison |
| BT4 | `fc_sku` | backtest, quantile ratios, model comparison |
| BT5 | `promo_effect`, `promo_type_effect` | method comparison |
| BT6 | `replenishment` | backtest, policy comparisons, sensitivity |
| BT7 | `markdown_plan`, `markdown_summary` | policy comparisons, sensitivity |
| BT8 | `growth_curves`, `growth_projection`, milestones | model comparison |

Thứ tự chạy chuẩn là `BT1, BT3, BT5, BT8, BT2, BT4, BT6, BT7`.

## Mục tiêu và implementation

| Model | Mục tiêu | Implementation/evaluation hiện có |
| --- | --- | --- |
| BT1 | Forecast đơn hàng theo kho | LightGBM quantile; SeasonalNaive baseline; MAPE và P90 coverage. |
| BT2 | Kế hoạch nhân sự/tài xế | Rule baseline và MIP bằng CBC; comparison, sensitivity, solver proof/log. |
| BT3 | Ước lượng lost sales | LightGBM Tweedie; moving-average baseline; WMAE/WMAPE/RMSE. |
| BT4 | Forecast nhu cầu SKU | LightGBM L1 + bốn baseline; WMAE/WMAPE/RMSE, bias và pinball P90. |
| BT5 | Đo promo effect | So sánh các phương pháp trong evaluation output. |
| BT6 | Khuyến nghị replenishment | Backtest, policy comparison và sensitivity. |
| BT7 | Kế hoạch markdown | Policy comparison và sensitivity. |
| BT8 | Đường cong tăng trưởng | Linear/log/logistic/Gompertz; chọn bằng MAPE sáu tháng cuối. |

## Đánh giá và chạy

```powershell
.\.venv\Scripts\python.exe -m pipeline.run evaluate
.\.venv\Scripts\python.exe -m pipeline.run models
```

Các giá trị mặc định/frozen trong params là điểm khởi đầu có thể tái lập, không phải bằng chứng model đã được kiểm định trên mọi môi trường. Chạy `evaluate` trên snapshot dữ liệu đích, lưu metrics và phê duyệt trước khi dùng output để ra quyết định.

## Contract tích hợp

- Input đến từ bảng Core/Mart đã đạt DQ, không đọc file tùy ý trong model.
- Output đúng schema và tên trong registry; metadata gắn model version, params, seed và thời điểm dữ liệu.
- Import output bên ngoài đi qua `pipeline.run import-outputs`.
- Không tạo forecast giả khi output thiếu; dashboard biểu diễn trạng thái unavailable/pending.
- Model execution là tác vụ CLI; Streamlit không khởi chạy runner.

Test tích hợp cần warehouse thật có thể skip trong môi trường source-only. Skip phải được báo cáo riêng, không ghi là pass.

## Reproducibility và giới hạn

Seed mặc định là 42; số worker được khóa theo params để giảm sai lệch. Mỗi run cần lưu snapshot/as-of, code version, params và metrics. Missing input phải làm model fail rõ ràng hoặc output trạng thái unavailable theo contract, không suy đoán dữ liệu.

Model phụ thuộc chất lượng nguồn, giả định cost/workforce và thời kỳ backtest đã cấu hình. Metrics trong code là cơ chế đánh giá; tài liệu này không công bố giá trị metric thực tế vì cleanup này chưa chạy real-data acceptance.
