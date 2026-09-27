/**
 * Attaching a photo to the current draft (PRD 6, sections 31, 34 and 60).
 *
 * A thin hook so both the manual form and the follow-up screen attach photos the
 * same way: pick, compress, put it in the draft. The photo stays on the phone
 * until the entry it belongs to has been saved, which is what stops an upload
 * from being attempted against an entry that does not exist yet -- and what makes
 * an offline save keep its photos (PRD 6, section 60).
 *
 * The outcome message is local state: it is a sentence that appears after a
 * permission refusal and is cleared on the next attempt. Nothing depends on it,
 * and the draft itself lives in the store where the tests can reach it.
 */
import { useCallback, useState } from 'react';

import { useSymptomDraftStore } from './draftStore';
import {
  pickMessage,
  pickPhoto as pickFromLibrary,
  takePhoto as takeWithCamera,
} from './photos';

export interface SymptomPicker {
  takePhoto: () => void;
  pickPhoto: () => void;
  /** What to say when a pick did not produce a photo, or null. */
  message: string | null;
  busy: boolean;
}

export function useSymptomPicker(): SymptomPicker {
  const addPhoto = useSymptomDraftStore((state) => state.addPhoto);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(
    async (pick: () => Promise<Awaited<ReturnType<typeof takeWithCamera>>>) => {
      setBusy(true);
      setMessage(null);
      try {
        const outcome = await pick();
        if (outcome.kind === 'picked') {
          addPhoto(outcome.photo);
        } else {
          setMessage(pickMessage(outcome));
        }
      } finally {
        setBusy(false);
      }
    },
    [addPhoto]
  );

  return {
    takePhoto: () => void run(takeWithCamera),
    pickPhoto: () => void run(pickFromLibrary),
    message,
    busy,
  };
}
