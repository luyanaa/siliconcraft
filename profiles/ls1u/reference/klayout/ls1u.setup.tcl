# LS1u adaptation of OpenRAM setup.tcl; device model names are profile-specific.
ignore class c
equate class {-circuit1 nfet} {-circuit2 LV1UNMOS}
equate class {-circuit1 pfet} {-circuit2 LV1UPMOS}
property {-circuit1 nfet} remove as ad ps pd
property {-circuit1 pfet} remove as ad ps pd
property {-circuit2 LV1UNMOS} remove as ad ps pd
property {-circuit2 LV1UPMOS} remove as ad ps pd
permute transistors
