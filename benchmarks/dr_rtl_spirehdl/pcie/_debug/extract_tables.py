"""Extract encoder + decoder lookup tables from pcie golden verilog.

Both modules are huge case statements that map between 8-bit byte and 10-bit
8b/10b encoding, parameterized by running disparity `rd` and K-character
flag `k`. The verilog text patterns:

  encoder (data_in → data_out):
      8'h<DI>: data_out =! rd ? 10'b<bits_rd0> : 10'b<bits_rd1>;
  decoder ({rd, data_in} → data_out):
      11'b<rd><bits>, 11'b<rd><bits>: data_out= 8'h<DO>;

This script reads the verilog and prints the equivalent Python dict
literals so they can be copy-pasted into starting_point.py without
hand-transcribing ~250 entries × 4 fields.
"""
import re
from pathlib import Path

VERILOG = Path(__file__).resolve().parents[3] / "dr_rtl/pcie/context/starting_point.v"
src = VERILOG.read_text()

# ----------------------------------------------------------------------------
# Encoder: 8'hXX: data_out =! rd ? 10'b<negrd> : 10'b<posrd>;
# (note the `!` before rd; matches both `! rd` and `!rd`)
# ----------------------------------------------------------------------------
enc_pat = re.compile(
    r"8'h([0-9A-Fa-f]+)\s*:\s*data_out\s*=\s*!\s*rd\s*\?\s*10'b([01_]+)\s*:\s*10'b([01_]+)\s*;",
    re.MULTILINE,
)

# Walk the encoder section (k==1 branch first, then k==0 branch).
# We need to know which `k` each entry belongs to. Easiest way: find the
# `if (k) begin … endcase` block and parse that first, then the `else …`.
enc_k_section = re.search(
    r"if\s*\(\s*k\s*\)\s*begin\s*case\s*\(\s*data_in\s*\)(.*?)endcase",
    src, re.DOTALL)
enc_notk_section = re.search(
    r"else\s*begin\s*case\s*\(\s*data_in\s*\)(.*?)endcase",
    src, re.DOTALL)

def parse_encoder_section(text):
    out = {}
    for m in enc_pat.finditer(text):
        di      = int(m.group(1), 16)
        negrd   = int(m.group(2).replace("_", ""), 2)
        posrd   = int(m.group(3).replace("_", ""), 2)
        out[di] = (negrd, posrd)
    return out

enc_k    = parse_encoder_section(enc_k_section.group(1))
enc_notk = parse_encoder_section(enc_notk_section.group(1))

# ----------------------------------------------------------------------------
# Decoder: 11'b<rd><10bits>, 11'b<rd><10bits>: data_out= 8'hXX;
# Each line maps TWO 11-bit encodings (one for rd=0, one for rd=1) to one
# 8-bit byte. We flatten to a dict keyed by the 11-bit value.
# ----------------------------------------------------------------------------
dec_pat = re.compile(
    r"11'b([01_]+)\s*,\s*11'b([01_]+)\s*:\s*data_out\s*=\s*8'h([0-9A-Fa-f]+)\s*;",
    re.MULTILINE,
)

dec_k_section = re.search(
    r"if\s*\(\s*k\s*\)\s*begin\s*case\s*\(\s*\{rd,data_in\}\s*\)(.*?)endcase",
    src, re.DOTALL)
dec_notk_section = re.search(
    r"else\s*begin\s*case\s*\(\s*\{rd,data_in\}\s*\)(.*?)endcase",
    src, re.DOTALL)

def parse_decoder_section(text):
    out = {}
    for m in dec_pat.finditer(text):
        v0 = int(m.group(1).replace("_", ""), 2)
        v1 = int(m.group(2).replace("_", ""), 2)
        do = int(m.group(3), 16)
        out[v0] = do
        out[v1] = do
    return out

dec_k    = parse_decoder_section(dec_k_section.group(1))
dec_notk = parse_decoder_section(dec_notk_section.group(1))

# ----------------------------------------------------------------------------
# Emit as Python dict literals
# ----------------------------------------------------------------------------
print(f"# Encoder: {len(enc_k)} k=1 entries, {len(enc_notk)} k=0 entries")
print(f"# Decoder: {len(dec_k)} k=1 entries, {len(dec_notk)} k=0 entries")
print()
print("ENCODER_K = {")
for di in sorted(enc_k):
    negrd, posrd = enc_k[di]
    print(f"    0x{di:02x}: (0b{negrd:010b}, 0b{posrd:010b}),")
print("}")
print()
print("ENCODER_NOTK = {")
for di in sorted(enc_notk):
    negrd, posrd = enc_notk[di]
    print(f"    0x{di:02x}: (0b{negrd:010b}, 0b{posrd:010b}),")
print("}")
print()
print(f"# Decoder K table: {len(dec_k)} entries")
print("DECODER_K = {")
for k in sorted(dec_k):
    print(f"    0b{k:011b}: 0x{dec_k[k]:02x},")
print("}")
print()
print(f"# Decoder NOTK table: {len(dec_notk)} entries")
print("DECODER_NOTK = {")
for k in sorted(dec_notk):
    print(f"    0b{k:011b}: 0x{dec_notk[k]:02x},")
print("}")
