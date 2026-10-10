// 4-bit synchronous up-counter with synchronous active-high reset and enable.
module counter (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    output reg  [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'd0;
        else if (en)
            count <= count + 4'd1;
    end
endmodule
