// 簡單閘級測資：in0 -> NOT -> n1 -> AND(with in1) -> n2 -> BUF -> out0
// 另有一條 path: in0 -> U_gc__buf0 -> out1 (供測試 replace_buffers_with_and)
module top (
  input in0,
  input in1,
  input clk,
  input rst_n,
  output out0,
  output out1
);
  wire n1;
  wire n2;
  not U1 ( n1, in0 );
  and U2 ( n2, n1, in1 );
  buf U3 ( out0, n2 );
  buf U_gc__buf0 ( out1, in0 );
endmodule
