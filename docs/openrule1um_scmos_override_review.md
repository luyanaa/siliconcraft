# OpenRule1um vs SCMOS: override review

Status: **analysis only — no policy change made.** This document exists so the
override design can be reviewed before any rule value is committed.

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
