// Reset behaviour: counter must return to 0 when rst is asserted mid-count.
`timescale 1ns/1ps
module tb;
    reg clk = 0, rst = 1, en = 1;
    wire [3:0] count;
    counter dut (.clk(clk), .rst(rst), .en(en), .count(count));
    always #5 clk = ~clk;
    initial begin
        repeat (2) @(posedge clk);
        rst = 0;
        repeat (7) @(posedge clk);
        #1 if (count === 4'd0) begin
            $display("ERROR: counter did not advance before reset (count=%0d)", count);
            $fatal(1, "setup failed");
        end
        rst = 1;
        @(posedge clk); #1;
        if (count !== 4'd0) begin
            $display("ASSERT FAIL: count=%0d after reset, expected 0", count);
            $fatal(1, "reset check failed");
        end
        $display("PASS: tb_counter_reset completed");
        $finish;
    end
endmodule
