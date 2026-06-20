create_clock -name CLK -period 30 [get_ports CLK]

set_input_delay 1.0 -clock [get_clocks CLK] [get_ports {vld_in rdy_out A[*] B[*]}]
set_output_delay 1.0 -clock [get_clocks CLK] [get_ports {vld_out rdy_in C[*]}]

set_false_path -from [get_ports rst_n]