#!/usr/bin/env python3
"""Validate materialized OpenRule1um frontend, support, and stdcell views."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
PROFILE = ROOT / "profiles" / "openrule1um"
COMPAT = PROFILE / "compatibility"
UPSTREAM = PROFILE / "reference" / "upstream"
ANAGIX = COMPAT / "klayout" / "anagixloader"

PINNED_COMMIT = "85dbacfb05351c5116158f4d8e0d5c995d3b4ad1"
EXPECTED_SUPPORT_CELLS = {
    "DIODE_COMMON", "PadFrame80", "Via", "Via2", "dcont", "dcont$1", "dcont1",
    "nchOR1", "ndio_min", "nsubcont", "pcont", "pdio_min", "psubcont", "rpolyOR1_ex",
}
EXPECTED_STDCELL_CELLS = {
    "FILL", "Via2", "an21", "an31", "an41", "buf1", "buf2", "buf4", "buf8", "cinv",
    "dff1", "dff1_r", "dff1m2", "dff1m2_r", "exnr", "exor", "inv1", "inv2", "inv4",
    "inv8", "na21", "na212", "na222", "na31", "na41", "nch", "nchOR1", "nchOR1ex",
    "nr21", "nr212", "nr222", "nr31", "or21", "or31", "pch", "pchOR1", "pchOR1ex",
    "rff1", "rff1_r", "rff1m2", "rff1m2_r", "sff1", "sff1_r", "sff1m2", "sff1m2_r",
}
EXPECTED_STDCELL_SYMBOLS = {
    "an21", "an31", "an41", "buf1", "buf2", "buf4", "buf8", "cinv",
    "dff1", "dff1_r", "dff1m2", "dff1m2_r", "exnr", "exor", "fill",
    "inv1", "inv2", "inv4", "inv8", "na21", "na212", "na222", "na31", "na41",
    "nr21", "nr212", "nr222", "nr31", "or21", "or31", "rff1", "rff1_r",
    "rff1m2", "rff1m2_r", "sff1", "sff1_r", "sff1m2", "sff1m2_r",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"[compat] FAIL: {message}")


def read(path: Path) -> str:
    require(path.is_file(), f"missing materialized file: {path.relative_to(ROOT)}")
    return path.read_text(errors="replace")


def check_manifest() -> dict:
    import yamlish

    manifest = yamlish.load(read(COMPAT / "manifest.yaml"))
    support = yamlish.load(read(PROFILE / "support_cells.yaml"))
    catalog = yamlish.load(read(COMPAT / "stdcell_catalog.yaml"))
    pex = yamlish.load(read(PROFILE / "pex" / "manifest.yaml"))
    official = yamlish.load(read(PROFILE / "official" / "manifest.yaml"))
    for doc_name, doc in (("compatibility", manifest), ("support", support), ("catalog", catalog)):
        require((doc.get("source") or {}).get("commit") == PINNED_COMMIT,
                f"{doc_name} source commit is not pinned")

    expected_paths = [
        COMPAT / "ltspice" / "models" / "OR1_mos",
        COMPAT / "ltspice" / "models" / "BSIM3V3N.mod",
        COMPAT / "ltspice" / "models" / "BSIM3V3P.mod",
        COMPAT / "ltspice" / "OR1LIB" / "NMOS.asy",
        COMPAT / "ltspice" / "OR1LIB" / "PMOS.asy",
        COMPAT / "kicad" / "LTspiceLIB.kicad_sym",
        COMPAT / "kicad" / "MinedaLIB.kicad_sym",
        COMPAT / "qucs-s" / "user_lib" / "LTspiceLIB.lib",
        COMPAT / "qucs-s" / "user_lib" / "MinedaLIB.lib",
        COMPAT / "klayout" / "OpenRule1um.lyt",
        COMPAT / "klayout" / "OpenRule1um.lyp",
        ANAGIX / "LICENSE.txt",
        ANAGIX / "README.md",
        ANAGIX / "macros" / "loader.lym",
        ANAGIX / "macros" / "MinedaCommon.rb",
        ANAGIX / "macros" / "MinedaPCell.rb",
        UPSTREAM / "OpenRule1um_Basic.gds",
        UPSTREAM / "OpenRule1um_StdCell.gds",
    ]
    for path in expected_paths:
        require(path.is_file() and path.stat().st_size > 0, f"empty compatibility asset: {path.relative_to(ROOT)}")
    basic_hash = hashlib.sha256((UPSTREAM / "OpenRule1um_Basic.gds").read_bytes()).hexdigest()
    stdcell_hash = hashlib.sha256((UPSTREAM / "OpenRule1um_StdCell.gds").read_bytes()).hexdigest()
    require(basic_hash == support["source"]["materialized_sha256"], "Basic support GDS hash changed")
    require(stdcell_hash == manifest["stdcell"]["gds_sha256"], "StdCell GDS hash changed")
    klayout_doc = manifest["klayout"]
    technology = read(COMPAT / "klayout" / "OpenRule1um.lyt")
    require("<dbu>0.001</dbu>" in technology, "KLayout technology DBU is not 0.001um")
    require("<layer-properties_file>OpenRule1um.lyp</layer-properties_file>" in technology,
            "KLayout technology does not select the local layer properties")
    require("original-base-path>C:\\Users" not in technology, "KLayout technology retains a host-specific base path")
    macro_names = {path.name for path in (COMPAT / "klayout" / "macros" / "upstream").glob("*.lym")}
    require(len(macro_names) == 13 and "Hello OpenRule1um.lym" in macro_names,
            "KLayout GUI macro sources are incomplete")
    require(klayout_doc["gui_technology_portable"] is True
            and klayout_doc["original_base_path_normalized"] is True,
            "KLayout GUI technology portability is not declared")
    runtime = klayout_doc["gui_runtime_dependency"]
    require(runtime["commit"] == "ca2da6795c4e216bae44cfd76b8fafeabff5c6b4",
            "AnagixLoader source commit is not pinned")
    require(klayout_doc["gui_runtime_sources_materialized"] is True,
            "AnagixLoader runtime sources are not materialized")
    runtime_hashes = {
        ANAGIX / "LICENSE.txt": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        ANAGIX / "README.md": "2c9f9953d0a9402ede44dc1d99d439a216eee95386213104867d876031b52c73",
        ANAGIX / "macros" / "loader.lym": "fa3f4769f6e150d336addc189a64dea2e344ad050124ceb93c61fa478d39d776",
        ANAGIX / "macros" / "MinedaCommon.rb": "ab10b5d9bc83010bbda3aceae0ed0bd4f29621d98325de96b561a2ca63b88009",
        ANAGIX / "macros" / "MinedaPCell.rb": "c629463e71526fb01ad8f289307cc0f8049dc75ca6b91425f8ba1c61d60bd9af",
    }
    for path, expected in runtime_hashes.items():
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                f"pinned AnagixLoader asset changed: {path.relative_to(ROOT)}")

    require(official["drc"]["available"] is False, "authoritative DRC was not disabled")
    require(official["drc"]["lambda_um"] == 0.5, "official override slot lost lambda=0.5")
    require(official["drc"]["geometry_scaling"] == "none", "official override scales geometry")
    require(pex["default"] == "none" and pex["status"] == "deferred", "PEX is not explicitly deferred")
    require(catalog["views"]["lef"]["status"] == "not_supplied_upstream", "LEF availability was fabricated")
    require(catalog["views"]["liberty"]["status"] == "not_supplied_upstream", "Liberty availability was fabricated")
    return manifest


def check_ltspice(manifest: dict) -> None:
    models = read(COMPAT / "ltspice" / "models" / "OR1_mos")
    nmos = read(COMPAT / "ltspice" / "models" / "BSIM3V3N.mod")
    pmos = read(COMPAT / "ltspice" / "models" / "BSIM3V3P.mod")
    require("BSIM3V3N.mod" in models and "BSIM3V3P.mod" in models, "LTspice wrapper omits a model card")
    require(re.search(r"^\s*\.model\s+nch\b", nmos, re.IGNORECASE | re.MULTILINE), "nch card is absent")
    require(re.search(r"^\s*\.model\s+pch\b", pmos, re.IGNORECASE | re.MULTILINE), "pch card is absent")
    for symbol_name, model_name in (("NMOS.asy", "nch"), ("PMOS.asy", "pch")):
        symbol = read(COMPAT / "ltspice" / "OR1LIB" / symbol_name)
        require("SYMATTR Prefix M" in symbol, f"{symbol_name} lacks MOS prefix")
        require(f"SYMATTR Value {model_name}" in symbol, f"{symbol_name} is not bound to {model_name}")
        for order in range(1, 5):
            require(f"SpiceOrder {order}" in symbol, f"{symbol_name} pin order is incomplete")
    asy_files = {path.name for path in (COMPAT / "ltspice" / "OR1LIB").glob("*.asy")}
    require(len(asy_files) == 19, f"LTspice OR1LIB symbol count changed: {len(asy_files)}")
    require(not any(path.name.endswith("~") for path in (COMPAT / "ltspice" / "OR1LIB").iterdir()),
            "LTspice backup symbols were materialized as compatibility inputs")
    kicad_ltspice = read(COMPAT / "kicad" / "LTspiceLIB.kicad_sym")
    kicad_mineda = read(COMPAT / "kicad" / "MinedaLIB.kicad_sym")
    require('(symbol "nmos"' in kicad_ltspice and '(symbol "pmos"' in kicad_ltspice,
            "KiCad LTspice bundle lacks generic MOS symbols")
    require("NMOS_MIN" in kicad_mineda and "PMOS_MIN" in kicad_mineda
            and "nch" in kicad_mineda and "pch" in kicad_mineda,
            "KiCad Mineda bundle lacks OpenRule1um process MOS bindings")
    require("NMOS" in read(COMPAT / "qucs-s" / "user_lib" / "LTspiceLIB.lib"),
            "Qucs-S LTspice bundle lacks NMOS")
    require(manifest["ltspice"]["models"]["names"] == ["nch", "pch"], "LTspice model names are not isolated")


def klayout_inventory(klayout: str, gds: Path, technology: Path | None = None) -> tuple[float, set[str], set[str]]:
    script = '''
layout = RBA::Layout::new
layout.read(ENV["GDS"])
puts "DBU=#{layout.dbu}"
puts "TOPS=#{layout.top_cells.map { |cell| cell.name }.sort.join("|")}"
puts "CELLS=#{layout.each_cell.map { |cell| cell.name }.sort.join("|")}"
'''
    with tempfile.NamedTemporaryFile("w", suffix=".rb", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        env = os.environ.copy()
        env["GDS"] = str(gds)
        command = [klayout, "-b"]
        if technology is not None:
            command.extend(["-nn", str(technology)])
        command.extend(["-r", str(script_path)])
        proc = subprocess.run(command, env=env,
                              capture_output=True, text=True, check=False)
    finally:
        script_path.unlink(missing_ok=True)
    detail = (proc.stdout + proc.stderr).strip()
    require(proc.returncode == 0, f"KLayout could not read {gds.name}: {detail}")
    fields = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    require("DBU" in fields and abs(float(fields["DBU"]) - 0.001) < 1e-12,
            f"{gds.name} DBU is not 0.001um")
    tops = set(fields.get("TOPS", "").split("|")) - {""}
    cells = set(fields.get("CELLS", "").split("|")) - {""}
    return float(fields["DBU"]), tops, cells


def check_gds_and_symbols(manifest: dict, klayout: str) -> None:
    technology = COMPAT / "klayout" / "OpenRule1um.lyt"
    _, support_tops, support_cells = klayout_inventory(
        klayout, UPSTREAM / "OpenRule1um_Basic.gds", technology
    )
    require(EXPECTED_SUPPORT_CELLS.issubset(support_cells), "Basic GDS lacks a declared support-cell role")
    require({"Via", "dcont", "pcont", "nsubcont", "psubcont"}.issubset(support_tops),
            "Basic GDS top-cell inventory does not expose core support cells")

    _, std_tops, _ = klayout_inventory(
        klayout, UPSTREAM / "OpenRule1um_StdCell.gds", technology
    )
    require(std_tops == EXPECTED_STDCELL_CELLS, "StdCell GDS top-cell catalog differs from the pinned catalog")
    require(len(std_tops) == manifest["stdcell"]["gds_top_cell_count"] == 45,
            "StdCell GDS top-cell count is not 45")
    symbol_names = {path.stem for path in (COMPAT / "xschem" / "stdcells").glob("*.sym")}
    require(symbol_names == EXPECTED_STDCELL_SYMBOLS, "Xschem standard-cell symbol catalog differs")
    require(len(symbol_names) == manifest["stdcell"]["xschem_symbol_count"] == 38,
            "Xschem standard-cell symbol count is not 38")


def check_top_cell_drc(klayout: str) -> None:
    run_drc = SCRIPT_DIR / "run_drc.py"
    with tempfile.TemporaryDirectory(prefix="openrule1um-compat-drc-") as tmp:
        work = Path(tmp)
        for gds, top in (("OpenRule1um_Basic.gds", "Via"), ("OpenRule1um_StdCell.gds", "inv1")):
            out = work / f"{top}.lyrdb"
            summary = work / f"{top}.json"
            proc = subprocess.run([
                sys.executable, str(run_drc), "--profile", "openrule1um", "--deck", "reference",
                "--layout", str(UPSTREAM / gds), "--top-cell", top,
                "--out", str(out), "--summary", str(summary), "--klayout", klayout,
            ], capture_output=True, text=True, check=False)
            detail = (proc.stdout + proc.stderr).strip()
            require(proc.returncode == 0, f"top-cell DRC failed for {gds}:{top}: {detail}")
            require(out.is_file() and summary.is_file(), f"top-cell DRC produced no report for {gds}:{top}")


def check_ngspice() -> None:
    ngspice = shutil.which("ngspice")
    if not ngspice:
        print("[compat] LTspice model smoke: SKIP ngspice is unavailable")
        return
    with tempfile.TemporaryDirectory(prefix="openrule1um-ngspice-") as tmp:
        deck = Path(tmp) / "mos.cir"
        deck.write_text("\n".join([
            "* OpenRule1um LTspice model compatibility smoke",
            f'.include "{(COMPAT / "ltspice" / "models" / "OR1_mos").resolve()}"',
            "Vd d 0 1",
            "Vg g 0 1",
            "Vs s 0 0",
            "Vb b 0 0",
            "M1 d g s b nch W=2u L=1u",
            ".op",
            ".end",
            "",
        ]))
        proc = subprocess.run([ngspice, "-b", str(deck)], capture_output=True, text=True, check=False)
        detail = (proc.stdout + proc.stderr).lower()
        require(proc.returncode == 0, f"ngspice could not load LTspice model family: {detail}")
        require("unknown model" not in detail and "could not find" not in detail,
                "ngspice reported an unresolved LTspice model")
        print("[compat] LTspice model smoke: PASS via ngspice")

def check_gui_runtime(klayout: str) -> None:
    ruby = shutil.which("ruby")
    if not ruby:
        print("[compat] KLayout GUI runtime syntax smoke: SKIP ruby is unavailable")
        return
    for source in (
        ANAGIX / "macros" / "MinedaCommon.rb",
        ANAGIX / "macros" / "MinedaPCell.rb",
    ):
        proc = subprocess.run([ruby, "-c", str(source)], capture_output=True, text=True, check=False)
        require(proc.returncode == 0, f"Ruby syntax failed for {source.relative_to(ROOT)}: {proc.stderr}")
    proc = subprocess.run(
        [klayout, "-b", "-r", str(ANAGIX / "macros" / "loader.lym")],
        capture_output=True,
        text=True,
        check=False,
    )
    require(proc.returncode == 0, f"KLayout could not load AnagixLoader macro: {proc.stderr}")
    print("[compat] KLayout GUI runtime source smoke: PASS")


def main() -> int:
    manifest = check_manifest()
    check_ltspice(manifest)
    klayout = shutil.which("klayout")
    require(klayout is not None, "KLayout is required for compatibility GDS checks")
    check_gui_runtime(klayout)
    check_gds_and_symbols(manifest, klayout)
    check_top_cell_drc(klayout)
    check_ngspice()
    print("[compat] LTspice/KiCad/Qucs-S/KLayout/stdcell/support-cell compatibility: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
