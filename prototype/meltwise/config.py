"""Plant, tariff and physics constants for the MeltWise prototype.

Tags in brackets point to Supporting_Material/Research_Notes_and_Sources.md
(F = sourced fact, E = engineering estimate, A = prototype assumption).
"""

# --- Furnace (one 1 t medium-frequency coreless furnace, iron foundry) ---
FURNACE_CAPACITY_T = 1.0          # clusters run 500 kg to 1 t furnaces [F6]
RATED_POWER_KW = 650.0            # gives ~52-55 min melting at best practice [E4, A]
UNDERPOWER_THRESHOLD = 0.90       # below 90% of rated counts as under-powered [F3]
SPEC_TAP_TEMP_C = {"grey": 1480.0, "sg": 1510.0}  # typical tapping temperatures [A]

# --- Thermal model (heat in kWh; liquid iron cp 0.228 kWh/t.K [E1]) ---
CP_LIQUID_KWH_T_K = 0.228
LIQUIDUS_C = 1150.0
H_AT_1450_KWH_T = 375.0           # heat content of liquid iron at 1450 C [F7: theoretical 388 kWh/t]
H_LIQUIDUS_KWH_T = H_AT_1450_KWH_T - CP_LIQUID_KWH_T_K * (1450.0 - LIQUIDUS_C)
STEEL_EXTRA_KWH_T = 12.0          # carburising and higher melting point of steel scrap, per t of steel [A]
SAND_HEAT_KWH_KG = 1.1 * 0.77     # 1 kg sand wastes ~1.1 kWh electricity [F9]
ETA_SOLID = 0.78                  # electricity to bath heat while solid; coil couples well to solid charge [F7, F17, A]
ETA_LIQUID = 0.77                 # on a molten bath, 0.97 x ~0.80 [F7, F17]
CLOSED_LOSS_KW_AT_1500 = 45.0     # conduction to water-cooled coil + lid-gap radiation [E3]
OPEN_LID_EXTRA_KW_AT_1500 = 43.0  # extra radiation with the lid open [E2]
LINING_SOAK_KWH = 25.0            # heat to re-soak the lining after each tap [A]
LINING_HOT_FACE_MIN_C = 1000.0    # lining hot face stays near this between back-to-back heats [A]

# --- Shop-floor practice (minutes of necessary lid-open time are not waste) ---
CHARGE_LID_MIN = 1.0              # each charging or back-charging event
DIP_LID_MIN = 1.0                 # each temperature dip / sample
TAP_MIN = 3.0                     # pouring, power off
BACKCHARGE_FRACTIONS = (0.30, 0.55, 0.75)
OVERSHOOT_TOLERANCE_C = 5.0       # tapping within 5 C of spec is good practice, not waste [A]

# --- Economics and carbon ---
TARIFF_INR_KWH = 8.0              # FY26 industrial average range 7.55-9.04 [F11]
SOLAR_DISCOUNT = 0.15             # solar hours 10-20% cheaper [F10]
PEAK_MULTIPLIER = 1.20            # C&I peak at least 1.2x normal [F10]
SOLAR_HOURS = (9, 17)             # 8 solar hours; each state regulator sets them [F10, A]
PEAK_HOURS = (18, 22)             # [A]
GRID_EF_KG_KWH = 0.710            # CEA v21.0, FY2024-25 [F12]
