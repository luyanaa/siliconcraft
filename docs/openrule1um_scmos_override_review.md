# OpenRule1um vs SCMOS: override review

Status: **analysis only — no policy change made.** This document exists so the
override design can be reviewed before any rule value is committed.

## SCMOS vs SCMOS_SUBM: which branch is this process?

This is the prior question, and it decides everything below. The profile
currently declares `scmos_variant: non_submicron`, i.e. the **classic** SCMOS
arm. There is real evidence it should be **SUBM**.

### The CDK classifies a 0.6um process as SUBM

`ncsu-cdk-1.6.0/skill/globalData.il` carries the per-technology table
`NCSU_techData`, whose `submicronRules` field is exactly the branch selector
(`techfile/divaDRC.rul` branches on `submicronAvailable =
NCSU_techData[techdesc]->submicronRules`):

| tech | description | lambda | minL | minW | submicronRules |
| --- | --- | --- | --- | --- | --- |
| AMI_ABN | AMI 1.6u ABN | 0.8 | 1.6 | 4.0 | **nil** |
| AMI_ABN_12 | AMI 1.2u ABN | 0.6 | 1.2 | 1.8 | **nil** |
| ORBIT_SCNA2 | Orbit 2.0u | 1.0 | 2.0 | 3.0 | **nil** |
| NCSU_EGRC | NCSU EGRC 3.0u | 1.5 | 1.5 | 1.5 | **nil** |
| AMI_CWL | AMI 0.80u CWL | 0.5 | 1.0 | 1.5 | nil (outlier) |
| **HP_CMOS26G** | **HP 0.80u** | 0.4 | 0.8 | 1.2 | **t** |
| **AMI_C5N** | **AMI 0.60u** | 0.3 | 0.6 | 1.5 | **t** |
| **HP_AMOS14TB** | **HP 0.60u** | 0.3 | 0.6 | 0.9 | **t** |
| TSMC_CMOS035_* | TSMC 0.40u | 0.2 | 0.4 | 0.6 | **t** |
| TSMC_CMOS020 | TSMC 0.20u | 0.10 | 0.20 | 0.30 | **t** |
| TSMC_CMOS025_DEEP | TSMC 0.24u DEEP | 0.12 | 0.24 | 0.36 | nil |
| TSMC_CMOS018_DEEP | TSMC 0.18u DEEP | 0.09 | 0.18 | 0.27 | nil |

Read off the table: **every 0.6um and 0.8um process is `submicronRules = t`**;
only 1.2um and larger are classic. (The two DEEP rows are `nil` because they take
the separate `deepRules` branch, not because they are classic.)

The profile's own note says OpenRule1um is *"a 1um design-rule envelope for a
nominal PTS 0.6um CMOS process"*. By the CDK's own classification, a **0.6um**
process is **SUBM**. So `scmos_variant: non_submicron` is very likely the wrong
arm, and everything derived from the `else:` branch is derived from the wrong
arm.

### The counter-evidence, stated plainly

OpenRule1um's native spacing values at lambda = 0.5 line up with the **classic**
arm, not SUBM:

| semantic rule | classic @0.5 | SUBM @0.5 | OR1 native | matches |
| --- | --- | --- | --- | --- |
| poly.min_spacing | 2λ = 1.0 | 3λ = 1.5 | `pol.space(1.0)` = 1.0 | classic |
| contact.cut_spacing | 2λ = 1.0 | 3λ = 1.5 | `dm_dcn.space(1.0)` = 1.0 | classic |
| metal.M1.min_spacing | 2λ = 1.0 | 3λ = 1.5 | `ml1.space(1.0)` = 1.0 | classic |
| poly.min_width | 2λ = 1.0 | 2λ = 1.0 | `pol.width(1.0)` = 1.0 | both |
| nwell.active_enclosure | 6λ = 3.0 | 6λ = 3.0 | `nwl.separation(ndiff,3.0)` = 3.0 | both |
| active.min_width | 3λ = 1.5 | 3λ = 1.5 | `diff.width(1.0)` = 1.0 | neither |
| nwell.min_width | 10λ = 5.0 | 12λ = 6.0 | `nwl.width(4.0)` = 4.0 | neither |
| metal.M2.min_spacing | 3λ = 1.5 | 3λ = 1.5 | `ml2.space(1.0)` = 1.0 | neither |
| metal.M3.min_spacing | 4λ = 2.0 | 3λ = 1.5 | `ml3.space(1.0)` = 1.0 | neither |

