## Task 3: KIS multi-anchor trên search hiện tại

- Thêm `QueryPlan`/`QueryAnchor`, tối đa ba anchor, tối đa 60 token CLIP thực tế.
- Query ngắn dùng single-anchor; planner lỗi hoặc anchor không trung thành phải
  fallback về dịch hiện tại.
- Validator chặn màu, số và số lượng mới không xuất hiện trong query gốc.
- Gọi `search()` độc lập cho từng anchor rồi hợp nhất ở shot/video bằng RRF k=7;
  query ordered nhận soft temporal bonus mặc định 1.25, không hard-filter.
- Mọi knob nằm trong `data/config/`; không đổi vector/index/search branch.
- Thêm test anchor/token/fidelity/fallback/RRF/temporal trước code.

