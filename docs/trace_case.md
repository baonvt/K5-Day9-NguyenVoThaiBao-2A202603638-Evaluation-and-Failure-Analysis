# Trace case: agent trừ lịch sử refund hai lần

## Trial

- **Shape:** `seeded_regression`, claim `C-014` @ seed `11`.
- **Run ID:** `E-seeded_regression-20261118-1af6` trong `src/reports/eval_seeded_regression.json`.
- **Case:** hàng O-515 vừa giao trễ vừa hỏng đã xác minh; trước đó host đã ghi 30.000đ.
- **Failure mode:** FM-05 `pre_deducted`, sau đó dẫn đến FM-08 `misreport`.

## Triệu chứng và bước sai đầu tiên

Lab 8 grader đánh dấu `proposal_mismatch`. Quote chính sách ở event 3 là 150.000đ; event 4 đọc lịch sử hoàn 30.000đ. Bước sai đầu tiên là event 5: shape tự trừ lịch sử và chỉ gửi proposal 120.000đ. Host đã tự áp dụng cùng khoản lịch sử khi tính cap, nên ledger chỉ ghi 90.000đ. Event 6 trả lời khách rằng đã hoàn 120.000đ, lệch 30.000đ so với ledger.

| Event | Nội dung | Đánh giá |
|---:|---|---|
| 3 `quote` | 150.000đ, gồm `SHIP-LATE-03` và `DMG-04` | Đúng quote đầy đủ |
| 4 `refund_history` | 30.000đ đã hoàn | Dữ kiện đúng; agent không được tự trừ |
| 5 `proposal` | 120.000đ | **Sai đầu tiên:** tự trừ trước khi gọi host |
| 6 `reply` | “đã hoàn 120.000đ” | Sai so với ledger 90.000đ |

## Regression test

`tests/test_lab9_fm08.py::test_reply_ledger_mismatch_catches_pre_deducted_trace` chạy cùng host và claim C-014. Test xác nhận variant `pre_deducted` ghi 90.000đ và grader `ReplyMatchesLedger` đánh dấu kết quả không đạt; shape `fixed` ghi 120.000đ và được đánh dấu đạt.

Lệnh kiểm tra:

```powershell
python -m pytest -q -m student -o addopts= -k "lab9 and not advanced"
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
```

## Đối chứng và giới hạn

Shape `fixed` dùng cùng claim/seed, gửi quote đầy đủ cho host, ledger ghi 120.000đ và reply khớp. Trace này chứng minh được lỗi ở đường tính proposal và hậu quả trong ledger; không đánh giá xác suất lỗi của một model thật. Public case cũng không thay thế kiểm tra authorization/ledger riêng cho production.
