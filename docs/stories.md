# Spoken Stories

Parley ships a catalogue of short public-domain stories read aloud. The audio
is part of the repository but never part of an installer. Settings downloads it
on demand, one file at a time, and verifies every SHA-256 hash.

## Catalogue

`assets/stories/manifest.json` is the source of truth:

```json
{
  "version": 1,
  "stories": [
    {
      "title": "A Horseman in the Sky",
      "author": "Ambrose Bierce",
      "filename": "A_Horseman_in_the_Sky_-_By_Ambrose_Bierce.mp3",
      "bytes": 5123456,
      "seconds": 320.4,
      "sha256": "…"
    }
  ]
}
```

The same content is copied to `src/parley/content/stories.json` so installed
packages know the catalogue before any download happens. The interface reads the
list, count and total size from that file, so it grows automatically when new
audio is added.

## Adding a story

1. Put the MP3 in `assets/stories`. The file name encodes the title and author:

   ```
   The_Tell_Tale_Heart_-_By_Edgar_Allan_Poe.mp3
   ```

2. Regenerate both manifest copies:

   ```sh
   python scripts/build_stories_manifest.py
   ```

3. Commit the MP3 plus both JSON files.

`ffprobe` is used for the duration when available. Without it the duration is
stored as `0.0` and the interface shows a dash. The script also removes zero
padding at the start or end of a file, because the audio backend stops at the
first invalid MP3 header.

## Download behaviour

- Nothing is downloaded at install time.
- Settings shows the current pack ("49 stories · 228.9 MB") and asks for
  confirmation before downloading.
- Downloads go to `~/.local/share/parley/stories` (or `PARLEY_STORIES_DIR`).
- Partial files use a `.part` suffix and are removed on failure or cancellation.
- A story is only kept when its SHA-256 matches the manifest.
- Removing the pack deletes the MP3 files but leaves the manifest and your
  other data untouched.

`PARLEY_STORIES_URL` overrides the download base URL. This is useful for a
mirror or for testing against a local directory served over HTTP.

## Testing before the repository is published

The default download URL points at the public GitHub repository. Until the audio
is pushed there, point Parley at the checkout instead:

```sh
PARLEY_STORIES_DIR="$PWD/assets/stories" parley
```

Settings then treats the files in `assets/stories` as already installed. To
exercise the real download path, serve the folder locally:

```sh
python3 -m http.server 8000 --directory assets/stories
PARLEY_STORIES_URL=http://127.0.0.1:8000 parley
```

Copying the MP3 files and `manifest.json` to
`~/.local/share/parley/stories` also works and needs no environment variable.

## Licensing

The recordings cover works that are in the public domain. Keep the author name
in both the file name and the manifest so attribution stays clear.
