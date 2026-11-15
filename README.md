# TwoMegCoCo MMU ("DAT") board — schematic analysis

Analysis of the MMU extension board in [go4retro/TwoMegCoCo](https://github.com/go4retro/TwoMegCoCo)
(upstream commit `236b636`, 2020‑10‑22). Reported symptom: the 2 MB SRAM board works,
but the MMU/DAT board does not.

> **Method caveat:** this is a desk review of the Eagle files only. Nothing here was
> measured on hardware. Each finding is traced to specific nets and pads so it can be
> checked quickly with a meter or scope before anyone cuts traces.

## Summary

| # | Issue | Revs | Effect | Severity |
|---|-------|------|--------|----------|
| 1 | **IC15 (74245) direction is backwards** — `DIR` = R/W' | v1.1 | On every CPU **write**, IC15 drives its undriven B side onto the CPU data bus → bus contention, corrupted writes system‑wide, and the board's registers latch garbage | **Likely show‑stopper** |
| 2 | **`$FFAx` decode ignores A7** — IC13 decodes A4–A6 only | v1.0, v1.1 | Writes to `$FF2x` (PIA1: DAC/sound, VDG mode) also write the DAT RAM, overwriting task‑0 bank entries 0–3 | **Breaks DAT behaviour** |
| 3 | **CRM latch uses D5 instead of D3** | v1.0, v1.1 | "Constant RAM at `$FExx`" follows the GIME IRQ‑enable bit (`$FF90` b5) instead of MC3 (b3) | Functional bug |
| 4 | Setup items (SJ1, bypass jumpers, 512K jumper) | v1.1 | Mis-set jumpers disable or fight the buffers | Check |
| 5 | BANK0/1 timing through 5 chip levels + E‑phase mux | both | May be marginal at 1.79 MHz | Scope check |

**Most likely explanation:** if the board built is **v1.1**, issue 1 alone would stop it
working (and can make the whole machine misbehave on writes). If it is **v1.0** (no
buffers), issue 2 is the prime suspect: normal BASIC/OS activity on `$FF20`–`$FF23`
silently rewrites the bank registers, so mappings appear to "not stick". Issue 3 is real
but would only show up as wrong behaviour of `$FExx`.

### How the conclusion was reached

1. Parsed the Eagle XML schematics (`TwoMegCoCo_MMU_v1.0.sch`, `_v1.1.sch`, `TwoMegCoCo_RAM.sch`)
   into netlists with [`tools/eagle_netlist.py`](tools/eagle_netlist.py); output is in
   [`netlists/`](netlists/).
2. Mapped gate pins to physical pads from each part's embedded library device, then
   confirmed the key nets against the `.brd` files (so the PCB matches the schematic —
   these are design errors, not layout errors).
3. Traced each function the board must implement against the GIME/Disto register model:
   `$FF90` (MMU enable, CRM), `$FF91` (task), `$FF9B` (video bank), `$FFA0–$FFAF`
   (upper bank bits, write‑only), and the per‑cycle bank selection path.
4. Cross‑checked against Jim Brain's own CPLD design for the CoCo 1/2 sibling
   ([go4retro/iMMUnity](https://github.com/go4retro/iMMUnity), `hdl/CocoMemJr.v`), which
   implements the same register semantics in Verilog (e.g. CRM = `data_cpu[3]`).
5. Diffed the v1.0 and v1.1 netlists: the only change is the addition of buffers
   IC15/IC16/IC18/IC19 and bypass solder jumpers — so issues 2 and 3 are inherited, and
   issue 1 was introduced in v1.1.

---

## How the board works (as designed)

The board sits between the 68B09E and its socket (`IC6` = socket on top, `HDR1` = pins
into the motherboard; all CPU signals pass straight through). The GIME still produces
bank bits 0–5 (512 KB); this board supplies **bank bits 6–7** (`BANK0`, `BANK1`) to the
TwoMegCoCo RAM board, giving 4 × 512 KB = 2 MB, Disto‑style.

| Block | Parts | Function |
|-------|-------|----------|
| Buffers (v1.1) | IC15 '245 data, IC16/IC18 '541 address, IC19 '541 E, R/W, RESET | Create primed `X'` copies of CPU signals; enabled by `BA'` (SJ1) |
| `$FExx/$FFxx` decode | IC11 '30, IC17C '10 (inverter), IC4A/B '32 | `!CE_FFXX`, `!CE_FEXX` (qualified by `ON/!OFF` = 512K jumper) |
| Write decode | IC13 '138 (A4–A6), IC12 '138 (`$FF90/91`), IC14 '138 (`$FF9B`) | Write strobes, active during E with R/W = 0 |
| Registers | IC2A `MMU_EN` (D6), IC1B `CRM` (D5 ← bug), IC1A `TASK` (D0), IC10A/B `VBANK1/0` (D1/D0) | Mirrors of GIME `$FF90`, `$FF91`, plus `$FF9B` video bank |
| DAT RAM | IC5 32K×8 SRAM (only A0–A3, D0–D1 used) | 16 entries × 2 bits: task (1 bit) × 8 slots |
| DAT address mux | IC3 '244: half A = `A0'–A3'` on `!WE_FFAX`; half B = `{A13'–A15', TASK}` on `!MMU_SEL` | Register‑write address vs. translation address |
| DAT data in | IC7A '244: `D6', D7'` → `BD0, BD1` on `!WE_FFAX` | Upper bank bits are D6/D7 of `$FFAx` writes |
| Bank output | IC9 '157 (DAT vs 0, sel `!MMU_SEL`), IC8 '157 (CPU vs `VBANK`, sel `CPU_BANK` = E' + !MMU_EN) | Drives `BANK0/1` to RAM board |

On the RAM board, `BANK0` is SRAM A0 on all four AS6C4008s and `BANK1` selects the
chip pair via the '139 gated by `!CAS`; both have 10 kΩ pull‑ups (R1/R2).

---

## Issue details

### 1 — IC15 74245 direction is reversed (v1.1)

Nets (v1.1):

```
R/!W' : IC13.G2B  IC15.DIR  IC19.Y2  SJ27        (.brd: IC15 pad 1)
D0..D7   (CPU side)  -> IC15 A1..A8 (pads 2–9)
D0'..D7' (board side)-> IC15 B1..B8 (pads 18–11) -> only flip-flop D inputs, IC7 inputs
```

74245: DIR = H → A→B, DIR = L → B→A.

* CPU read (R/W = 1): A→B — harmless, board sees the bus.
* CPU **write** (R/W = 0): **B→A** — IC15 drives the CPU data bus from the board‑side
  nets, which nothing drives. This fights the 6809 on every write cycle, and the board
  never sees the written data, so `$FF90/$FF91/$FF9B/$FFAx` latch garbage.

The board only ever *receives* data (all its registers are write‑only), so the 245
should be one‑way.

**Fix:** lift IC15 pin 1 and tie it to VCC (A→B always), or substitute a 74x541.
Next revision: tie DIR high (or use a '541).

### 2 — `$FFAx` write strobe ignores A7 (v1.0 and v1.1)

```
IC13 (74138):  A = A4'  B = A5'  C = A6'   G1 = E'  G2A = !CE_FFXX  G2B = R/!W'
               Y1 -> !WE_FF9X     Y2 -> !WE_FFAX  (pad 13)
A7' : IC12.G1  IC14.G1  IC16.Y8  SJ9            <- reaches the $FF9x decoders, NOT IC13
```

`!WE_FFAX` therefore asserts for any write to **`$FF2x` or `$FFAx`** (A7 = don't care).
`!WE_FF9X` likewise fires for `$FF1x`, but IC12/IC14 gate it again with A7, so the
`$FF9x` registers are safe — which is probably why the missing term on the `$FFAx` path
went unnoticed.

`$FF20`–`$FF2F` is PIA1 (DAC/sound, cassette, VDG mode/CSS). Its registers are written
constantly. Each write stores D6/D7 into DAT entry `A3..A0`:

| CPU write | Clobbers DAT entry |
|-----------|--------------------|
| `$FF20` (DAC / cassette out) | task 0, slot 0 (`$FFA0`) |
| `$FF21` (CA control) | task 0, slot 1 (`$FFA1`) |
| `$FF22` (VDG mode / single‑bit sound) | task 0, slot 2 (`$FFA2`) |
| `$FF23` (CB control / sound enable) | task 0, slot 3 (`$FFA3`) |

Symptom: upper bank bits for `$0000–$7FFF` in task 0 drift to whatever bits 6–7 the
PIA writes contained — mappings "don't stick", or memory above 512 KB seems to alias.

**Fix:** require A7' = 1 in IC13's enable. All gates on the board are in use (IC4, IC11,
IC17 full), so a bodge needs one extra gate, e.g. lift **IC13 pin 6 (G1)** and drive it
from a piggy‑backed 74HCT08 (or 74AHCT1G08) computing `E' AND A7'`:

* `E'` is available at IC19 pin 18 (v1.1) / CPU E (v1.0)
* `A7'` is available at IC16 pin 11 (v1.1) / CPU A7 (v1.0)

### 3 — CRM flip‑flop latches D5 instead of D3 (v1.0 and v1.1)

```
!WE_FF90 -> IC1B.CLK, IC2A.CLK
D5'  : IC1.B.D (pad 12)  IC15.B6  SJ23        <- CRM
D6'  : IC2.A.D           ...                  <- MMU_EN (correct)
D3'  : IC15.B4 (pad 15)  SJ21                 <- unused
```

GIME `$FF90` (INIT0): b7 COCO, b6 MMUEN, b5 IEN, b4 FEN, **b3 MC3 (`$FExx` constant)**,
b2 MC2, b1–0 ROM map. MMU_EN is correctly bit 6; CRM should be bit 3. The CPLD sibling
design uses `data_cpu[3]` for the same flag.

Effect: when software enables GIME IRQs, the board forces `$FExx` to bank‑bits 00 even
if MC3 is off, and vice versa. It doesn't explain "no DAT at all", but it will cause odd
behaviour under OS‑9/NitrOS‑9 (which uses constant `$FExx`).

**Fix:** cut the trace to IC1 pin 12 and jumper it to D3' (IC15 pin 15 in v1.1; CPU D3
in v1.0).

### 4 — Assembly / jumper checks (v1.1)

* **SJ1** (3‑way) must be bridged to either GND or BA. Left open, `BA'` floats and every
  buffer's output‑enable is undefined.
* **SJ2–SJ28** are buffer bypasses. Bridge them only if IC15/16/18/19 are *not*
  fitted; with both, buffers and jumpers short against each other.
* The **512K** jumper must be open (it pulls `ON/!OFF` low and disables decoding).
* IC19 inputs A4–A8 (pads 5–9) and all of IC2B (except CLR) are left floating — tie them
  off on the next revision. Unlikely to cause the failure.

### 5 — Bank‑bit timing (both)

The translated path is `A13–A15` → IC18 '541 → IC3 '244 → IC5 SRAM (tAA) → IC9 '157 →
IC8 '157 → RAM board '139/SRAM A0. That's 4 gate delays plus SRAM access, and IC8 switches
`BANK0/1` between the CPU and `VBANK` values on E. The RAM board uses `BANK0` as SRAM
A0 and decodes `BANK1` under `!CAS`, so the bits must be stable for the whole
CPU‑phase CAS window. Worth scoping `BANK0/1` against `!CAS` and E at 1.79 MHz (`POKE
65497,0`) once issues 1–3 are fixed; with LS parts and a slow SRAM it may be tight.

Minor, related: `!WE_FFAX` both strobes IC5 `!WE` and enables the IC3A/IC7A address/data
buffers, so address and data are released at the same instant WE rises (zero hold time).
It usually works with fast SRAM, but delaying the buffer release slightly relative to WE
would be more robust.

---

## Suggested bring‑up order

1. Confirm which revision was built.
2. v1.1: fix IC15 DIR (issue 1); verify SJ1, bypass jumpers, 512K jumper.
3. Fix the A7 qualification (issue 2) and CRM bit (issue 3).
4. Test with MMU on: write distinct D6/D7 patterns to `$FFA0–$FFAF`, then `POKE` `$FF20`
   and `$FF22`, and confirm with a scope/logic probe on `BANK0/1` (or by reading back
   tagged memory) that entries 0–3 are unchanged.
5. Scope `BANK0/1` vs `!CAS` at 0.89 and 1.79 MHz.

## Files

* [`tools/eagle_netlist.py`](tools/eagle_netlist.py) — Eagle XML → text netlist
* [`netlists/`](netlists/) — extracted netlists for MMU v1.0, MMU v1.1 and the RAM board

Reproduce:

```sh
git clone https://github.com/go4retro/TwoMegCoCo
python3 tools/eagle_netlist.py TwoMegCoCo/pcb/TwoMegCoCo_MMU_v1.1.sch
```
