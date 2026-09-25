# Problem Statement (Plain English)

## What is this research about, in one sentence?

We want to teach a computer to learn the "grammar" of tabla rhythm from real
recordings — so it can both **create** new rhythm patterns and **explain, in
a human-readable way, why each pattern is correct** — and then measure
honestly what that explainability costs, if anything, compared to today's
best "black box" AI models.

## Some background

Tabla is a pair of hand drums central to Hindustani (North Indian classical)
music. A tabla player doesn't just improvise randomly — they work within a
**tāla** (a repeating rhythmic cycle) using a vocabulary of **bols**, spoken
syllables like "Dha," "Ge," "Ti," "Na" that stand for specific drum strokes.
Tabla players learn named patterns and operations passed down through
teacher-student lineages called **gharānās** (schools) — things like a
**kāydā** (a theme), its **palṭās** (variations on that theme), and a
**tihāī** (a phrase repeated exactly three times that lands precisely back
on beat one of the cycle, which requires real arithmetic to get right).

So unlike a lot of music, tabla rhythm already comes with its own
**explicit vocabulary of structure** — the tradition itself names the
building blocks. That makes it an unusually good subject for a computer
system that is supposed to both perform and *explain itself*.

## The problem

Today there are two separate approaches to getting a computer to produce
tabla-like rhythm, and each is missing something:

1. **Hand-written rule systems** (the main historical example is a program
   called the Bol Processor, built starting in 1981). An expert musician
   sat down and wrote out the rules and their importance by hand. This
   produces musically sensible results, but the rules were never *learned*
   from real recordings, and were never measured against real data or
   compared to modern methods — there's no number you can point to that says
   how well these rules actually predict real performances.

2. **Modern AI models** (neural networks — the same general family of
   technology behind today's large language models, applied here to
   generating drum patterns). These are *trained* on real data and can
   produce very plausible-sounding rhythms. But they are "black boxes": ask
   one why it generated a particular pattern, or whether a pattern is
   "correct," and it cannot give a real answer — at best you can try to
   guess at its reasoning after the fact using indirect techniques, which is
   not the same as the model actually reasoning in a way you can inspect.

**No one has combined the two**: a system whose rules are *learned from real
recordings* (like the AI approach) but whose structure is still *openly
readable and checkable* (like the hand-written approach) — and then actually
measured, with real numbers, how much (if anything) you give up in quality
by insisting on that transparency.

## What we are building

A computer program that:

1. **Starts from real tabla structure, not guesswork.** The basic categories
   it uses (kāydā, dohrā, palṭā, tihāī, etc.) come from published tabla
   teaching material, not from the computer inventing its own categories.
2. **Learns from real recordings.** We are using a dataset of 38 tabla
   solo recordings, spanning 6 different gharānās, each with a
   syllable-by-syllable written-out score lined up in time with the audio.
   The program studies these recordings and learns *how likely* each rule
   is to be used, based on what actually appears in real performances —
   rather than a person guessing the likelihoods.
3. **Generates new rhythm patterns together with an explanation.** When the
   program creates a new pattern, it doesn't just hand you the pattern — it
   also hands you the "family tree" showing exactly which rules it applied,
   in order, to build that pattern. That tree *is* the explanation; it isn't
   generated separately or guessed at afterward.
4. **Checks its own arithmetic.** For tricky structures like the tihāī
   (three repeats that must land exactly back on beat one), the program
   actually verifies the timing math is correct, rather than just hoping the
   pattern sounds right.
5. **Gets compared fairly against modern AI, with real numbers.** We train
   several standard "black box" models (the same general kind of technology
   used in modern AI systems, scaled down and applied to this task) on the
   same recordings, and directly compare: which one predicts real tabla
   performances better? Which one's patterns look more "correct" to actual
   tabla players? Does having the explanation tree actually help a person
   do useful things — like guessing what comes next, or spotting a mistake
   in a pattern — better than seeing the raw pattern alone, or better than
   an AI model's after-the-fact guess at its own reasoning?

## The central question we're trying to answer

**If you insist that an AI system's reasoning be genuinely readable and
checkable by a human — not just plausible-sounding — how much, if
anything, do you have to give up in terms of how well it performs?**

We don't know the answer in advance, and we're not assuming it will be
flattering to our own approach. If the transparent system turns out to
perform worse than the black-box models, that is itself a real, reportable
result — it tells you what transparency costs. If it performs about the
same, that's evidence you don't have to choose between an AI system you can
trust and one that works well.

## Four specific questions the research answers

1. **Does it actually predict real tabla music well?** Compare our system's
   accuracy at predicting real performances against the black-box AI models,
   on data none of the models have seen before.
2. **Do the rules it learns actually match what tabla teachers say?** Check
   whether the patterns the program considers "important" line up with the
   categories real tabla pedagogy already uses (kāydā, dohrā, palṭā, etc.),
   or whether the computer ends up inventing its own, different categories.
3. **Does the explanation actually help a person?** Run real tests with
   people (ideally including tabla students) to see if having the
   explanation tree actually improves their ability to predict, verify, or
   fix rhythm patterns — not just ask people if they *like* the explanation.
4. **What can this kind of system handle, and what can't it?** Some tabla
   phenomena (like the tihāī's arithmetic) need more than the basic rule
   system to describe correctly. This question maps out exactly which parts
   of tabla rhythm fit naturally into our approach, which need extra
   machinery bolted on, and which might not fit at all — an honest account
   of the limits, not just the successes.

## Where the dataset side of this stands right now

We have already checked the real dataset (not just trusted its
documentation) and confirmed: 38 compositions across all 6 claimed
gharānās, all in the same tāla (tīntāl), and — most importantly — the
written score and the timestamped recording data match up **exactly**,
proving this is a genuinely trustworthy, time-aligned dataset to learn from,
not just an assumption we're taking on faith. Full details are in
`docs/PHASE1_DATASET_AUDIT.md` if you want the evidence.
