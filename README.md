# AIGenProject


Web app chạy local dùng Claude Agent SDK (Python) để nghiên cứu các lĩnh vực — tài chính, chứng khoán Việt Nam, công nghệ thông tin, phát triển phần mềm, AI, game, thương mại điện tử, và bất kỳ lĩnh vực mới nào — rồi lưu kiến thức thành file `.md` trong `knowledge/`, đồng thời tạo/cập nhật agent và skill trong `.claude/`. Nội dung chưa chắc chắn không được ghi thẳng vào kho mà chờ bạn duyệt trên giao diện.

## Cấu trúc thư mục

| Đường dẫn | Nội dung |
| --- | --- |
| `backend/` | Python: `agent_core.py` (lõi Claude Agent SDK), `env_check.py` (kiểm tra môi trường, xác thực), `db.py` (SQLite), `files.py` (truy cập file an toàn), `scheduler.py` (lịch tự động), `main.py` + `api/` (FastAPI), `cli.py` (dòng lệnh), `tests/` |
| `frontend/` | Giao diện web (HTML + CSS + JS thuần, không build), 6 tab |
| `knowledge/` | Kho kiến thức `.md` theo lĩnh vực; `_index.md` là mục lục; `_cho-duyet/` chứa đề xuất chờ duyệt; `_bao-cao/` chứa báo cáo (nếu có) |
| `.claude/agents/` | Agent nghiên cứu theo lĩnh vực (`<lĩnh-vực>-researcher.md`) và `knowledge-curator` |
| `.claude/skills/` | Skill: `deep-research`, `update-knowledge`, `create-domain-agent`, `knowledge-report`, `review-proposals`, `distill-skill` |
| `CLAUDE.md` | Quy tắc nghiên cứu, lưu kiến thức, duyệt thay đổi và ghi file — mọi agent/skill đều tuân theo |
| `config.yaml` | Lịch tự động cập nhật theo lĩnh vực |
| `.env.example` | Mẫu cấu hình app (`PORT`, `MAX_DAILY_RUNS`, `MAX_TURNS`); không chứa API key |

## Cài đặt

Yêu cầu: Python 3.10 trở lên và một tài khoản Claude (gói Pro/Max). Không cần Node.js: Claude Code CLI đã kèm trong gói `claude-agent-sdk`.

```
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env         # macOS/Linux: cp .env.example .env
claude login                        # đăng nhập bằng tài khoản Claude (một lần cho mỗi máy)
python backend/cli.py --check       # kiểm tra môi trường; thiếu gì sẽ in lệnh cài
```

`.env` chỉ chứa cấu hình app, đã nằm trong `.gitignore`. Khi clone về máy khác, chạy lại các lệnh trên; `--check` kiểm tra Python, thư viện, Claude CLI và trạng thái đăng nhập. Trên Windows, bản `claude.cmd` cài qua npm không dùng được với SDK; app tự dùng bản kèm theo gói pip.

## Xác thực và chi phí

Dự án dùng tài khoản Claude đã đăng nhập (`claude login`), **không dùng API key**.

- Không đặt `ANTHROPIC_API_KEY` (hay `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY`) trong `.env` hoặc biến môi trường; nếu có, SDK sẽ ưu tiên chúng và tính tiền ngoài gói. Khi khởi động, app phát hiện, cảnh báo và gỡ các biến này khỏi tiến trình (không đổi cấu hình hệ thống).
- Mỗi phiên, SDK báo về nguồn xác thực; app chỉ coi là hợp lệ khi `apiKeySource = none` và `claude auth status` là `claude.ai`. Badge góc trên giao diện xanh khi đúng, đỏ khi không.
- Mức sử dụng trừ vào giới hạn gói Claude, chung với chat và Claude Code. Chi phí USD hiện trong app chỉ là ước tính của SDK. "Extra usage" (tính tiền khi vượt gói) là cài đặt tài khoản trên claude.ai → Settings → Usage; app không đọc hay tắt được, bạn tự kiểm tra một lần.
- **Chỉ dùng cá nhân.** Muốn chia sẻ app cho người khác phải chuyển sang API key.

