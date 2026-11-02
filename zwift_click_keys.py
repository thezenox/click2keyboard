"""
Zwift Click -> keyboard shifter (Windows).

Connects to a Zwift Click over BLE and turns its two buttons into key presses
(default: numpad + / -), so you can shift gears in apps that don't support the
Click natively (TrainingPeaks Virtual, the local web bike trainer, ...).

Dependencies:  pip install bleak keyboard
Run:           python zwift_click_keys.py
               python zwift_click_keys.py --up up --down down -v

This is a stripped-down rewrite of jat255/zwift_click_handling: the unused
(and non-working) encryption path, the protobuf library, dotenv and rich are
all gone. The Click speaks plain, unencrypted notifications; the button payload
is just two protobuf varints, which we parse directly.
"""
import argparse
import asyncio
import logging

import keyboard
from bleak import BleakClient, BleakScanner

# Zwift custom GATT service (BC1 / Click).
ASYNC_CHAR = "00000002-19ca-4651-86e5-fa29dcdd09d1"   # notifies button state
SYNC_RX_CHAR = "00000003-19ca-4651-86e5-fa29dcdd09d1"  # we write the handshake here
BATTERY_CHAR = "00002a19-0000-1000-8000-00805f9b34fb"

RIDE_ON = b"RideOn"                 # handshake payload
CLICK_MESSAGE_TYPE = 0x37           # 55: button state notification
BATTERY_MESSAGE_TYPE = 0x19         # 25: battery level

log = logging.getLogger("zwift-click")


def read_varint(buf, i):
    """Read one protobuf varint from buf at offset i -> (value, next_index)."""
    result = 0
    shift = 0
    while i < len(buf):
        b = buf[i]
        result |= (b & 0x7F) << shift
        i += 1
        if not (b & 0x80):
            return result, i
        shift += 7
    return None, i


def parse_varint_fields(buf):
    """Parse a flat protobuf message of varint (and skip other) fields -> dict."""
    out = {}
    i = 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        if key is None:
            break
        field, wire = key >> 3, key & 0x07
        if wire == 0:               # varint
            val, i = read_varint(buf, i)
            if val is None:
                break
            out[field] = val
        elif wire == 2:             # length-delimited -> skip
            ln, i = read_varint(buf, i)
            i += ln or 0
        elif wire == 5:             # 32-bit
            i += 4
        elif wire == 1:             # 64-bit
            i += 8
        else:
            break
    return out


class ClickShifter:
    def __init__(self, up_key, down_key, fire_on):
        self.up_key = up_key
        self.down_key = down_key
        self.fire_on = fire_on          # "press" or "release"
        self.up_down = False            # current pressed state of + button
        self.down_down = False          # current pressed state of - button

    def tap(self, key, name):
        log.info("shift %s -> key '%s'", name, key)
        try:
            keyboard.send(key)
        except Exception as exc:        # noqa: BLE001
            log.error("could not send key '%s': %s", key, exc)

    def on_async(self, _characteristic, data):
        if not data:
            return
        msg_type, payload = data[0], bytes(data[1:])

        if msg_type == BATTERY_MESSAGE_TYPE:
            fields = parse_varint_fields(payload)
            if 2 in fields:
                log.info("battery: %d%%", fields[2])
            return

        if msg_type != CLICK_MESSAGE_TYPE:
            return

        fields = parse_varint_fields(payload)
        # field 1 = "+" button, field 2 = "-" button; 0 = pressed, 1 = released.
        up = fields.get(1, 1) == 0
        down = fields.get(2, 1) == 0
        self._edge(up, "up", self.up_key, is_up=True)
        self._edge(down, "down", self.down_key, is_up=False)

    def _edge(self, pressed, name, key, is_up):
        prev = self.up_down if is_up else self.down_down
        if pressed != prev:
            fired = (self.fire_on == "press" and pressed) or (
                self.fire_on == "release" and not pressed
            )
            if fired:
                self.tap(key, name)
        if is_up:
            self.up_down = pressed
        else:
            self.down_down = pressed


async def find_click(mac):
    if mac:
        return mac
    log.info('scanning for "Zwift Click" (10 s)... press a button to wake it')
    dev = await BleakScanner.find_device_by_name("Zwift Click", timeout=10.0)
    if not dev:
        raise RuntimeError('no "Zwift Click" found - put it in pairing mode (pulsing blue)')
    log.info("found Click at %s", dev.address)
    return dev.address


async def run(args):
    shifter = ClickShifter(args.up, args.down, args.on)
    while True:
        try:
            address = await find_click(args.mac)
            async with BleakClient(address) as client:
                await client.start_notify(ASYNC_CHAR, shifter.on_async)
                if not args.no_battery:
                    try:
                        await client.start_notify(BATTERY_CHAR, shifter.on_async)
                    except Exception:   # noqa: BLE001
                        pass            # battery notify is optional
                await client.write_gatt_char(SYNC_RX_CHAR, RIDE_ON, response=True)
                log.info("connected - mapping buttons to '%s' / '%s' (Ctrl-C to quit)",
                         args.up, args.down)
                while client.is_connected:
                    await asyncio.sleep(0.5)
            log.warning("disconnected - reconnecting...")
        except asyncio.CancelledError:
            raise
        except Exception as exc:        # noqa: BLE001
            log.error("%s - retrying in 3 s", exc)
            await asyncio.sleep(3)


def main():
    p = argparse.ArgumentParser(description="Map Zwift Click buttons to key presses.")
    p.add_argument("--mac", help="Click BLE address (skip the scan)")
    p.add_argument("--up", default="num plus", help="key for the + button (default: num plus)")
    p.add_argument("--down", default="num minus", help="key for the - button (default: num minus)")
    p.add_argument("--on", choices=["press", "release"], default="press",
                   help="fire on button press (default) or release")
    p.add_argument("--no-battery", action="store_true", help="don't subscribe to battery")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        log.info("bye")


if __name__ == "__main__":
    main()
