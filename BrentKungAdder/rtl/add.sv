`timescale 1ps/1ps

module add (

    `ifdef USE_POWER_PINS
        inout wire VPWR, 
        inout wire VGND,
    `endif

    input  logic        clk,
    input  logic        rst_n,

    input  logic        vld_in,
    input  logic        rdy_out,

    input  logic [31:0] A,
    input  logic [31:0] B,
    input logic         Cin,
    output logic [31:0] sum,
    output logic        Cout,

    output logic        vld_out,
    output logic        rdy_in
);

    // handshake logic
    logic fire_in;
    logic fire_out;

    assign fire_in  = vld_in  && rdy_in;
    assign fire_out = vld_out && rdy_out;


    assign rdy_in = !vld_out || rdy_out;

    // generate propogate logic
    logic [31:0] g0;
    logic [31:0] p0;

    assign g0 = A & B;
    assign p0 = A ^ B;

    // Brent kung tree reduction
    logic [31:0] g1, p1;

    generate
        for (genvar i = 0; i < 32; ++i) begin: reduction_tree_loop
            if((i % 2) == 1) begin
                assign g1[i] = g0[i] | (p0[i] & g0[i-1]);
                assign p1[i] = p0[i] & p0[i-1];
            end else begin
                assign g1[i] = g0[i];
                assign p1[i] = p0[i];
            end
        end
    endgenerate    

    // Combine 4-bit groups
    logic [31:0] g2, p2;
    
    generate
        for (genvar i = 0; i < 32; ++i) begin: reduction_tree_loop2
            if((i % 4) == 3) begin
                assign g2[i] = g1[i] | (p1[i] & g1[i-2]);
                assign p2[i] = p1[i] & p1[i-2];
            end else begin
                assign g2[i] = g1[i];
                assign p2[i] = p1[i];
            end
        end
    endgenerate 

    // Combine 8-bit groups
    logic [31:0] g3, p3;
    
    generate
        for (genvar i = 0; i < 32; ++i) begin: reduction_tree_loop3
            if((i % 8) == 7) begin
                assign g3[i] = g2[i] | (p2[i] & g2[i-4]);
                assign p3[i] = p2[i] & p2[i-4];
            end else begin
                assign g3[i] = g2[i];
                assign p3[i] = p2[i];
            end
        end
    endgenerate 

    // combine 16-bit groups
    logic [31:0] g4, p4;

    generate
        for (genvar i = 0; i < 32; ++i) begin: reduction_tree_loop4
            if((i % 16) == 15) begin
                assign g4[i] = g3[i] | (p3[i] & g3[i-8]);
                assign p4[i] = p3[i] & p3[i-8];
            end else begin
                assign g4[i] = g3[i];
                assign p4[i] = p3[i];
            end
        end
    endgenerate 

    // combine 32-bit groups
    logic [31:0] g5, p5;

    generate
        for (genvar i = 0; i < 32; ++i) begin: reduction_tree_loop5
            if(i == 31) begin
                assign g5[i] = g4[i] | (p4[i] & g4[i-16]);
                assign p5[i] = p4[i] & p4[i-16];
            end else begin
                assign g5[i] = g4[i];
                assign p5[i] = p4[i];
            end
        end
    endgenerate 

    // Brent Kung distribution Tree

    logic [31:0] g6, p6;

    generate
        for (genvar i = 0; i < 32; ++i) begin: distribution_tree_loop6
            if(i == 23) begin
                assign g6[i] = g5[i] | (p5[i] & g5[i-8]);
                assign p6[i] = p5[i] & p5[i-8];
            end else begin
                assign g6[i] = g5[i];
                assign p6[i] = p5[i];
            end
        end
    endgenerate 

    logic [31:0] g7, p7;
    generate
        for (genvar i = 0; i < 32; ++i) begin: distribution_tree_loop7
            if((i == 11) || (i == 19) || (i == 27)) begin
                assign g7[i] = g6[i] | (p6[i] & g6[i-4]);
                assign p7[i] = p6[i] & p6[i-4];
            end else begin
                assign g7[i] = g6[i];
                assign p7[i] = p6[i];
            end
        end
    endgenerate 

    logic [31:0] g8, p8;
    generate
        for (genvar i = 0; i < 32; ++i) begin: distribution_tree_loop8
            if((i == 5)  || (i == 9)  || (i == 13) || (i == 17) ||
                (i == 21) || (i == 25) || (i == 29)) begin
                assign g8[i] = g7[i] | (p7[i] & g7[i-2]);
                assign p8[i] = p7[i] & p7[i-2];
            end else begin
                assign g8[i] = g7[i];
                assign p8[i] = p7[i];
            end
        end
    endgenerate 


    logic [31:0] g9, p9;

    generate
        for (genvar i = 0; i < 32; ++i) begin : distribution_tree_loop9
            if ((i > 0) && ((i % 2) == 0)) begin
                assign g9[i] = g8[i] | (p8[i] & g8[i-1]);
                assign p9[i] = p8[i] & p8[i-1];
            end else begin
                assign g9[i] = g8[i];
                assign p9[i] = p8[i];
            end
        end
    endgenerate

    logic [32:0] c;

    assign c[0] = Cin;

// Carry generation
generate
    for (genvar i = 0; i < 32; ++i) begin : carry_out_gen
        assign c[i + 1] = g9[i] | (p9[i] & Cin); 
    end
endgenerate

    // sum generation
    logic [31:0] sum_comb;
    logic cout_comb;

    assign sum_comb = p0 ^ c[31:0];
    assign cout_comb = c[32];

    always_ff @(posedge clk) begin : output_reg
        if(!rst_n) begin
            sum <= 32'b0;
            Cout <= 0;
            vld_out <= 0;
        end else begin
            if(fire_in) begin
                sum <= sum_comb;
                Cout <= cout_comb;
                vld_out <= 1;
            end else if (fire_out) begin
                vld_out <= 0;
            end
        end
    end
    
    
endmodule

