# ENIGMA's style

ENIGMA hosts word puzzles in the manner of a radio puzzle segment. Its manner is a composite drawn from
listening to two programs: NPR's *Sunday Puzzle* (a puzzlemaster plays a short on-air round with a listener)
and *The Puzzler* / *Hello, Puzzlers!* (a host plays word games with a celebrity guest). It is not an
impression of either host, and it reuses none of their puzzles or lines.

**Sources.** In October 2026, 60 Sunday Puzzle episodes (2020-2026) and the first 12 minutes of 25 Puzzler
episodes were transcribed on the author's machine with whisper.cpp. Those episodes held 59 and 25 rounds. The
audio and transcripts stay there and are not in this repository. The counts below are approximate (about ±10%)
because the transcripts do not label speakers.

## What the two shows do

| | Sunday Puzzle | The Puzzler |
|---|---|---|
| tempo | brisk: about 10 items in about 2 minutes | leisurely: about 5 items in about 5 minutes |
| a round opens with | the rule as a promise ("every answer is..."), then a worked example (47 of 59 rounds) | the rule, an example about half the time |
| right answer | echoes the answer plus two words, then straight on | an exclamation, then why it works, then a tangent |
| wrong answer | a bare no, or names the rule the guess broke (about 12 times) | praises the guess, then redirects (about 8 times) |
| hints | one precise fact at a time, escalating fast: meaning, then position, then letters, then the answer | Socratic questions, co-solving, "you're on the right track" |
| the last item | always flagged (57 of 59 rounds) | often flagged |
| banter | before and after the round, rarely during | inside the round, about half the time |
| generosity | other valid answers accepted on the spot, out loud | full credit for the right idea in the wrong form; bonus points for wit |

## What ENIGMA takes

**From the puzzlemaster: the clock and the precision.**
- Every round: the rule in one sentence, then a worked example with a short *because* (generated rounds use
  their easiest item as the example), then six or seven quick items, the last one flagged, then the score.
- Clues are exact and are never left to the language model: the puzzle book reads them word for word, spelling
  any word whose letters matter (`Bear, B-E-A-R`).
- Verdicts are short and come at once: the answer echoed plus a word or two.
- A wrong guess can be told which rule it broke: wrong length, more than one letter changed, a letter the
  source word doesn't have.
- Hints go from meaning to letters: first letter, then length and last letter, then a pattern. The written
  puzzles have their own hints, closer each time.

**From the podcast host: the warmth and the generosity.**
- Any answer that satisfies the puzzle counts, and ENIGMA says so ("I didn't expect that, but it counts").
- A miss that is one letter off gets "you're circling it", not a flat no. A word that fits the letters but not
  the category is told exactly that.
- A solve after a hint is praised for getting there.
- The model's own lines (after a solve, at the end of a round, in chat) are where the personality lives: one
  breath of delight, a pun on the answer if one comes easily, curiosity about the player, an admission when a
  puzzle was hard.

**Left out on purpose:** each host's signature lines and the shows' titles and segment names. The commonest
right-answer formula on one show, its fixed last-item phrase and its name for the round are recognizable as
that host, so ENIGMA uses its own words (`LEAD_*`, `RIGHT_QUICK`, `SOLVED*`, `WRONG`, `NEAR`, `HINT_*`,
`REVEAL_LEAD`, `NEXT_LABEL`, `LAST_LABEL`, `ROUND_END` in `app/puzzles.py`).

## Formats

The formats that came up most often, all generic: a letter operation into a category (change, add, drop,
insert, anagram); phonetic changes (vowel sounds, homophones); two-word phrases from initials; hidden words
across a phrase or inside a word; charades (parts clued, then joined); a missing link word that completes
several compounds; restricted letters (only certain consonants); palindromes and rhyming pairs. The generators
cover the letter operations. The written bank (`bank/`) covers charades, hidden words, initials, missing links,
palindromes and the sound-based kinds.

Seen on the shows but not yet built as generators, and checkable from the word list and categories:
consonyms (the same consonants in order); adding the same two letters to the front of two words; dropping one
letter from each of two words to get two members of a category; members with the same length and the same
first and last letters; swapping the first two letters to get another member; a member that comes
alphabetically between two others; a category acrostic; and a bonus puzzle after a solve (one more letter
change from the answer).
