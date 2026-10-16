/**
 * Every sentence the Nura screens can say (PRD 8, sections 2, 16, 39 and 73).
 *
 * The same shape as the symptom and report copy tests: read *all* of it and
 * fail on a diagnosis, a likelihood, a cause, a treatment suggestion, or a
 * promise of help Nura cannot give. It is exhaustive only because `copy.ts`
 * is the only place a screen sentence lives, so the second describe block
 * checks that no screen has started writing prose of its own.
 *
 * What this does **not** cover is what the model says. That is generated
 * text, bounded by the guardrails in `services/assistant/policy.py` and
 * tested there. No amount of app-side copy changes what a model can be made
 * to say, and a test in this file claiming otherwise would be the wrong kind
 * of reassurance.
 */
import { readFileSync } from 'fs';
import { join } from 'path';

import * as copy from '../src/features/nura/copy';

/** Every string the module exports, flattened out of its records and lists. */
function everySentence(): string[] {
  const out: string[] = [];
  for (const value of Object.values(copy)) {
    if (typeof value === 'string') out.push(value);
    else if (Array.isArray(value)) {
      out.push(...value.filter((entry): entry is string => typeof entry === 'string'));
    } else if (value !== null && typeof value === 'object') {
      out.push(
        ...Object.values(value).filter(
          (entry): entry is string => typeof entry === 'string'
        )
      );
    }
  }
  return out;
}

describe('the Nura screens say nothing clinical', () => {
  const sentences = everySentence();

  it('has something to check', () => {
    expect(sentences.length).toBeGreaterThan(50);
  });

  it.each([
    // A claim about what is wrong with the user (sections 3 and 16).
    /\byou (?:have|may have|might have|probably have|likely have) (?:a |an |the )?(?:condition|infection|disease|virus|cancer|diagnosis)\b/i,
    /\bit (?:is|sounds|looks) like you (?:have|are having)\b/i,
    /\byour (?:symptoms?|results?) (?:suggest|indicate|mean|point to)\b/i,
    /\bdiagnos(?:is|es|ed)\b/i,
    // A likelihood (section 3).
    /\b(?:likely|probably|most likely|unlikely) (?:caused|due to|a sign|related)\b/i,
    // A cause attributed to something of theirs (section 17).
    /\b(?:because|caused by|a result) of your (?:condition|medication|symptom)/i,
    // Treatment or dose advice (sections 3 and 19).
    /\byou should (?:take|stop|double|increase|reduce|skip)\b/i,
    /\b(?:recommend|prescribe)s? (?:a |the |this )?(?:dose|medication|treatment)\b/i,
    // Reassurance that a symptom is harmless (section 3).
    /\b(?:nothing to worry about|perfectly normal|harmless|it'?s fine)\b/i,
    // A promise of escalation PRD 8 does not have (sections 39 and 75).
    /\b(?:we|nura|i)(?:'ll| will)? (?:call|alert|contact|notify) (?:your|a|an|the) (?:doctor|caregiver|emergency|ambulance|family)\b/i,
  ])('never says %s', (pattern) => {
    expect(sentences.filter((sentence) => pattern.test(sentence))).toEqual([]);
  });

  it('describes Nura as a companion and never as a doctor (section 16)', () => {
    for (const sentence of sentences) {
      expect(sentence).not.toMatch(/\bAI doctor\b/i);
      expect(sentence).not.toMatch(/\byour doctor Nura\b/i);
    }
  });

  it('never promises escalation it does not have (sections 39 and 75)', () => {
    // The emergency notice itself is backend copy. What this file must not
    // do is contradict it with a promise of its own.
    for (const sentence of sentences) {
      if (!/emergency/i.test(sentence)) continue;
      expect(sentence).toMatch(/not (?:yet )?(?:set up|configured)|cannot|can’t/i);
    }
  });

  it('points at a clinician for anything about a dose (section 19)', () => {
    // Every mention of changing a dose, in app copy, hands off rather than
    // advising. There is exactly one such sentence today; the test is here
    // so the second one cannot be different.
    for (const sentence of sentences) {
      if (!/\b(?:dose|dosage)\b/i.test(sentence)) continue;
      expect(sentence).toMatch(/clinician|pharmacist|doctor/i);
    }
  });
});

describe('copy lives in one file', () => {
  /** Screens and components that must import their wording rather than write it. */
  const FILES = [
    'app/(tabs)/nura.tsx',
    'app/nura/[id].tsx',
    'app/nura/history.tsx',
    'app/nura/memory.tsx',
    'app/nura/personality.tsx',
    'app/nura/proactivity.tsx',
    'app/nura/voice.tsx',
    'app/nura/instructions.tsx',
    'src/features/nura/components/Banners.tsx',
    'src/features/nura/components/ChatBubble.tsx',
    'src/features/nura/components/ConversationComposer.tsx',
    'src/features/nura/components/MemoryCards.tsx',
    'src/features/nura/components/PendingActionCard.tsx',
    'src/features/nura/components/ProactivePromptCard.tsx',
  ];

  /**
   * A quoted string on one line that reads as prose: long, several words,
   * and finished with a full stop. Labels, hints and headings are none of
   * those things, which is what keeps this from flagging every attribute.
   */
  function proseIn(source: string): string[] {
    const code = source
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '')
      .replace(/^import[\s\S]*?from .*;$/gm, '');
    const quoted = [
      ...code.matchAll(/'([^'\n]{45,})'/g),
      ...code.matchAll(/"([^"\n]{45,})"/g),
    ].map((match) => match[1] ?? '');
    return quoted.filter(
      (text) => text.split(' ').length >= 6 && /[.!?]$/.test(text.trim())
    );
  }

  it.each(FILES)('%s writes no prose of its own', (file) => {
    const source = readFileSync(join(__dirname, '..', file), 'utf8');
    expect(proseIn(source)).toEqual([]);
  });

  it('would notice prose if it appeared', () => {
    // The check is only worth having if it can fail, so here it does.
    const planted = `const message = 'Your symptoms suggest this is probably something serious.';`;
    expect(proseIn(planted)).toHaveLength(1);
  });
});
