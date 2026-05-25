module simple (
  in0, in1, in2, out0
);
  input   in0;
  input   in1;
  input   in2;
  output   out0;
  wire n1;
  and U1 ( .o(n1), .a(in0), .b(in1) );
  or U2 ( .o(out0), .a(n1), .b(in2) );
endmodule