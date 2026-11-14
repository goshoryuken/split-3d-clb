# Compiles the kit's liberty files for Design Compiler. Some files are named
# differently from the library inside them, so the name is read from the file.
file mkdir $::env(ASAP7)/db
foreach lib [glob $::env(ASAP7)/LIB/NLDM/*.lib] {
    set handle [open $lib]
    regexp {library\s*\(\s*(\S+?)\s*\)} [read $handle 2000] -> name
    close $handle
    read_lib $lib
    write_lib $name -format db -output $::env(ASAP7)/db/$name.db
}
exit
