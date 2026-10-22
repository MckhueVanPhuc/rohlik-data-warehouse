"""Trang "Nhập dữ liệu" (M9, D02/D13/D14): chọn bảng → tải template → tải file lên → xem lỗi → xác nhận ghi.

Cả file hoặc không ghi gì; tối đa 50.000 dòng/lần; bắt buộc ô Người nhập + Lý do (tài khoản chung admin_local).
Nút "Cập nhật kho" chạy refresh STG → Core → Mart → DQ (không chạy mô hình).
"""

from __future__ import annotations

from html import escape

import streamlit as st

from app.common import DataStatus, _readiness


def _refresh_block(ops) -> None:
    st.subheader("Cập nhật kho (refresh)")
    pending = ops.pending_refresh()
    st.caption(f"Lô nhập liệu/undo chưa vào báo cáo: **{pending}**. Refresh mất khoảng 1 phút; trong lúc chạy "
               "không thao tác trang khác. Mô hình KHÔNG chạy lại ở đây (dùng lệnh `python -m pipeline.run models`).")
    if st.button("Cập nhật kho ngay", key="entry-refresh", type="secondary"):
        from app.services.operations import WriterLockTimeout
        with st.spinner("Đang chạy STG → Core → Mart → kiểm định…"):
            try:
                rep = ops.refresh()
            except WriterLockTimeout:
                st.error("Hệ thống đang bận (pipeline hoặc DBeaver đang mở kho) – chưa ghi gì, thử lại sau.")
                return
        if rep.status == "SUCCESS":
            st.success(f"Đã cập nhật kho ({rep.run_id}). DQ: {len(rep.warned)} WARN, 0 FAIL. Tải lại trang để xem số mới.")
        else:
            st.error("Kiểm định có lỗi ERROR – báo cáo giữ bản cũ: " + ", ".join(c["check_id"] for c in rep.failed)
                     + ". Xem trang Vận hành hệ thống; nếu do lô vừa nhập thì undo lô đó rồi cập nhật lại.")


def render() -> None:
    from app.auth import require_admin
    from app.services.operations import EntryError, OperationsService, WriterLockTimeout

    require_admin()
    st.title("Nhập dữ liệu")
    st.markdown(
        '<div class="rdh-heading-copy"><p>Thêm số mới, sửa giá trị nghi sai hoặc chạy kịch bản tham số giả định. '
        'Mỗi lần nhập là một lô ghi thêm vào Landing (không sửa/xoá dòng cũ); bản mới nhất có hiệu lực sau khi '
        'cập nhật kho; hoàn tác ở trang Lịch sử lô / Undo.</p></div>', unsafe_allow_html=True)
    ops = OperationsService()
    if not ops.database.is_file():
        _readiness(DataStatus.WAREHOUSE_NOT_READY, "Chưa có kho – chạy `python -m pipeline.run init` trước.")
        return
    tables = ops.tables()
    labels = {label: name for name, label in tables}
    label = st.selectbox("1. Chọn bảng", list(labels), key="entry-table")
    name = labels[label]
    table = ops.table(name)
    st.dataframe(ops.guide(name), use_container_width=True, hide_index=True)
    st.caption(f"Khoá: {', '.join(table.business_keys)} · full-row: mỗi dòng phải đủ mọi cột · UTF-8, dấu phẩy, "
               "ngày dạng YYYY-MM-DD, số thập phân dùng dấu chấm, ô trống = NULL (chỉ ở cột không bắt buộc).")
    c1, c2 = st.columns(2)
    c1.download_button("2. Tải template CSV (chỉ tiêu đề)", ops.template(name), file_name=f"template_{name}.csv",
                       mime="text/csv", key="entry-template")
    c2.download_button("Tải mẫu có 3 dòng thật gần nhất", ops.template(name, 3), file_name=f"mau_{name}.csv",
                       mime="text/csv", key="entry-example")

    upload = st.file_uploader("3. Tải file CSV đã điền", type=["csv"], key=f"entry-file-{name}")
    if upload is not None:
        raw = upload.getvalue()
        report = ops.validate(name, raw, upload.name)
        st.subheader("4. Xem trước & kiểm tra")
        for msg in report.blocking:
            st.error(msg)
        if not report.blocking:
            m = st.columns(4)
            m[0].metric("Tổng dòng", f"{report.n_rows:,}")
            m[1].metric("Lỗi", f"{len(report.row_errors):,}")
            m[2].metric("Khoá sẽ thay bản cũ", f"{report.n_keys_replaced:,}")
            m[3].metric("Ngày sau as_of", f"{report.n_after_as_of:,}")
            if report.n_unchanged:
                st.caption(f"{report.n_unchanged:,} dòng giống hệt bản đang có (không đổi số liệu).")
            if report.n_after_as_of:
                st.caption("Dòng có ngày sau as_of chỉ được dùng khi đổi as_of trong config/settings.yaml.")
            if report.row_errors:
                st.error("File còn lỗi – chưa ghi gì. Sửa theo danh sách dưới rồi tải lại.")
                errors = report.errors_frame()
                st.dataframe(errors, use_container_width=True, hide_index=True)
                st.download_button("Tải danh sách lỗi", errors.to_csv(index=False).encode("utf-8"),
                                   file_name=f"loi_{name}.csv", mime="text/csv", key="entry-errors")
            st.dataframe(report.clean.head(50) if report.clean is not None else None, use_container_width=True,
                         hide_index=True)
        if report.ok:
            st.subheader("5. Xác nhận ghi")
            operator = st.text_input("Người nhập (bắt buộc, 2–50 ký tự)", key="entry-operator")
            reason = st.text_input("Lý do (bắt buộc, 5–200 ký tự)", key="entry-reason")
            ready = 2 <= len(operator.strip()) <= 50 and 5 <= len(reason.strip()) <= 200
            if st.button("Xác nhận ghi lô", disabled=not ready, type="primary", key="entry-confirm"):
                try:
                    info = ops.write(name, report, operator, reason)
                except WriterLockTimeout:
                    st.error("Hệ thống đang bận – chưa ghi gì, thử lại sau vài giây.")
                except EntryError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Đã ghi lô {escape(info['batch_id'])} · {info['rows']:,} dòng vào {info['table']}. "
                               "Số liệu chưa vào báo cáo – bấm \"Cập nhật kho ngay\" bên dưới.")
    st.divider()
    _refresh_block(ops)
