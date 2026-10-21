"""Constants for the Vitovent 300-W eBUS integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "vitovent_ebus"

CONF_PREFIX = "topic_prefix"
DEFAULT_PREFIX = "ebusd/Vitovent300W400"

# options (all optional, set in the options flow)
CONF_KITCHEN_POWER = "kitchen_power"
CONF_COOKING_WATTS = "cooking_watts"
CONF_BATH_HUMIDITY = "bath_humidity"
CONF_BATH_LIMIT = "bath_humidity_limit"
CONF_ROOM_HUMIDITY = "room_humidity_max"
CONF_ROOM_LIMIT = "room_humidity_limit"
CONF_CO2 = "co2"
CONF_CO2_LIMIT = "co2_limit"
CONF_INDOOR_TEMP = "indoor_temperature"
CONF_PRESENCE = "presence"
CONF_VACATION = "vacation"
CONF_WEEKLY_PLAN = "weekly_plan"
CONF_HEATING_MONTHS = "heating_months"
CONF_COOLING_MONTHS = "cooling_months"
CONF_NIGHT_START = "night_start"
CONF_NIGHT_END = "night_end"

DEFAULTS = {
    CONF_COOKING_WATTS: 500,
    CONF_BATH_LIMIT: 70,
    CONF_ROOM_LIMIT: 65,
    CONF_CO2_LIMIT: 1000,
    CONF_HEATING_MONTHS: ["10", "11", "12", "1", "2", "3", "4"],
    CONF_COOLING_MONTHS: ["5", "6", "7", "8", "9"],
    CONF_NIGHT_START: 21,
    CONF_NIGHT_END: 6,
}

# Stages. "Holiday" (50 m³/h) is deliberately not offered: on the tested unit it ran in ConstantPWM
# with the exhaust fan at ~3,460 rpm (negative pressure in the house). For less air, lower the air volume
# of the stage "Reduced" instead (parameter "Air volume Reduced", 50–400 m³/h, stays in ConstantFlow).
STAGES = ["reduced", "normal", "high"]
STAGE_TO_EBUS = {"reduced": "Reduced", "normal": "Normal", "high": "High"}
EBUS_TO_STAGE = {"Holiday": "holiday", "Reduced": "reduced", "Normal": "normal", "High": "high", "Auto": "auto"}
MODES = ["auto", "reduced", "normal", "high"]

REASONS = [
    "fixed", "vacation", "boost", "cooking", "bathroom_humid", "room_humidity_high", "co2_high",
    "summer_night_cooling", "nobody_home", "time_program", "weekly_plan", "heating_period", "night", "day",
]

# Time program (like a heating/hot-water program): 4 windows, each with days, start, end, stage.
# start == end means the whole day; start > end runs over midnight.
SLOTS = 4
DAY_OPTIONS = ["daily", "mon_fri", "sat_sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]
SLOT_DEFAULTS = [
    {"active": False, "days": "mon_fri", "start": "06:30", "end": "08:00", "stage": "normal"},
    {"active": False, "days": "mon_fri", "start": "17:00", "end": "22:00", "stage": "normal"},
    {"active": False, "days": "sat_sun", "start": "08:00", "end": "22:00", "stage": "normal"},
    {"active": False, "days": "daily", "start": "12:00", "end": "13:00", "stage": "high"},
]

# ebusd message names (config Vitovent300W400 from pvyleta/ebusd-brink-hru)
MSG_STAGE_SET = "Ventilatorbetrieb"
MSG_RESET = "ResetNotifications"
# unit parameters (installer level): air volume per stage and permanent imbalance (supply = volume + imbalance)
PARAM_MESSAGES = {
    "LuftmengeStufe1": {"key": "flow_reduced", "min": 50, "max": 400, "step": 5},
    "LuftmengeStufe2": {"key": "flow_normal", "min": 50, "max": 400, "step": 5},
    "LuftmengeStufe3": {"key": "flow_high", "min": 50, "max": 400, "step": 5},
    "StaendigesUngleichgewicht": {"key": "imbalance", "min": -100, "max": 100, "step": 1},
}
LIVE_MESSAGES = [
    "Ventilatorbetrieb", "TatsaechlicheZuluftmenge", "TatsaechlicheAbluftmenge", "TatsaechlicheDrehzahlZuluft",
    "TatsaechlicheDrehzahlAbluft", "Ablufttemperatur", "Aussenlufttemperatur", "StatusBypass", "StatusFrostschutz",
    "StatusVentilator",
]
PRESSURE_MESSAGES = ["IstwertZuluftdruck", "IstwertAbluftdruck"]
MAINTENANCE_MESSAGES = [
    "Filtermeldung", "FilterverwendungTage", "Filterverwendung", "MaximalerDurchsatzFilter", "Betriebsdauer",
    "Gesamtdurchsatz", "GespeicherteFehler", "SoftwareVersion",
]

# kitchen power: a sensor that has not reported for this long is treated as failed
KITCHEN_STALE = timedelta(minutes=30)

# a value is shown as unavailable when ebusd has not sent it for this long
EXPIRE = {
    **{m: timedelta(minutes=5) for m in LIVE_MESSAGES},
    **{m: timedelta(minutes=15) for m in PRESSURE_MESSAGES},
    **{m: timedelta(hours=2) for m in MAINTENANCE_MESSAGES},
    **{m: timedelta(hours=2) for m in PARAM_MESSAGES},
}

TICK = timedelta(seconds=30)
PRESSURE_INTERVAL = timedelta(minutes=5)
MAINTENANCE_INTERVAL = timedelta(hours=1)
BOOST_DURATION = timedelta(minutes=30)
MISMATCH_DELAY = timedelta(minutes=10)
COOKING_MEAN_WINDOW = timedelta(minutes=15)
COOKING_RUN_ON = timedelta(minutes=60)
