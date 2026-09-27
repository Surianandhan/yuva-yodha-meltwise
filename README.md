# MeltWise: AI Energy Copilot for India's Foundries

Our entry for Schneider Electric's Yuva Yodha Energy Tech Hackathon 2026, Challenge 04: Smart Manufacturing.

**Team:** Surianandhan Sridhar (Team lead) and Sameera Hussainy Pattan.
**Deadline:** idea submission closes 4 October 2026, 11:59 PM IST. We aim to submit by 2 October.

## What's in this repo

| Path | Contents |
|---|---|
| `Application_Form_Answers.md` | Text for the YouNoodle form: project name, challenge and the 457-word description |
| `MeltWise_Presentation.pdf` | The 11-slide deck to upload |
| `MeltWise_Presentation.pptx` | The same deck for PowerPoint, with speaker notes. Each slide is a picture, so edit the source instead |
| `Submission_Checklist.md` | Steps left before and after submitting |
| `Supporting_Material/` | Hackathon brief, research notes with sources, impact model and name options |
| `Deck_Source/` | Slide sources and the scripts that build the PDF and PPTX |

## Changing the deck

Edit the slide in `Deck_Source/slides/`, then rebuild both files:

```bash
Deck_Source/build.sh
```

The script needs Python 3, Node.js, and Google Chrome or Chromium; set `CHROME=/path/to/chrome` if it can't find the browser. It also needs internet access, to install `pptxgenjs` on the first run and to load the Google Fonts. It writes `MeltWise_Presentation.pdf` and `.pptx` at the top of the repo, plus a contact sheet of all slides at `Deck_Source/build/contact.png`.

`Deck_Source/deck.json` sets the slide order. Each slide is a single 1920×1080 `<section>` with inline styles, and its speaker notes go in `<aside>`.

## Re-running the impact model

```bash
python3 Supporting_Material/impact_model.py
```

This rewrites `Supporting_Material/impact_results.json`.
