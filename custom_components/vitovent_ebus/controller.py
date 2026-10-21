"""Talks to ebusd via MQTT and decides the ventilation stage."""

from __future__ import annotations

from collections import deque
from datetime import datetime, time, timedelta
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    BOOST_DURATION,
    CONF_BATH_HUMIDITY,
    CONF_BATH_LIMIT,
    CONF_CO2,
    CONF_CO2_LIMIT,
    CONF_COOKING_WATTS,
    CONF_COOLING_MONTHS,
    CONF_HEATING_MONTHS,
    CONF_INDOOR_TEMP,
    CONF_KITCHEN_POWER,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_PREFIX,
    CONF_PRESENCE,
    CONF_ROOM_HUMIDITY,
    CONF_ROOM_LIMIT,
    CONF_VACATION,
    CONF_WEEKLY_PLAN,
    COOKING_MEAN_WINDOW,
    COOKING_RUN_ON,
    DAY_OPTIONS,
    KITCHEN_STALE,
    SLOT_DEFAULTS,
    DEFAULTS,
    DOMAIN,
    EBUS_TO_STAGE,
    EXPIRE,
    LIVE_MESSAGES,
    MAINTENANCE_INTERVAL,
    MAINTENANCE_MESSAGES,
    MISMATCH_DELAY,
    MSG_RESET,
    MSG_STAGE_SET,
    PARAM_MESSAGES,
    PARAM_WRITE_MIN,
    STAGE_FLOW,
    FLOW_DEFAULTS,
    PRESSURE_INTERVAL,
    PRESSURE_MESSAGES,
    STAGE_TO_EBUS,
    STAGES,
    TICK,
)

_LOGGER = logging.getLogger(__name__)

_BAD = (STATE_UNKNOWN, STATE_UNAVAILABLE, "", None)


