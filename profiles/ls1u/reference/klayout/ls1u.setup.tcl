# LS1u adaptation of OpenRAM setup.tcl; device model names are profile-specific.
ignore class c
equate class {-circuit1 n} {-circuit2 LV1UNMOS}
equate class {-circuit1 p} {-circuit2 LV1UPMOS}
property {-circuit1 n} remove as ad ps pd
property {-circuit1 p} remove as ad ps pd
property {-circuit2 LV1UNMOS} remove as ad ps pd
property {-circuit2 LV1UPMOS} remove as ad ps pd
permute transistors