So the native **spacings** are 2λ at λ=0.5 — a classic-envelope signature —
while the native **well** values match neither arm. That is the tension: the
process *node* says SUBM, the rule *envelope* looks classic.

### Why it matters materially

Under "take the stricter of the two", the branch changes the well rules by
roughly 2x:

| rule | classic @0.5 | SUBM @0.5 | OR1 native | classic outcome | SUBM outcome |
| --- | --- | --- | --- | --- | --- |
| nwell spacing (1.2) | 4.5 | **9.0** | 5.0 | native 5.0 | **SCMOS 9.0** |
| nwell.min_width (1.1) | 5.0 | **6.0** | 4.0 | SCMOS 5.0 | **SCMOS 6.0** |

The spacings are unaffected in practice, because the native 1.0 is tighter than
SUBM's 1.5 either way. The well rules are where the choice bites: switching to
SUBM nearly doubles the required well spacing, which directly enlarges rows.

### Note on λ itself

The profile also warns that `lambda_um = 0.5` *"is the grid/reference baseline,
not a multiplier"*. If that is taken literally, neither arm's λ-scaled values can
be applied to this process without first deciding what λ means here — which is
the same lineage question, one level deeper. Worth settling together with the
branch choice.

## The SUBM computation, at both candidate λ

Two λ values are in play and they are not the same thing:

- **λ_envelope = 0.5um** — the drawing grid of the "1um design-rule envelope".
- **λ_process = 0.3um** — the nominal 0.6um process (0.6 / 2).

Computed below with openrule1um's branch context (metal3 yes, metal4 no, elec no,
submicron yes), SUBM multiples from `common/drc/scmos_reference.py`, native values
from `profiles/openrule1um/reference/drc.lydrc`:

| semantic rule | SUBM mult | @λ=0.3 | @λ=0.5 | OR1 native | tighter @0.3 | tighter @0.5 |
| --- | --- | --- | --- | --- | --- | --- |
| poly.min_width | 2.0 | 0.60 | 1.00 | 1.00 | SCMOS 0.60 | tie 1.00 |
| poly.min_spacing | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| active.min_width | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| contact.cut_size | 2.0 | 0.60 | 1.00 | 1.00 | SCMOS 0.60 | tie 1.00 |
| contact.cut_spacing | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| metal.M1.min_width | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| metal.M1.min_spacing | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| metal.M2.min_width | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| metal.M2.min_spacing | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| metal.M3.min_width | 5.0 | 1.50 | 2.50 | 1.00 | native 1.00 | native 1.00 |
| metal.M3.min_spacing | 3.0 | 0.90 | 1.50 | 1.00 | SCMOS 0.90 | native 1.00 |
| nwell.min_width | 12.0 | 3.60 | 6.00 | 4.00 | SCMOS 3.60 | **SCMOS 6.00** |
| nwell spacing (1.2) | 18.0 | 5.40 | 9.00 | 5.00 | **SCMOS 5.40** | **SCMOS 9.00** |
| nwell.active_enclosure | 6.0 | 1.80 | 3.00 | 3.00 | SCMOS 1.80 | tie 3.00 |
| gate.extension | 2.0 | 0.60 | 1.00 | 1.00 | SCMOS 0.60 | tie 1.00 |
| via12.cut_spacing | 3.0 | 0.90 | 1.50 | 0.50 | native 0.50 | native 0.50 |
| via23.cut_spacing | 3.0 | 0.90 | 1.50 | 0.50 | native 0.50 | native 0.50 |
| poly.contact_spacing | 5.0 | 1.50 | 2.50 | (none) | SCMOS 1.50 | SCMOS 2.50 |
| select.channel_enclosure | 3.0 | 0.90 | 1.50 | (none) | SCMOS 0.90 | SCMOS 1.50 |
| active.contact_enclosure | 1.0 | 0.30 | 0.50 | (none) | SCMOS 0.30 | SCMOS 0.50 |
| metal1.contact_enclosure | 1.0 | 0.30 | 0.50 | (none) | SCMOS 0.30 | SCMOS 0.50 |
| via12.lower_enclosure | 1.0 | 0.30 | 0.50 | (none) | SCMOS 0.30 | SCMOS 0.50 |

