# Nura brand assets

Supplied logo files, stored **unmodified**. The logo was not traced, redrawn or
recoloured (PRD 0, section 13).

## Source files

| File                        | What it is                                    |
| --------------------------- | --------------------------------------------- |
| `nura-logo-full.png`        | Mark above the wordmark, on soft white        |
| `nura-logo-horizontal.png`  | Mark beside the wordmark (horizontal lockup)  |
| `nura-logo-mono.png`        | Single-colour dark teal version               |
| `nura-logo-dark.png`        | Dark-background treatment, lighter mark       |
| `nura-mark.png`             | Symbol only, no wordmark                      |
| `nura-app-icon-source.png`  | Pre-composed rounded-square icon              |
| `nura-mark-transparent.png` | Symbol only, transparent background, 256 px   |

`nura-mark-transparent.png` is the one used **inside the app** — on the Today
header and the Nura tab. The source files all sit on a near-white ground, which
would show as a white box in Dark mode, so a transparent version is required.

## Generated app assets

These live in `mobile/assets/` and were derived from the sources above by
replacing the flat near-white (or near-black) background with alpha, trimming
to the artwork, and resizing. No shapes or colours were altered.

| File                          | Derived from        | Notes                                                        |
| ----------------------------- | ------------------- | ------------------------------------------------------------ |
| `icon.png`                    | `nura-mark.png`     | 1024², **opaque**, symbol only, on soft white                |
| `android-icon-foreground.png` | `nura-mark.png`     | 1024², transparent, inset to the adaptive-icon safe zone     |
| `android-icon-monochrome.png` | `nura-logo-mono.png`| 1024², white silhouette for Android themed icons             |
| `splash-icon.png`             | `nura-logo-full.png`| 1024², transparent, mark + wordmark                          |
| `splash-icon-dark.png`        | `nura-logo-dark.png`| 1024², transparent, for the dark splash                      |

Two details worth knowing before regenerating any of these:

- **The app icon is the symbol only, never the wordmark** (PRD 0, section 13).
  It is also deliberately opaque and full-bleed: iOS rejects transparency in
  app icons and applies its own rounded mask, so a pre-rounded icon inside a
  square would look inset.
- **The centre cross of the mark is a cutout, not white paint.** Keeping it
  transparent is what lets the splash background show through it in both
  themes — soft white in Light, deep teal in Dark — exactly as the supplied
  dark artwork does.

Splash background colours are set in `app.json` and match the theme
backgrounds: `#F6FAF9` light, `#0E1C1B` dark.

## Wordmark in the UI

The Today header pairs `nura-mark-transparent.png` with the word "Nura" set in
the system font, rather than using a wordmark image. Two reasons: the supplied
wordmark is dark teal and would fail contrast on a dark background, and PRD 0
section 12 says not to bundle a custom font. If the official logo typeface is
provided later, the header is the place to use it.

## Colour tokens

The brand palette is defined once, in `mobile/src/theme/tokens.ts`:

```text
Nura Dark Teal  #1C605C
Nura Deep Teal  #3D9086
Nura Mid Teal   #53A9A6
Nura Aqua       #7ECFC4
Nura Mint       #A5E3D1
```

Screens should use semantic theme colours (`theme.colors.accent`) rather than
reaching for a brand colour directly, so Light and Dark stay correct.
