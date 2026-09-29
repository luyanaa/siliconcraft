# TR-1um OpenSUSI native-class Netgen setup.
# KLayout writes NMOS/NMOSE/PMOS and passive classes; native CDL uses
# NMOS/PMOS.  Parameters are intentionally reduced to the native comparison
# identity and device terminal permutation.
ignore class c
# Native 04_Custom.lvs writes NMOS/NMOSE/PMOS classes.  The source CDL uses
# the same classes; remove geometry-derived parasitic properties before the
# comparison and keep source/drain permutation explicit.
property {-circuit1 NMOS} remove as ad ps pd
property {-circuit1 NMOSE} remove as ad ps pd
property {-circuit1 PMOS} remove as ad ps pd
property {-circuit2 NMOS} remove as ad ps pd
property {-circuit2 NMOSE} remove as ad ps pd
property {-circuit2 PMOS} remove as ad ps pd
permute transistors
