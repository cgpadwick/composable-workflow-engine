---
name: propose
description: |
  You are playing a guess-the-number game. There is a hidden target somewhere
  between 0 and 1. You are NOT told what it is.

  Read `history.txt` for your previous guesses and the feedback on each:
  "higher" means the target is higher than that guess, "lower" means it is lower.
  Use the history to binary-search toward the target. If history.txt does not
  exist yet, this is your first turn — start at 0.5.

  Reply with ONLY your next guess as a decimal number (e.g. "0.625"), nothing else.
tools: [read_file]
---
SKILL_ID: propose

You guess a hidden number in [0, 1]. Read the higher/lower feedback history and
binary-search toward the target. Output ONLY the number — no words.
