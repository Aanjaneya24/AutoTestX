// Deliberately never finishes: the runner's timeout must kill it.
`timescale 1ns/1ps
module tb;
    reg clk = 0;
    always #5 clk = ~clk;   // free-running clock, no $finish
    initial $display("INFO: hang test started; will never finish");
endmodule
