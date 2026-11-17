# Judge audit

Kết quả replay từ hai CSV công khai, chạy bằng `python -m lab9.judge` ngày 18/11/2026. PASS/FAIL được tính trên 100 ví dụ cho mỗi tiêu chí; lớp dương là FAIL. Ngưỡng dùng làm gate: κ ≥ 0.6, precision ≥ 0.8, recall ≥ 0.7.

| Tiêu chí | n | κ | Precision | Recall | Đạt ngưỡng? | Quyết định |
|---|---:|---:|---:|---:|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có | Dùng để theo dõi tone, có người rà lại thay đổi rubric. |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không | Không dùng làm gate; bỏ sót 70% reply bị người gắn FAIL. |

Tone có confusion `tp=24, fp=4, fn=6, tn=66`; helpful có `tp=9, fp=0, fn=21, tn=70`. Rogan–Gladen hiệu chỉnh tỉ lệ lỗi tone từ 0.280 lên 0.300; helpful từ 0.090 lên 0.300. Kappa không đạt hoặc không xác định luôn được tính là FAIL calibration.

## Bất đồng tone đã audit

| Case | Judge / người | Ai đúng? | Hành động với rubric |
|---|---|---|---|
| H-008 | PASS / FAIL — “Em … nha” | Người đúng: cách xưng hô quá suồng sã trong ngữ cảnh CSKH. | Nêu rõ đại từ thân mật và “nha” là lỗi trong văn cảnh này. |
| H-029 | PASS / FAIL — “không cần nhắn thêm” | Người đúng: câu mang giọng ra lệnh. | Thêm ví dụ câu phủ định mệnh lệnh vào nhóm thiếu tôn trọng. |
| H-042 | FAIL / PASS — thông báo hoàn tiền ngắn, đủ ý | Người đúng: xin lỗi không bắt buộc khi thông tin đã rõ và lịch sự. | Bỏ quy tắc ngầm “reply nào cũng phải xin lỗi”. |
| H-051 | FAIL / PASS — dùng từ “refund” | Người đúng: từ này được LogiX cho phép. | Đưa “refund” vào danh sách từ chấp nhận được. |
| H-063 | PASS / FAIL — giọng lịch sự nhưng hứa sẽ hoàn thêm | Judge đúng cho tiêu chí tone; lý do người chấm ghi là lỗi nội dung, không phải giọng điệu. | Chỉnh nhãn tone thành PASS; chấm lời hứa vượt trạng thái bằng grader nội dung riêng. |
| H-081 | FAIL / PASS — thông báo đơn chưa đủ điều kiện | Judge đúng theo nhãn giải thích trong CSV: người gán nhãn đọc nhầm ticket. | Sửa nhãn sau adjudication; không đổi rubric theo nhãn sai. |
| H-088 | FAIL / PASS — lặp “Dạ” | Người đúng: lỗi lặp nhẹ này vẫn đọc được và người chấm cho qua. | Đặt ngưỡng lặp rõ ràng thay vì phạt mọi lặp từ. |

## Bất đồng helpful đã audit

| Case | Judge / người | Ai đúng? | Hành động với rubric |
|---|---|---|---|
| HL-015 | PASS / FAIL — reply 55.000đ, ledger 40.000đ | Người đúng: số tiền sai. | So số reply với ledger bằng code, không để judge tự suy ra. |
| HL-016 | PASS / FAIL — reply 55.000đ, ledger 35.000đ | Người đúng: số tiền sai dù câu có xin lỗi dài. | Chấm đúng tiền độc lập với độ dài/lịch sự. |
| HL-020 | PASS / FAIL — reply 90.000đ, ledger 120.000đ | Người đúng: số tiền sai. | Bổ sung ví dụ reply thấp hơn số đã commit. |
| HL-043 | PASS / FAIL — reply 35.000đ, ledger 20.000đ | Người đúng: số tiền sai. | Thêm kiểm tra đối chiếu số tiền bắt buộc. |
| HL-047 | PASS / FAIL — “Ok bạn … nhé” | Người đúng: cách xưng hô quá thân mật cho hỗ trợ khách hàng. | Tách tiêu chí xưng hô khỏi tiêu chí có giải quyết đúng yêu cầu. |

## Kết luận

- `tone_ok` chỉ dùng để theo dõi chất lượng ngôn ngữ: replay công khai đạt các floor, nhưng H-081 cho thấy nhãn người cũng cần adjudication.
- `helpful` không được dùng làm gate. Recall 0.300 và κ 0.375 khiến nó bỏ lọt phần lớn lỗi, đặc biệt là sai số tiền; dùng `RefundAmountCorrect` và `ReplyMatchesLedger` cho các quyết định tiền.
- Hai file replay đều công khai, nên các con số chưa chứng minh chất lượng trên prompt, model hoặc người dùng mới. Cần mẫu held-out được người gán nhãn độc lập trước khi mở rộng gate.
