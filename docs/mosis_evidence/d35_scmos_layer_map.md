# D35 / SCN4ME GDS layer map — provenance and limits

Evidence file for the TSMC 0.35 µm Mixed-Signal 2P4M Polycide 3.3/5 V process
(TSRI "D35", NCSU CDK `TSMC_CMOS035_4M2P`, MOSIS code `SCN4ME_SUBM`).

Consumed by `profiles/tsmc035_4m2p/gds_layer_map.yaml` and materialised into
`profiles/tsmc035_4m2p/layers.yaml`.

---

## 1. What this map is, and what it is not

**It is** the historical **MOSIS SCMOS submission** layer map: the map a designer
used when streaming an SCMOS-format GDS to MOSIS. Source file
`../ncsu-cdk-1.6.0/pipo/streamInLayermap`, whose own header reads:

```
# Layer map for converting from GDSII to Cadence format (SCMOS processes)
```

The same numbers are shared across the SCMOS ladder (AMI 0.6/1.2/1.6, HP, Orbit,
TSMC 0.25/0.35 variants), i.e. the layer *numbers* are an interface convention of
the SCMOS program, not a TSMC-specific mask numbering.

**It is not** the current TSRI/CIC or foundry-direct stream map. The historical
flow was:

```
designer SCMOS GDS  →  MOSIS/CIC interface  →  foundry mask translation
```

so a current TSRI D35 stream-out may legitimately use different numbers.
`gds_layer_map.yaml` therefore sets `tapeout_eligible: false` and
`current_foundry_map.status: unavailable`.

---

## 2. The map (verbatim from `pipo/streamInLayermap`)

| Cadence layer | GDSII layer | datatype |
|---|---|---|
| nwell | 42 | 0 |
| pwell | 41 | 0 |
| cwell | 59 | 0 |
| pbase | 58 | 0 |
| active | 43 | 0 |
| tactive | 60 | 0 |
| ccd | 57 | 0 |
| nselect | 45 | 0 |
| pselect | 44 | 0 |
| poly | 46 | 0 |
| polycap | 28 | 0 |
| elec | 56 | 0 |
| metal1 | 49 | 0 |
| metal2 | 51 | 0 |
| metal3 | 62 | 0 |
| metal4 | 31 | 0 |
| metal5 | 33 | 0 |
| metal6 | 37 | 0 |
| cc | **25, 47, 48, 55** | 0 |
| via | 50 | 0 |
| via2 | 61 | 0 |
| via3 | 30 | 0 |
| via4 | 32 | 0 |
| via5 | 36 | 0 |
| glass | 52 | 0 |
| pad | 26 | 0 |
| sblock | 29 | 0 |
| open | 23 | 0 |
| pstop | 24 | 0 |
| highres | 34 | 0 |
| metalcap | 35 | 0 |

The subset actually enabled for the 4M2P option is decided by the techfile
`../ncsu-cdk-1.6.0/techfile/tsmc_04_4m2p.tf`
(`metal3Available`, `metal4Available`, `elecAvailable`, `hvAvailable` all `t`;
`metal5/6`, `polycap`, `sblock`, `highres`, `metalcap`, `ccd`, `pbase`, `cwell`
not enabled).

---

## 3. The four contact numbers are aliases, not four layers

The SCMOS spec defines dedicated contact layers that a unified CONTACT layer may
replace. In the CDK map, **all four GDS numbers are assigned to the single
Cadence layer `cc`**:

```
cc                  drawing                     25  0
cc                  drawing                     47  0
cc                  drawing                     48  0
cc                  drawing                     55  0
```

So geometry on 47/48/55 is a **contact cut**, identical in meaning to 25. They
are input aliases; they are not distinct physical cuts. `gds_layer_map.yaml`
records them under `contact_compatibility.legacy_aliases` with
`physical_cut: false`, and `layers.yaml` carries `cc: [25, 47, 48, 55]`.

---

## 4. datatype 0 is a serialisation convention, not an official purpose matrix

MOSIS SCMOS documentation defines GDS **layer numbers**. The CDK stream map
records layer/datatype `0` for every drawing layer, and no public
drawing/pin/label/net datatype matrix was recovered. Accordingly:

* `gds_policy.datatype.value = 0`
* `gds_policy.datatype.authority = siliconcraft_convention`
* `gds_policy.purpose_matrix.status = unavailable`

Claiming datatype 0 as "the official MOSIS datatype" would overstate the
evidence.

---