class VitoventController:
    """Holds the values from the unit, the user switches and the stage logic."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.prefix: str = entry.data[CONF_PREFIX].rstrip("/")
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.values: dict[str, tuple[Any, datetime]] = {}
        # user controls (restored by their entities)
        self.mode = "auto"
        self.control = False  # off = read only, nothing is written to the unit
        self.humidity_boost = True
        self.co2_boost = True
        self.cooking_boost = True
        self.time_program = False  # 0.4.0: time windows only count (and are shown) while this is on
        self.eco_mode = False      # 0.4.0: stages eco/max via air volume of the unit stages Reduced/High
        self.summer_cooling = False
        # limits, restored by their number entities (start values from the options)
        self.limits = {k: float(self.opts[k]) for k in (CONF_BATH_LIMIT, CONF_ROOM_LIMIT, CONF_CO2_LIMIT, CONF_COOKING_WATTS)}
        self.flows = dict(FLOW_DEFAULTS)
        self._param_written: dict[str, datetime] = {}
        self.boost_until: datetime | None = None
        # time program, restored by its entities
        self.slots: list[dict[str, Any]] = [
            {**d, "start": time.fromisoformat(d["start"]), "end": time.fromisoformat(d["end"])} for d in SLOT_DEFAULTS
        ]
        # derived state
        self.target: str | None = None
        self.reason: str | None = None
        self.inputs_unavailable: list[str] = []
        self.cooking = False
        self.kitchen_mean: float | None = None
        self.mismatch = False
        self._mismatch_since: datetime | None = None
        self._kitchen: deque[tuple[datetime, float]] = deque()
        self._kitchen_means: deque[tuple[datetime, float]] = deque()
        self._unsubs: list = []
        self._pending: set[CALLBACK_TYPE] = set()  # delayed MQTT requests, cancelled on unload
        self._issue_open = False
        self._param_asked: datetime | None = None

    # ── setup ────────────────────────────────────────────────────────────────────────────────────────────
    @property
    def opts(self) -> dict[str, Any]:
        return {**DEFAULTS, **self.entry.options}

    async def async_start(self) -> None:
        if not await mqtt.async_wait_for_mqtt_client(self.hass):
            raise RuntimeError("MQTT is not available")
        self._unsubs.append(await mqtt.async_subscribe(self.hass, f"{self.prefix}/+", self._message, qos=0))
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, TICK))
        self._unsubs.append(
            async_track_time_interval(self.hass, callback(lambda _now: self._request(PRESSURE_MESSAGES)), PRESSURE_INTERVAL)
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, callback(lambda _now: self._request(MAINTENANCE_MESSAGES + list(PARAM_MESSAGES))),
                                      MAINTENANCE_INTERVAL)
        )
        if kitchen := self.opts.get(CONF_KITCHEN_POWER):
            self._unsubs.append(async_track_state_change_event(self.hass, [kitchen], self._kitchen_changed))
            self._add_kitchen_sample(dt_util.utcnow(), self._float(kitchen))
        self._later(5, lambda: self._request(LIVE_MESSAGES + PRESSURE_MESSAGES + MAINTENANCE_MESSAGES + list(PARAM_MESSAGES)))

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for cancel in list(self._pending):
            cancel()
        self._pending.clear()
        ir.async_delete_issue(self.hass, DOMAIN, f"stage_mismatch_{self.entry.entry_id}")

    @callback
    def _later(self, delay: float, action) -> None:
        """Run action after delay; the timer is cancelled when the integration unloads."""
        cancel = None

        @callback
        def _run(_now) -> None:
            self._pending.discard(cancel)
            action()

        cancel = async_call_later(self.hass, delay, _run)
        self._pending.add(cancel)

    # ── MQTT ─────────────────────────────────────────────────────────────────────────────────────────────
    @callback
    def _message(self, msg: mqtt.ReceiveMessage) -> None:
        name = msg.topic.rsplit("/", 1)[-1]
        payload = msg.payload
        if isinstance(payload, bytes):
            payload = payload.decode(errors="replace")
        value: Any = payload
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                first = data.get("0", next(iter(data.values()), None))
                value = first.get("value") if isinstance(first, dict) else first
            else:
                value = data
        except (ValueError, TypeError, StopIteration):
            pass
        self.values[name] = (value, dt_util.utcnow())
        if name == MSG_STAGE_SET:
            self._update_mismatch(dt_util.utcnow())
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def _request(self, names: list[str]) -> None:
        """Ask ebusd to read messages; answers arrive on prefix/<name>."""
        for i, name in enumerate(names):
            # spread the requests a little so the bus is not flooded
            self._later(i * 1.5, lambda n=name: self.hass.async_create_task(
                mqtt.async_publish(self.hass, f"{self.prefix}/{n}/get", "")
            ))

    def value(self, name: str) -> Any:
        """Current value or None when missing/expired."""
        item = self.values.get(name)
        if item is None:
            return None
        val, ts = item
        if dt_util.utcnow() - ts > EXPIRE.get(name, timedelta(hours=2)):
            return None
        return val

    def number(self, name: str) -> float | None:
        try:
            return float(self.value(name))
        except (TypeError, ValueError):
            return None

    @property
    def stage(self) -> str | None:
        val = self.value("Ventilatorbetrieb")
        return EBUS_TO_STAGE.get(val) if val is not None else None

    # ── user actions ─────────────────────────────────────────────────────────────────────────────────────
    async def async_boost(self) -> None:
        self.boost_until = dt_util.utcnow() + BOOST_DURATION
        await self.async_refresh()

    async def async_reset_filter(self) -> None:
        # read-only means read-only: nothing is written while the switch "Control" is off
        if not self.control:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_only")
        await mqtt.async_publish(self.hass, f"{self.prefix}/{MSG_RESET}/set", "Filter")
        self._later(5, lambda: self._request(["FilterverwendungTage", "Filterverwendung", "Filtermeldung"]))

    async def async_set_parameter(self, name: str, value: float) -> None:
        """Write a unit parameter (air volume per stage, imbalance) and read it back."""
        if not self.control:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_only_parameter")
        spec = PARAM_MESSAGES[name]
        value = int(round(min(spec["max"], max(spec["min"], value)) / spec["step"]) * spec["step"])
        await mqtt.async_publish(self.hass, f"{self.prefix}/{name}/set", str(value))
        self._later(3, lambda: self._request([name, "TatsaechlicheZuluftmenge", "TatsaechlicheAbluftmenge"]))

    async def async_refresh(self) -> None:
        """Re-evaluate now (after a user change) and send the stage."""
        await self._evaluate_and_send(dt_util.utcnow())

    # ── periodic work ────────────────────────────────────────────────────────────────────────────────────
    async def _tick(self, now: datetime) -> None:
        stale = [m for m in LIVE_MESSAGES if (it := self.values.get(m)) is None or now - it[1] > timedelta(seconds=90)]
        if stale:
            self._request(stale)
        # unit parameters: the bus is busy right after start, so ask again (at most every 5 min) until all are known
        missing = [m for m in PARAM_MESSAGES if self.value(m) is None]
        if missing and (self._param_asked is None or now - self._param_asked > timedelta(minutes=5)):
            self._param_asked = now
            self._request(missing)
        await self._evaluate_and_send(now)

    async def _evaluate_and_send(self, now: datetime) -> None:
        self._update_cooking(now)
        self.target, self.reason = self._decide(dt_util.as_local(now))
        if self.control and self.target in STAGES:
            if self.eco_mode:
                await self._ensure_flow(self.target, now)
            await mqtt.async_publish(self.hass, f"{self.prefix}/{MSG_STAGE_SET}/set", STAGE_TO_EBUS[self.target])
        self._update_mismatch(now)
        async_dispatcher_send(self.hass, self.signal)

    async def _ensure_flow(self, stage: str, now: datetime) -> None:
        """Eco mode: set the air volume of the unit stage that eco/reduced or high/max share (only if it differs)."""
        if stage not in STAGE_FLOW:
            return
        msg, key = STAGE_FLOW[stage]
        want = int(self.flows[key])
        have = self.number(msg)
        if have is None or int(have) == want:
            return
        last = self._param_written.get(msg)
        if last is not None and now - last < PARAM_WRITE_MIN:
            return
        self._param_written[msg] = now
        await mqtt.async_publish(self.hass, f"{self.prefix}/{msg}/set", str(want))
        self._later(3, lambda: self._request([msg]))

    @callback
    def _update_mismatch(self, now: datetime) -> None:
        if not self.control or self.target not in STAGES or self.stage == EBUS_TO_STAGE.get(STAGE_TO_EBUS[self.target]):
            self._mismatch_since, self.mismatch = None, False
            self._sync_issue()
            return
        self._mismatch_since = self._mismatch_since or now
        self.mismatch = now - self._mismatch_since >= MISMATCH_DELAY
        self._sync_issue()

    @callback
    def _sync_issue(self) -> None:
        """Visible repair notice (Settings › Repairs) while the unit does not follow – no automation needed."""
        issue_id = f"stage_mismatch_{self.entry.entry_id}"
        if self.mismatch and not self._issue_open:
            ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                                  translation_key="stage_mismatch",
                                  translation_placeholders={"target": str(self.target), "stage": str(self.stage)})
            self._issue_open = True
        elif not self.mismatch and self._issue_open:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            self._issue_open = False

    # ── cooking detection: 15-min time-weighted mean of the kitchen power, highest mean of the last 60 min ──
    @callback
    def _kitchen_changed(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        self._add_kitchen_sample(dt_util.utcnow(), self._parse(new.state if new else None))

    def _add_kitchen_sample(self, ts: datetime, value: float | None) -> None:
        # None = sensor unavailable: the gap is left out of the mean instead of carrying the last value on
        self._kitchen.append((ts, value))

    def _kitchen_valid(self) -> bool:
        """Kitchen sensor has a value and reported within KITCHEN_STALE (last_reported also counts unchanged reports)."""
        st = self.hass.states.get(self.opts.get(CONF_KITCHEN_POWER) or "")
        if st is None or self._parse(st.state) is None:
            return False
        seen = getattr(st, "last_reported", None) or st.last_updated
        return dt_util.utcnow() - seen <= KITCHEN_STALE

    def _update_cooking(self, now: datetime) -> None:
        if not self.opts.get(CONF_KITCHEN_POWER):
            self.cooking, self.kitchen_mean = False, None
            return
        if not self._kitchen_valid() and self._kitchen and self._kitchen[-1][1] is not None:
            self._add_kitchen_sample(now, None)  # stale or unavailable: stop carrying the last value on
        start = now - COOKING_MEAN_WINDOW
        # keep exactly one sample before the window (it defines the value at the window start)
        while len(self._kitchen) > 1 and self._kitchen[1][0] <= start:
            self._kitchen.popleft()
        if self._kitchen:
            total, covered = 0.0, 0.0
            pts = list(self._kitchen)
            for i, (ts, val) in enumerate(pts):
                seg_start = max(ts, start)
                seg_end = pts[i + 1][0] if i + 1 < len(pts) else now
                if val is not None and seg_end > seg_start:
                    dur = (seg_end - seg_start).total_seconds()
                    total += val * dur
                    covered += dur
            self.kitchen_mean = total / covered if covered > 0 else None
        else:
            self.kitchen_mean = None
        if self.kitchen_mean is not None:
            self._kitchen_means.append((now, self.kitchen_mean))
        while self._kitchen_means and now - self._kitchen_means[0][0] > COOKING_RUN_ON:
            self._kitchen_means.popleft()
        watts = self.limits[CONF_COOKING_WATTS]
        self.cooking = any(m > watts for _, m in self._kitchen_means)

    # ── stage logic ──────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _parse(state: str | None) -> float | None:
        if state in _BAD:
            return None
        try:
            return float(state)
        except (TypeError, ValueError):
            return None

    def _state(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        return st.state if st else None

    def _float(self, entity_id: str | None) -> float | None:
        return self._parse(self._state(entity_id))

    def _decide(self, now: datetime) -> tuple[str, str]:
        o = self.opts
        missing: list[str] = []

        def num(key: str) -> float | None:
            ent = o.get(key)
            if not ent:
                return None
            val = self._float(ent)
            if val is None:
                missing.append(ent)
            return val

        bath_vals = []
        for ent in o.get(CONF_BATH_HUMIDITY) or []:
            val = self._float(ent)
            if val is None:
                missing.append(ent)
            else:
                bath_vals.append(val)
        if o.get(CONF_KITCHEN_POWER) and not self._kitchen_valid():
            missing.append(o[CONF_KITCHEN_POWER])  # unavailable or silent for more than 30 min
        rh = num(CONF_ROOM_HUMIDITY)
        co2 = num(CONF_CO2)
        inside = num(CONF_INDOOR_TEMP)
        presence = self._state(o.get(CONF_PRESENCE))
        if o.get(CONF_PRESENCE) and presence in _BAD:
            missing.append(o[CONF_PRESENCE])
        self.inputs_unavailable = missing

        if self.mode != "auto":
            if self.mode in ("eco", "max") and not self.eco_mode:  # eco/max need eco mode (air volume changes)
                return ("reduced" if self.mode == "eco" else "high"), "fixed"
            return self.mode, "fixed"

        h = now.hour
        night_start, night_end = int(o[CONF_NIGHT_START]), int(o[CONF_NIGHT_END])
        night = h >= night_start or h < night_end
        lim = self.limits
        wet = self.humidity_boost and bool(bath_vals) and max(bath_vals) > lim[CONF_BATH_LIMIT]
        rh_high = self.humidity_boost and rh is not None and rh >= lim[CONF_ROOM_LIMIT]
        co2_high = self.co2_boost and co2 is not None and co2 >= lim[CONF_CO2_LIMIT]
        low = "eco" if self.eco_mode else "reduced"  # minimum stage
        outside = self.number("Aussenlufttemperatur")
        cool = (
            self.summer_cooling
            and str(now.month) in o[CONF_COOLING_MONTHS]
            and inside is not None and inside > 24
            and outside is not None and outside < inside - 2
            and (h >= night_start or h < 8)
        )
        away = bool(o.get(CONF_PRESENCE)) and presence in ("off", "not_home", "0")
        vacation = self._state(o.get(CONF_VACATION)) == "on"
        boost = self.boost_until is not None and dt_util.utcnow() < self.boost_until
        plan_id = o.get(CONF_WEEKLY_PLAN)
        plan = self.hass.states.get(plan_id) if plan_id else None

        if vacation and not (wet or rh_high or co2_high):
            return low, "vacation"
        if boost:
            return "high", "boost"
        if self.cooking_boost and self.cooking:
            return "high", "cooking"
        if wet:
            return "high", "bathroom_humid"
        if rh_high:
            return "high", "room_humidity_high"
        if co2_high:
            return "high", "co2_high"
        if cool:
            return "high", "summer_night_cooling"
        if away:
            return low, "nobody_home"
        if (slot_stage := self.program_stage(now)) is not None:
            return slot_stage, "time_program"
        if plan is not None and plan.state == "on":
            stage = str(plan.attributes.get("stufe") or plan.attributes.get("stage") or "normal").lower()
            return (stage if stage in STAGES else "normal"), "weekly_plan"
        if str(now.month) in o[CONF_HEATING_MONTHS]:
            return low, "heating_period"
        if night:
            return low, "night"
        return "normal", "day"

    # ── time program ─────────────────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _day_ok(days: str, weekday: int) -> bool:
        if days == "daily":
            return True
        if days == "mon_fri":
            return weekday < 5
        if days == "sat_sun":
            return weekday >= 5
        return DAY_OPTIONS.index(days) - 3 == weekday if days in DAY_OPTIONS else False

    def program_stage(self, now: datetime) -> str | None:
        """Highest stage of all active windows that cover 'now' (local time), None if no window is active."""
        if not self.time_program:
            return None
        hits = []
        wd, t = now.weekday(), now.time().replace(second=0, microsecond=0)
        for slot in self.slots:
            if not slot["active"]:
                continue
            start, end, days = slot["start"], slot["end"], slot["days"]
            if start == end:
                hit = self._day_ok(days, wd)
            elif start < end:
                hit = self._day_ok(days, wd) and start <= t < end
            else:  # over midnight: the window belongs to the day it starts on
                hit = (self._day_ok(days, wd) and t >= start) or (self._day_ok(days, (wd - 1) % 7) and t < end)
            if hit:
                hits.append(slot["stage"])
        return max(hits, key=STAGES.index) if hits else None

    # ── derived maintenance values ───────────────────────────────────────────────────────────────────────
    @property
    def filter_remaining(self) -> float | None:
        used, limit = self.number("Filterverwendung"), self.number("MaximalerDurchsatzFilter")
        if used is None or not limit:
            return None
        return max(0.0, round(100 * (1 - used / limit)))

    @property
    def filter_change_in(self) -> float | None:
        used, limit, days = self.number("Filterverwendung"), self.number("MaximalerDurchsatzFilter"), self.number("FilterverwendungTage")
        if not used or not limit or days is None or days < 3:
            return None
        return max(0.0, round((limit - used) / (used / days)))

    @property
    def filter_change_needed(self) -> bool | None:
        status, rest = self.value("Filtermeldung"), self.filter_remaining
        if status is None and rest is None:
            return None
        return status == "Dirty" or (rest is not None and rest <= 3)

    @property
    def boost_active(self) -> bool:
        return self.boost_until is not None and dt_util.utcnow() < self.boost_until
