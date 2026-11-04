import { useCallback, useLayoutEffect, useRef, useState } from "react";
import type { ExportPayload } from "./types";

interface Ticket {
  key: string;
  generation: number;
  request: number;
}

/** Export responses belong to one committed input snapshot and request.
 * Generation also rejects A -> B -> A changes and responses after unmount.
 */
export function useExportPreview<T extends ExportPayload>(key: string | null) {
  const current = useRef({ key, generation: 0, request: 0, mounted: false });
  const [value, setValue] = useState<{ ticket: Ticket; payload: T } | null>(null);
  const [failure, setFailure] = useState<Ticket | null>(null);

  useLayoutEffect(() => {
    current.current.key = key;
    current.current.generation += 1;
    current.current.mounted = true;
    return () => {
      current.current.mounted = false;
      current.current.generation += 1;
    };
  }, [key]);

  const matches = useCallback((ticket: Ticket) => {
    const active = current.current;
    return active.mounted && active.key === ticket.key
      && active.generation === ticket.generation && active.request === ticket.request;
  }, []);

  const invalidate = useCallback(() => {
    // Event handlers revoke immediately, before React commits the next render.
    current.current.generation += 1;
    setValue(null);
    setFailure(null);
  }, []);

  const load = useCallback(async (request: () => Promise<T>) => {
    const active = current.current;
    if (!active.mounted || active.key === null) return;
    const ticket = { key: active.key, generation: active.generation, request: ++active.request };
    setValue(null);
    setFailure(null);
    try {
      const payload = await request();
      if (matches(ticket)) setValue({ ticket, payload });
    } catch {
      if (matches(ticket)) setFailure(ticket);
    }
  }, [matches]);

  const getPreview = useCallback(() => (
    value && value.ticket.key === key && matches(value.ticket) ? value.payload : null
  ), [key, matches, value]);

  return {
    preview: getPreview(),
    failed: failure !== null && failure.key === key && matches(failure),
    getPreview,
    load,
    invalidate,
  };
}
