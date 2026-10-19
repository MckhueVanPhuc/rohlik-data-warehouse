# Checklist bàn giao model — BT1–BT8

**Cập nhật:** 19/10/2026. **Trạng thái:** chưa xác minh nhận đủ gói kỹ thuật nào.
Dùng cùng [Model Integration Guide](model_integration_contract.md). Checklist này
ghi nhận bằng chứng bàn giao thực tế; không phải biểu mẫu Data Contract bắt buộc.

## Thành viên ML cần gửi

Gửi những gì đang có; không cần viết lại notebook hay đổi thuật toán/preprocessing.
Thông tin đã có bằng chứng thì dẫn link/cell, không nhập lại. Thiếu gì cứ ghi rõ.

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

Kèm mã BT, tên người phụ trách và link notebook/source/output tương ứng. Không gửi mật khẩu,
token hoặc dữ liệu nhạy cảm vào tài liệu/Git. Nếu không thể chuyển một dataset,
ghi rõ hạn chế quyền và cách cấp quyền/tái tạo để người nhận xác minh.

## Người nhận kiểm tra

- [ ] Mở được notebook và link/file, nhận đủ theo inventory hoặc ghi phần thiếu.
- [ ] Xác minh cách chạy lại, input/output và môi trường với chủ model; ghi bằng chứng.
- [ ] Ghi mapping, phụ thuộc và trở ngại; chưa đủ bằng chứng thì ghi rõ, không tự suy diễn.
- [ ] Thống nhất phần việc chuyển notebook với người tích hợp; chưa triển khai Model Runner.

## Theo dõi BT1–BT8

`CHƯA XÁC MINH` nghĩa là chưa có bằng chứng đã nhận/xác minh tại đây, không kết luận thành
viên chưa làm. “Đã nhận” và “đã chạy lại/được nghiệm thu” là hai trạng thái khác nhau.
Chỉ cập nhật khi có người nhận, ngày, phiên bản và link bằng chứng. Artifact không
áp dụng có thể đổi N/A sau khi chủ model xác nhận lý do.

| BT | Notebook/code | Dữ liệu và output | Nguồn + cách chạy | Dependencies + artifact/N/A | Điểm còn thiếu | Người nhận / ngày / bằng chứng | Tái lập / nghiệm thu |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BT1 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT2 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT3 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT4 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT5 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT6 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT7 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |
| BT8 | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH | CHƯA XÁC MINH |

Người tích hợp sẽ kiểm tra notebook, xác nhận mapping với DE, tách inference/tối ưu
khi phù hợp, đối chiếu kết quả rồi mới publish cho Streamlit. Đây là quy trình dự
kiến; checklist không chứng minh đã triển khai hoặc tích hợp thành công.