## 5. TSMC-specific layer semantics (from the CDK Diva deck)

Both quotes below are verbatim from `../ncsu-cdk-1.6.0/techfile/divaDRC.rul`.

### 5.1 `tactive` / THICK_ACTIVE (GDS 60) — the 5 V / HV entry point

```
/*
 * From http://www.mosis.org/Faqs/faq-design.html#4.0: "Active
 * overlapped by Thick_Active will have the thicker gate oxide.
 * Thick_Active by itself does nothing."
 */
if( hvAvailable then
    saveDerived( geomOutside( tactive active) "(DBM Rule 5.0) Thick-active without active does nothing" )
)
```

`hvAvailable` is `t` for `TSMC_CMOS035_4M2P`. So THICK_ACTIVE is the historical
entry point for the thick-oxide (5 V-class) devices, and the deck itself enforces
that tactive alone does nothing. `layers.yaml` keeps `tactive` natively, and the
reference extractor's HV markers are gated on `hvAvailable` in
`common/drc/scmos_layers.py`.

### 5.2 `elec` / POLY2 (GDS 56) — capacitor, not transistor

```
/*
 * Can't use elec in these processes to make transistors
 * From http://www.mosis.org/Whatsnew/1999/990301-ami-c5.html:
 *
 * "The AMI C5N poly2 can be used to build capacitors in a style identical to
 * SCNE (as for AMI 1.2u, Orbit 2u and TSMC 0.35u), but not transistors (same as
 * TSMC 0.35u)."
 */
if( member( techdesc list( "TSMC_CMOS035_4M2P" "TSMC_CMOS035_3M2P" ) ) then
    saveDerived( geomAnd( active elec ) "(DBM Rule 4.0, TSMC 0.4um) Elec and active may not overlap" )
)
```

Two consequences for this port:

1. POLY2 is a **capacitor/electrode** layer, so it must not be treated as a
   second gate — the profile binds no poly2 device.
2. The TSMC 0.4 µm branch adds a process-specific check that active and elec may
   not overlap, which is why the CDK deck is process-conditional here.

`pad` (GDS 26) is a non-fabrication annotation layer. `open` (23) and `pstop`
(24) belong to MEMS-class options and are not enabled for 4M2P.

---

## 6. Verification hook for the current map

If the current TSRI `TSMC035_2P4M_laker.tf` (or any legitimate D35 example GDS)
becomes available, compare these anchors first:

```
M1=49  V1=50  M2=51  V2=61  M3=62  V3=30  M4=31
CONTACT=25  POLY=46  POLY2/ELEC=56  ACTIVE=43  THICK_ACTIVE=60
```

* **All match** → the current D35 stream-out still inherits the MOSIS SCMOS map,
  and the historical map can be promoted to `inferred_authorized`.
* **Mismatch** → the mismatch localises the MOSIS→foundry translation step, and
  `gds_layer_map.yaml` must be re-derived from the licensed kit.

Until then the map stays `authority: public_reference`,
`tapeout_eligible: false`.

---

## 7. References

* `../ncsu-cdk-1.6.0/pipo/streamInLayermap` — SCMOS GDS→Cadence layer map
  (local first-hand).
* `../ncsu-cdk-1.6.0/pipo/cifInLayermap` — CIF equivalents.
* `../ncsu-cdk-1.6.0/techfile/tsmc_04_4m2p.tf` — lambda, grid, and the
  `*Available` feature flags (local first-hand).
* `../ncsu-cdk-1.6.0/techfile/divaDRC.rul` — Diva DRC deck, lines 79–101 for the
  `elec` and `tactive` semantics quoted above (local first-hand).
* `../ncsu-cdk-1.6.0/skill/globalData.il` — `NCSU_techData["TSMC_CMOS035_4M2P"]`
  (process name, techfile, techlib, `mosisCode SCN4ME_SUBM`, lambda 0.2,
  minL 0.4, minW 0.6, gridRes 0.1, `fetModelPrefix tsmc35`).
* MOSIS SCMOS 8.0 technology-code table mapping TSMC 0.35 µm 2P4M polycide to
  `SCN4ME` / `SCN4ME_SUBM` — requester-supplied citation; **not re-verified
  offline** (no network egress in the port environment).
* MOSIS FAQ 4.0 (`faq-design.html#4.0`) and the 1999-03-01 AMI C5 news item —
  quoted verbatim inside `divaDRC.rul` above; the live URLs were not fetched
  offline.
