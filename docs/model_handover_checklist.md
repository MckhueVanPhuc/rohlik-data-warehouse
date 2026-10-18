# Checklist bàn giao model — BT1–BT8

**Ngày:** 18/10/2026. **Trạng thái:** đang thu thập, chưa xác nhận nhận đủ gói nào.
Dùng cùng [Model Integration Contract](model_integration_contract.md) và
[Data Contract template](data_contract_template.md).

## Thành viên ML cần gửi

Gửi những gì đang có; không cần viết lại notebook hay đổi thuật toán/preprocessing.
Thông tin đã điền ở contract thì dẫn link/cell, không nhập lại. Thiếu gì cứ ghi rõ.

- [ ] Notebook `.ipynb` hoàn chỉnh, kèm code/module ngoài notebook nếu có.
- [ ] Toàn bộ dataset/file notebook dùng hoặc tạo: raw, clean, features, predictions,
  optimization/evaluation và file bổ sung nếu có. Chỉ file không áp dụng mới ghi N/A
  kèm lý do; không tạo dữ liệu hoặc output giả để đủ checklist.
- [ ] Tên/nguồn gốc, vị trí/link truy cập và phiên bản dữ liệu; chỉ rõ file nào là
  input, file trung gian hay output, file nào nhận từ BT khác.
- [ ] Hướng dẫn chạy hoặc thứ tự cell, tham số/seed quan trọng, output mong đợi;
  nêu cell cần mount Google Drive, tải file hoặc thao tác thủ công.
- [ ] Dependencies đặc thù/phiên bản Python và thư viện đã dùng, cell pip install,
  yêu cầu CPU/GPU/dịch vụ ngoài nếu có; có thể gửi thông tin môi trường đang có.
- [ ] Model/encoder/scaler đã lưu **nếu có**, phiên bản và cách load. Nếu chưa lưu
  hoặc phương pháp không dùng artifact thì ghi rõ, không bắt tạo lại ngay.
- [ ] Điểm chưa hoàn thiện, dữ liệu còn thiếu, lỗi đã biết, giả định và hạn chế.

Kèm mã BT, tên người phụ trách và link Data Contract tương ứng. Không gửi mật khẩu,
token hoặc dữ liệu nhạy cảm vào tài liệu/Git. Nếu không thể chuyển một dataset,
ghi rõ hạn chế quyền và cách cấp quyền/tái tạo để người nhận xác minh.

## Người nhận kiểm tra

- [ ] Mở được notebook và link/file, nhận đủ theo inventory hoặc ghi phần thiếu.
- [ ] Xác minh cách chạy lại, input/output và môi trường với chủ model; ghi bằng chứng.
- [ ] Ghi mapping, phụ thuộc và trở ngại; chưa đủ thì giữ PENDING, không tự suy diễn.
- [ ] Thống nhất phần việc chuyển notebook với người tích hợp; chưa triển khai Model Runner.

## Theo dõi BT1–BT8

`PENDING` nghĩa là chưa có bằng chứng đã nhận/xác minh tại đây, không kết luận thành
viên chưa làm. “Đã nhận” và “đã chạy lại/được nghiệm thu” là hai trạng thái khác nhau.
Chỉ cập nhật khi có người nhận, ngày, phiên bản và link bằng chứng. Artifact không
áp dụng có thể đổi N/A sau khi chủ model xác nhận lý do.

| BT / Data Contract | Notebook/code | Dữ liệu và output | Nguồn + cách chạy | Dependencies + artifact/N/A | Điểm còn thiếu | Người nhận / ngày / bằng chứng | Tái lập / nghiệm thu |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [BT1](contracts/BT1.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT2](contracts/BT2.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT3](contracts/BT3.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT4](contracts/BT4.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT5](contracts/BT5.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT6](contracts/BT6.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT7](contracts/BT7.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| [BT8](contracts/BT8.md) | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

Người tích hợp sẽ kiểm tra notebook, xác nhận mapping với DE, tách inference/tối ưu
khi phù hợp, đối chiếu kết quả rồi mới publish cho Streamlit. Đây là quy trình dự
kiến; checklist không chứng minh đã triển khai hoặc tích hợp thành công.
