---
name: knowledge-report
description: Tổng hợp kiến thức ĐÃ CÓ trong kho của một lĩnh vực thành báo cáo ngắn (chỉ đọc, trả lời trong chat; chỉ lưu file khi được yêu cầu) gồm xu hướng chính, điểm mới, rủi ro, nguồn và đề xuất việc cần làm tiếp. Dùng khi người dùng muốn báo cáo, tóm tắt, tổng kết, điểm lại một lĩnh vực. Không tìm kiếm web và không sửa kho; muốn có thông tin mới thì chạy update-knowledge trước, muốn dọn kho thì dùng knowledge-curator.
---

# Báo cáo kiến thức theo lĩnh vực

Đầu vào (`$ARGUMENTS`): tên lĩnh vực, ví dụ `ai` hoặc `knowledge/ai/`. Có thể kèm khoảng thời gian cho "điểm mới" (mặc định 30 ngày gần nhất).

Skill này chỉ đọc kho kiến thức, không tìm kiếm web và không thêm dữ kiện ngoài kho.

## Bước 1 – Thu thập

1. Glob `knowledge/<linh-vuc>/*.md`. Không có file nào thì báo lại và đề xuất chạy `deep-research`.
2. Đọc toàn bộ từng file: frontmatter, "Tóm tắt", "Nhận định", "Lịch sử thay đổi", và phần "Chi tiết" liên quan.
3. Ghi lại file nào có `last_updated` quá 90 ngày hoặc `confidence: thấp`.

## Bước 2 – Tổng hợp

- **Xu hướng chính**: các hướng thay đổi xuất hiện ở nhiều file hoặc được nhiều nguồn xác nhận. Mỗi xu hướng nêu căn cứ và file chứa nó.
- **Điểm mới**: nội dung được thêm hoặc sửa trong khoảng thời gian yêu cầu, lấy từ `last_updated` và "Lịch sử thay đổi".
- **Rủi ro**: rủi ro của chính lĩnh vực được nêu trong các file, và rủi ro về độ tin cậy của kho (thông tin cũ, mức chắc chắn thấp, nguồn mâu thuẫn, chỗ "chưa có nguồn xác nhận").
- Hai file mâu thuẫn nhau thì nêu cả hai, không tự chọn.
- Giữ nguyên mức độ chắc chắn ghi trong file gốc; không nâng lên khi tổng hợp.

## Bước 3 – Viết báo cáo

Theo mẫu trong [mau-bao-cao.md](mau-bao-cao.md), dài không quá khoảng 500 từ, không tính mục "Nguồn". Mỗi ý kèm liên kết tới file kiến thức chứa nó: khi trả lời trong chat dùng đường dẫn từ gốc dự án (`knowledge/<linh-vuc>/<ten-file>.md`); khi lưu vào `knowledge/_bao-cao/` dùng đường dẫn tương đối như trong mẫu (`../<linh-vuc>/...`). Số liệu phải giữ nguyên thời điểm và đơn vị như trong file gốc.

## Bước 4 – Trả kết quả

- Mặc định: trả báo cáo trong câu trả lời, không ghi file.
- Người dùng yêu cầu lưu: ghi vào `knowledge/_bao-cao/<linh-vuc>-YYYY-MM-DD.md`. Thư mục bắt đầu bằng `_` không phải là lĩnh vực; file trong đó không cần frontmatter kiến thức và không đưa vào `knowledge/_index.md`.

Cuối báo cáo, đề xuất file nào nên chạy `update-knowledge` và chủ đề nào còn thiếu nên chạy `deep-research`.
