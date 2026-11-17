---
name: deep-research
description: Quy trình nghiên cứu sâu một câu hỏi hoặc chủ đề từ đầu đến cuối - chia câu hỏi con, chọn agent theo lĩnh vực, tìm ít nhất 5 nguồn uy tín, đối chiếu, viết file kiến thức trong knowledge/ và cập nhật _index.md. Dùng khi người dùng muốn nghiên cứu, tìm hiểu, tổng quan một chủ đề CHƯA có trong kho kiến thức. Chủ đề đã có file thì dùng update-knowledge.
---

# Nghiên cứu sâu

Đầu vào: câu hỏi hoặc chủ đề cần nghiên cứu (`$ARGUMENTS`), có thể kèm tên lĩnh vực.

Bạn là người điều phối. Việc tìm và đọc nguồn do agent nghiên cứu của lĩnh vực làm; bạn chia việc, kiểm tra kết quả và chịu trách nhiệm về file cuối cùng. Mọi quy tắc trong `CLAUDE.md` đều áp dụng.

## Bước 1 – Xác định câu hỏi con

1. Viết lại câu hỏi chính thành một câu rõ ràng: đối tượng, phạm vi địa lý, khoảng thời gian.
2. Chia thành 3–7 câu hỏi con cụ thể, trả lời được bằng dữ kiện có nguồn. Ví dụ với một thị trường: quy mô và tăng trưởng, cơ cấu theo phân khúc hoặc quốc gia, các bên tham gia chính, quy định pháp lý, xu hướng, rủi ro.
3. Câu hỏi quá rộng để gói trong một file thì thu hẹp lại và ghi rõ phần đã bỏ ra ngoài phạm vi.

## Bước 2 – Chọn agent theo lĩnh vực

1. Dùng Glob liệt kê `.claude/agents/*-researcher.md` và đọc `description` của từng agent.
2. Chọn đúng một agent có phạm vi bao trùm chủ đề. Người dùng đã chỉ định lĩnh vực thì dùng agent của lĩnh vực đó.
3. Chủ đề nằm giữa hai lĩnh vực: chọn lĩnh vực mà phần lớn câu hỏi con thuộc về. Không ép chủ đề vào một agent có phạm vi không bao trùm nó.
4. Không agent nào phù hợp: đây là lĩnh vực mới. Chạy skill `create-domain-agent` để tạo agent và thư mục kiến thức, rồi quay lại bước này.

## Bước 3 – Kiểm tra kho kiến thức

Đọc `knowledge/_index.md` và Grep từ khoá chính trong `knowledge/<linh-vuc>/`. Chủ đề đã có file thì dừng và chuyển sang skill `update-knowledge` cho file đó, không tạo file trùng.

## Bước 4 – Giao việc cho agent

Gọi agent đã chọn bằng tool `Agent` (tên cũ: `Task`) với `subagent_type` là tên agent. Lời giao việc phải tự đủ nghĩa vì agent không thấy cuộc trò chuyện này, gồm:

- Câu hỏi chính và danh sách câu hỏi con.
- Đường dẫn file cần ghi: `knowledge/<linh-vuc>/<ten-chu-de>.md`.
- Yêu cầu **ít nhất 5 nguồn uy tín khác nhau**, thuộc ít nhất 3 tổ chức độc lập, đã đọc trang gốc.
- Ngày hôm nay, để ghi `last_updated` và `accessed`.
- Nhắc lại: thiếu dữ liệu thì ghi "chưa có nguồn xác nhận", không bịa số liệu.

Không gọi được subagent (hoặc agent vừa được tạo ở bước 2.4 nên chưa được nạp trong phiên này) thì tự đọc file agent đó và làm đúng theo hướng dẫn trong đó, kể cả danh sách nguồn và quy tắc riêng.

## Bước 5 – Đối chiếu và xử lý mâu thuẫn

Đọc file agent vừa ghi và kiểm tra:

1. **Đủ nguồn**: ít nhất 5 nguồn uy tín theo tiêu chí của `CLAUDE.md` và của agent. Nguồn không đạt (diễn đàn, blog không rõ tác giả, trang tổng hợp) không được tính.
2. **Mỗi dữ kiện có nguồn**: mọi số liệu trong "Chi tiết" có chú thích trỏ xuống mục "Nguồn", kèm thời điểm và đơn vị.
3. **Mâu thuẫn giữa các nguồn**: với mỗi cặp số liệu lệch nhau, tìm lý do (khác kỳ, khác định nghĩa, khác phạm vi, khác đơn vị tiền tệ).
   - Giải thích được: giữ số liệu của nguồn gốc hoặc nguồn mới hơn, ghi lý do loại số liệu kia.
   - Không giải thích được: không ghi số nào vào file như dữ kiện; ghi cả hai thành đề xuất chờ duyệt (xem mục 6). Không tự chọn một bên, không lấy trung bình.
4. **Câu hỏi con**: mỗi câu đã được trả lời, hoặc ghi rõ "chưa có nguồn xác nhận".
5. **Dữ kiện và nhận định tách riêng**: suy luận chỉ nằm ở mục "Nhận định", mỗi nhận định có mức độ chắc chắn.
6. **Chọn lọc và chờ duyệt**: theo mục "Duyệt thay đổi" trong `CLAUDE.md`, file kiến thức chỉ chứa nội dung chắc chắn. Chuyển ra khỏi file và ghi thành đề xuất trong `knowledge/_cho-duyet/`: dữ kiện chỉ có một nguồn không phải nguồn chính thức gốc, số liệu chỉ đọc được qua bên dẫn lại, số liệu mâu thuẫn chưa giải thích được, phỏng đoán và nhận định mức `thấp`. Ở chỗ bị chuyển đi, ghi "chưa có nguồn xác nhận (có đề xuất chờ duyệt)". Không tự đổi `status` của đề xuất.

Thiếu điểm nào thì giao lại cho agent đúng phần còn thiếu, tối đa 2 vòng. Sau 2 vòng vẫn thiếu thì giữ file, hạ `confidence` và ghi rõ phần thiếu.

## Bước 6 – Hoàn thiện file kiến thức

File cuối cùng phải có:

- Frontmatter đủ `title`, `domain`, `last_updated`, `sources` (mỗi nguồn có `url`, `title`, `accessed`), `confidence`.
- Bốn mục theo thứ tự: "Tóm tắt", "Chi tiết", "Nhận định", "Nguồn".
- `confidence` của cả file không cao hơn mức của nhận định quan trọng nhất.

## Bước 7 – Cập nhật mục lục

Kiểm tra `knowledge/_index.md` đã có đúng một dòng cho file này dưới mục lĩnh vực tương ứng, theo định dạng ghi ở đầu file đó. Thiếu hoặc sai thì sửa.

## Bước 8 – Báo cáo

Trả về, mở đầu bằng dòng "**Cần bạn duyệt:** N đề xuất" nếu N > 0 (kèm đường dẫn file đề xuất và nhắc mở tab "Chờ duyệt" trong app):

- Đường dẫn file và agent đã dùng.
- Tóm tắt 3–5 câu.
- Số nguồn và mức độ chắc chắn.
- Các mâu thuẫn đã gặp và cách xử lý.
- Số đề xuất chờ duyệt và đường dẫn file trong `knowledge/_cho-duyet/`.
- Câu hỏi con chưa trả lời được.
