/**
 * Assistant endpoints (PRD 8, section 89).
 *
 * Every path is nested under the profile the conversation belongs to, because
 * that is what it belongs to -- not the account that is signed in.
 *
 * Responses are parsed rather than cast, the same way the appointment client
 * parses: a role, a safety mode, whether a reply exists at all are checked and
 * given safe fallbacks, so a field the server renames cannot become a screen
 * that silently shows the wrong thing.
 *
 * Two shapes are refused rather than tolerated. A message role the API should
 * never send -- `system`, `tool` -- is folded to `assistant` rather than
 * rendered as an unknown kind, and a `pending_action` whose state is not one
 * of the three known values is dropped, so an unrecognised offer is never
 * given a Confirm button.
 *
 * Nothing in this module chooses a model, a provider or a prompt. PRD 8
 * section 76 puts all three server-side, and there is no request body here
 * with a field for any of them.
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  ActionConfirmed,
  AssistantHome,
  AssistantMode,
  AssistantVoice,
  Conversation,
  ConversationDetail,
  ConversationList,
  Memory,
  MemoryCategory,
  MemoryList,
  MemorySource,
  MemorySuggestion,
  Message,
  MessageMeta,
  MessageRole,
  MessageSent,
  MessageType,
  PendingAction,
  PersonalityLevel,
  PersonalityPreset,
  Preferences,
  PreferencesPatch,
  ProactivePrompt,
  ProactivityLevel,
  PromptKind,
  SafetyMode,
  SpeakingSpeed,
  Verbosity,
} from './types';

const ROLES: readonly MessageRole[] = ['user', 'assistant'];
const MESSAGE_TYPES: readonly MessageType[] = [
  'text',
  'tool_call',
  'tool_result',
  'notice',
];
const SAFETY_MODES: readonly SafetyMode[] = [
  'normal',
  'serious',
  'emergency_unconfigured',
];
const PRESETS: readonly PersonalityPreset[] = [
  'gentle',
  'friendly',
  'focused',
  'professional',
];
const LEVELS: readonly PersonalityLevel[] = ['low', 'medium', 'high'];
const PROACTIVITY: readonly ProactivityLevel[] = ['off', 'low', 'medium', 'high'];
const VERBOSITIES: readonly Verbosity[] = ['concise', 'balanced', 'detailed'];
const SPEEDS: readonly SpeakingSpeed[] = ['slow', 'normal', 'fast'];
const VOICES: readonly AssistantVoice[] = ['calm', 'clear', 'warm', 'bright'];
const MODES: readonly AssistantMode[] = ['normal', 'focus', 'sleep', 'privacy'];
const CATEGORIES: readonly MemoryCategory[] = [
  'preferences',
  'communication',
  'routine',
  'personal_context',
  'assistant_behavior',
];
const SOURCES: readonly MemorySource[] = ['user', 'conversation'];
const PROMPT_KINDS: readonly PromptKind[] = [
  'appointment_preparation',
  'daily_checkin',
  'medication_supply',
];
const ACTION_STATES = ['pending', 'confirmed', 'cancelled'] as const;

// --- small parsing helpers --------------------------------------------------

function object(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(
  body: Record<string, unknown>,
  key: string,
  endpoint: string
): string {
  const value = body[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new ApiError('server', `${endpoint} response is missing ${key}.`);
  }
  return value;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function nullableCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

// --- parsing ----------------------------------------------------------------

function parseMeta(raw: unknown): MessageMeta {
  const body = raw === null || raw === undefined ? {} : object(raw, '/assistant');
  return {
    model: text(body.model),
    latencyMs: nullableCount(body.latency_ms),
    tools: stringList(body.tools),
    safetyMode: oneOf(body.safety_mode, SAFETY_MODES, 'normal'),
    promptVersion: nullableCount(body.prompt_version),
    truncated: body.truncated === true,
  };
}

function parsePendingAction(raw: unknown): PendingAction | null {
  if (raw === null || raw === undefined) return null;
  const body = object(raw, '/assistant');
  const state = body.state;
  // An offer whose state the app does not recognise gets no Confirm button.
  if (!ACTION_STATES.includes(state as (typeof ACTION_STATES)[number])) return null;
  return {
    tool: text(body.tool) ?? '',
    summary: text(body.summary) ?? '',
    state: state as PendingAction['state'],
  };
}

export function parseMessage(raw: unknown, endpoint: string): Message {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    // A role the API should never send is read as an assistant line rather
    // than as an unknown kind: it is text that arrived from the server, and
    // rendering it as the user's own words would be worse (section 7).
    role: oneOf(body.role, ROLES, 'assistant'),
    messageType: oneOf(body.message_type, MESSAGE_TYPES, 'text'),
    content: text(body.content) ?? '',
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    safetyMode: oneOf(body.safety_mode, SAFETY_MODES, 'normal'),
    meta: parseMeta(body.meta),
    pendingAction: parsePendingAction(body.pending_action),
  };
}

export function parseConversation(raw: unknown, endpoint: string): Conversation {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    title: text(body.title) ?? 'New conversation',
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    updatedAt: text(body.updated_at) ?? new Date().toISOString(),
    lastMessageAt: text(body.last_message_at),
    archivedAt: text(body.archived_at),
    messageCount: count(body.message_count),
  };
}

export function parsePreferences(raw: unknown, endpoint: string): Preferences {
  const body = object(raw, endpoint);
  return {
    profileId: text(body.profile_id) ?? '',
    personalityPreset: oneOf(body.personality_preset, PRESETS, 'gentle'),
    warmth: oneOf(body.warmth, LEVELS, 'medium'),
    humour: oneOf(body.humour, LEVELS, 'low'),
    talkativeness: oneOf(body.talkativeness, LEVELS, 'medium'),
    proactivity: oneOf(body.proactivity, PROACTIVITY, 'low'),
    reminderFirmness: oneOf(body.reminder_firmness, LEVELS, 'medium'),
    verbosity: oneOf(body.verbosity, VERBOSITIES, 'balanced'),
    voiceId: oneOf(body.voice_id, VOICES, 'calm'),
    speakingSpeed: oneOf(body.speaking_speed, SPEEDS, 'normal'),
    assistantLanguage: text(body.assistant_language) ?? 'en',
    customInstructions: text(body.custom_instructions),
    mode: oneOf(body.mode, MODES, 'normal'),
    matchesPreset: body.matches_preset === true,
    voicePlaybackAvailable: body.voice_playback_available === true,
  };
}

export function parseMemory(raw: unknown, endpoint: string): Memory {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    category: oneOf(body.category, CATEGORIES, 'preferences'),
    content: text(body.content) ?? '',
    source: oneOf(body.source, SOURCES, 'user'),
    isActive: body.is_active !== false,
    confirmedAt: text(body.confirmed_at),
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    updatedAt: text(body.updated_at) ?? new Date().toISOString(),
  };
}

function parseSuggestion(raw: unknown): MemorySuggestion | null {
  if (raw === null || raw === undefined) return null;
  const body = object(raw, '/assistant/messages');
  const content = text(body.content);
  if (content === null) return null;
  return { category: oneOf(body.category, CATEGORIES, 'preferences'), content };
}

function parsePrompt(raw: unknown): ProactivePrompt | null {
  const body = object(raw, '/assistant/home');
  const kind = body.kind;
  // A prompt kind the app cannot route is dropped rather than shown as a
  // card that does nothing when pressed.
  if (!PROMPT_KINDS.includes(kind as PromptKind)) return null;
  return {
    kind: kind as PromptKind,
    subjectKey: text(body.subject_key) ?? '',
    text: text(body.text) ?? '',
    route: text(body.route),
    actionLabel: text(body.action_label),
  };
}

// --- paths ------------------------------------------------------------------

const base = (profileId: string) => `/api/v1/profiles/${profileId}/assistant`;

// --- the Nura tab -----------------------------------------------------------

export async function fetchHome(
  profileId: string,
  localDate: string
): Promise<AssistantHome> {
  const endpoint = `${base(profileId)}/home`;
  const body = object(
    await apiRequest<unknown>(`${endpoint}?local_date=${localDate}`),
    endpoint
  );
  return {
    profileId: text(body.profile_id) ?? profileId,
    assistantAvailable: body.assistant_available === true,
    preferences: parsePreferences(body.preferences, endpoint),
    recentConversations: list(body.recent_conversations).map((entry) =>
      parseConversation(entry, endpoint)
    ),
    prompts: list(body.prompts)
      .map(parsePrompt)
      .filter((prompt): prompt is ProactivePrompt => prompt !== null),
    memoryCount: count(body.memory_count),
  };
}

export async function dismissPrompt(
  profileId: string,
  kind: PromptKind,
  subjectKey: string
): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/prompts/dismiss`, {
    method: 'POST',
    body: { kind, subject_key: subjectKey },
  });
}

// --- preferences ------------------------------------------------------------

export async function fetchPreferences(profileId: string): Promise<Preferences> {
  const endpoint = `${base(profileId)}/preferences`;
  return parsePreferences(await apiRequest<unknown>(endpoint), endpoint);
}

export function preferencesPayload(patch: PreferencesPatch): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (patch.personalityPreset !== undefined) {
    body.personality_preset = patch.personalityPreset;
  }
  if (patch.warmth !== undefined) body.warmth = patch.warmth;
  if (patch.humour !== undefined) body.humour = patch.humour;
  if (patch.talkativeness !== undefined) body.talkativeness = patch.talkativeness;
  if (patch.proactivity !== undefined) body.proactivity = patch.proactivity;
  if (patch.reminderFirmness !== undefined) {
    body.reminder_firmness = patch.reminderFirmness;
  }
  if (patch.verbosity !== undefined) body.verbosity = patch.verbosity;
  if (patch.voiceId !== undefined) body.voice_id = patch.voiceId;
  if (patch.speakingSpeed !== undefined) body.speaking_speed = patch.speakingSpeed;
  if (patch.customInstructions !== undefined) {
    body.custom_instructions = patch.customInstructions;
  }
  if (patch.mode !== undefined) body.mode = patch.mode;
  return body;
}

export async function updatePreferences(
  profileId: string,
  patch: PreferencesPatch
): Promise<Preferences> {
  const endpoint = `${base(profileId)}/preferences`;
  return parsePreferences(
    await apiRequest<unknown>(endpoint, {
      method: 'PATCH',
      body: preferencesPayload(patch),
    }),
    endpoint
  );
}

// --- memory -----------------------------------------------------------------

export async function fetchMemories(profileId: string): Promise<MemoryList> {
  const endpoint = `${base(profileId)}/memories`;
  const body = object(await apiRequest<unknown>(endpoint), endpoint);
  return {
    memories: list(body.memories).map((entry) => parseMemory(entry, endpoint)),
    maxMemories: count(body.max_memories),
  };
}

export async function createMemory(
  profileId: string,
  input: { content: string; category: MemoryCategory; source?: MemorySource }
): Promise<Memory> {
  const endpoint = `${base(profileId)}/memories`;
  return parseMemory(
    await apiRequest<unknown>(endpoint, {
      method: 'POST',
      body: {
        content: input.content,
        category: input.category,
        source: input.source ?? 'user',
      },
    }),
    endpoint
  );
}

export async function updateMemory(
  profileId: string,
  memoryId: string,
  patch: { content?: string; category?: MemoryCategory; isActive?: boolean }
): Promise<Memory> {
  const endpoint = `${base(profileId)}/memories/${memoryId}`;
  const body: Record<string, unknown> = {};
  if (patch.content !== undefined) body.content = patch.content;
  if (patch.category !== undefined) body.category = patch.category;
  if (patch.isActive !== undefined) body.is_active = patch.isActive;
  return parseMemory(
    await apiRequest<unknown>(endpoint, { method: 'PATCH', body }),
    endpoint
  );
}

export async function deleteMemory(profileId: string, memoryId: string): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/memories/${memoryId}`, {
    method: 'DELETE',
  });
}

// --- conversations ----------------------------------------------------------

export async function fetchConversations(
  profileId: string,
  includeArchived = false
): Promise<ConversationList> {
  const endpoint = `${base(profileId)}/conversations`;
  const query = includeArchived ? '?include_archived=true' : '';
  const body = object(await apiRequest<unknown>(`${endpoint}${query}`), endpoint);
  return {
    conversations: list(body.conversations).map((entry) =>
      parseConversation(entry, endpoint)
    ),
    assistantAvailable: body.assistant_available === true,
  };
}

export async function fetchConversation(
  profileId: string,
  conversationId: string
): Promise<ConversationDetail> {
  const endpoint = `${base(profileId)}/conversations/${conversationId}`;
  const body = object(await apiRequest<unknown>(endpoint), endpoint);
  return {
    conversation: parseConversation(body.conversation, endpoint),
    messages: list(body.messages).map((entry) => parseMessage(entry, endpoint)),
  };
}

export async function createConversation(profileId: string): Promise<Conversation> {
  const endpoint = `${base(profileId)}/conversations`;
  return parseConversation(
    await apiRequest<unknown>(endpoint, { method: 'POST', body: {} }),
    endpoint
  );
}

export async function updateConversation(
  profileId: string,
  conversationId: string,
  patch: { title?: string; archived?: boolean }
): Promise<Conversation> {
  const endpoint = `${base(profileId)}/conversations/${conversationId}`;
  const body: Record<string, unknown> = {};
  if (patch.title !== undefined) body.title = patch.title;
  if (patch.archived !== undefined) body.archived = patch.archived;
  return parseConversation(
    await apiRequest<unknown>(endpoint, { method: 'PATCH', body }),
    endpoint
  );
}

export async function deleteConversation(
  profileId: string,
  conversationId: string
): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/conversations/${conversationId}`, {
    method: 'DELETE',
  });
}

// --- talking ----------------------------------------------------------------

export async function sendMessage(
  profileId: string,
  conversationId: string,
  input: { content: string; clientMessageId: string; localDate: string }
): Promise<MessageSent> {
  const endpoint = `${base(profileId)}/conversations/${conversationId}/messages`;
  const body = object(
    await apiRequest<unknown>(`${endpoint}?local_date=${input.localDate}`, {
      method: 'POST',
      body: {
        content: input.content,
        source: 'mobile_text',
        client_message_id: input.clientMessageId,
      },
    }),
    endpoint
  );
  const reply = body.reply;
  return {
    conversation: parseConversation(body.conversation, endpoint),
    userMessage: parseMessage(body.user_message, endpoint),
    reply: reply === null || reply === undefined ? null : parseMessage(reply, endpoint),
    failure: text(body.failure),
    failureMessage: text(body.failure_message),
    memorySuggestion: parseSuggestion(body.memory_suggestion),
    suggestSymptomLog: body.suggest_symptom_log === true,
  };
}

export async function confirmAction(
  profileId: string,
  conversationId: string,
  messageId: string,
  confirmed: boolean,
  localDate: string
): Promise<ActionConfirmed> {
  const endpoint =
    `${base(profileId)}/conversations/${conversationId}` +
    `/messages/${messageId}/confirm`;
  const body = object(
    await apiRequest<unknown>(`${endpoint}?local_date=${localDate}`, {
      method: 'POST',
      body: { confirmed },
    }),
    endpoint
  );
  const message = body.message;
  const outcome = body.outcome;
  return {
    message:
      message === null || message === undefined ? null : parseMessage(message, endpoint),
    outcome:
      outcome === null || outcome === undefined ? null : parseMessage(outcome, endpoint),
  };
}