### Which λ is coherent: 0.5, not 0.3

The envelope's own arithmetic says λ = 0.5. Two independent checks:

- `pol.width(1.0)` = 1.00, and SCMOS poly width is **2λ in both branches** →
  λ = 0.5. At λ = 0.3 that rule would be 0.6, which does not describe a 1um
  envelope.
- `pol.space(1.0)`, `ml1.space(1.0)`, `dm_dcn.space(1.0)` are all 1.00, which is
  the **classic** 2λ value at λ = 0.5.

So λ_process = 0.3 does not describe the deck's geometry: it would make the
SCMOS envelope tighter than the process's own native rules almost everywhere
(0.6-0.9 vs 1.0), which would make the "native override" concept nearly vacuous.
λ = 0.5 is the drawing λ the envelope is written in.

### The combination that fits all the evidence

**SUBM branch, evaluated at λ = 0.5.** The branch follows the *process node*
(the CDK classifies 0.6um as submicron); λ follows the *drawing envelope*
(1um → 0.5). Under "take the stricter", that yields:

- **spacings** — SUBM 1.5 vs native 1.0 → **native wins** (unchanged from today)
- **widths** — SUBM 1.0 vs native 1.0 → **tie** (unchanged from today)
- **wells** — SUBM 9.0 / 6.0 vs native 5.0 / 4.0 → **SCMOS wins**, versus 4.5 / 5.0
  under classic today

So switching the branch to SUBM changes exactly one thing: **the well rules
roughly double** (nwell spacing 4.5 → 9.0, nwell width 5.0 → 6.0), which directly
enlarges rows. Every other semantic key keeps the value it has today.

That is the smallest defensible change consistent with the CDK's classification,
and it is testable: regenerating the openrule1um row and re-running its native
deck should show whether the larger wells are what the native DRC expects.

## Upstream source reviewed

`github.com/mineda-support/OpenRule1um` @
`85dbacfb05351c5116158f4d8e0d5c995d3b4ad1`, file `tech/tech/drc/drc.lydrc`.
The copy at `profiles/openrule1um/reference/drc.lydrc` is **byte-identical** to
that revision (verified by diff), so the profile is tracking current upstream.

### It is a living deck, not a frozen rule table

Its own header carries the revision log:

```
ver1.00 2018/02/10  akita11     initial
ver1.01 2018/02/23  akita11     bug fix
ver1.10 2018/03/17  akita11     add rules based on rule v110
ver1.20 2018/04/13  akita11     add rules based on rule v120
ver1.30 2018/11/27  akita11     add rules based for HPOL
ver1.31 2018/11/28  akita11     modified HPOL gap rule
ver1.50 2021/09/27  akita11     widemetal, gate-extension, NWL space
ver1.51 2021/09/30  akita11     non-MOS POL touching DIFF
       2023/08/13  S. Moriyama "temporary refine for HPOL (22-82um) -> (20-80um)"
ver1.52 2024/08/22  C. Takahashi add OFF-GRIDS rules
```

Two rules this profile leans on (`NWL space < 5.0` at line 84 and
`NWL-Ndiff space < 3.0` at line 89) were introduced in **ver1.50, 2021**. The
deck still contains a rule labelled a **"temporary refine"** from 2023.

### Rule-kind census (what the deck actually constrains)

| kind | count |
| --- | --- |
| separation (layer to layer) | 22 |
| space (self spacing) | 13 |
| ongrid (off-grid, added 2024) | 13 |
| enclosing | 11 |
| width | 10 |

### The part that matters for the override question

**1. Contacts and vias are MARKER layers, not drawn geometry.** The deck defines
`dm_dcn = input(101,0)`, `dm_pcn = 102`, `dm_nscn = 103`, `dm_pscn = 104`,
`dm_via1 = 105`, `dm_via2 = 106`. Every contact/via rule operates on those
markers; there is no rule against a drawn cut layer, because the process has no
`ca`-equivalent drawn contact.

