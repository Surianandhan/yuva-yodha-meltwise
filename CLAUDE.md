# MeltWise project notes for Claude

@README.md

## Rules for this repo

- Every number in the description or the deck must trace back to `Supporting_Material/Research_Notes_and_Sources.md` or `Supporting_Material/Impact_Model.md`. Keep claims conservative, and don't make any claim the research notes list as deliberately avoided.
- The project description (section 3 of `Application_Form_Answers.md`) must stay between 300 and 500 words. Count it with `awk '/^## 3\./{f=1;next} /^## 4\./{f=0} f' Application_Form_Answers.md | wc -w`.
- After changing a slide, run `Deck_Source/build.sh`, look at `Deck_Source/build/contact.png` and the changed slide PNGs, then commit the rebuilt PDF and PPTX together with the source change.
- There is no team name or college. The deck shows only the two members' names and roles.
- Deliver work as files in this repo, not as hosted links.
- The organizers allowed AI-assisted code for the prototype (confirmed by the team on 26 October 2026). Say so honestly if asked.
- Prototype numbers come only from `prototype/scripts/evaluate.py` (`prototype/results/metrics.json`). After changing the simulator or models, rerun it and `python -m pytest` in `prototype/`, then regenerate the Phase 2 deck and update `Phase2_Submission/Phase2_Form_Answers.md`.
- Results are simulated; never present them as plant results.
