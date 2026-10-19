# signature-archive

Fallback Signature Archive for Artists' Signatures.

Processed assets are PNGs with a fully transparent background and pure-white
ink, ready to sit on a dark page. Raw mode keeps the original file instead.

## Add signatures

```sh
just fill
```

This opens an endless form. Choose processed or raw mode, paste an image URL,
type the artist name, and the file is saved under `assets/<artist name>.*`.
Leave the URL blank or press Ctrl-C to stop.

Add a single one without the prompts:

```sh
just add https://example.com/signature.png "Pablo Picasso"
# -> assets/Pablo Picasso.png
```

You can also call the script directly:

```sh
python3 fill.py https://example.com/signature.png "Pablo Picasso"
```

When running inside WezTerm, a temporary PNG copy is generated for the preview
and piped to `wezterm imgcat` after each fill. Raw WebP/JPEG/SVG files are
converted for that preview only — the saved asset stays untouched. Nothing is
converted or previewed outside WezTerm. Pass `--no-preview` to turn it off.

## Processed or raw

By default every image goes through the processing pipeline: background
removed, ink recoloured white, saved as a transparent PNG.

If a source is already prepared (or you want the untouched original), use raw
mode instead. The downloaded bytes and original extension are preserved:

```sh
just add-raw https://example.com/signature.svg "Pablo Picasso"
# -> assets/Pablo Picasso.svg
```

`just fill` asks for the mode when run in a terminal. `just fill-raw` starts
the endless form with raw as the default. Only one file is kept per artist
name: switching between processed and raw removes the previous format. Raw SVG
files are saved byte-for-byte, so only use sources you trust.

## File naming

The artist name is used exactly as typed — case, spaces, punctuation and
Unicode are preserved:

```text
assets/<artist name>.*
```

For example, `$uicideboy$` becomes `assets/$uicideboy$.png` (or
`assets/$uicideboy$.webp` in raw mode). Processed files use `.png`; raw files
keep their original extension.

Path separators and control characters are refused rather than rewritten.
Names may contain URL-unsafe characters, so percent-encode them when serving
the asset. Print the exact stem for any artist with:

```sh
just key '$uicideboy$'
# $uicideboy$
```

Inputs can be SVG, PNG, JPEG, WebP, GIF, or anything else Pillow/ImageMagick can
read. In processed mode, plain light or dark backgrounds are stripped, existing
transparent backgrounds are kept, and the ink is recoloured white. Adding an
artist again replaces their existing file.

## Requirements

- Python 3
- Pillow (run `just setup` to create a `.venv`, or install it yourself)
- For SVG input: `rsvg-convert` (librsvg) or ImageMagick
