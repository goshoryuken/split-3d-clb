module ten_luts(input a,b,c,d,e,f, output n0,n1,n2,n3,n4,n5,n6,n7,n8,n9);
  assign n0 = a ^ b ^ c ^ d ^ e ^ f;
  assign n1 = n0 ^ b ^ c ^ d ^ e ^ f;
  assign n2 = n1 ^ b ^ c ^ d ^ e ^ f;
  assign n3 = n2 ^ b ^ c ^ d ^ e ^ f;
  assign n4 = n3 ^ b ^ c ^ d ^ e ^ f;
  assign n5 = n4 ^ b ^ c ^ d ^ e ^ f;
  assign n6 = n5 ^ b ^ c ^ d ^ e ^ f;
  assign n7 = n6 ^ b ^ c ^ d ^ e ^ f;
  assign n8 = n7 ^ b ^ c ^ d ^ e ^ f;
  assign n9 = n8 ^ b ^ c ^ d ^ e ^ f;
endmodule
