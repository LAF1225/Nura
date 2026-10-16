/**
 * Every sentence the caregiver and family screens can say.
 *
 * PRD 9, sections 2, 12, 15, 35, 37, 38, 47, 49, 94 and 102.
 *
 * The same shape as the symptom, report and Nura copy tests: read *all* of it and
 * fail on anything clinical -- and then on the four things this PRD in particular
 * must not say.
 *
 * **No promise of contact.** Section 47 puts escalation in PRD 10 and section 102
 * forbids autonomous caregiver alerts, so nothing here may say Nura will call,
 * alert or notify anybody. The sentence that *does* appear says the opposite.
 *
 * **No promise of delivery.** Section 37 allows "sent" and "read" and no stronger
 * claim, and there is no push for a family message yet -- so no "delivered", no
 * "received", no "notified".
 *
 * **No implication of monitoring.** Section 2 rules out a surveillance
 * experience, section 36 that check-ins are compulsory, and section 49 that the
 * user is told when a caregiver looks at something. Nothing here reports a view.
 *
 * **No vague permission wording.** Section 15 forbids "access health
 * information" by name. The category labels come from the server, and this checks
 * the surrounding prose has not reinvented them.
 *
 * What this does not cover is the permission labels themselves, which the backend
 * owns and tests.
 */
import { readFileSync } from 'fs';
import { join } from 'path';

import * as copy from '../src/features/caregivers/copy';

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

describe('the caregiver screens say nothing clinical and promise nothing they cannot do', () => {
  const sentences = everySentence();

  it('has something to check', () => {
    expect(sentences.length).toBeGreaterThan(50);
  });

  it.each([
    // A claim about what is wrong with somebody.
    /\b(?:you|they) (?:have|may have|might have|probably have) (?:a |an |the )?(?:condition|infection|disease|diagnosis)\b/i,
    /\bdiagnos(?:is|es|ed)\b/i,
    /\btheir (?:symptoms?|results?) (?:suggest|indicate|mean|point to)\b/i,
    // Treatment or dose advice.
    /\b(?:you|they) should (?:take|stop|double|increase|reduce|skip)\b/i,
    /\b(?:recommend|prescribe)s? (?:a |the |this )?(?:dose|medication|treatment)\b/i,
    // A verdict on adherence, which is what section 19's "counts" rules out.
    /\b(?:doing (?:badly|well)|poor adherence|not taking (?:their|your) medication properly)\b/i,
    // A promise of contact PRD 9 does not have (sections 47 and 102).
    /\b(?:nura|we|i)(?:'ll| will)? (?:call|ring|alert|contact|notify|message) (?:them|your|a|an|the) (?:doctor|caregiver|emergency|ambulance|family|contacts?)\b/i,
    /\b(?:emergency services|999|911)\b/i,
    // A promise of delivery (section 37).
    /\b(?:delivered|has been received|they have been notified|notification sent)\b/i,
    // Surveillance (sections 2, 36 and 49).
    /\b(?:viewed your|looked at your|checked on you|is watching|monitoring you)\b/i,
    /\byou must (?:reply|answer|respond|check in)\b/i,
    // The exact phrasing section 15 names as too vague.
    /\baccess health information\b/i,
  ])('never says %s', (pattern) => {
    expect(sentences.filter((sentence) => pattern.test(sentence))).toEqual([]);
  });

  it('says what the contact chain is for, without overstating it', () => {
    // PRD 9 said "Nura does not contact anyone". PRD 10 walks the chain, so
    // that sentence became wrong in the direction that undersells it -- and
    // "Nura will call these people" would be wrong in the dangerous one. The
    // replacement says both halves (PRD 10, sections 30, 39 and 74).
    expect(copy.CONTACTS_NOT_YET).toMatch(/uses this order/i);
    expect(copy.CONTACTS_NOT_YET).toMatch(/cannot call or text anyone/i);
    // A family check-in is still a message, not an alert (PRD 9, section 35).
    expect(copy.CHECK_IN_NOTE).toMatch(/does not call anyone/i);
  });

  it('says plainly that Nura cannot send an invitation (section 12)', () => {
    expect(copy.INVITE_DELIVERY).toMatch(/cannot send/i);
  });

  it('no longer says any category shares nothing (PRD 12 s42)', () => {
    // `safety_alerts` left this list in PRD 10, which built the source PRD 9
    // section 94 said not to fabricate; `routines` left it in PRD 12, which
    // built the record nothing in PRD 0-11 defined. The map stays for the next
    // permission reserved before its data exists.
    expect(Object.keys(copy.PERMISSION_NOT_YET)).toEqual([]);
  });

  it('says what a safety alert actually is, and what it is not', () => {
    // PRD 10, sections 38 and 93: an in-app alert exists, and nothing is
    // pushed, texted or called -- because no provider exists to do it.
    expect(copy.SAFETY_ALERTS_NOTE).toMatch(/alert in the app/i);
    expect(copy.SAFETY_ALERTS_NOTE).toMatch(/cannot send/i);
  });

  it('says a draft is kept rather than queued (sections 71 and 72)', () => {
    expect(copy.DRAFT_KEPT).toMatch(/has not been sent/i);
    // Specifically not a promise to send it later: there is no queue.
    expect(copy.DRAFT_KEPT).not.toMatch(/will (?:be )?sen[dt]/i);
    expect(copy.OFFLINE_NOTE).not.toMatch(/will (?:be )?sen[dt]/i);
  });

  it('says calling is unavailable rather than offering one (section 38)', () => {
    expect(copy.CALLING_UNAVAILABLE).toMatch(/not available yet/i);
  });

  it('says an approval request stays visible whatever the settings (section 48)', () => {
    expect(copy.CARE_NOTIFICATIONS_INTRO).toMatch(/always appear in the app/i);
  });
});

describe('no caregiver screen writes prose of its own', () => {
  const FILES = [
    'app/caregivers/index.tsx',
    'app/caregivers/invite.tsx',
    'app/caregivers/[id].tsx',
    'app/caregivers/accept.tsx',
    'app/caregivers/notifications.tsx',
    'app/caregivers/requests/index.tsx',
    'app/caregivers/requests/[id].tsx',
    'app/care-mode/index.tsx',
    'app/care-mode/profiles.tsx',
    'app/care-mode/suggest.tsx',
    'app/care-mode/notifications.tsx',
    'app/family/index.tsx',
    'app/family/[threadId].tsx',
    'app/emergency-contacts/index.tsx',
    'app/emergency-contacts/[id].tsx',
    'src/features/caregivers/components/CaregiverCards.tsx',
    'src/features/caregivers/components/CareRequestsTodayCard.tsx',
  ];

  /**
   * A quoted string on one line that reads as prose: long, several words, and
   * finished with a full stop. Labels, hints and headings are none of those
   * things, which is what keeps this from flagging every attribute.
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
    const planted = `const note = 'Nura will call your emergency contacts if this happens again.';`;
    expect(proseIn(planted)).toHaveLength(1);
  });
});
