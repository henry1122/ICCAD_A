// 更簡單：兩層邏輯 in0,in1 -> AND -> n1 -> OR(with in2) -> out0
module simple (
  input in0,
  input in1,
  input in2,
  output out0
);
  wire n1;
  and U1 ( n1, in0, in1 );
  or U2 ( out0, n1, in2 );
endmodule