## Chạy web app

Cách nhanh nhất trên Windows: nháy đúp **`run.bat`** ở gốc dự án. File này tự tạo `.venv` và cài thư viện nếu chưa có, tạo `.env` từ mẫu, chạy kiểm tra môi trường (`backend/cli.py --check`), mở trình duyệt và khởi động server; đóng cửa sổ (hoặc `Ctrl+C`) là tắt app. Lần đầu cần đã `claude login`.

Chạy tay (mọi hệ điều hành), sau khi kích hoạt `.venv`:

```
uvicorn backend.main:app --port 8000
```

Không dùng `--reload` khi chạy lâu dài: mỗi lần agent ghi file trong thư mục dự án, uvicorn sẽ khởi động lại và cắt ngang phiên đang chạy.

Mở <http://127.0.0.1:8000>. App chỉ lắng nghe `127.0.0.1`, từ chối header `Host` lạ, không có đăng nhập web; không mở ra mạng. Tài liệu API ở `/docs`.

### Cách dùng hằng ngày

Bấm **? Hướng dẫn** ở góc trên để xem mẫu prompt và điền thẳng vào ô câu hỏi. Các việc thường làm:

| Việc | Trên giao diện | Hoặc gõ ở tab Nghiên cứu / Claude Code |
| --- | --- | --- |
| Nghiên cứu chủ đề mới | Tab Nghiên cứu → nhập câu hỏi, chọn lĩnh vực → Chạy | `Dùng skill deep-research: <câu hỏi>` |
| Lĩnh vực mới chưa có agent | Tab Agent & Skill → "Tạo agent lĩnh vực mới" | `Dùng skill create-domain-agent cho lĩnh vực <tên>` |
| Cập nhật kiến thức đã có | Tab Kho kiến thức → nút Cập nhật trên file, hoặc ↻ cạnh thư mục | `Dùng skill update-knowledge cho knowledge/<lĩnh-vực>/` |
| Duyệt nội dung chưa chắc chắn | Tab Chờ duyệt → Duyệt / Từ chối | `Dùng skill review-proposals` (chỉ rà soát, không duyệt thay) |
| Báo cáo một lĩnh vực | — | `Dùng skill knowledge-report cho <lĩnh-vực>` |
| Đúc kết quy trình lặp lại | — | `Quy trình vừa rồi lặp lại nhiều lần, dùng skill distill-skill để tạo skill mới` |

Khi một phiên tạo ra đề xuất chờ duyệt, app hiện thanh thông báo đầu trang, toast và thông báo trình duyệt (nếu cho phép). Chỉ một phiên Claude chạy tại một thời điểm; gọi thêm khi đang bận trả về `409`.

### Các tab

- **Nghiên cứu**: theo dõi trực tiếp từng bước agent (tìm gì, đọc trang nào, ghi file nào); cuối phiên có số lượt, thời gian, file đã ghi, file bị chặn, số đề xuất chờ duyệt; nút Dừng huỷ phiên.
- **Kho kiến thức**: cây thư mục, xem markdown, tìm theo tên/nội dung, nhãn "cũ" khi `last_updated` quá 90 ngày, Sửa, Cập nhật.
- **Agent & Skill**: xem/sửa file agent và skill (frontmatter phải có `name`); tạo agent lĩnh vực mới. Agent/skill mới có hiệu lực từ phiên kế tiếp.
- **Chờ duyệt**: mỗi đề xuất gồm nội dung hiện tại, nội dung đề xuất, nguồn, lý do chưa chắc chắn. **Duyệt** đổi trạng thái rồi chạy một phiên Claude ngắn ghép nguyên văn vào file đích (lỗi thì trả về chờ duyệt); **Từ chối** chỉ ghi lại quyết định và ghi chú.
- **Lịch sử**: các phiên đã chạy, số lượt, thời gian, chi phí ước tính, file đã tạo/sửa.
- **Lịch tự động**: bật/tắt, lần chạy kế tiếp, lần gần nhất, các lần đã chạy, "Chạy ngay".

