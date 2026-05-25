module top (
  in0, in1, clk, rst_n, out0, out1
);
  input   in0;
  input   in1;
  input   clk;
  input   rst_n;
  output   out0;
  output   out1;
  wire n1;
  wire n2;
  not U1 ( .o(n1), .i(in0) );
  and U2 ( .o(n2), .a(n1), .b(in1) );
  buf U3 ( .o(out0), .i(n2) );
  and U_gc__bufand_0 ( .o(out1), .a(in0), .b(1'b1) );
endmodule