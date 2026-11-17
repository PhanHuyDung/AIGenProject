---
name: distill-skill
description: Đúc kết một quy trình nghiên cứu đã lặp lại nhiều lần thành skill mới trong .claude/skills/ (SKILL.md kèm mẫu đầu ra nếu cần). Dùng khi người dùng nói quy trình vừa rồi lặp lại nhiều lần, muốn lưu cách làm để dùng lại, hoặc khi cùng một chuỗi bước đã được làm từ 3 lần trở lên. Không dùng để tạo agent lĩnh vực mới (create-domain-agent) hay để sửa một skill chỉ vì một lần làm khác.
---

# Đúc kết quy trình thành skill

Đầu vào (`$ARGUMENTS`): mô tả quy trình cần đúc kết, hoặc để trống nếu là quy trình vừa làm trong phiên này.

## Bước 1 – Xác định quy trình

Viết ra:

- **Mục đích**: quy trình tạo ra kết quả gì.
- **Khi nào dùng**: người dùng thường nói gì khi cần nó.
- **Đầu vào** và **đầu ra**.
- **Các bước** đã thực sự làm, theo thứ tự, kèm công cụ và agent đã dùng.
- **Chỗ từng sai hoặc phải làm lại**, và cách đã sửa.

Chỉ dựa vào những gì đã thực sự diễn ra: cuộc trò chuyện hiện tại, các file trong `knowledge/` và mục "Lịch sử thay đổi" của chúng. Không tự nghĩ ra bước chưa từng làm.

## Bước 2 – Quyết định có nên tạo skill không

Tạo skill mới khi đủ cả ba điều kiện:

1. Quy trình đã lặp lại, hoặc chắc chắn sẽ lặp lại, từ 3 lần trở lên.
2. Có những bước mà nếu không ghi lại thì dễ làm sai hoặc làm thiếu.
3. Chưa có skill nào làm việc này: Glob `.claude/skills/*/SKILL.md` và đọc `description` của từng skill.

Nếu một skill hiện có đã bao trùm phần lớn quy trình thì **sửa skill đó**, không tạo skill mới. Nếu không đủ điều kiện thì dừng và giải thích lý do.

## Bước 3 – Viết skill

Đặt tên: tiếng Anh, chữ thường, nối bằng gạch ngang, 2–4 từ, mô tả việc làm (ví dụ `earnings-summary`). Tên chưa được dùng.

Ghi `.claude/skills/<ten>/SKILL.md`:

```markdown
---
name: <ten>
description: <Làm gì> - <kết quả>. Dùng khi <tình huống, câu người dùng hay nói>. <Khi nào KHÔNG dùng, dùng skill nào thay>.
---

# <Tiêu đề>

Đầu vào (`$ARGUMENTS`): ...

## Bước 1 – ...
## Bước 2 – ...

## Báo cáo
```

Yêu cầu:

- `description` nêu rõ khi nào dùng và phân biệt được với các skill khác; đây là thứ duy nhất Claude đọc để quyết định có dùng skill hay không.
- Mỗi bước là một hành động cụ thể, kiểm tra được. Giải thích ngắn lý do ở những bước dễ bị bỏ qua.
- Ghi các lỗi đã gặp ở bước 1 thành chỉ dẫn phòng tránh.
- Tham chiếu tới `CLAUDE.md` và các agent, skill hiện có thay vì chép lại nội dung của chúng.
- Viết bằng tiếng Việt, không quá khoảng 150 dòng.

## Bước 4 – Thêm mẫu đầu ra nếu cần

Khi kết quả của quy trình có cấu trúc cố định (bảng, báo cáo, bộ mục cố định), tạo file mẫu **trong thư mục của skill**, ví dụ `.claude/skills/<ten>/mau-dau-ra.md`, và nhắc tới nó trong `SKILL.md` bằng đường dẫn tương đối. Mẫu chỉ chứa khung và chú thích, không chứa số liệu thật.

## Bước 5 – Kiểm tra

- Đọc lại skill như một người chưa biết gì về phiên làm việc này: mỗi bước có đủ thông tin để làm không.
- Skill không cho phép ghi file ngoài `knowledge/` và `.claude/`.
- Skill không mâu thuẫn với `CLAUDE.md`.

## Báo cáo

- Đường dẫn skill đã tạo hoặc đã sửa, và file mẫu nếu có.
- `description` của skill.
- Một ví dụ câu lệnh để gọi skill.
- Lưu ý: skill mới chỉ được nạp ở phiên chạy sau.
