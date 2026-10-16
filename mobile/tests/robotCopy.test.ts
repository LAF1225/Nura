/**
 * Every robot sentence the app writes for itself, read in one pass.
 *
 * PRD 11, sections 8, 9, 20, 47, 49 and 75.
 *
 * Section 75 asks for reviewable robot-copy modules. The payoff is that this
 * test is exhaustive rather than a spot check: it collects every string the
 * module exports, including the ones inside the label maps, and applies four
 * rules to all of them.
 *
 *   section 8   nothing says help is coming
 *   section 9   nothing describes a detector
 *   section 20  nothing claims the robot showed, spoke or played anything
 *   section 49  a future capability is described as *when*, not *now*
 *
 * The fourth is the one that is easy to get wrong and is specific to PRD 11.
 * "Read reminders aloud" describes something this build does. Nothing in this
 * build can make a sound, so the sentence has to say "when Nura has a working
 * speaker" -- a preference being kept for later, which is what is true.
 */
import * as copy from '../src/features/robot/copy';

/** Every string the module exports, including inside the label maps. */
const ALL: [string, string][] = Object.entries(copy).flatMap(([name, value]) => {
  if (typeof value === 'string') return [[name, value] as [string, string]];
  if (value !== null && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .filter(([, text]) => typeof text === 'string')
      .map(([key, text]) => [`${name}[${key}]`, text as string] as [string, string]);
  }
  return [];
});

it('collected the module, so the rules below are not vacuous', () => {
  // The guard PRD 10's copy audit learned to add: a refactor that changed the
  // module's shape would otherwise make every assertion below pass over an
  // empty list.
  expect(ALL.length).toBeGreaterThan(40);
});

it.each(ALL)('%s says nothing about help arriving', (_name, text) => {
  const lowered = text.toLowerCase();
  for (const phrase of [
    'help is on the way',
    'help is coming',
    'on their way',
    'emergency services',
    'ambulance',
    'dispatched',
  ]) {
    expect(lowered).not.toContain(phrase);
  }
});

it.each(ALL)('%s does not describe a detector', (_name, text) => {
  const lowered = text.toLowerCase();
  for (const phrase of [
    'fall detection',
    'detects',
    'detector',
    'watching you',
    'seizure',
    'vomiting',
  ]) {
    expect(lowered).not.toContain(phrase);
  }
});

it.each(ALL)('%s does not claim the robot showed or said anything', (_name, text) => {
  const lowered = text.toLowerCase();
  for (const phrase of [
    'nura showed',
    'nura displayed',
    'was displayed',
    'nura said',
    'read it out',
    'played the',
  ]) {
    expect(lowered).not.toContain(phrase);
  }
});

it.each(ALL)('%s promises nothing', (_name, text) => {
  const lowered = text.toLowerCase();
  for (const phrase of ['guarantee', 'we promise', 'never miss', 'always shows']) {
    expect(lowered).not.toContain(phrase);
  }
});

describe('the read-aloud settings describe when, not now', () => {
  // Section 49, as its own group because it is the rule specific to PRD 11:
  // a preference may be configured before the hardware exists, and must not
  // imply that it exists.
  it.each([
    ['medications', copy.READ_MEDICATIONS_HINT],
    ['messages', copy.READ_MESSAGES_HINT],
    ['assistant', copy.READ_ASSISTANT_HINT],
  ])('%s says "when Nura has a working speaker"', (_which, hint) => {
    expect(hint).toContain('When Nura has a working speaker');
  });

  it('the volume hint does not claim Nura can make a sound now', () => {
    expect(copy.VOLUME_HINT).toContain('when it can make a sound');
  });
});

describe('what the module deliberately does not hold', () => {
  it('writes no capability state label', () => {
    // Those are the server's (section 75), so there is one place a reviewer
    // reads to be sure "not_verified" is not described as working.
    const text = ALL.map(([, value]) => value).join(' ');
    expect(text).not.toContain('Not tested yet');
    expect(text).not.toContain('Not fitted');
  });

  it('writes no history line', () => {
    // The composed form, which is what the server renders: "Medication
    // reminder — sent to Nura". The app's own empty state is allowed to say
    // "nothing has been sent to Nura's screen yet", because that is a
    // sentence about the list rather than a claim about a card.
    const text = ALL.map(([, value]) => value).join(' ');
    expect(text).not.toContain('— sent to Nura');
    expect(text).not.toContain('— shown');
    expect(text).not.toContain('— expired');
    expect(text).not.toContain('— waiting');
  });

  it('writes no hardware note', () => {
    // Section 135's sentence is the server's, so it is written once.
    const text = ALL.map(([, value]) => value).join(' ');
    expect(text).not.toContain('has not been built');
  });
});

describe('what it does hold', () => {
  it('explains every mode the status read can return', () => {
    // Section 4's ten. A mode without a hint would be a status chip with
    // nothing underneath it.
    expect(Object.keys(copy.MODE_HINTS).sort()).toEqual(
      [
        'companion',
        'emergency',
        'error',
        'focus',
        'information',
        'offline',
        'privacy',
        'safety',
        'setup',
        'sleep',
      ].sort()
    );
  });

  it('labels every step of both level controls', () => {
    for (const step of [0, 25, 50, 75, 100]) {
      expect(copy.BRIGHTNESS_LABELS[step]).toBeTruthy();
      expect(copy.VOLUME_LABELS[step]).toBeTruthy();
    }
  });

  it('says why a private medication preview exists', () => {
    expect(copy.PRIVACY_PREVIEW_HINT).toContain('visible to other people');
  });

  it('says that Nura has to confirm before the history says shown', () => {
    expect(copy.HISTORY_HINT).toContain('confirm');
  });
});