**2. Contact/via ENCLOSURE is only checked for wide metal.** Six of the eleven
enclosure rules are gated on `*_in_widemetal`:

```
ml1.enclosing(dm_dcn_in_widemetal, 0.5)   "for wide M1 (>15um)"
ml1.enclosing(dm_pcn_in_widemetal, 0.5)
ml1.enclosing(dm_via1_in_widemetal, 0.5)
ml2.enclosing(dm_via1_in_widemetal, 0.5)
ml2.enclosing(dm_via2_in_widemetal, 0.5)
ml3.enclosing(dm_via2_in_widemetal, 0.5)
```

The other five are well/diff/poly: `nwl.enclosing(pdiff, 2.0)`,
`parea.enclosing(diff, 0.5)`, `narea.enclosing(diff, 0.5)`,
`hpol.enclosing(hipol, 5.0)`, `pol.enclosing(diff, 1.0)`.

**3. Several rules are self-declared unreliable.** The deck ships rules whose own
output text says so:

```
POL-pcont space < 0.5, may be pseudo-error (can be ignored)
ML1-dcont space < 0.5, may be pseudo-error (can be ignored)
ML1-pcont space < 0.5, may be pseudo-error (can be ignored)
```

## Why this reframes the override question

The declared policy is "SCMOS non_submicron envelope, native where stricter".
The upstream deck shows the two sources **constrain different things**, so
"take the stricter" is not sound across the board:

- SCMOS constrains a **drawn** contact layer (`ca`) with general enclosure rules
  (`5.2.b`, `6.2.b`, `7.3`, `8.3`, `9.3`). OpenRule1um has no drawn contact and
  checks enclosure only in widemetal regions against **markers**. Comparing
  SCMOS `6.2.b active-encloses-contact` with an OpenRule1um number compares rules
  about different objects.
- SCMOS's `ca`/`cc` vocabulary and OpenRule1um's marker vocabulary do not
  correspond, so a shared key like `contact.cut_size` means different things on
  each side.
- Conversely `nwl.enclosing(pdiff, 2.0)` is a real OpenRule1um enclosure rule
  with no SCMOS counterpart, so a policy that only overrides SCMOS keys cannot
  see it.

## Revised options

- **A. SCMOS-envelope-only for the shared semantic keys**, treating the
  OpenRule1um deck purely as the legality oracle it declares itself to be
  (`portable.legality.acceptance: zero_markers`) rather than as a source of
  override values for keys it does not constrain the same way.
- **B. Native-first for BEOL and contact/via**, accepting that the SCMOS
  envelope contributes little there, and recording explicitly which semantic keys
  have no OpenRule1um counterpart at all.
- **C. Keep the current mixed policy**, but only after deciding how to treat the
  marker-vs-drawn-contact mismatch, the widemetal-only enclosure gating, and the
  deck's own pseudo-error disclaimers.

## Unused upstream material worth noting

The same repository at the same revision also ships:

- `tech/tech/lvs/lvs.lylvs` — an LVS deck (the profile references only the DRC)
- `Basic/libraries/OpenRule1um_Basic.gds`
- `Basic/libraries/OpenRule1um_StdCell.gds`

Those two GDS libraries are first-hand reference layout for this process and are
referenced nowhere in the profile today. They are the natural oracle for
validating generated stdcell geometry against this process, rather than deriving
values from a rule table whose vocabulary does not line up with SCMOS.

## Why this is a question at all

OpenRule1um is a de-documented abstraction of PTC06. The expectation recorded in
the profile is that PTC06 sits close to SCMOS / SCMOS_SUBM, so the profile
chooses a **SCMOS lambda envelope as its base** and then overrides it with values
from the native deck. The open question is whether those overrides are chosen
consistently.

## What the profile already declares

`profiles/openrule1um/rules.yaml` → `rules.portable`:

