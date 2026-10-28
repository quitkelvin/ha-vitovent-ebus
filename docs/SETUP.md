# Setup

## 1. Which unit?

The older **Viessmann Vitovent 300-W** (approx. 2010–2015, 300/400 m³/h) is a rebranded
**Brink Renovent Excellent 300/400 (Plus)**. You can recognise it by the Brink-style connection board:
RJ12 socket (X2, step switch), 2-pin screw plug **X1 (eBUS)** and on "Plus" units a 9-pin block (X15).
The newer Vitovent 300-W "C" series (Modbus X15/X17) is a different unit and **not** covered here.

Tested with (example values of one test unit – yours may differ): Vitovent 300-W, Brink software **S1.05.04**, eBUS slave address **7c**.
Use the slave address the ebusd scan reports for your unit.

## 2. eBUS adapter

Any ebusd-compatible adapter works. Tested: **eBUS Adapter Shield C6** (ESP32-C6, Wi-Fi, "enhanced" protocol).

1. Power the adapter via USB-C, join its Wi-Fi access point, enter your Wi-Fi, choose mode **enhanced**.
   Give it a fixed IP address in your router.
2. **Disconnect the ventilation unit from mains** (plug).
3. Connect the adapter's two eBUS wires **in parallel to X1** (same terminals as the wall panel cable).
   eBUS on this board is **polarity sensitive**: + to +, − to −. (X1 is eBUS by factory default; parameter 8 would switch it to OpenTherm – leave it.)
4. Reconnect mains. The adapter should show a bus signal.

Wall panel: once Home Assistant controls the unit, the original panel will keep sending its own stage and fight
with HA. We disconnected it (if HA is down the unit keeps running and falls back to its own stage after a few minutes).

## 3. ebusd

Home Assistant app/add-on "eBUSd" (or any ebusd ≥ 23) with these options:

```
network_device: enh:<adapter-ip>:9999
commandline options:
  --mqttjson
  --configpath=/share/ebusd_vitovent/conf
  --pollinterval=30
  --latency=50
```

