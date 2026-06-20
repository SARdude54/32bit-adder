`timescale 1ps/1ps

module add (

    `ifdef USE_POWER_PINS
        inout wire VPWR, 
        inout wire VGND,
    `endif

    input  logic        CLK,
    input  logic        rst_n,

    input  logic        vld_in,
    input  logic        rdy_out,

    input  logic [31:0] A,
    input  logic [31:0] B,
    output logic [31:0] C,

    output logic        vld_out,
    output logic        rdy_in
);

    // logic [63:0] c_q;

    logic fire_in;
    logic fire_out;

    assign fire_in  = vld_in  && rdy_in;
    assign fire_out = vld_out && rdy_out;


    assign rdy_in = !vld_out || rdy_out;

    // assign c_q = A * B;

    always_ff @(posedge CLK) begin
        if (!rst_n) begin
            C       <= 32'b0;
            vld_out <= 1'b0;
        end else begin
            if (fire_in) begin
                C       <= A + B;
                vld_out <= 1'b1;
            end else if (fire_out) begin
                vld_out <= 1'b0;
            end
        end
    end
    
endmodule

