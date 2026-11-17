---
name: update-knowledge
description: Cập nhật kiến thức ĐÃ CÓ trong kho - nhận một lĩnh vực (ví dụ ai hoặc knowledge/ai/) hoặc một file cụ thể, tìm thông tin mới hơn last_updated, sửa nội dung và ghi "Lịch sử thay đổi" cuối file. Dùng khi người dùng muốn làm mới, cập nhật, kiểm tra lại một file hoặc cả một lĩnh vực, hoặc khi chạy cập nhật định kỳ. Chủ đề chưa có file thì dùng deep-research.
---

# Cập nhật kiến thức

Đầu vào (`$ARGUMENTS`): một trong hai dạng

- **Lĩnh vực**: tên thư mục như `ai`, `tai-chinh`, hoặc đường dẫn `knowledge/ai/`.
- **File**: tên hoặc đường dẫn một file, ví dụ `knowledge/ai/mo-hinh-ngon-ngu.md`.

Không có đầu vào, hoặc đầu vào không khớp thư mục hay file nào: dừng và báo lại, không tự chọn.

## Bước 1 – Xác định file cần cập nhật

- **Một file**: chỉ cập nhật file đó.
- **Một lĩnh vực**: Glob `knowledge/<linh-vuc>/*.md`, đọc `last_updated` của từng file và xếp từ cũ nhất. Cập nhật tối đa 5 file cũ nhất trong một lần chạy; các file còn lại liệt kê trong báo cáo. Lĩnh vực chưa có file nào thì báo lại và dừng.

## Bước 2 – Đọc file cũ

Với mỗi file, đọc toàn bộ và ghi lại:

- `last_updated`: mốc thời gian để tìm thông tin mới.
- Các số liệu, phiên bản, trạng thái dễ thay đổi theo thời gian.
- Các chỗ ghi "chưa có nguồn xác nhận" và các nhận định có mức độ chắc chắn `thấp`.

## Bước 3 – Tìm thông tin mới

Giao cho agent nghiên cứu của lĩnh vực (`.claude/agents/<...>-researcher.md` có `description` khớp với `domain` của file). Lời giao việc gồm: đường dẫn file, mốc `last_updated`, ngày hôm nay, và danh sách ở bước 2. Agent cần:

1. Tìm thông tin công bố **sau** `last_updated`: số liệu kỳ mới, phiên bản mới, thay đổi chính sách, sự kiện lớn.
2. Kiểm tra lại các nguồn đã ghi: còn truy cập được không, nội dung có bị sửa không.
3. Thử lấp các chỗ "chưa có nguồn xác nhận".

Không gọi được subagent thì tự đọc file agent đó và làm theo.

## Bước 4 – Phân loại và cập nhật nội dung

Chọn lọc trước khi ghi: chỉ giữ thông tin liên quan trực tiếp tới chủ đề của file. Với mỗi thay đổi dự định, phân loại theo mục "Duyệt thay đổi" trong `CLAUDE.md`:

- **Chắc chắn** (ít nhất 2 nguồn uy tín độc lập cùng xác nhận hoặc nguồn chính thức gốc, không mâu thuẫn, đã đọc trang gốc): ghi thẳng vào file theo các quy tắc bên dưới.
- **Chưa chắc chắn** (một nguồn, nguồn mâu thuẫn, xoá hoặc đảo ngược nội dung cũ, phỏng đoán hay nhận định mức `thấp`, số liệu chỉ có qua bên dẫn lại, đổi `confidence` của cả file): **không sửa file kiến thức**. Ghi thành đề xuất trong `knowledge/_cho-duyet/` đúng định dạng của `CLAUDE.md` và chờ người dùng duyệt trên giao diện app. Đọc `knowledge/_cho-duyet/` trước để không lặp lại đề xuất đang chờ hoặc đã bị từ chối.

Không tự đổi `status` của đề xuất và không tự áp dụng đề xuất.

Quy tắc ghi cho phần chắc chắn:

- Thông tin mới thay thế thông tin cũ: sửa ở mục "Chi tiết", kèm nguồn mới. Số liệu cũ còn giá trị so sánh thì giữ lại, ghi rõ kỳ của nó.
- Thông tin cũ vẫn đúng: giữ nguyên, cập nhật ngày `accessed` của nguồn đã kiểm tra lại.
- Nguồn không còn truy cập được: giữ dòng nguồn, ghi chú "không còn truy cập được (kiểm tra ngày YYYY-MM-DD)"; nếu dữ kiện chỉ dựa vào nguồn đó thì hạ mức độ chắc chắn.
- Thông tin mới mâu thuẫn với thông tin cũ mà không rõ bên nào đúng: giữ nguyên nội dung cũ trong file và ghi thông tin mới thành đề xuất chờ duyệt.
- Xem lại mục "Tóm tắt" và "Nhận định" cho khớp với nội dung mới.
- Gỡ dòng "Cần cập nhật" do `knowledge-curator` đặt, nếu có.

Frontmatter:

- `last_updated`: ngày hôm nay, **chỉ khi** đã thực sự kiểm tra lại nội dung, kể cả khi kết quả là không có gì mới.
- `sources`: thêm nguồn mới, cập nhật `accessed`.
- `confidence`: giữ nguyên; nếu thấy cần đổi thì ghi thành đề xuất chờ duyệt.

## Bước 5 – Ghi "Lịch sử thay đổi"

Thêm vào **cuối file**, sau mục "Nguồn". Chưa có mục này thì tạo; đã có thì thêm dòng mới lên đầu danh sách.

```markdown
## Lịch sử thay đổi

- YYYY-MM-DD — Tóm tắt thay đổi: thêm gì, sửa gì (giá trị cũ → giá trị mới), bỏ gì và vì sao.
```

Không tìm thấy thông tin mới thì vẫn ghi một dòng: `- YYYY-MM-DD — Đã kiểm tra lại, không có thay đổi.`

Không xoá hay sửa các dòng lịch sử cũ.

## Bước 6 – Cập nhật mục lục

Sửa dòng tương ứng trong `knowledge/_index.md`: ngày cập nhật, độ chắc chắn, câu tóm tắt nếu đã đổi, và gỡ nhãn `— CẦN CẬP NHẬT`.

## Bước 7 – Báo cáo

Mở đầu bằng dòng "**Cần bạn duyệt:** N đề xuất" nếu N > 0, kèm nhắc mở tab "Chờ duyệt" trong app. Sau đó:

- Các file đã cập nhật, mỗi file một dòng nêu thay đổi chính.
- Các file đã kiểm tra nhưng không có gì mới.
- Các file chưa xử lý trong lần chạy này.
- **Đề xuất chờ duyệt**: số đề xuất, đường dẫn file trong `knowledge/_cho-duyet/`, và một dòng tóm tắt cho mỗi đề xuất.
- Nguồn hỏng và mâu thuẫn tìm thấy.
