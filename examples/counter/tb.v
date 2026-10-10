// Basic counter testbench: reset, count up 5 cycles, check wrap-around.
`timescale 1ns/1ps
module tb;
    reg clk = 0, rst = 1, en = 0;
    wire [3:0] count;
    integer errors = 0;

    counter dut (.clk(clk), .rst(rst), .en(en), .count(count));
    always #5 clk = ~clk;

    task check(input [3:0] expected, input [127:0] what);
        begin
            if (count !== expected) begin
                $display("ERROR: %0s: expected %0d, got %0d at time %0t", what, expected, count, $time);
                errors = errors + 1;
            end
        end
    endtask

    integer i;
    initial begin
        repeat (2) @(posedge clk);
        #1 check(4'd0, "after reset");
        rst = 0; en = 1;
        for (i = 1; i <= 5; i = i + 1) begin
            @(posedge clk); #1 check(i[3:0], "counting");
        end
        for (i = 6; i <= 16; i = i + 1) @(posedge clk);
        #1 check(4'd0, "wrap-around");
        if (errors == 0) begin
            $display("PASS: tb_counter completed with 0 errors");
            $finish;
        end else begin
            $display("FAIL: tb_counter completed with %0d errors", errors);
            $fatal(1, "tb_counter failed");
        end
    end
endmodule
