---
name: create-domain-agent
description: Tạo agent nghiên cứu cho một lĩnh vực MỚI chưa có agent - tìm hiểu lĩnh vực (nguồn uy tín, thuật ngữ chính, chỉ số quan trọng), tạo file .claude/agents/<linh-vuc>-researcher.md theo mẫu các agent hiện có và tạo thư mục knowledge/<linh-vuc>/. Dùng khi người dùng muốn nghiên cứu một lĩnh vực mà không agent *-researcher nào bao trùm, hoặc khi deep-research không chọn được agent.
---

# Tạo agent cho lĩnh vực mới

Đầu vào (`$ARGUMENTS`): tên lĩnh vực mới, ví dụ "thương mại điện tử", "y tế".

## Bước 1 – Kiểm tra lĩnh vực có thực sự mới không

1. Đặt tên thư mục (slug): không dấu, chữ thường, nối bằng gạch ngang, ngắn gọn. Ví dụ: "thương mại điện tử" → `thuong-mai-dien-tu`.
2. Glob `.claude/agents/*-researcher.md` và đọc `description` cùng mục "Phạm vi" của từng agent. Đã có agent bao trùm lĩnh vực này thì dừng và báo tên agent đó.
3. Kiểm tra `knowledge/<slug>/` và `.claude/agents/<slug>-researcher.md` chưa tồn tại. Đã tồn tại thì dừng và báo lại, không ghi đè.

## Bước 2 – Tìm hiểu lĩnh vực

Dùng WebSearch và WebFetch, theo quy tắc nguồn của `CLAUDE.md`. Cần thu được:

1. **Nguồn uy tín của lĩnh vực**, xếp theo thứ tự ưu tiên:
   - Cơ quan quản lý và tổ chức tiêu chuẩn (quốc tế và Việt Nam).
   - Nguồn dữ liệu gốc: thống kê chính thức, báo cáo của doanh nghiệp đầu ngành.
   - Tổ chức nghiên cứu và hãng phân tích được trích dẫn rộng rãi, có nêu phương pháp.
   - Tạp chí khoa học, hội nghị, báo chuyên ngành lớn.

   Chỉ đưa vào danh sách những nguồn bạn đã mở và xác nhận là tồn tại, còn hoạt động. Cũng ghi các loại nguồn kém tin cậy đặc thù của lĩnh vực cần tránh.
2. **Thuật ngữ chính**: 10–20 thuật ngữ, kèm tên tiếng Anh và giải thích một câu.
3. **Chỉ số quan trọng**: các chỉ số thường dùng để đo lĩnh vực này, đơn vị, và ai công bố.
4. **Cạm bẫy khi nghiên cứu**: các nhầm lẫn hay gặp, ví dụ định nghĩa khác nhau giữa các hãng, số ước tính với số thực tế, số do doanh nghiệp tự công bố.
5. **Ranh giới** với các lĩnh vực đã có agent.

## Bước 3 – Tạo file agent

Đọc `game-researcher.md` (có đủ các mục, kể cả "Thuật ngữ và chỉ số") và một agent khác để lấy mẫu, rồi ghi `.claude/agents/<slug>-researcher.md` với đúng cấu trúc đó:

- Frontmatter:
  - `name: <slug>-researcher`
  - `description`: nêu lĩnh vực, các chủ đề con, thư mục ghi kết quả, và khi nào dùng. Phải đủ rõ để phân biệt với các agent khác.
  - `tools: WebSearch, WebFetch, Read, Write, Edit, Glob, Grep`
- Đoạn mở đầu nêu vai trò và thư mục `knowledge/<slug>/`.
- "Phạm vi": các chủ đề con, và chủ đề nào thuộc agent khác.
- "Nguồn": danh sách ở bước 2, theo thứ tự ưu tiên, kèm nguồn không được dùng.
- "Thuật ngữ và chỉ số": kết quả mục 2 và 3 của bước 2.
- "Quy trình": giữ nguyên 8 bước như các agent hiện có (kể cả bước ghi đề xuất chờ duyệt và dòng "Cần bạn duyệt" trong báo cáo), đổi tên thư mục.
- "Định dạng file": giữ nguyên, đổi `domain: <slug>`.
- "Quy tắc riêng cho <lĩnh vực>": từ các cạm bẫy ở bước 2; luôn có quy tắc không bịa số liệu và ghi "chưa có nguồn xác nhận".
- "Giới hạn ghi file": chỉ `knowledge/<slug>/`, `knowledge/_index.md` và đề xuất trong `knowledge/_cho-duyet/`; chép nguyên câu về đề xuất chờ duyệt từ các agent hiện có.

Viết bằng tiếng Việt. Không sao chép các quy tắc riêng của lĩnh vực khác nếu không áp dụng được.

## Bước 4 – Tạo thư mục kiến thức

1. Tạo thư mục `knowledge/<slug>/` bằng cách ghi file `knowledge/<slug>/.gitkeep` rỗng.
2. Thêm mục mới vào `knowledge/_index.md`, đặt trước mục "Lĩnh vực khác":

   ```markdown
   ## <Tên lĩnh vực> (`<slug>/`)

   _Chưa có chủ đề nào._
   ```

## Bước 5 – Kiểm tra

- Frontmatter của agent đọc được, `name` trùng tên file.
- `description` không chồng lấn với agent khác.
- Mọi nguồn trong danh sách đều đã được mở kiểm tra.

## Bước 6 – Báo cáo

- Đường dẫn file agent và thư mục kiến thức đã tạo.
- Danh sách nguồn ưu tiên và chỉ số chính, tóm tắt.
- Lưu ý: agent mới chỉ được nạp ở phiên chạy sau; trong phiên hiện tại, muốn dùng ngay thì đọc file agent và làm theo.
- Nhắc người dùng: cây thư mục trong `CLAUDE.md` và lịch trong `config.yaml` không tự cập nhật (nằm ngoài phạm vi ghi của agent); muốn chạy tự động cho lĩnh vực mới thì thêm một job vào `config.yaml`.
