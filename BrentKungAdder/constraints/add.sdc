create_clock -name clk -period 7.5 [get_ports clk]

set_input_delay 1.0 -clock [get_clocks clk] [get_ports {vld_in rdy_out A[*] B[*] Cin}]
set_output_delay 1.0 -clock [get_clocks clk] [get_ports {vld_out rdy_in sum[*] Cout}]

set_false_path -from [get_ports rst_n]