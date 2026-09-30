# SCMOS 7.2 device extensions

This document is the implementation boundary for the SCMOS 7.2 option layers
listed in `schema/historical_scmos_process_matrix.yaml`.  The matrix remains
reference-only: historical lambda rules do not create a foundry-qualified
profile, calibrated model card, or signoff PEX flow.

## Current implementation

`ProcessIR.scmos_extensions` exposes the profile-local result of this table.
The status is derived from the profile feature flags, typed DRC rule IDs, and
`devices.yaml` rows.  `unavailable` means the process profile does not expose
the option; `blocked` means the option is declared but the required collateral
is intentionally absent; `partial` preserves a lambda-only, recipe-only, or
profile-specific boundary.

| Extension | SCMOS source | Current profile boundary | DRC | LVS |
| --- | --- | --- | --- | --- |
| HVCMOS / CVP/CVN | SCMOS 7.2 layer vocabulary; profile-specific HV contracts | `xh035`, `xh018` marker/net-aware contracts; no generic SCMOS 7.2 lambda rules | partial | partial |
| Electrode capacitor | Table 11; `CapacitorElec` | `ami06`, `ami16` | implemented | implemented |
| Electrode transistor | Table 12; `nmos4_elec` / `pmos4_elec` | `ami16`; AMI06 retains the geometry rules but no electrode-MOS LVS rows | implemented | partial by profile |
| Electrode contact | Table 13; `ce` classification | profiles with `elecAvailable` | implemented | geometry/connectivity semantics |
| Vertical NPN | Table 16; `npnTran` | `ami16` | implemented typed derived-layer checks | implemented as `Generic_NPN` |
| Linear capacitor | Tables 17/18; `lcCap` | `hp06` (`cwellAvailable`) | implemented typed derived-layer checks | implemented |
| Buried CCD | Table 19; `ccd` / `ccdDiff` | no active profile enables `ccdAvailable` | unavailable | not applicable |
| Silicide-block resistor | Table 20; `polySRes` | `hp06` (`sblockAvailable`) | lambda-only typed checks | resistor recipe only |
| MEMS open / etch stop | `COP` / `CPS` layer vocabulary | no active profile enables `memsAvailable` | none by source | none |
| SCNPC `POLY_CAP1` | Table 23; `CPC` | no active profile enables `scnpcAvailable` | lambda-only source family, not activated | none |

The active typed checks use the normalized derived regions in
`common/drc/scmos_layers.py`.  They cover the source rule relationships using
the available width, spacing, enclosure, and overlap operators.  Magic
`edge4way` behavior is not silently presented as identical geometry; the
source rule and the typed approximation are retained in each rule's `source`
and `note` fields.

## Non-interchangeable capacitor semantics

These are three different layout contracts:

- **Electrode/PiP**: `CapacitorElec` is `elec` over `poly`.
- **Linear/cap-well**: `lcCap` is `poly` over the `cwell`/active-derived
  `lcDiff` region.
- **SCNPC/CPC**: `POLY_CAP1` is a separate AMI CWL option and is not modeled
  as either of the above.

The status contract uses `scnpcAvailable`, not `polycapAvailable`, for the
SCNPC option so an ordinary process PiP/poly-cap flag cannot accidentally
activate the AMI CWL device semantics.

## HVCMOS boundary

SCMOS 7.2 defines the HV marker vocabulary but does not provide a generic
official HV lambda rule section.  The repository therefore keeps HVCMOS
marker, hierarchy, drift, and voltage-net checks in profile-specific
`rules.yaml` contracts.  The historical Magic AMI 1.5 µm 20.x rules remain
behind the explicit `hvcmosLambdaOverride` gate in `common/process_ir.py` and
must not be used to infer a voltage rating.

## CCD and MEMS boundary

Buried CCD is a charge-coupled geometry option, not a normal three-terminal
LVS device; it is `not_applicable` for LVS rather than an omitted transistor
model.  No materialized profile currently enables the CCD feature, so the
Table 19 rules remain a source-backed extension boundary rather than active
profile collateral.

Magic explicitly states that MEMS open/etch-stop geometry has no enforced
lambda DRC and must be checked against process-specific micrometer guidelines.
The repository keeps `open`/`pstop` layer vocabulary available where mapped,
but does not invent generic rules or LVS extraction.

## Provenance

- MOSIS, *SCMOS Design Rules*, version 7.2: `schema/historical_scmos_process_matrix.yaml` source `mosis_scmos_7_2`.
- Bundled Magic SCMOS source: `profiles/ls1u/reference/magic/scmos.tech.in`.
- Profile rule contracts: `profiles/ami16/rules.yaml` and `profiles/hp06/rules.yaml`.
- Profile device contracts: `profiles/ami16/devices.yaml` and `profiles/hp06/devices.yaml`.
- Machine-readable status implementation: `common/scmos_extensions.py`.
- Contract regression: `scripts/test_scmos_device_extensions.py`.