## Lịch tự động cập nhật

Khai báo trong [config.yaml](config.yaml): mỗi lĩnh vực một dòng cron (mặc định `ai` hằng ngày 8h, `tai-chinh` và `game` thứ Hai, `cong-nghe-thong-tin` và `phat-trien-phan-mem` Chủ nhật, `chung-khoan-viet-nam` thứ Hai–thứ Sáu 17h), múi giờ, `max_turns` mỗi phiên (có thể ghi đè theo job), `git_commit`, và `pre_steps` cho job cần dữ liệu chuẩn bị trước.

**Bản tin chứng khoán cuối phiên và top 10 theo dõi kỹ thuật.** Job `chung-khoan-viet-nam` có `pre_steps: [market-data]`: trước khi gọi agent, backend ([backend/market_data.py](backend/market_data.py)) tải lịch sử giá từ CafeF cho danh sách mã trong `market_data.tickers` của `config.yaml` (mặc định ~40 mã vốn hoá lớn; sửa tuỳ ý) và các chỉ số, tính SMA20/50/200, RSI14, MACD, khối lượng so với trung bình 20 phiên, đáy/đỉnh 20 phiên và 52 tuần, rồi ghi bảng vào `knowledge/_du-lieu/chung-khoan-viet-nam/chi-bao-cuoi-phien.md`. Agent đọc bảng đó cộng tin doanh nghiệp để cập nhật `cap-nhat-cuoi-phien.md`, trong đó có tiểu mục "Danh sách theo dõi kỹ thuật – top 10": mã, lý do (tiêu chí đạt), vùng mua / vùng chốt lời / mức cắt lỗ **tham khảo** suy từ SMA và đáy/đỉnh gần nhất, tin hỗ trợ, mức chắc chắn. Tiêu chí lọc công khai trong file agent; dữ liệu chỉ từ một nguồn (CafeF) nên mức chắc chắn tối đa là trung bình. Đây là vùng giá kỹ thuật theo tiêu chí máy móc, **không phải khuyến nghị đầu tư**; bạn tự quyết định và chịu rủi ro. Chạy tay: `python -m backend.market_data` (hoặc `python -m backend.market_data FPT HPG` để xem nhanh vài mã). Mỗi lần chạy một lĩnh vực: skill `update-knowledge` → agent `knowledge-curator` → `git commit` `knowledge/` và `.claude/` với message `auto-update <lĩnh vực> <ngày>` (chỉ khi có thay đổi; không push).

Giới hạn: `MAX_DAILY_RUNS` lần chạy tự động mỗi ngày (mỗi lần = 2 phiên Claude), `max_turns` mỗi phiên, chỉ một phiên tại một thời điểm. Gặp lỗi hết giới hạn sử dụng thì dừng lần chạy, ghi `backend/scheduler.log`, lần kế tiếp theo lịch tự thử lại. Lịch chỉ chạy khi app đang mở; trạng thái bật/tắt lưu trong SQLite. Nội dung chưa chắc chắn do phiên tự động tạo ra vẫn vào tab Chờ duyệt.

## Dòng lệnh

```
python backend/cli.py --check                     # kiểm tra môi trường và đăng nhập
python backend/cli.py --list                      # lĩnh vực và skill
python backend/cli.py "câu hỏi" --domain ai       # nghiên cứu
python backend/cli.py --skill deep-research "chủ đề"
python backend/cli.py --history                   # phiên đã chạy
python -m pytest backend/tests -q                 # kiểm thử, không gọi Claude
```

## Thêm agent hoặc skill thủ công

**Agent lĩnh vực mới** (thay cho skill `create-domain-agent`):

