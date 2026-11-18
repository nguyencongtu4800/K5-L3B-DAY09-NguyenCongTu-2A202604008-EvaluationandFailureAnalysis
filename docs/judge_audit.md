# Judge audit

Chạy (từ `src/`): `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5`. Backend REPLAY (verdict judge lưu sẵn trong CSV), lớp dương = `FAIL`.

| Tiêu chí | n | κ | Precision | Recall | Ma trận (tp/fp/fn/tn) | Fail rate quan sát → Rogan-Gladen | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | **Đạt** (exit 0) | **dùng**, chỉ để theo dõi, không chặn release (xem kết luận) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | 0.09 → 0.30 | **Không đạt** κ và R (exit 1) | **loại**, không dùng làm gate |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em" và dùng "nha" quá suồng sã với khách khiếu nại. Rubric thêm: *xưng hô phải là "LogiX" và "anh/chị", không xưng "em"/"bạn", không dùng "nha/nhé"*. Cùng lỗi với H-017 ("bạn ơi … rồi nha"). |
| 2 | tone H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ thấy "Dạ, vui lòng" mà bỏ qua giọng ra lệnh. Rubric thêm: *không được bảo khách ngừng liên hệ hoặc dùng câu mệnh lệnh*. Kèm 1 few-shot FAIL có mở đầu lịch sự. |
| 3 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Câu ngắn nhưng lịch sự, đủ ý. Rubric ghi rõ: *xin lỗi không bắt buộc; ngắn gọn không phải lỗi tone*. |
| 4 | tone H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Style guide CS LogiX cho phép từ "refund". Rubric thêm danh sách từ tiếng Anh được phép (refund, ship, voucher). |
| 5 | tone H-063 "… đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người, nhưng sai tiêu chí | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống là lỗi **nội dung/cam kết**, không phải tone. Lỗi này nên do grader code bắt (reply so với ledger, FM-08), không đưa vào rubric tone. |
| 6 | tone H-070 "… cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại là không phù hợp. Rubric thêm: *không dùng emoji*. Có thể bắt luôn bằng regex. |
| 7 | tone H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** (theo note) | Note ghi nhãn người sai do đọc nhầm ticket. Nhưng câu này lịch sự, nên PASS mới đúng cho *tone*: người gán nhãn đã trộn đúng/sai nội dung vào tone. Cần gán lại nhãn và ghi rõ trong hướng dẫn gán nhãn rằng tone không xét đúng/sai kết quả. |
| 8 | tone H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi …" | PASS | FAIL | Người | Mất dấu tiếng Việt (giống dịch máy) là thiếu chuyên nghiệp. Rubric thêm: *phải là tiếng Việt có dấu*. |
| 9 | helpful HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Ledger ghi 40.000đ, reply báo sai số tiền. Judge chỉ đọc reply, không có ledger, nên **không thể** biết. Đây đúng là FM-08 và phải chấm bằng code. Cùng mẫu: HL-020, HL-062, HL-087, HL-100. |
| 10 | helpful HL-043 (xin lỗi dài lặp 2 lần + "đã hoàn 35.000đ cho đơn O-202") | PASS | FAIL | Người | Ledger 20.000đ. Đoạn xin lỗi dài, lặp lại làm judge tưởng là "hữu ích" (thiên vị độ dài/độ lịch sự), trong khi thông tin chính sai. Cùng mẫu: HL-016, 028, 035, 041, 053, 058, 070, 072, 074, 090, 096, 098. |
| 11 | helpful HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nói kết quả (hoàn bao nhiêu, hay bị từ chối) và cũng không nói bước tiếp theo, nên khách không biết gì thêm. Rubric helpful phải yêu cầu *nêu kết quả cụ thể (số tiền/trạng thái) và bước tiếp theo*. Cùng mẫu: HL-091, HL-097. |

## Kết luận

**`tone_ok`: dùng.** κ = 0.757, P = 0.857, R = 0.80 đều qua sàn. Có 10 bất đồng: 6 là FN (judge bỏ sót xưng hô suồng sã, giọng ra lệnh, emoji, mất dấu) và 4 là FP (phạt câu ngắn, phạt "refund", lặp "Dạ", và H-081 do nhãn người sai). Sửa rubric như bảng trên rồi chạy lại calibration. Chỉ dùng judge này để **theo dõi** (non-blocking): tone không phải tiêu chí tiền hay approval, và R = 0.8 vẫn bỏ sót 1/5 reply có tone xấu. Fail rate quan sát 0.28, sau hiệu chỉnh Rogan-Gladen còn 0.30, nên ước lượng tỉ lệ lỗi tone gần như không lệch.

**`helpful`: loại, không được làm gate.**
- Ma trận tp=9, fp=0, fn=21, tn=70: judge **bỏ sót 21/30** reply mà người chấm FAIL (R = 0.30), κ = 0.375 < 0.6.
- P = 1.0 trông đẹp nhưng gây hiểu nhầm. Judge gần như luôn nói PASS, nên mỗi lần nó nói FAIL thì đúng, nhưng nó hầu như không tìm ra lỗi. Một judge lớp dương mà chỉ có precision cao thì vô dụng làm gate.
- Fail rate quan sát 0.09, sau Rogan-Gladen là 0.30, tức judge **báo thấp hơn thực tế khoảng 3 lần**. Nếu dùng judge này làm gate, một PR làm reply tệ đi vẫn qua.
- Nguyên nhân gốc: 18/21 lỗi bị bỏ sót là **reply nói số tiền khác ledger** (FM-08). Judge chỉ thấy text, không thấy ledger. Thêm vào đó, đoạn xin lỗi dài làm judge chấm cao (thiên vị độ dài). Lỗi này phải chấm bằng **code** (parse số tiền trong reply rồi so với `refund_vnd` của ledger), đó là metric FM-08 ở M3. Đúng quy tắc: *tiền và approval luôn chấm bằng code*.
- 3/21 lỗi còn lại (HL-047/091/097, "Ok bạn, … xử lý rồi nhé") là reply mơ hồ. Rubric helpful mới phải yêu cầu nêu kết quả cụ thể. Sau khi sửa phải calibrate lại trên tập nhãn mới, không dùng lại 100 dòng này.

**Rủi ro còn lại:**
- Judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí). Sửa rubric dựa trên chính các bất đồng này rồi đo lại trên cùng tập sẽ overfit. Cần nhãn người mới để có held-out thật.
- Tập tone chỉ có 30 mẫu FAIL, nên khoảng tin cậy của recall còn rộng.
- Ít nhất 1 nhãn người sai (H-081), tức human label cũng có nhiễu. Nên có 2 người gán nhãn độc lập và đo κ giữa hai người.
