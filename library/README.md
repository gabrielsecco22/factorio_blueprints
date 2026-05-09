# Local blueprint library

A file-system mirror of Factorio blueprints managed by
`tools/blueprint_storage.py`. Layout:

```
library/
├── README.md           This file. Tracked.
├── .gitkeep            Tracked.
├── personal/           Mirror of the user's blueprint-storage-2.dat
│   ├── .gitkeep
│   ├── <slug>.bp       One file per blueprint. Each file holds a single
│   │                   blueprint string (the same form Factorio
│   │                   exchanges via the in-game "Export string" UI),
│   │                   trailing newline.
│   └── <book>/         Books expand to a directory.
│       ├── _book.json  Book metadata: label, description, icons.
│       └── <slug>.bp
└── external/           Scraped blueprints (sibling agent territory).
```

`.bp` files contain *strings*, not JSON. Decode them with
`tools/blueprint_codec.py decode '<string>'` or with
`tools/blueprint_storage.py show <name>`.

`personal/` and `external/` are gitignored. Only `.gitkeep`,
`README.md`, and shape-defining files (`_book.json` schemas) are
tracked.

## Workflows

### Import a blueprint string from the game

1. In Factorio, right-click a blueprint -> **Export string**.
2. Locally:

   ```sh
   python3 tools/blueprint_storage.py import-string '<paste>' my-name
   ```

   Or from a file you saved the string into:

   ```sh
   python3 tools/blueprint_storage.py import-file solar-array.txt
   ```

### List, show, search

```sh
python3 tools/blueprint_storage.py list
python3 tools/blueprint_storage.py show  my-name
python3 tools/blueprint_storage.py search "solar"
```

### Send a stored blueprint back to the game

```sh
python3 tools/blueprint_storage.py export my-name
```

Copy the output and paste it into Factorio's **Import string** dialog
(open the blueprint library, click the upload-arrow icon).

### What about the binary library file?

`~/.factorio/blueprint-storage-2.dat` holds the user's blueprints in
an undocumented binary format. We only decode the high-level header
(version, migrations, prototype index, top-level slot table); the
actual blueprint payloads are not yet round-trippable. Use the manual
**Export string** workflow above. See
`docs/blueprint_storage_format.md` for what is and isn't decoded.