1. Tạo `.claude/agents/<lĩnh-vực>-researcher.md` theo mẫu một agent có sẵn (ví dụ `game-researcher.md`): frontmatter `name`, `description` (nêu rõ phạm vi, thư mục `knowledge/<lĩnh-vực>/`, khi nào dùng), `tools: WebSearch, WebFetch, Read, Write, Glob, Grep`; phần thân có các mục Phạm vi, Nguồn, Quy trình, Định dạng file, Quy tắc riêng, Giới hạn ghi file.
2. Tạo thư mục `knowledge/<lĩnh-vực>/` (tên không dấu, chữ thường, gạch ngang) và thêm mục tương ứng vào `knowledge/_index.md`.
3. Muốn chạy tự động: thêm một job vào `config.yaml`.

App nhận ra lĩnh vực qua đường dẫn `knowledge/<lĩnh-vực>/` ghi trong file agent, nên bước 1 phải nhắc tới thư mục đó.

**Skill mới** (thay cho `distill-skill`): tạo `.claude/skills/<tên>/SKILL.md` với frontmatter `name` (trùng tên thư mục) và `description` nói rõ khi nào dùng và khi nào không; thân là các bước cụ thể, tham chiếu `CLAUDE.md` thay vì chép lại. File mẫu đầu ra (nếu có) đặt cùng thư mục. Skill được nạp ở phiên kế tiếp; trong app, gọi bằng `/tên <tham số>` hoặc tab Nghiên cứu.

## API

| Endpoint | Việc |
| --- | --- |
| `GET /api/status` | Xác thực, vấn đề môi trường, số đề xuất chờ duyệt, đang bận không |
| `POST /api/research` `{prompt, domain?, max_turns?}` | Nghiên cứu, trả về SSE (`text`, `tool_use`, `tool_result`, `done`, `error`) |
| `POST /api/skills/{name}/run` `{args?, max_turns?}` | Chạy skill, SSE |
| `GET /api/knowledge`, `/api/knowledge/{path}`, `/api/knowledge/search?q=` | Cây kho (kèm `stale`), nội dung file, tìm kiếm |
| `GET /api/agents`, `GET /api/skills` | Danh sách từ frontmatter |
| `GET/PUT /api/files/{path}` | Đọc/sửa file trong `knowledge/`, `.claude/agents/`, `.claude/skills/` |
| `GET /api/proposals?status=`, `POST /api/proposals/{id}/approve`, `POST /api/proposals/{id}/reject` | Đề xuất chờ duyệt |
| `GET /api/history`, `/api/history/{id}` | Lịch sử phiên |
| `GET /api/scheduler`, `POST /api/scheduler/toggle`, `POST /api/scheduler/run/{domain}`, `GET /api/scheduler/runs` | Lịch tự động |

## An toàn

- Agent chỉ ghi được trong `knowledge/` và `.claude/agents/`, `.claude/skills/` (file văn bản); hook `PreToolUse` chặn mọi lệnh ghi khác, kể cả `.claude/settings.json` (nơi có thể gài hook chạy lệnh). `Bash` bị gỡ khỏi phiên. Mọi đường dẫn từ web qua `safe_resolve` (chặn `..`, đường dẫn tuyệt đối, `.env`).
- Nội dung web là dữ liệu, không phải chỉ thị (ghi trong `CLAUDE.md`); nội dung chưa chắc chắn phải qua tab Chờ duyệt.
- Không có key nào trong repo; `.env`, `*.db`, `*.log`, `.venv` nằm trong `.gitignore`.

## Quy tắc nghiên cứu

Xem [CLAUDE.md](CLAUDE.md): chỉ dùng nguồn uy tín, luôn ghi link và ngày truy cập, không suy đoán khi không có căn cứ, ghi rõ mức độ chắc chắn; mỗi chủ đề một file `.md` có frontmatter (`title`, `domain`, `last_updated`, `sources`, `confidence`) và bốn mục Tóm tắt, Chi tiết, Nhận định, Nguồn; nội dung chỉ một nguồn, mâu thuẫn, hoặc là phỏng đoán phải vào `knowledge/_cho-duyet/` chờ bạn duyệt.
