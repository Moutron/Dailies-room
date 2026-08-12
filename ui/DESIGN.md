# Design direction — the cutting room

Generic AI chat is a solved and boring look: a centered column, bubbles,
a text input. None of that belongs here. This is a review tool for people
who spend their day looking at footage on a calibrated monitor in a dark
room — the interface should look like it grew up next to that monitor,
not next to a chatbot.

## Why dark, specifically

Post-production suites are dark on purpose: deliberately desaturated,
neutral grays so the footage's own color reads true against the chrome
around it. A saturated or warm-toned UI competes with the image and
throws off the eye's read of the footage's actual color. This is **not**
dark-mode-as-aesthetic (a preference toggle) — it's dark **because you are
judging images**, and every token below is chosen to stay out of the way
of that judgment.

That means:
- No color in the chrome except one accent, reserved for the current
  selection/playhead, and one warning tone for flagged technical
  problems. Everything else is neutral gray.
- Grays are true neutral, not blue- or warm-tinted — a tinted "dark mode"
  gray still casts onto the footage next to it.
- Nothing decorative. No gradients, no drop shadows standing in for
  hierarchy, no card-shine. Hierarchy comes from spacing, from the
  monospace/grotesque type pairing, and from the one accent color.

## Typographic conventions, not typographic decoration

Film and post use type functionally, and those conventions exist for
reasons that still hold:

- **Timecode is always monospace.** `HH:MM:SS:FF` is a fixed-width value
  read as a column, at speed, by someone who is not looking at it
  carefully — it has to align digit-under-digit or it's unreadable at a
  glance. Every number in this UI (timecode, scene, slate, take) uses the
  monospace face for the same reason.
- **Interface text** (labels, the agent's prose, buttons) uses a tight
  grotesque — legible at small sizes, doesn't compete with the monospace
  numbers for attention.
- **Slates read like slates**: scene/slate/take rendered as a compact
  code (`S03 · 2A · T1`), not spelled out as "Scene 3, Slate 2A, Take 1."
- **Film leader countdown** motif: subtle, used once, in the empty state
  — not on every panel. A leader countdown that appears everywhere stops
  meaning "about to start" and becomes wallpaper.

## The signature element: the contact strip

The thing that makes this look like a cutting room and not a chat app:
every result renders as a **contact strip** — a horizontal row of
thumbnail frames, one per notable moment in the result, with its timecode
printed directly beneath it in monospace. This is a literal contact
sheet, the physical object editors used to scan negatives before an edit
even had a timeline. Clicking a frame seeks the player to that timecode
and starts playback. Results are film to be watched, not text to be read
— the contact strip is the mechanism that makes that literal: the agent's
prose is the caption under the strip, not the main event.

## Layout

- Desktop-first (the audience uses laptops, not phones), but degrades to
  tablet width without breaking — a two-column desktop layout (session on
  the left, active clip player pinned right) collapses to a single
  scrolling column with the player docked above the conversation on
  narrower viewports.
- The active `ClipPlayer` stays visible while scrolling the conversation
  — you should never lose the frame you just seeked to because you
  scrolled to read a follow-up answer.

## Motion

Minimal by default: a short opacity/position transition on new results
appearing, nothing else animated continuously. Anything animated is
skipped entirely under `prefers-reduced-motion: reduce` — not just
shortened, removed, since this is a professional tool, not a marketing
site, and motion here is decoration rather than the point.

## Tokens

Committed in `ui/tokens.css`. Neutral grays for every surface, one accent
(`--tally`, named for the camera tally light, i.e. "recording") reserved
exclusively for current-selection/playhead state, and one warning tone
(`--flag-note`) reserved for technical-problem flags. No other color
exists in this interface.
