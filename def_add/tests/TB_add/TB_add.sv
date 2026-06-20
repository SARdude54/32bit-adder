`timescale 1ps/1ps

module TB_add;

logic CLK;
logic rst_n;
logic [31:0] A;
logic [31:0] B;
logic [31:0] C;

`ifdef USE_POWER_PINS
  supply1 VPWR, VPB;
  supply0 VGND, VNB;
`endif

add add(
    .CLK(CLK),
    .rst_n(rst_n),
    .A(A),
    .B(B),
    .C(C)
    `ifdef USE_POWER_PINS
            , .VPWR(VPWR)
            , .VGND(VGND)
    `endif
);

initial CLK = 0;
always #5 CLK = ~CLK;

initial begin
    if ($test$plusargs("dump") || 1) begin
        $dumpfile("wave.vcd");
        $dumpvars(0, add_tb);
    end
end

function automatic [31:0] add_ref(input [31:0] A, input [31:0] B);
    return A + B;
endfunction

initial begin
    A = '0;
    B = '0;
    rst_n = 0;
    repeat (4) @(posedge CLK);
    rst_n = 1;
    repeat (2) @(posedge CLK);
end

task automatic send_and_check(input logic [31:0] A_test, input logic [31:0] B_test);
    logic [31:0] expected = 32'(A_test) * 32'(B_test);
 
    @(negedge CLK);

    A = A_test;
    B = B_test;

    @(posedge CLK);
    @(posedge CLK);
    @(negedge CLK);

    if(C != expected)
        $error("[%0t] Mismatch: A=%0d B=%0d C=%0d exp=%0d", $time, A_test, B_test, C, expected);

endtask

initial begin

    wait (rst_n === 1);
    repeat (2) @(posedge CLK);

    for(int i = 1; i <= 10; i++) begin
        for (int j = 1; j <= 10; j++) begin
            send_and_check(i, j);
        end
    end

    $display("Test Complete");
    #50
    $finish;

end


endmodule

