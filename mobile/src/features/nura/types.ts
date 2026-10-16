/**
 * Conversation, memory and preference shapes (PRD 8, sections 7, 44 and 88).
 *
 * Wire fields are snake_case; everything the app works with is camelCase, and
 * `api.ts` is the only place the two meet.
 *
 * Three shapes here are worth noticing.
 *
 * **A message has two roles and no more.** The backend stores `system` and
 * `tool` rows so a thread can be replayed exactly, and never returns them
 * (PRD 8, section 7). There is no variant here for either, so a future change
 * that started sending them would fail to parse rather than quietly render.
 *
 * **A reply can be absent.** `MessageSent.reply` is null when the model could
 * not be reached, and `failure` says why in one of a fixed set of codes. There
 * is no shape in this file for a fabricated answer, because section 56 forbids
 * one (`no fake assistant reply`).
 *
 * **Metadata is small on purpose.** `MessageMeta` is what section 80 permits --
 * model, latency, which tools ran, which safety mode applied. No prompt, no
 * chain of thought, and nothing the user would be surprised to find in their
 * own conversation.
 */

export type MessageRole = 'user' | 'assistant';

export type MessageType = 'text' | 'tool_call' | 'tool_result' | 'notice';

/** How one reply was handled (PRD 8, sections 37, 39 and 80). */
export type SafetyMode = 'normal' | 'serious' | 'emergency_unconfigured';

export type PersonalityPreset = 'gentle' | 'friendly' | 'focused' | 'professional';

/** The scale every personality dial uses (PRD 8, section 23). */
export type PersonalityLevel = 'low' | 'medium' | 'high';

export type ProactivityLevel = 'off' | 'low' | 'medium' | 'high';

export type Verbosity = 'concise' | 'balanced' | 'detailed';

export type SpeakingSpeed = 'slow' | 'normal' | 'fast';

export type AssistantVoice = 'calm' | 'clear' | 'warm' | 'bright';

/** The modes PRD 8 implements (section 65). Serious mode is not one of them. */
export type AssistantMode = 'normal' | 'focus' | 'sleep' | 'privacy';

export type MemoryCategory =
  'preferences' | 'communication' | 'routine' | 'personal_context' | 'assistant_behavior';

export type MemorySource = 'user' | 'conversation';

export type PromptKind =
  'appointment_preparation' | 'daily_checkin' | 'medication_supply';

/** The five dials, in the order the Personality screen shows them. */
export const PERSONALITY_TRAITS = [
  'warmth',
  'humour',
  'talkativeness',
  'proactivity',
  'reminderFirmness',
] as const;

export type PersonalityTrait = (typeof PERSONALITY_TRAITS)[number];

export interface MessageMeta {
  model: string | null;
  latencyMs: number | null;
  tools: string[];
  safetyMode: SafetyMode;
  promptVersion: number | null;
  /** True when the reply hit the output ceiling and stops mid-thought. */
  truncated: boolean;
}

/** A change Nura has offered to make, waiting on the user (section 14). */
export interface PendingAction {
  tool: string;
  summary: string;
  state: 'pending' | 'confirmed' | 'cancelled';
}

export interface Message {
  id: string;
  role: MessageRole;
  messageType: MessageType;
  content: string;
  createdAt: string;
  safetyMode: SafetyMode;
  meta: MessageMeta;
  pendingAction: PendingAction | null;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  lastMessageAt: string | null;
  archivedAt: string | null;
  messageCount: number;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}

export interface Preferences {
  profileId: string;
  personalityPreset: PersonalityPreset;
  warmth: PersonalityLevel;
  humour: PersonalityLevel;
  talkativeness: PersonalityLevel;
  proactivity: ProactivityLevel;
  reminderFirmness: PersonalityLevel;
  verbosity: Verbosity;
  voiceId: AssistantVoice;
  speakingSpeed: SpeakingSpeed;
  assistantLanguage: string;
  customInstructions: string | null;
  mode: AssistantMode;
  /** False once a dial has moved away from the stored preset. */
  matchesPreset: boolean;
  /** False in PRD 8: the settings are stored, nothing can speak yet. */
  voicePlaybackAvailable: boolean;
}

/** A partial change. Anything omitted is left alone. */
export interface PreferencesPatch {
  personalityPreset?: PersonalityPreset;
  warmth?: PersonalityLevel;
  humour?: PersonalityLevel;
  talkativeness?: PersonalityLevel;
  proactivity?: ProactivityLevel;
  reminderFirmness?: PersonalityLevel;
  verbosity?: Verbosity;
  voiceId?: AssistantVoice;
  speakingSpeed?: SpeakingSpeed;
  customInstructions?: string;
  mode?: AssistantMode;
}

export interface Memory {
  id: string;
  category: MemoryCategory;
  content: string;
  source: MemorySource;
  isActive: boolean;
  confirmedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface MemoryList {
  memories: Memory[];
  maxMemories: number;
}

/** Something Nura noticed and is offering to remember (section 94). */
export interface MemorySuggestion {
  category: MemoryCategory;
  content: string;
}

/** One thing Nura is offering to help with, from app data only (section 35). */
export interface ProactivePrompt {
  kind: PromptKind;
  subjectKey: string;
  text: string;
  route: string | null;
  actionLabel: string | null;
}

export interface AssistantHome {
  profileId: string;
  /** False when no provider is configured on the server (section 55). */
  assistantAvailable: boolean;
  preferences: Preferences;
  recentConversations: Conversation[];
  prompts: ProactivePrompt[];
  memoryCount: number;
}

export interface ConversationList {
  conversations: Conversation[];
  assistantAvailable: boolean;
}

export interface MessageSent {
  conversation: Conversation;
  userMessage: Message;
  /** Null when nothing could be said (section 56). */
  reply: Message | null;
  failure: string | null;
  failureMessage: string | null;
  memorySuggestion: MemorySuggestion | null;
  /** True when the user described something they have not logged (section 18). */
  suggestSymptomLog: boolean;
}

export interface ActionConfirmed {
  message: Message | null;
  outcome: Message | null;
}
