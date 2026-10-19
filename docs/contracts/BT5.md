# Data Contract — BT5

> Trạng thái contract: `PENDING_CONFIRMATION` — đang thu thập, chưa được phê duyệt để thiết kế dữ liệu.
> Mẫu chung: [data_contract_template.md](../data_contract_template.md)

## Quy ước điền

- `PENDING_CONFIRMATION`: chưa nhận được hoặc chưa xác minh thông tin thực tế; không đồng nghĩa với chưa thực hiện hay không có dữ liệu.
- `REFERENCE_ONLY`: thông tin tham khảo từ tài liệu, chưa được thành viên xác nhận.
- Khi trả lời, thay dấu chờ bằng thông tin thực tế và ghi người xác nhận, ngày xác nhận, bằng chứng (file/link/notebook). Việc không áp dụng cần ghi lý do và người xác nhận.
- Thêm dòng cho từng dataset, cột, thao tác và output. Đây là biểu mẫu metadata, không phải schema nghiệp vụ đã quyết định. Không gửi secrets hoặc credentials.

## Quick Handover

Trả lời nhanh sáu câu trước; dùng tên file/đường dẫn để đối chiếu với phần chi tiết A–F.

1. **Đang sử dụng những file/dataset nào?** Tên, nguồn, đường dẫn, phiên bản và file bổ sung: `PENDING_CONFIRMATION`.
2. **Model cần những cột, target, khoá nào?** Theo từng file, kèm grain nếu biết: `PENDING_CONFIRMATION`.
3. **Đã xử lý/làm sạch và tạo feature gì?** Tách đã thực hiện và dự kiến: `PENDING_CONFIRMATION`.
4. **Đã xuất những file Clean/Features/Prediction nào?** Bổ sung Optimization/Evaluation nếu có, đường dẫn và trạng thái: `PENDING_CONFIRMATION`.
5. **Còn thiếu dữ liệu gì?** Ghi cả phụ thuộc BT khác và điểm cần chốt: `PENDING_CONFIRMATION`.
6. **Có thể gửi file/notebook/script liên quan ở đâu?** Link chia sẻ/repository, quyền truy cập và lệnh chạy: `PENDING_CONFIRMATION`.

## A. Thông tin bài toán

| Thông tin | Nội dung |
| --- | --- |
| Mã bài toán | BT5 |
| Tên bài toán thực tế | PENDING_CONFIRMATION |
| Người phụ trách / liên hệ | PENDING_CONFIRMATION |
| Mục tiêu mô hình thực tế | PENDING_CONFIRMATION |
| Trạng thái thực hiện mô hình | PENDING_CONFIRMATION |
| Người xác nhận contract | PENDING_CONFIRMATION |
| Ngày xác nhận / phiên bản contract | PENDING_CONFIRMATION |
| Bằng chứng xác nhận | PENDING_CONFIRMATION |

### Tham khảo định hướng — chưa xác nhận

- Tên: `REFERENCE_ONLY` — Đo hiệu ứng nhân quả của giảm giá
- Mục tiêu: `REFERENCE_ONLY` — Ước lượng tác động nhân quả của giảm giá tới lượng bán.
- Nguồn: [Hướng dẫn Rohlik v3](../../Rohlik_Decision_Hub_Huong_dan_thuc_hien_v3.md), mục E6 – BT5; mục tiêu được diễn giải từ định hướng tài liệu.
- Thành viên xác nhận tên và mục tiêu: `PENDING_CONFIRMATION`.

Tham khảo không xác nhận dataset, cột, target, JOIN, preprocessing, output hoặc phụ thuộc thực tế.

## B. Nguồn dữ liệu

Liệt kê tất cả nguồn đang dùng, kể cả nguồn bổ sung và đầu ra từ thành viên khác. Bộ 6 CSV ban đầu chưa phải nguồn chính thức hoặc đầy đủ; file có trong workspace không chứng minh mô hình đang sử dụng nó.

| Dataset / tên file | Nguồn gốc / link | Vị trí lưu / cách truy cập | Phiên bản / snapshot | Thuộc 6 CSV ban đầu hay bổ sung (kèm căn cứ) | Khoảng thời gian dữ liệu | Người / bằng chứng xác nhận |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

