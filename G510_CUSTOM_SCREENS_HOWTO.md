# Custom Screens — How to Use It

The "Custom Screens" tab lets you build your own little dashboards for
the L2-L5 buttons on the keyboard. Here's the whole thing, short version.

## The basics

1. **Pick a screen** — click L1, L2, L3, L4, or L5 at the top.
   - **L1 is just a preview.** It's the built-in clock, you can't edit
     it — it's there so you can see what it looks like without
     pressing the actual button on the keyboard.
   - **L2-L5 are yours.** Add whatever you want to these.

2. **Add something** — pick a sensor (CPU %, RAM, GPU temp, whatever)
   from the first dropdown, pick **Number** (just shows the value) or
   **Bar** (shows a bar + the value), click **Add**. It shows up on
   the preview above.

3. **Move it** — click and drag it around on the preview, right where
   you see it. Wherever you drop it is where it'll show up on the real
   keyboard screen.

4. **Put an image on it** — click **Import Image...**, pick a picture
   from your computer, and it gets shrunk down and converted
   automatically to fit the tiny black-and-white screen. Drag it around
   like anything else. (No resizing images yet — pick one that's
   already roughly the right size, or just re-import it.)

5. **Resize a bar** — hover your mouse near a bar and a little blue
   square appears at its right end. Drag that to make the bar longer
   or shorter. (Number-style items don't have this — there's nothing
   to resize, it's just text.)

6. **Remove something** — click the ✕ next to it in the list on the
   right.

That's it. **Nothing needs a Save button** — every change (move,
resize, add, remove) saves itself instantly.

## Things worth knowing

- **The screen is tiny** — 160×43 pixels, same as the real LCD. If you
  cram too much in, rows will overlap or run off the bottom. The
  preview shows you exactly what the real keyboard will show, so if it
  looks wrong in the app, it'll look wrong on the keyboard too — space
  things out.
- **8 elements max per screen.** Plenty for a small display, but the
  app will tell you if you hit the limit.
- **"Bar" isn't available for every sensor** — only ones with an
  honest 0-100% or a sensible temperature range (the app will tell you
  if you pick one that can't; it just shows as a number instead).
- **The blue resize handle only shows up when you're near a bar.** It
  used to always show on every bar at once, which looked cluttered and
  confusing — now it only appears when you're actually about to use it.

## Bringing it to the real keyboard

Once your custom screen looks right in the app, press the matching
physical L-button on the keyboard (L2, L3, L4, or L5) to see it live.
If the keyboard doesn't seem to reflect your latest changes, it might
need the LCD service restarted — ask for that if you're not sure how.
