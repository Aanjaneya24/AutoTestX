// Deliberately broken testbench (missing semicolon) to exercise compile-error handling.
module tb;
    initial begin
        $display("this never compiles")
        $finish;
    end
endmodule
