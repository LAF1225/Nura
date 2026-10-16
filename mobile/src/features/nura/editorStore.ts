/**
 * The two small text editors on the Nura settings screens.
 *
 * A memory being written, and the custom instructions being edited. Neither
 * is persisted: a memory is one line typed and saved in the same breath, and
 * custom instructions are read back from the server every time the screen
 * opens. The unsent *message* draft is a different thing and lives in
 * `composerStore`, which does reach disk (PRD 8, section 57).
 *
 * So the honest reason this is a store and not `useState` is the one this
 * project keeps running into: **a store update re-renders under React 19
 * where a local `useState` update from a fired event does not**, which is
 * what makes a Save button that enables when you type something testable at
 * all. The same decision PRD 6 made for the symptom draft and PRD 7 for the
 * appointment form; it is written down here rather than rediscovered.
 *
 * It buys one real thing besides: switching from the memory screen to the
 * instructions screen and back no longer throws away what was half-typed.
 */
import { create } from 'zustand';

interface EditorState {
  // --- the memory screen ---
  memoryDraft: string;
  /** Set while an existing memory is being edited rather than a new one added. */
  memoryEditingId: string | null;
  memoryError: string | null;

  setMemoryDraft: (text: string) => void;
  startEditingMemory: (id: string, content: string) => void;
  stopEditingMemory: () => void;
  setMemoryError: (error: string | null) => void;

  // --- the custom instructions screen ---
  /** Null until the field is touched, so the server's value shows through. */
  instructions: string | null;
  instructionsError: string | null;
  instructionsSaved: boolean;

  setInstructions: (text: string) => void;
  setInstructionsError: (error: string | null) => void;
  markInstructionsSaved: () => void;
  resetInstructions: () => void;
}

export const useEditorStore = create<EditorState>()((set) => ({
  memoryDraft: '',
  memoryEditingId: null,
  memoryError: null,

  setMemoryDraft: (text) => set({ memoryDraft: text, memoryError: null }),

  startEditingMemory: (id, content) =>
    set({ memoryEditingId: id, memoryDraft: content, memoryError: null }),

  stopEditingMemory: () =>
    set({ memoryEditingId: null, memoryDraft: '', memoryError: null }),

  setMemoryError: (error) => set({ memoryError: error }),

  instructions: null,
  instructionsError: null,
  instructionsSaved: false,

  setInstructions: (text) =>
    set({ instructions: text, instructionsError: null, instructionsSaved: false }),

  setInstructionsError: (error) =>
    set({ instructionsError: error, instructionsSaved: false }),

  markInstructionsSaved: () => set({ instructionsSaved: true, instructionsError: null }),

  resetInstructions: () =>
    set({ instructions: null, instructionsError: null, instructionsSaved: false }),
}));
