# Installing Half-Life on the R36HD

You need a PC, the console's SD card and Half-Life on Steam. It takes about 10 minutes.

## 1. Get the right version of the game files

The port needs the **original** Half-Life files, not the 25th Anniversary update.

1. In Steam, right-click **Half-Life** and choose **Properties**.
2. Open **Betas**.
3. Pick **steam_legacy - Pre-25th Anniversary Build**.
4. Wait until Steam has finished the download.

Check: the folder `Half-Life/valve` must contain a file named `skill.cfg`. If it is missing, you still have the
25th Anniversary files and the port will not start.

## 2. Put the port on the SD card

1. Download `halflife-r36hd-1.1.0.zip` from the Releases page.
2. Put the console's SD card in your PC.
3. Unzip the file onto the **root** of the SD card. If asked, allow it to merge with the existing `roms` folder.

You should now have:

```
SD card
└── roms
    └── ports
        ├── Half-Life.sh
        └── halflife
            ├── halflife_libretro.so
            ├── run.sh
            ├── tweaks/           (speed helpers, see the README)
            └── valve          <- your game files go in here
```

## 3. Copy your game files

1. In Steam, right-click **Half-Life** → **Manage** → **Browse local files**.
2. Open the `valve` folder.
3. Select **everything inside it** and copy it into `roms/ports/halflife/valve/` on the SD card.

Copy the contents of `valve`, not the `valve` folder itself. When you are done, this file must exist:
`roms/ports/halflife/valve/halflife.wad`

The copy is about 400 MB. You can skip the folders `cl_dlls`, `dlls`, `SAVE` and any `.dll` or `.exe` files;
the port does not use them.

## 4. Play

1. Safely eject the SD card and put it back in the console.
2. Turn it on and open **Ports**.
3. Start **Half-Life**.

The first start and each new level take a few seconds to load. Saves are kept in
`roms/ports/halflife/valve/save/`.

## If it does not start

The port writes the reason to `cubegm/port_error.txt` on the SD card.

| Message | Fix |
|---|---|
| Half-Life data missing | The game files are not in `roms/ports/halflife/valve/`. Check step 3. |
| valve/skill.cfg missing | You copied the 25th Anniversary files. Do step 1, then copy again. |

If the game starts but the screen stays black, create an empty file named `direct_off.txt` in
`roms/ports/halflife/` and start it again. This sends frames through picoarch the old way.

If you update from an older version, unzip over the old files and allow the replace. The `tweaks` folder is new in 1.1.0.

If the game does not start after the update, create an empty file named `tweaks_off` in `roms/ports/halflife/` and start it again: that skips every helper. If that fixes it, please report which console and firmware you have.

If the game does not start but did before a power loss, move the folder `roms/ports/halflife/valve/save` out of the way. A damaged save stops the game from loading, and it starts a new one without the folder.
