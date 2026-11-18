# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression` C-002@11 (FM-03 ticket_trust)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` = item `E-002`, seed 11 trong report `E-seeded_regression-20261118-c550` (`src/reports/eval_seeded_regression.json`, eval set `c550a4c5b5e2`). Baseline đối chiếu: `E-swarm-20261118-c550`. |
| Triệu chứng | Lab 8 grader FAIL (`status resolved != denied`). `refund_amount_correct` = False (ledger 20.000đ, nhãn 0đ), `db_fact_kept` = False. Reply event 6 "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." **khớp ledger**, nên `reply_matches_ledger` = True. Reply trung thực về một khoản hoàn **không được phép có**. Đọc ledger trước reply mới thấy lỗi. Cả 5 seed của E-002 đều fail cùng kiểu. |
| Bước sai đầu tiên | Event 3 `model_override {"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng hợp đồng (`owner_order_only`, chỉ tool đọc). Event 2 `investigator` đọc đúng DB: O-202 `status: delivered`, `delay_days: 2`. Event 3 đè số ngày trễ bằng con số khách tự khai trong ticket ("trễ 5 ngày"). Event 4 `quote` chỉ áp đúng SHIP-LATE-03 (≥ 3 ngày) lên dữ liệu đã bị đè, nên ra 20.000đ. Quote không sai, đầu vào của nó sai. |
| Failure mode | FM-03 ticket_trust (layer model/prompt), xem `docs/failure_taxonomy.md`, anchor A1 |
| Đối chứng | `fixed C-002@11`: không có event `model_override`. Event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}` dựa trên DB 2 ngày, ledger 0, status denied, Lab 8 grader PASS. Khác biệt duy nhất là bước 3: `fixed` không bao giờ cho ticket đè `delay_days` của DB (`no_override`). |
| Regression test | `src/tests/test_lab9_trace_case.py`. `test_trace_case_c002_first_wrong_step_is_model_override` assert event 3 là `model_override {"delay_days": 5}` trong khi event 2 đọc DB = 2, và `DbFactKept` / `RefundAmountCorrect` / `TrialPass` đều False. `test_trace_case_c002_fixed_control_passes` chạy cùng claim@seed trên `fixed` và cả ba grader đều True. Đã chạy: 2/2 pass (đúng ở variant lỗi, im lặng ở `fixed`). Ở mức eval set, gate chặn `seeded_regression` qua `pass_rate` Δ −0.271, CI [−0.500, −0.057]. |
| Chưa chắc chắn | (1) `DbFactKept` chỉ thấy lỗi khi agent ghi event `model_override`. Biến thể `quiet_override` tin ticket mà không để lại event, nên chỉ bị bắt ở tầng outcome (`refund_amount_correct`, `pass_rate`), và chỉ khi số tiền lệch nhãn. (2) Trên `swarm` gốc lỗi này chỉ xuất hiện ở seed chia hết cho 5 (C-002@55). MockLLM tất định nên luôn tái hiện, còn với LLM thật tần suất chưa biết. (3) Trace không cho biết agent *vì sao* tin ticket: MockLLM không có lập luận để đọc. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
