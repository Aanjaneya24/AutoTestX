#!/usr/bin/env tclsh
# AutoTestX Tcl component: testbench scenario lint.
#
# ROLE (honest scope): Icarus Verilog does not use Tcl for control, so this script does NOT drive
# the simulator. It is a standalone flow check, run as its own configured test, that walks scenario
# directories and verifies each testbench (<dir>/tb.v):
#   1. exists,
#   2. declares top module "tb" in real code (not in a comment or string),
#   3. can report success: a string literal containing PASS (e.g. in $display),
#   4. can report failure: a string literal containing FAIL, ASSERT or ERROR, or a $fatal/$error call.
# Text inside // and /* */ comments never counts. A scenario that is intentionally unable to report
# (e.g. a hang test with no PASS message, or a deliberately non-compiling file) says so explicitly
# with a relax list: "name:no-pass", "name:no-fail", "name:no-pass,no-fail".
#
# Usage: tclsh demo_tests.tcl <examples_root> <scenario[:relax,...]> ...
# Output: "SCENARIO <name> <OK|BAD> <detail>" per scenario, then "SUMMARY ok=N bad=M".
# Exit:   0 if all OK, 1 if any BAD, 64 on usage error (including an unknown relax keyword).

# Split Verilog source into {code strings}: code with comments and string contents removed,
# and the list of string literals' contents. Single left-to-right scan; handles \" escapes.
proc scan_verilog {src} {
    set code ""
    set strings {}
    set n [string length $src]
    set i 0
    while {$i < $n} {
        set c [string index $src $i]
        set d [string index $src [expr {$i + 1}]]
        if {$c eq "/" && $d eq "/"} {
            set e [string first "\n" $src $i]
            if {$e < 0} { set i $n } else { set i $e }
        } elseif {$c eq "/" && $d eq "*"} {
            set e [string first "*/" $src [expr {$i + 2}]]
            if {$e < 0} { set i $n } else { set i [expr {$e + 2}] }
            append code " "
        } elseif {$c eq "\""} {
            set j [expr {$i + 1}]
            set lit ""
            while {$j < $n} {
                set ch [string index $src $j]
                if {$ch eq "\\"} {
                    append lit $ch [string index $src [expr {$j + 1}]]
                    incr j 2
                    continue
                }
                if {$ch eq "\""} break
                append lit $ch
                incr j
            }
            lappend strings $lit
            append code "\"\""
            set i [expr {$j + 1}]
        } else {
            append code $c
            incr i
        }
    }
    return [list $code $strings]
}

proc read_file {path} {
    set fh [open $path r]
    set data [read $fh]
    close $fh
    return $data
}

proc check_scenario {root name relax} {
    set tb [file join $root $name tb.v]
    if {![file isfile $tb]} {
        return [list BAD "missing $tb"]
    }
    lassign [scan_verilog [read_file $tb]] code strings
    if {![regexp {\ymodule\s+tb\y} $code]} {
        return [list BAD "top module 'tb' not declared in code"]
    }
    set has_pass 0
    set has_fail [regexp {\$(fatal|error)\y} $code]
    foreach s $strings {
        if {[regexp {PASS} $s]} { set has_pass 1 }
        if {[regexp {FAIL|ASSERT|ERROR} $s]} { set has_fail 1 }
    }
    if {!$has_pass && "no-pass" ni $relax} {
        return [list BAD "no string literal containing PASS (comments do not count)"]
    }
    if {!$has_fail && "no-fail" ni $relax} {
        return [list BAD "no FAIL/ASSERT/ERROR string literal and no \$fatal/\$error call"]
    }
    return [list OK "pass-marker=$has_pass fail-marker=$has_fail"]
}

if {$argc < 2} {
    puts stderr "usage: tclsh demo_tests.tcl <examples_root> <scenario\[:no-pass,no-fail\]> ..."
    exit 64
}

set root [lindex $argv 0]
set specs {}
foreach arg [lrange $argv 1 end] {
    set parts [split $arg ":"]
    set relax [expr {[llength $parts] > 1 ? [split [lindex $parts 1] ","] : {}}]
    foreach r $relax {
        if {$r ni {no-pass no-fail}} {
            puts stderr "unknown relax keyword '$r' in '$arg' (allowed: no-pass, no-fail)"
            exit 64
        }
    }
    lappend specs [list [lindex $parts 0] $relax]
}

set ok 0
set bad 0
foreach spec $specs {
    lassign $spec name relax
    lassign [check_scenario $root $name $relax] verdict detail
    puts "SCENARIO $name $verdict $detail"
    if {$verdict eq "OK"} { incr ok } else { incr bad }
}
puts "SUMMARY ok=$ok bad=$bad"
exit [expr {$bad > 0 ? 1 : 0}]
