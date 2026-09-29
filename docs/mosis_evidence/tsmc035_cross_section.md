# TSMC 0.35um cross-section thickness — TSMC035 design rules

Evidence for the TSMC035 (N88Y) planned profile field stack.

Source: "TSMC035um Thickness Rule" — TSMC 0.35 um design rules (official TSMC
content), third-party-hosted PowerPoint on scribd presentation 363796096
(retrieved 2026-09-29, text extraction). Same class as the T27K scribd mirror:
`official` content, `official-mirror` hosting.

## Cross-section (slide 3, 4-metal option)

| Layer | Thickness |
| --- | --- |
| M4 | 0.925 um |
| Via3 / Oxide4 (M3->M4 ILD) | 1.1 um |
| M3 | 0.64 um |
| Via2 / Oxide3 (M2->M3 ILD) | 1.1 um |
| M2 | 0.64 um |
| Via1 / Oxide2 (M1->M2 ILD) | 1.1 um |
| M1 | 0.67 um |
| Thick oxide (poly->M1) | 1.09 um |
| Gate oxide | 0.0078 um (78 A) |
| Poly2 / Poly1 / active + substrate | (poly thickness not stated) |

Total stack height: 7.275 um.

## Consistency

- Gate oxide 78 A matches T27K's TOX 78 A and is consistent with N88Y's 76 A
  (run-to-run spread). N88Y report: SCN035H, dual poly (POLY2 47.4 ohm/sq), so
  the double-poly cross-section applies.
- k values are not stated in this rules deck; use SiO2 3.9 for all oxide tiers.
- AMS C35 (ENG-182, the ams_c35 stack source) is the same 0.35 um generation:
  its M1 0.665 um / IMD1 1.0 um agree numerically with the above M1 0.67 /
  IMD1 1.1 um, cross-validating both (no licensing relationship asserted).

## N88Y mapping (3-metal run)

The N88Y report has MTL1..MTL3 only (no MTL4 column): sheet 0.07/0.07/0.04.
M3 = 0.04 ohm/sq is the thick top-metal tier, matching the 4M option's M4
(0.04 ohm/sq in T27K/N88Y). Mapping for the N88Y profile:
M1 0.67 um / M2 0.64 um / M3(top) 0.925 um; ILD tiers 1.1 um; poly->M1 1.09 um.
[INFERENCE: 3M top metal falls in the 4M M4 thickness class — the rules deck
only gives the 4M option.]

## Gaps

- Poly1/Poly2 film thickness not stated in the deck.
- Substrate resistivity not stated (node-typical ~15 ohm-cm in RF papers; treat
  as derived).
- The deck shows the 4M option; N88Y is 3M (top-metal mapping inferred above).
