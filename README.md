# Zwift Click → keyboard shifter (Windows)

Connects to a **Zwift Click** over Bluetooth LE and turns its two buttons into
key presses, so you can shift gears in anything that listens to the keyboard
(TrainingPeaks Virtual, the local web bike trainer, …).

By default `+` → **numpad +**, `-` → **numpad -**.

## Use the ready-made program

Run `dist/zwift_click_keys.exe` (no Python needed). Put the Click in pairing
mode (pulsing blue light) and it connects automatically.

```
dist\zwift_click_keys.exe                 # defaults: numpad + / -
dist\zwift_click_keys.exe --up up --down down   # arrow keys instead
dist\zwift_click_keys.exe --mac DE:53:77:EB:6B:A1 --on release -v
```

| Option | Meaning |
|---|---|
| `--up` / `--down` | key name for the + / − button (`keyboard` library names, e.g. `num plus`, `up`, `pageup`) |
| `--mac` | connect to a specific Click address and skip the scan |
| `--on press\|release` | fire on button press (default) or release |
| `--no-battery` | don't subscribe to the battery level |
| `-v` | verbose logging |

## Run from source

```
pip install -r requirements.txt
python zwift_click_keys.py
```

## Rebuild the .exe

```
pip install pyinstaller
pyinstaller --onefile --name zwift_click_keys zwift_click_keys.py
```

## How it works

One file, two dependencies (`bleak` for BLE, `keyboard` for the key presses):

1. Scan for `Zwift Click` (or use `--mac`), connect, and send the `RideOn`
   handshake to the Zwift sync-write characteristic.
2. Subscribe to the async characteristic; each notification is a one-byte
   message type plus a tiny protobuf. For the button message (type `0x37`),
   field 1 is the `+` button and field 2 is the `-` button (`0` = pressed).
3. On each press edge, send the mapped key. Reconnects automatically on drop.

This is a stripped-down rewrite of
[jat255/zwift_click_handling](https://github.com/jat255/zwift_click_handling):
the unused (and never-working) encryption path, the protobuf/crypto/dotenv/rich
dependencies and the Poetry setup are gone. BLE protocol details originally from
[ajchellew/zwiftplay](https://github.com/ajchellew/zwiftplay). See `LICENSE`.
