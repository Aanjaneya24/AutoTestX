// Deliberately failing test: expects the wrong count to show how failures are reported.
`timescale 1ns/1ps
module tb;
    reg clk = 0, rst = 1, en = 1;
    wire [3:0] count;
    counter dut (.clk(clk), .rst(rst), .en(en), .count(count));
    always #5 clk = ~clk;
    initial begin
        repeat (2) @(posedge clk);
        rst = 0;
        repeat (3) @(posedge clk);
        #1 if (count !== 4'd9) begin
            $display("ASSERT FAIL: expected count 9, got %0d at time %0t", count, $time);
            $display("FAIL: tb_counter_fail (intentional)");
            $fatal(1, "intentional assertion failure");
        end
        $display("PASS: unexpected");
        $finish;
    end
endmodule
