"""Trang "Lịch sử lô / Undo" (M9 mục 10): danh sách lô nguồn + upload, người nhập/lý do, soft undo."""

from __future__ import annotations

import streamlit as st

from app.common import DataStatus, _readiness
from app.views.entry import _refresh_block


def render() -> None:
    from app.auth import require_admin
    from app.services.operations import EntryError, OperationsService, WriterLockTimeout

    require_admin()
    st.title("Lịch sử lô / Undo")
    st.markdown(
        '<div class="rdh-heading-copy"><p>Mọi lần nạp nguồn và nhập liệu. Undo = ghi sự kiện UNDONE (không xoá dòng); '
        'sau khi cập nhật kho, bản trước đó có hiệu lực trở lại. Chỉ undo được lô UPLOAD đang COMPLETED.</p></div>',
        unsafe_allow_html=True)
    ops = OperationsService()
    if not ops.database.is_file():
        _readiness(DataStatus.WAREHOUSE_NOT_READY, "Chưa có kho – chạy `python -m pipeline.run init` trước.")
        return
    df = ops.batches()
    if df.empty:
        st.info("Chưa có lô nào (hoặc kho chưa chạy refresh lần đầu).")
        return
    m = st.columns(4)
    m[0].metric("Lô upload", int((df["batch_type"] == "UPLOAD").sum()))
    m[1].metric("Lô đã undo", int((df["status"] == "UNDONE").sum()))
    m[2].metric("Chờ cập nhật kho", ops.pending_refresh())
    runs = ops.pipeline_runs(50)
    ok = runs[(runs["status"] == "SUCCESS") & runs["command"].isin(["refresh", "init", "all", "ui-refresh"])] if not runs.empty else runs
    m[3].metric("Refresh gần nhất (UTC)", str(ok["finished_at"].iloc[0])[:16] if not ok.empty else "chưa có")
    f1, f2, f3 = st.columns(3)
    t = f1.selectbox("Bảng", ["Tất cả", *sorted(df["table_name"].dropna().unique())], key="batch-table")
    k = f2.selectbox("Loại", ["Tất cả", "UPLOAD", "SOURCE"], key="batch-type")
    s = f3.selectbox("Trạng thái", ["Tất cả", "COMPLETED", "UNDONE"], key="batch-status")
    view = df
    if t != "Tất cả":
        view = view[view["table_name"] == t]
    if k != "Tất cả":
        view = view[view["batch_type"] == k]
    if s != "Tất cả":
        view = view[view["status"] == s]
    st.dataframe(view, use_container_width=True, hide_index=True)

    uploads = df[(df["batch_type"] == "UPLOAD")]
    if uploads.empty:
        return
    st.subheader("Xem chi tiết / hoàn tác một lô")
    batch_id = st.selectbox("Chọn lô upload", uploads["batch_id"].tolist(), key="batch-pick")
    rows = ops.batch_rows(batch_id)
    st.caption(f"{len(rows):,} dòng đầu của lô (tối đa 500)")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    status = uploads.loc[uploads["batch_id"] == batch_id, "status"].iloc[0]
    if status != "COMPLETED":
        st.info(f"Lô đang ở trạng thái {status} – không undo được.")
        return
    with st.form("undo-form"):
        st.warning("Undo không xoá dữ liệu: lô bị đánh dấu UNDONE và bị bỏ qua từ lần cập nhật kho kế tiếp. "
                   "Nếu khoá đó còn lô upload mới hơn thì số hiển thị vẫn là của lô mới hơn.")
        operator = st.text_input("Người undo (bắt buộc, 2–50 ký tự)")
        reason = st.text_input("Lý do undo (bắt buộc, 5–200 ký tự)")
        submitted = st.form_submit_button("Xác nhận undo lô này")
    if submitted:
        try:
            ops.undo(batch_id, operator, reason)
        except WriterLockTimeout:
            st.error("Hệ thống đang bận – chưa ghi gì, thử lại sau.")
        except EntryError as exc:
            st.error(str(exc))
        else:
            st.success(f"Đã undo lô {batch_id}. Bấm \"Cập nhật kho ngay\" để báo cáo phản ánh thay đổi.")
    st.divider()
    _refresh_block(ops)