- Dữ liệu nguồn còn thiếu: `PENDING_CONFIRMATION`.
- Nguồn gốc, quyền truy cập hoặc nội dung chưa xác minh: `PENDING_CONFIRMATION`.

## C. Input của mô hình

| Bảng / file input | Các cột thực sự sử dụng | Cột target hoặc không áp dụng có lý do | Business key | JOIN key / bảng liên kết | Grain (một dòng đại diện cho gì) |
| --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

Mô tả từng cột thực sự dùng, không tự bổ sung cột theo suy đoán:

| File / bảng | Tên cột thực tế | Vai trò / ý nghĩa | Kiểu dữ liệu dự kiến | Đơn vị / định dạng ngày / múi giờ | Null có hợp lệ không | Bằng chứng / trạng thái xác nhận |
| --- | --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

- Quy tắc JOIN, cardinality, xử lý khoá không khớp: `PENDING_CONFIRMATION`.

## D. Data preprocessing

Ghi riêng **ĐÃ THỰC HIỆN** và **DỰ KIẾN**. Code có trong notebook chưa chứng minh đã chạy; cần bằng chứng hoặc đầu ra.

| File / cột | Thao tác làm sạch / biến đổi / feature | Quy tắc / tham số | ĐÃ THỰC HIỆN hay DỰ KIẾN | Notebook / script / cell / phiên bản | Bằng chứng / kết quả |
| --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

- Xử lý null: `PENDING_CONFIRMATION`.
- Xử lý duplicate: `PENDING_CONFIRMATION`.
- Xử lý outlier: `PENDING_CONFIRMATION`.
- Biến đổi và tạo feature: `PENDING_CONFIRMATION`.

### File Clean / Features đã xuất hoặc dự kiến

| Loại Clean / Features | Tên file | Đường dẫn | Định dạng / phiên bản | Schema thực tế hoặc link schema | Grain | Đã có / chưa có / dự kiến | Script tạo / bằng chứng |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

## E. Model output

Liệt kê từng file/bảng Prediction, Optimization, Evaluation nếu áp dụng. Chỉ ghi ĐÃ CÓ khi có bằng chứng; chưa nhận thông tin vẫn để `PENDING_CONFIRMATION`.

| Loại output | Tên file / bảng | Đường dẫn / phiên bản | Định dạng | Schema thực tế hoặc link schema | Grain | Đã có / chưa có / dự kiến | Bằng chứng |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

| File / bảng output | Cột giá trị dự báo / tối ưu / đánh giá và ý nghĩa | Khoá liên kết | Cột ngày dự báo / ngày được dự báo | Kiểu dữ liệu / đơn vị / múi giờ | Khoảng dự báo nếu áp dụng |
| --- | --- | --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

### Cách chạy lại để tái tạo kết quả

- Notebook / script / repository và phiên bản code: `PENDING_CONFIRMATION`.
- Phiên bản input, môi trường và dependencies: `PENDING_CONFIRMATION`.
- Lệnh chạy / thứ tự cell / tham số / seed nếu có: `PENDING_CONFIRMATION`.
- Vị trí đầu ra và cách đối chiếu kết quả: `PENDING_CONFIRMATION`.
- Người chạy gần nhất / thời điểm / bằng chứng chạy thành công: `PENDING_CONFIRMATION`.

## F. Phụ thuộc và dữ liệu thiếu

| BT / bên cung cấp phụ thuộc | File / thông tin cần nhận | Tình trạng / phiên bản | Người xác nhận / bằng chứng |
| --- | --- | --- | --- |
| PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

| Nội dung cần chốt | Chi tiết | Ảnh hưởng | Người cần trả lời | Trạng thái / bằng chứng |
| --- | --- | --- | --- | --- |
| Dữ liệu còn thiếu | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |
| Giả định đã sử dụng trong mô hình | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |
| Yêu cầu dành cho Data Engineer | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |
| Điểm chưa quyết định | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION | PENDING_CONFIRMATION |

E1 chỉ tổng hợp thông tin ở bước này. Thiết kế Silver, Gold, Data Mart và triển khai xử lý dữ liệu cần thống nhất ở bước sau.
