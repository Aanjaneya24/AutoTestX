#!/usr/bin/env perl
# Parse a simulation log into structured JSON events.
# Usage: parse_logs.pl <logfile>
# Output (stdout): {"log":..., "line_count":N, "events":[{"line":N,"category":C,"snippet":S}, ...]}
# Categories: ERROR WARNING PASS FAIL ASSERT TIMEOUT FATAL
# A line yields at most one event (first matching rule wins, most specific first).
# Missing/unreadable file -> exit 2 with {"error":...}; empty file -> zero events.
use strict;
use warnings;
use JSON::PP;

my $MAX_SNIPPET = 200;
my $MAX_EVENTS  = 500;

# Ordered: first match wins.
my @RULES = (
    [ TIMEOUT => qr/\b(?:timed?[ -]?out|timeout|watchdog)\b/i ],
    [ ASSERT  => qr/\bassert(?:ion)?\b/i ],
    [ FATAL   => qr/^\s*FATAL\b|\bSegmentation fault\b|\bcore dumped\b|\bI give up\b/i ],
    [ FAIL    => qr/\bFAIL(?:ED|URE)?\b/i ],
    [ PASS    => qr/\bPASS(?:ED)?\b/i ],
    [ ERROR   => qr/\berrors?\b/i ],
    [ WARNING => qr/\bwarnings?\b/i ],
);

my $path = shift @ARGV;
my $json = JSON::PP->new->canonical->utf8;

sub bail {
    my ($msg) = @_;
    print $json->encode({ log => $path, error => $msg, line_count => 0, events => [] }), "\n";
    exit 2;
}

bail("usage: parse_logs.pl <logfile>") unless defined $path;
bail("cannot open log: no such file") unless -e $path;
bail("not a regular file: $path") unless -f $path;
open(my $fh, '<:raw', $path) or bail("cannot open log: $!");

my @events;
my $n = 0;
my $truncated = JSON::PP::false;
while (my $line = <$fh>) {
    $n++;
    $line =~ s/[\r\n]+\z//;
    $line =~ s/[^\x09\x20-\x7e]/?/g;    # keep output valid ASCII JSON
    for my $rule (@RULES) {
        my ($cat, $re) = @$rule;
        next unless $line =~ $re;
        # "0 errors" / "no warnings" are counts, not events
        next if ($cat eq 'ERROR' || $cat eq 'WARNING') && $line =~ /\b(?:0|no|zero)\s+(?:errors?|warnings?)\b/i;
        if (@events >= $MAX_EVENTS) { $truncated = JSON::PP::true; last; }
        my $snip = length($line) > $MAX_SNIPPET ? substr($line, 0, $MAX_SNIPPET) . '...' : $line;
        push @events, { line => $n, category => $cat, snippet => $snip };
        last;
    }
}
close $fh;

print $json->encode({ log => $path, line_count => $n, truncated => $truncated, events => \@events }), "\n";
exit 0;
