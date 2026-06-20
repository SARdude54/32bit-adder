# openroad_load.tcl
#
# Usage:
#   RUN_DIR=runs/RUN_2026-06-17_22-30-47 openroad -gui scripts/openroad_load.tcl
#
# Default:
#   openroad -gui scripts/openroad_load.tcl
#
# The default run is runs/recent.

# ----------------------------------------------------------------------
# Choose run directory.
# ----------------------------------------------------------------------

if {[info exists ::env(RUN_DIR)] && $::env(RUN_DIR) ne ""} {
    set RUN_DIR $::env(RUN_DIR)
} else {
    set RUN_DIR "runs/recent"
}

if {![file isdirectory $RUN_DIR]} {
    error "Run directory does not exist: $RUN_DIR"
}

set FINAL_DIR [file join $RUN_DIR final]

if {![file isdirectory $FINAL_DIR]} {
    error "Final directory does not exist: $FINAL_DIR"
}

puts "============================================================"
puts "Loading OpenLane run: $RUN_DIR"
puts "Final directory:      $FINAL_DIR"
puts "============================================================"

# ----------------------------------------------------------------------
# Locate final ODB.
# ----------------------------------------------------------------------

set odb_files [glob -nocomplain [file join $FINAL_DIR odb *.odb]]

if {[llength $odb_files] == 0} {
    error "No .odb file found under: [file join $FINAL_DIR odb]"
}

set ODB [lindex $odb_files 0]

if {[llength $odb_files] > 1} {
    puts "WARNING: Multiple ODB files found. Using: $ODB"
}

# ----------------------------------------------------------------------
# Locate final SDC.
# ----------------------------------------------------------------------

set sdc_files [glob -nocomplain [file join $FINAL_DIR sdc *.sdc]]

if {[llength $sdc_files] == 0} {
    error "No .sdc file found under: [file join $FINAL_DIR sdc]"
}

set SDC [lindex $sdc_files 0]

if {[llength $sdc_files] > 1} {
    puts "WARNING: Multiple SDC files found. Using: $SDC"
}

# ----------------------------------------------------------------------
# Locate PDK Liberty timing model.
#
# Priority:
#   1. $PDKPATH environment variable
#   2. Common Volare installation under ~/.volare
#   3. Common Ciel installation under ~/.ciel
#
# Optional override:
#   LIB_CORNER=sky130_fd_sc_hd__tt_025C_1v80.lib \
#       RUN_DIR=runs/recent \
#       openroad -gui scripts/openroad_load.tcl
# ----------------------------------------------------------------------

set PDKPATH ""

# Preferred: explicitly exported by the user.
if {[info exists ::env(PDKPATH)] && $::env(PDKPATH) ne ""} {
    set PDKPATH $::env(PDKPATH)
    puts "Using PDKPATH from environment: $PDKPATH"
} else {
    # Try common Volare installation paths.
    set volare_roots [glob -nocomplain \
        [file normalize "~/.volare/volare/sky130/versions/*/sky130A"]]

    if {[llength $volare_roots] > 0} {
        set PDKPATH [lindex $volare_roots end]
        puts "Using PDKPATH discovered under Volare: $PDKPATH"
    } else {
        # Fallback to Ciel, if installed.
        set ciel_roots [glob -nocomplain \
            [file normalize "~/.ciel/ciel/sky130/versions/*/sky130A"]]

        if {[llength $ciel_roots] > 0} {
            set PDKPATH [lindex $ciel_roots end]
            puts "Using PDKPATH discovered under Ciel: $PDKPATH"
        }
    }
}

if {$PDKPATH eq ""} {
    error "Could not locate Sky130A PDK. Set PDKPATH before launching OpenROAD."
}

if {[info exists ::env(LIB_CORNER)] && $::env(LIB_CORNER) ne ""} {
    set LIB_NAME $::env(LIB_CORNER)
} else {
    # Slow corner, suitable for setup-path analysis.
    set LIB_NAME "sky130_fd_sc_hd__ss_100C_1v60.lib"
}

set LIB [file join \
    $PDKPATH \
    libs.ref \
    sky130_fd_sc_hd \
    lib \
    $LIB_NAME]

if {![file exists $LIB]} {
    error "Liberty file not found: $LIB"
}

# ----------------------------------------------------------------------
# Locate extracted parasitics.
#
# First search the final directory. If none exist there, search the run.
# This handles OpenLane versions that preserve SPEF in an intermediate step.
# ----------------------------------------------------------------------

set spef_files [glob -nocomplain [file join $FINAL_DIR spef *.spef]]

if {[llength $spef_files] == 0} {
    set spef_files [glob -nocomplain \
        [file join $RUN_DIR * spef *.spef] \
        [file join $RUN_DIR * * spef *.spef]]
}

set SPEF ""

if {[llength $spef_files] > 0} {
    set SPEF [lindex $spef_files 0]

    if {[llength $spef_files] > 1} {
        puts "WARNING: Multiple SPEF files found. Using: $SPEF"
    }
}

# ----------------------------------------------------------------------
# Load physical design and timing data.
# ----------------------------------------------------------------------

puts "ODB: $ODB"
puts "LIB: $LIB"
puts "SDC: $SDC"

read_db $ODB
read_lib $LIB
read_sdc $SDC

if {$SPEF ne ""} {
    puts "SPEF: $SPEF"
    read_spef $SPEF
} else {
    puts "WARNING: No SPEF found."
    puts "WARNING: Timing reports will not include extracted post-route RC parasitics."
}

# ----------------------------------------------------------------------
# Print timing context.
# ----------------------------------------------------------------------

puts "============================================================"
puts "Clock objects: [get_clocks *]"
puts "============================================================"

puts "Worst setup slack:"
report_worst_slack -max

puts "Worst hold slack:"
report_worst_slack -min

puts "============================================================"
puts "Top 10 setup paths:"
puts "============================================================"

report_checks -path_delay max \
    -fields {slew cap input_pins nets fanout} \
    -digits 4 \
    -sort_by_slack \
    -group_count 10

puts "============================================================"
puts "Top 10 hold paths:"
puts "============================================================"

report_checks -path_delay min \
    -fields {slew cap input_pins nets fanout} \
    -digits 4 \
    -sort_by_slack \
    -group_count 10

# ----------------------------------------------------------------------
# Open GUI after all timing information is loaded.
# ----------------------------------------------------------------------

gui::show