```yaml
policy: scmos_lambda_envelope
lambda_um: 0.5
scmos_variant: non_submicron          # the classic (non-submicron) SCMOS arm
base_source: common/drc/scmos_reference.py
target_drc: reference/drc.lydrc
well_tightenings:
  - {id: OR1-WELL-SPACE,  layer: nwell,          base_um: 4.5, value_um: 5.0}
  - {id: OR1-WELL-NDIFF,  layer: nwell, layer2: nactive, base_um: 2.5, value_um: 3.0}
beol:
  policy: native_override
  rules:  # M1/M2/M3 width and spacing all 1.0; via marker spacings 0.5
nominal_geometry: {contact_cut_um: 1.0, via1_cut_um: 1.0, via2_cut_um: 1.0}
```

So the declared policy is: **SCMOS non_submicron envelope, with native values
substituted wherever the native deck is stricter.**

## The two sources, mechanically derived

SCMOS non_submicron values come from the `else:` arm of
`common/drc/scmos_reference.py` (the `if submicron or deep:` branch), scaled by
`lambda_um = 0.5`. Native values come from
`profiles/openrule1um/reference/drc.lydrc`, at the line numbers the profile
cites.

| semantic rule | SCMOS non-submicron @ λ=0.5 | OpenRule1um native | stricter | declared/expected |
| --- | --- | --- | --- | --- |
| active.min_width | 3λ = 1.50 | `diff.width(1.0)` = 1.00 | SCMOS 1.50 | SCMOS |
| poly.min_width | 2λ = 1.00 | `pol.width(1.0)` = 1.00 | tie 1.00 | 1.00 |
| nwell.min_width | 10λ = 5.00 | `nwl.width(4.0)` = 4.00 | SCMOS 5.00 | SCMOS |
| nwell spacing (diff potential) | 9λ = 4.50 | `nwl.space(5.0)` = 5.00 | native 5.00 | **native 5.00** (OR1-WELL-SPACE) |
| nwell–ndiff spacing | 5λ = 2.50 | `nwl.separation(ndiff,3.0)` = 3.00 | native 3.00 | **native 3.00** (OR1-WELL-NDIFF) |
| metal.M1.min_width | 3λ = 1.50 | `ml1.width(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M1.min_spacing | 2λ = 1.00 | `ml1.space(1.0)` = 1.00 | tie 1.00 | 1.00 |
| metal.M2.min_width | 3λ = 1.50 | `ml2.width(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M2.min_spacing | 3λ = 1.50 | `ml2.space(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M3.min_width | 6λ = 3.00 | `ml3.width(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| metal.M3.min_spacing | 4λ = 2.00 | `ml3.space(1.0)` = 1.00 | native 1.00 | **native 1.00** |
| via1 / via2 spacing | 3λ = 1.50 | `dm_via1.space(0.5)` = 0.50 | native 0.50 | **native 0.50** |
| contact cut size | 2λ = 1.00 | nominal geometry 1.00 | tie 1.00 | 1.00 |

Every row the profile declares as a native override is genuinely **the stricter
of the two**, and every row it leaves alone is a case where the SCMOS envelope is
already the stricter (or equal) value. So the declared policy is internally
consistent and conservative: **no rule is loosened relative to either source.**

## The one thing worth deciding

The policy is safe, but "safe" and "reasonable" are not the same question here.
Two observations to weigh:

1. **M3 is where the two sources diverge most.** SCMOS non_submicron wants M3 at
   6λ = 3.0µm wide / 4λ = 2.0µm spaced, because in the classic SCMOS stack M3 is
   a thick top metal. OpenRule1um's native M3 is an ordinary 1.0µm metal. Taking
   the native 1.0 is conservative against *both* decks, but it means the SCMOS
   envelope contributes nothing at M3 — the row geometry is driven entirely by
   the native deck there.

2. **The well tightenings are not semantic-key rules.** `OR1-WELL-SPACE` (1.2)
   and `OR1-WELL-NDIFF` (nwell/nactive) are native tightenings of SCMOS well
   spacing, but neither maps onto a key the stdcell/PCell consumers read (they
   read `nwell.min_width` and `nwell.active_enclosure`, both of which stay on the
   SCMOS value). So today those two tightenings affect the DRC envelope but not
   generated geometry.

See "Revised options" above, which supersedes the earlier A/B framing in light of
the upstream deck review.


Nothing in this document has been applied to `rules.yaml`.
