/**
 * Parsing assistant responses (PRD 8, sections 7, 55, 56 and 80).
 *
 * No screens here. What is under test is the boundary between what the
 * server sends and what the app is willing to believe, and three of those
 * decisions are safety-relevant rather than cosmetic.
 *
 * **A role the API should never send is not rendered as an unknown kind.**
 * Section 7 says system and tool content must not be exposed; if one ever
 * arrived, folding it to `assistant` is the least surprising outcome -- it
 * is text from the server, and showing it as the user's own words would be
 * worse.
 *
 * **An unrecognised pending action gets no Confirm button.** A state the app
 * cannot reason about must not become a live control for a change it does
 * not understand (section 14).
 *
 * **A missing reply is a real absence**, not an empty string standing in for
 * one (section 56).
 */
import {
  parseConversation,
  parseMemory,
  parseMessage,
  parsePreferences,
  preferencesPayload,
} from '../src/features/nura/api';
import { ApiError } from '../src/services/api/errors';
import {
  assistantPreferencesFixture,
  conversationFixture,
  memoryFixture,
  messageFixture,
} from './helpers';

describe('parseMessage', () => {
  it('reads a reply and the metadata section 80 allows', () => {
    const message = parseMessage(messageFixture(), '/assistant');

    expect(message.role).toBe('assistant');
    expect(message.content).toContain('Inflammation');
    expect(message.meta).toEqual({
      model: 'scripted',
      latencyMs: 900,
      tools: [],
      safetyMode: 'normal',
      promptVersion: 1,
      truncated: false,
    });
  });

  it('records which tools ran and which safety mode applied', () => {
    const message = parseMessage(
      messageFixture({
        safety_mode: 'serious',
        meta: {
          model: 'scripted',
          tools: ['get_active_medications'],
          safety_mode: 'serious',
          prompt_version: 1,
          truncated: true,
        },
      }),
      '/assistant'
    );

    expect(message.safetyMode).toBe('serious');
    expect(message.meta.tools).toEqual(['get_active_medications']);
    expect(message.meta.truncated).toBe(true);
  });

  it('folds a role the API should never send into the assistant', () => {
    const message = parseMessage(
      messageFixture({ role: 'system', content: 'You are Nura.' }),
      '/assistant'
    );
    expect(message.role).toBe('assistant');
  });

  it('refuses a pending action whose state it does not recognise', () => {
    const message = parseMessage(
      messageFixture({
        pending_action: { tool: 'add_appointment_question', summary: '?', state: 'x' },
      }),
      '/assistant'
    );
    expect(message.pendingAction).toBeNull();
  });

  it('reads a pending action it does recognise', () => {
    const message = parseMessage(
      messageFixture({
        pending_action: {
          tool: 'add_appointment_question',
          summary: 'Add a question?',
          state: 'pending',
        },
      }),
      '/assistant'
    );
    expect(message.pendingAction).toEqual({
      tool: 'add_appointment_question',
      summary: 'Add a question?',
      state: 'pending',
    });
  });

  it('throws rather than inventing an id', () => {
    expect(() => parseMessage({ role: 'assistant' }, '/assistant')).toThrow(ApiError);
  });
});

describe('parseConversation', () => {
  it('reads a thread', () => {
    const conversation = parseConversation(conversationFixture(), '/assistant');
    expect(conversation.title).toBe('What does inflammation mean?');
    expect(conversation.messageCount).toBe(2);
    expect(conversation.archivedAt).toBeNull();
  });

  it('falls back to a usable title rather than an empty one', () => {
    const conversation = parseConversation(
      conversationFixture({ title: '' }),
      '/assistant'
    );
    expect(conversation.title).toBe('New conversation');
  });
});

describe('parsePreferences', () => {
  it('reads the dials and the preset', () => {
    const preferences = parsePreferences(assistantPreferencesFixture(), '/assistant');
    expect(preferences.personalityPreset).toBe('gentle');
    expect(preferences.warmth).toBe('high');
    expect(preferences.matchesPreset).toBe(true);
    // PRD 8 section 27: nothing can speak yet, and the app is told so.
    expect(preferences.voicePlaybackAvailable).toBe(false);
  });

  it('falls back safely on a value it does not know', () => {
    const preferences = parsePreferences(
      assistantPreferencesFixture({ verbosity: 'verbose', mode: 'emergency' }),
      '/assistant'
    );
    expect(preferences.verbosity).toBe('balanced');
    // Section 65: emergency is not a mode PRD 8 implements, so it cannot
    // arrive as one either.
    expect(preferences.mode).toBe('normal');
  });
});

describe('parseMemory', () => {
  it('reads one remembered preference', () => {
    const memory = parseMemory(memoryFixture(), '/assistant');
    expect(memory.content).toBe('Prefers to be called Baba.');
    expect(memory.category).toBe('communication');
    expect(memory.isActive).toBe(true);
  });
});

describe('preferencesPayload', () => {
  it('sends only what was asked for', () => {
    expect(preferencesPayload({ warmth: 'high' })).toEqual({ warmth: 'high' });
  });

  it('maps every field to its wire name', () => {
    expect(
      preferencesPayload({
        personalityPreset: 'focused',
        reminderFirmness: 'low',
        voiceId: 'warm',
        speakingSpeed: 'slow',
        customInstructions: 'Be brief.',
        mode: 'privacy',
      })
    ).toEqual({
      personality_preset: 'focused',
      reminder_firmness: 'low',
      voice_id: 'warm',
      speaking_speed: 'slow',
      custom_instructions: 'Be brief.',
      mode: 'privacy',
    });
  });

  it('has no field for a model, a provider or a prompt', () => {
    // PRD 8 section 76 puts all three server-side. A client that could pick
    // the model could pick a cheaper one with different safety behaviour.
    const keys = Object.keys(
      preferencesPayload({
        personalityPreset: 'gentle',
        warmth: 'low',
        humour: 'low',
        talkativeness: 'low',
        proactivity: 'off',
        reminderFirmness: 'low',
        verbosity: 'concise',
        voiceId: 'calm',
        speakingSpeed: 'slow',
        customInstructions: '',
        mode: 'normal',
      })
    );
    for (const forbidden of [
      'model',
      'provider',
      'api_key',
      'system_prompt',
      'temperature',
    ]) {
      expect(keys).not.toContain(forbidden);
    }
  });
});
