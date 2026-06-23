`timescale 1ps/1ps

`default_nettype none

module TB_add;

    logic        CLK;
    logic        rst_n;

    logic [31:0] A;
    logic [31:0] B;
    logic        Cin;

    logic [31:0] sum;
    logic        Cout;

    logic vld_in;
    logic rdy_in;
    logic vld_out;
    logic rdy_out;

    localparam integer TIMEOUT_CYCLES = 1000;

    `ifdef USE_POWER_PINS
        supply1 VPWR;
        supply1 VPB;
        supply0 VGND;
        supply0 VNB;
    `endif

    add DUT (

    `ifdef USE_POWER_PINS
        .VPWR(VPWR),
        .VGND(VGND),
    `endif

        .clk     (CLK),
        .rst_n   (rst_n),

        .vld_in  (vld_in),
        .rdy_out (rdy_out),

        .A       (A),
        .B       (B),
        .Cin     (Cin),

        .sum     (sum),
        .Cout    (Cout),

        .vld_out (vld_out),
        .rdy_in  (rdy_in)
    );

    initial begin
        CLK = 1'b0;
    end

    always #10000 CLK = ~CLK;

    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, TB_add);
    end

    // Reference unsigned 32-bit addition with carry-in.
    // The zero-extension preserves the full 33-bit result
    function automatic logic [32:0] reference_add (
        input logic [31:0] A_test,
        input logic [31:0] B_test,
        input logic        Cin_test
    );
        reference_add = {1'b0, A_test} + {1'b0, B_test} + {32'b0, Cin_test};
    endfunction

    // Drive one request.
    // Inputs change only on negedge CLK. 
    //The DUT samples the ready/valid handshake on the following posedge CLK.
    task automatic send_request (
        input logic [31:0] A_test,
        input logic [31:0] B_test,
        input logic        Cin_test
    );
        integer timeout;

        begin
            timeout = 0;

            // Wait for input readiness before presenting valid data.
            while (rdy_in !== 1'b1) begin
                @(negedge CLK);

                timeout = timeout + 1;
                if (timeout > TIMEOUT_CYCLES) begin
                    $fatal(1, "Timeout waiting for rdy_in: A=%0d B=%0d Cin=%0b", A_test, B_test, Cin_test);
                end
            end

            // Present a stable request during the low clock phase.
            @(negedge CLK);
            A      = A_test;
            B      = B_test;
            Cin    = Cin_test;
            vld_in = 1'b1;

            // Request is accepted at the next rising edge if rdy_in is high.
            @(negedge CLK);
            vld_in = 1'b0;
        end
    endtask

    // Wait for and verify one response.
    // hold_cycles deliberately stalls rdy_out after the result becomes valid. 
    // This verifies that sum, Cout, and vld_out remain stable while the output is backpressured.
    task automatic receive_and_check (
        input logic [32:0] expected,
        input integer      hold_cycles
    );
        integer timeout;
        integer i;

        begin
            timeout = 0;

            // Keep output stalled until the expected result arrives.
            rdy_out = 1'b0;

            while (vld_out !== 1'b1) begin
                @(negedge CLK);

                timeout = timeout + 1;
                if (timeout > TIMEOUT_CYCLES) begin
                    $fatal(1, "Timeout waiting for vld_out; expected=%h", expected);
                end
            end

            // Result must be correct before acknowledging it.
            if ({Cout, sum} !== expected) begin
                $fatal(1, "Incorrect result: got=%h expected=%h Cout=%0b sum=%h",
                       {Cout, sum}, expected, Cout, sum);
            end

            // Intentionally hold the output stalled and confirm that validity and data remain unchanged.
            for (i = 0; i < hold_cycles; i = i + 1) begin
                @(negedge CLK);

                if (vld_out !== 1'b1) begin
                    $fatal(1, "vld_out dropped while output was stalled");
                end

                if ({Cout, sum} !== expected) begin
                    $fatal(1, "Output changed during stall: got=%h expected=%h", {Cout, sum}, expected);
                end
            end

            // Consume the response on the following posedge.
            rdy_out = 1'b1;

            @(negedge CLK);
            rdy_out = 1'b0;
        end
    endtask

    // Complete one request/response test case.
    task automatic run_case (
        input logic [31:0] A_test,
        input logic [31:0] B_test,
        input logic        Cin_test,
        input integer      hold_cycles
    );
        logic [32:0] expected;

        begin
            expected = reference_add(A_test, B_test, Cin_test);

            $display("Testing: A=%h B=%h Cin=%0b expected={Cout,sum}=%h hold_cycles=%0d", A_test, B_test, Cin_test, expected, hold_cycles);

            send_request(A_test, B_test, Cin_test);
            receive_and_check(expected, hold_cycles);

            $display("PASSED:  A=%h B=%h Cin=%0b result=%h", A_test, B_test, Cin_test, expected);
        end
    endtask

    // Reset and test sequence.
    initial begin
        A       = 32'b0;
        B       = 32'b0;
        Cin     = 1'b0;
        rst_n   = 1'b0;
        vld_in  = 1'b0;
        rdy_out = 1'b0;

        // Keep reset asserted across several active clock edges.
        repeat (20) @(posedge CLK);

        // Release reset away from the DUT's sampling edge.
        @(negedge CLK);
        rst_n = 1'b1;

        // Allow one clean cycle after reset release.
        @(negedge CLK);

        // Basic addition.
        run_case(32'd100,       32'd100,       1'b0, 0);
        run_case(32'd3423,      32'd1123,      1'b0, 3);

        // Addition with carry-in.
        run_case(32'd100,       32'd100,       1'b1, 0);
        run_case(32'h0000_0000, 32'h0000_0000, 1'b1, 1);

        // Addition by zero.
        run_case(32'd0,         32'd123456789, 1'b0, 1);

        // Mixed values.
        run_case(32'd17,        32'h8000_0001, 1'b0, 2);
        run_case(32'd17,        32'h8000_0001, 1'b1, 2);

        // Carry-out cases.
        run_case(32'hFFFF_FFFF, 32'h0000_0001, 1'b0, 0);
        run_case(32'hFFFF_FFFF, 32'h0000_0000, 1'b1, 1);
        run_case(32'hFFFF_FFFF, 32'hFFFF_FFFF, 1'b0, 0);
        run_case(32'hFFFF_FFFF, 32'hFFFF_FFFF, 1'b1, 3);

        // A few random tests.
        repeat (100) begin
            run_case($urandom, $urandom, logic'($urandom_range(0, 1)), $urandom_range(0, 3));
        end

        $display("Test complete: all Brent-Kung adder tests passed.");

        repeat (4) @(posedge CLK);
        $finish;
    end

endmodule

`default_nettype wire

