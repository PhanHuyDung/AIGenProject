---
name: review-proposals
description: Rà soát (chỉ đọc) các đề xuất chờ duyệt trong knowledge/_cho-duyet/ - gom theo file đích, phát hiện trùng lặp, đã có trong kho, đã bị từ chối, file đích mất, quá hạn - và tóm tắt để người dùng quyết định trên app. KHÔNG tự duyệt hay từ chối. Dùng khi người dùng hỏi có gì cần duyệt hoặc muốn xem lại đề xuất. Không dùng để tạo kiến thức mới (deep-research), cập nhật (update-knowledge) hay dọn kho (knowledge-curator).
---

# Rà soát đề xuất chờ duyệt

Đầu vào (`$ARGUMENTS`): để trống (tất cả), hoặc tên lĩnh vực, hoặc đường dẫn một file đề xuất.

Skill này chỉ đọc. Nó **không** đổi `status`, không sửa file kiến thức và không tìm web. Quyền duyệt hay từ chối thuộc về người dùng, thực hiện trên tab "Chờ duyệt" của app (hoặc API `/api/proposals`).

## Bước 1 – Thu thập

1. Glob `knowledge/_cho-duyet/*.md`, đọc frontmatter (`target`, `created`, `status`, `proposed_by`, `decided`, `decision_note`) và các khối `## Đề xuất N – …`.
2. Lọc theo đầu vào: lĩnh vực → các file có `target` bắt đầu bằng `knowledge/<linh-vuc>/`; một file → chỉ file đó.
3. Với mỗi đề xuất `cho-duyet`, đọc file đích để biết nội dung hiện tại ở "Vị trí" tương ứng.

## Bước 2 – Kiểm tra từng đề xuất

Đánh dấu các trường hợp sau, mỗi trường hợp một nhãn:

- **File đích không tồn tại** → không duyệt được, cần nghiên cứu lại hoặc sửa `target`.
- **Đã có trong file đích**: "Nội dung đề xuất" đã xuất hiện trong file đích (ví dụ đã được duyệt ở lần khác) → đề nghị từ chối với ghi chú "đã có".
- **Trùng đề xuất khác**: cùng `target`, cùng "Vị trí" và nội dung gần giống trong file đề xuất khác đang chờ → gom lại, chỉ cần duyệt một.
- **Đã bị từ chối trước đó**: nội dung giống một đề xuất có `status: tu-choi` → nêu lại lý do từ chối cũ để người dùng cân nhắc.
- **Cũ**: `created` quá 30 ngày mà chưa quyết định → nhắc; nguồn có thể đã thay đổi.
- **Thiếu trường**: không có "Nội dung đề xuất", "Nguồn" hoặc "Lý do chưa chắc chắn" → không đủ thông tin để duyệt.
- **Mâu thuẫn với kho**: nội dung đề xuất trái với dữ kiện có nguồn trong file đích → nêu cả hai.

Không tự kết luận đúng sai của nội dung; chỉ nêu dữ kiện để người dùng quyết.

## Bước 3 – Báo cáo

Trả về bằng tiếng Việt, ngắn gọn, theo thứ tự ưu tiên:

1. Dòng đầu: "**Cần bạn duyệt:** N đề xuất", rồi tổng theo lĩnh vực và file đích.
2. Với mỗi file đích: danh sách đề xuất, mỗi đề xuất một dòng gồm số thứ tự, tiêu đề, loại, lý do chưa chắc chắn, và các nhãn ở bước 2.
3. Gợi ý thao tác (không thực hiện): nên duyệt / nên từ chối (kèm lý do) / cần nghiên cứu thêm (giao agent nào).
4. Nhắc: "Mở tab Chờ duyệt trong app để duyệt hoặc từ chối."

Nếu không có đề xuất nào: báo "Không có đề xuất chờ duyệt" và dừng.