Configuration file: `Vitovent300W400` from **[pvyleta/ebusd-brink-hru](https://github.com/pvyleta/ebusd-brink-hru)**
(GPL-3.0, not included here). Pick the file matching your software version (≥ 1.01.06 or 1.01.01–1.01.05), save it as
`/share/ebusd_vitovent/conf/7c.csv` (7c = slave address found by the ebusd scan).

Check in the ebusd log that the scan finds slave `7c` and that `ebusd/Vitovent300W400/...` topics appear in MQTT.
Start **without** writing: add `--readonly` first, look at the values, then remove it.

## 4. Home Assistant

### Integration (HACS)

Install via HACS (custom repository, see README) and add the integration. In **Configure** pick your sensors.
Everything is optional; without sensors the stage follows heating period, night and the weekly plan only.

| Entity | Purpose |
|---|---|
| Mode (select) | Auto, or a fixed stage Reduced / Normal / High |
| Control (switch) | **Off = read only** (default after the first setup, nothing is written – also no filter reset). On = HA writes the stage every 30 s. The last state survives restarts |
| Target stage / Reason | what HA wants and why (attribute `inputs_unavailable` lists configured sensors without a value) |
| Unit does not follow | problem sensor: target ≠ reported stage for 10 min while control is on |
| Filter change needed / Filter remaining / Filter change in | maintenance |
| Boost 30 min, Reset filter | buttons (reset only after replacing the filters) |

**Time program** (on the device page, section *Configuration*, or in a dashboard): four windows *Time window 1–4*,
each with an on/off switch, *days* (daily, Mon–Fri, Sat–Sun or one weekday), *start*, *end* and *stage*.
Start = end means the whole day, start later than end runs over midnight. If several windows overlap, the highest
stage wins. Priority: boost, cooking, humidity, CO₂ and summer cooling go first, then *nobody home*, then the time
program, then the weekly plan, then heating period/night.

Alternatively a weekly plan: create a **Schedule** helper, draw the blocks; for a stage other than Normal open a block › Advanced ›
additional data `stufe: high` (or `reduced`). Select the helper in the options.

While the unit does not follow for 10 min a repair notice appears under Settings › Repairs. For phone notifications,
create an automation on *Filter change needed* or *Unit does not follow* turning on.

### YAML package (alternative)

1. Enable packages in `configuration.yaml` if you have not yet:
   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```
2. Copy `packages/vitovent_ebus.yaml` to `/config/packages/`.
3. Edit **only** the attributes of `sensor.vitovent_settings` at the top (your kitchen power sensor, bathroom
   humidity, CO₂, presence …) and the `entity_id` of the first statistics sensor (same kitchen power sensor).
   Replace `notify.notify` in the filter automation with your phone.
4. Optional weekly plan: Settings › Devices & services › Helpers › Create helper › **Schedule**, e.g. "Vitovent Weekly Plan".
   Draw the time blocks; for a stage other than Normal open a block › Advanced › additional data `stufe: High` (or `Reduced`).
   Put the entity ID (e.g. `schedule.vitovent_weekly_plan`) into `weekly_plan`. Needs a Home Assistant version whose
   Schedule helper offers additional data per block (current versions do).
5. Restart Home Assistant. `input_select.vitovent_mode` = **Auto** lets HA decide; the attribute `reason` of
   `sensor.vitovent_target_stage` tells you why.
6. The package starts **read only** (0.4.1): nothing is sent to the unit until you turn on **Vitovent Control**
   (`input_boolean.vitovent_control`). Check the values first; the filter reset also needs Control on.

## 5. Findings worth knowing

| Topic | Finding |
|---|---|
| Setting the stage | `Ventilatorbetrieb/set` (40a1) only holds for a few minutes, `VentilatorbetriebAlternative` (40cb) was ignored by this unit → the package re-sends every 30 s, like the original panel. |
| Holiday (50 m³/h) | Ran in *ConstantPWM* with the exhaust fan at ~3,460 rpm → negative pressure. Not offered. For less air lower `LuftmengeStufe1` (stage Reduced, 50–400 m³/h) – the unit stays in ConstantFlow (0.3.0 number entities, 0.4.0 eco mode). |
| Maintenance values | Filter status/days/flow, operating hours, total flow, pressures and error memory are only sent on request → polled by the package (pressures every 5 min, rest hourly). |
| Filter limit | Factory: 432,000 m³ (≈ 3 months at ~200 m³/h). The unit reports "Dirty" when reached. |
| Filter reset | Script `Vitovent Filter Reset` → `ResetNotifications = Filter`. "ErrorsAndFilter" does not work. |
| Pressures | Supply/exhaust pressure in Pa – a slow rise over weeks is an early sign of clogging filters. |
| Unbalance | `StaendigesUngleichgewicht` may be set by the installer (test unit: −20). Leave it unless you know why. |
| Error memory | Raw 18-byte HEX. Decoding is not documented yet – contributions welcome. |

## 5. Optional: supply and exhaust air sensors

The unit itself only measures outdoor and extract air. A second ESP32 with two probes in the **supply air** (to the
rooms) and the **exhaust air** (to outside) shows the real heat recovery and the humidity of both air streams.

- Probes: two I²C temperature/humidity probes in a stainless sleeve (sold e.g. as "FS200-SHT45"). The tested ones
  answered as **SHT3x** (ESPHome `sht3xd`), not SHT4x – if `sht4x` only reads `0xFF`/CRC errors, try `sht3xd`.
- All probes have the address 0x44 → one I²C bus per probe (the ESP32 has two).
- Wires (typical colour code): red VCC **3.3 V** (not 5 V), black GND, yellow SCL, green SDA. With 1.5 m cable plus
  connectors 10 kHz bus speed was reliable.
- Position: 30–50 cm after the unit's supply and exhaust stub, straight duct section, tip in the middle of the air
  stream, sealed air-tight. Do not put the exhaust probe at the lowest point (condensate). Which stub is which: see
  the dimension drawing in the installation manual of your type (top view, letters A–D).

```yaml
# ESPHome (excerpt) – secrets in secrets.yaml
i2c:
  - id: bus_supply
    sda: GPIO21
    scl: GPIO22
    frequency: 10kHz
  - id: bus_exhaust
    sda: GPIO25
    scl: GPIO26
    frequency: 10kHz
sensor:
  - platform: sht3xd
    i2c_id: bus_supply
    update_interval: 30s
    temperature: { name: "Supply air temperature" }
    humidity: { name: "Supply air humidity" }
  - platform: sht3xd
    i2c_id: bus_exhaust
    update_interval: 30s
    temperature: { name: "Exhaust air temperature" }
    humidity: { name: "Exhaust air humidity" }
```

Heat recovery (supply side) = (supply − outdoor) / (extract − outdoor), only meaningful with ≥ 4 K between extract and
outdoor air and the bypass closed. Recovered heat ≈ supply air flow × 0.34 Wh/(m³·K) × (supply − outdoor).
Test unit, 10 °C outside, 50–80 m³/h: about 80 %.

## 6. Safety

Ventilation matters for the building: too little air means humidity and mould, wrong settings in winter can affect
frost protection. The package never switches the unit off and never writes installer parameters. Check humidity in
the first weeks. Only one unit/software version was tested – see README *Tested on* and *Failure behaviour*.
Everything here is provided free of charge **without warranty**; liability is excluded as far as the law permits
(mandatory statutory liability stays unaffected).
